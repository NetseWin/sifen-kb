"""XSD y XML de SIFEN: esquemas oficiales sin red, introspección, validación y lectura segura.

Referencia de diseño: docs/arquitectura.md §D.4 (módulo `xsd`), §D.5 (autoridad por dimensión), §G.3
(última fila: estructura consultada antes de la primera instantánea), §G.4 (eje temporal) y §M
(seguridad). Hechos del esquema verificados contra la instantánea registrada en `sources/XSD_DIR/`.

Piezas:

- `load_schema(snapshot_dir)`: carga la instantánea con `xmlschema` SIN RED. El XSD oficial incluye
  otros por URL HTTPS absoluta (`https://ekuatia.set.gov.py/sifen/xsd/DE_Types_v150.xsd`) y solo
  `xmldsig-core-schema.xsd` por ruta relativa; un `uri_mapper` redirige toda URL del portal a la copia
  local, cualquier otra URL remota es un error y `allow="sandbox"` + `defuse="always"` cierran el resto.
- `XsdIndex`: declaraciones de elementos por nombre local (ruta, padre, ocurrencia, tipo, facetas) y
  `check_occurrence` (la "Ocurrencia" del Manual Técnico frente a `minOccurs`/`maxOccurs`).
- `validate_xml`: errores de esquema con ruta. SIFEN informa solo el primer error; aquí salen varios.
- `read_values`, `read_emission_date`, `read_processing_date`: lectura de solo lectura de un XML real
  (`defuse="always"`, sin red; el archivo nunca se modifica ni se escribe).
- `mask` y `PII_ELEMENTS`: enmascarado de datos personales (§M). Verificados contra el XSD.
- `snapshot_from_manifest`: localiza la instantánea más reciente de `XSD_DIR` en el manifiesto y
  `anachronistic` marca una consulta anterior a su `retrieved_at` (el XSD solo es evidencia desde
  entonces: DNIT no publica historial).

Formato de `fecUTC` (`dFecProc` de `rProtDe`, `SIFEN_Types_v141.xsd`, verificado en la instantánea de
2026-10-17): `xs:dateTime` restringido por el patrón `\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d[+|-]\\d\\d:\\d\\d`,
es decir `AAAA-MM-DDThh:mm:ss±hh:mm`: segundos obligatorios, SIN fracciones, y desplazamiento horario
OBLIGATORIO (el patrón no admite `Z`). El nombre del tipo dice "UTC", pero lo que vale es el
desplazamiento escrito, que puede ser `-03:00` (hora de Paraguay) o `+00:00`. En cambio `dFeEmiDE` es
`fecHhmmss` (`\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d`): SIN zona, hora local de Asunción. Por eso
`to_paraguay_date` convierte a fecha de Paraguay si hay zona y toma la fecha tal cual si no la hay.
La zona de `fecUTC` en producción real queda [VERIFICAR-DNIT] (el XSD solo fija el formato).

Zona horaria: se usa `zoneinfo` "America/Asuncion" (con su historial: UTC-4 en invierno y UTC-3 en
verano hasta octubre de 2024, UTC-3 permanente después). En Windows `zoneinfo` necesita el paquete
`tzdata`; si falta, se cae a UTC-03:00 fijo, que es exacto desde octubre de 2024 pero puede errar una
hora (y, junto a medianoche, un día) en invierno anterior. `paraguay_tz_is_exact()` lo informa.
"""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from pathlib import Path
from typing import Literal, NamedTuple
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError
from xmlschema import (
    XMLResource,
    XMLResourceError,
    XMLSchema,
    XMLSchemaException,
    XMLSchemaImportWarning,
    XMLSchemaIncludeWarning,
)
from xmlschema.names import (
    XSD_FRACTION_DIGITS,
    XSD_LENGTH,
    XSD_MAX_LENGTH,
    XSD_MIN_LENGTH,
    XSD_TOTAL_DIGITS,
)
from xmlschema.validators import XsdAnyElement, XsdElement, XsdGroup, XsdSimpleType

from sifen_kb.load import load_manifest
from sifen_kb.normalize import sha12 as _sha12
from sifen_kb.yamlio import KBYamlError

# --- Constantes --------------------------------------------------------------------------------
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
"""Espacio de nombres de los elementos del DE y de las respuestas (los de firma están en `ds`)."""
XSD_URL_PREFIXES: tuple[str, ...] = (
    "https://ekuatia.set.gov.py/sifen/xsd/",
    "http://ekuatia.set.gov.py/sifen/xsd/",
)
"""Prefijos de URL de los XSD oficiales: `uri_mapper` los redirige a la instantánea local."""
XSD_DOC = "XSD_DIR"
DE_ENTRY = "siRecepDE_v150.xsd"
"""Raíz del DE (`rDE`): incluye `DE_v150.xsd` y, por URL, los tipos."""
RESPONSE_ENTRY = "WS_SiRecepDE_v150.xsd"
"""Envío y respuesta de recepción (`rEnviDe`, `rRetEnviDe/rProtDe`): incluye `protProcesDE_v150.xsd`."""
DEFAULT_ENTRIES: tuple[str, ...] = (DE_ENTRY, RESPONSE_ENTRY)

MAX_XML_BYTES = 16 * 1024 * 1024
"""Tope de tamaño de un XML que se lee (un DE pesa decenas de KB; un lote, pocos MB)."""
DEFAULT_MAX_ERRORS = 50
MAX_DEPTH = 64
"""Profundidad máxima al recorrer el esquema (el del DE llega a ~9; protege de tipos recursivos)."""

_REMOTE_SCHEMES = frozenset({"http", "https", "ftp", "ftps"})
_XSD_NAME = re.compile(r"^[A-Za-z0-9_.\-]+\.xsd$")


class XsdError(ValueError):
    """Error al cargar, indexar o leer (se informa en español)."""


class XsdOfflineError(XsdError):
    """Algo intentó salir a la red o falta un esquema que la instantánea debía traer."""


class XmlReadError(XsdError):
    """El XML no se pudo leer de forma segura (no existe, no está bien formado, usa DTD, es enorme...)."""


class _NetworkBlocked(OSError):
    """Lo lanza el `uri_mapper` para que `xmlschema` lo trate como recurso inaccesible."""


# --- Carga sin red -------------------------------------------------------------------------------
class _OfflineMapper:
    """`uri_mapper` de `xmlschema`: URL del portal -> archivo de la instantánea; otra URL remota -> error."""

    def __init__(self, snapshot: Path) -> None:
        self._snapshot = snapshot

    def __call__(self, uri: str) -> str:
        for prefix in XSD_URL_PREFIXES:
            if uri.startswith(prefix):
                name = uri[len(prefix) :]
                if not _XSD_NAME.match(name):
                    raise _NetworkBlocked(f"nombre de esquema no admitido en {uri!r}")
                local = self._snapshot / name
                if not local.is_file():
                    raise _NetworkBlocked(
                        f"el esquema {uri} no está en la instantánea {self._snapshot} "
                        "(modo sin red: no se descarga)"
                    )
                return str(local)
        if urlsplit(uri).scheme.lower() in _REMOTE_SCHEMES:
            raise _NetworkBlocked(f"acceso a red bloqueado: {uri}")
        return uri


def load_schema(snapshot_dir: str | Path, *, entries: Sequence[str] = DEFAULT_ENTRIES) -> XMLSchema:
    """Carga los XSD de `snapshot_dir` (carpeta plana con los `.xsd` oficiales) sin tocar la red.

    `entries`: archivos raíz, todos del mismo espacio de nombres (por defecto el DE y la respuesta de
    recepción). Un `xs:include`/`xs:import` que no se pueda resolver localmente es un
    `XsdOfflineError` (`xmlschema` solo lo avisa como `Warning`; aquí se vuelve error, porque un
    esquema sin sus tipos validaría de menos en silencio).
    """
    base = Path(snapshot_dir).resolve()
    if not base.is_dir():
        raise XsdError(f"la instantánea XSD no existe o no es una carpeta: {base}")
    paths: list[str] = []
    for entry in entries:
        p = base / entry
        if not p.is_file():
            raise XsdError(f"falta {entry} en la instantánea {base}")
        paths.append(str(p))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", XMLSchemaIncludeWarning)
            warnings.simplefilter("error", XMLSchemaImportWarning)
            return XMLSchema(
                paths,
                allow="sandbox",
                defuse="always",
                uri_mapper=_OfflineMapper(base),
                base_url=str(base),
            )
    except (XMLSchemaIncludeWarning, XMLSchemaImportWarning) as w:
        raise XsdOfflineError(f"no se pudo resolver una inclusión sin red: {w}") from None
    except (XMLSchemaException, OSError) as e:
        raise XsdError(f"esquema inválido o ilegible en {base}: {e}") from None


def snapshot_from_manifest(kb_root: str | Path) -> tuple[Path, str, datetime] | None:
    """Instantánea XSD más reciente del manifiesto: `(carpeta, sha12, retrieved_at)`.

    `sha12` es el prefijo del sha256 del `SHA256SUMS` de la instantánea (la identidad de la revisión).
    `None` si no hay revisión de `XSD_DIR` o su carpeta no existe. Un manifiesto ilegible o una ruta que
    escape de `kb_root` son errores, no `None`.
    """
    root = Path(kb_root).resolve()
    try:
        manifest = load_manifest(root)
    except (KBYamlError, ValidationError) as e:
        raise XsdError(f"manifiesto de fuentes inválido: {e}") from None
    revs = [r for r in manifest.revisions if r.doc == XSD_DOC]
    if not revs:
        return None
    rev = revs[-1]
    folder = (root / rev.path).resolve()
    if not folder.is_relative_to(root):
        raise XsdError(f"la ruta de la instantánea sale del repositorio: {rev.path!r}")
    if not folder.is_dir():
        return None
    return folder, _sha12(rev.sha256), rev.retrieved_at


# --- Zona horaria y fechas -----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _paraguay_tz() -> tzinfo:
    try:
        return ZoneInfo("America/Asuncion")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-3), "UTC-03:00")


def paraguay_tz_is_exact() -> bool:
    """`True` si se usa `zoneinfo` (historial completo); `False` si cayó al UTC-03:00 fijo."""
    return isinstance(_paraguay_tz(), ZoneInfo)


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$",
    re.IGNORECASE,
)


def to_paraguay_date(value: str) -> date:
    """Fecha de calendario de Paraguay de un `dFeEmiDE`, un `dFecProc` o una fecha ISO.

    Con zona (`-03:00`, `+00:00`, `Z`) se convierte a America/Asuncion; sin zona se toma la parte de
    fecha tal cual (`dFeEmiDE` ya es hora local). `XmlReadError` si no es una fecha o fecha-hora ISO.
    """
    text = value.strip()
    try:
        if _DATE_ONLY.match(text):
            return date.fromisoformat(text)
        if _DATE_TIME.match(text):
            moment = datetime.fromisoformat(text)
            if moment.tzinfo is None:
                return moment.date()
            return moment.astimezone(_paraguay_tz()).date()
    except ValueError:
        pass
    raise XmlReadError(f"fecha no interpretable: {value!r} (se espera AAAA-MM-DD[Thh:mm:ss[±hh:mm]])")


def anachronistic(at: date, retrieved_at: datetime) -> bool:
    """`True` si `at` es anterior a la instantánea: el XSD es referencia, no evidencia (§D.5, §G.3).

    `retrieved_at` se compara como fecha de Paraguay. No altera el estado de ninguna regla de negocio.
    """
    return at < retrieved_at.astimezone(_paraguay_tz()).date()


# --- Índice de declaraciones -----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Facets:
    """Facetas de la declaración tal como las resuelve `xmlschema` (las heredadas incluidas).

    `patterns`: los patrones del paso de derivación más cercano que declara alguno (en XSD los de un
    mismo paso son alternativas; los de pasos distintos se conjugan y aquí no se reportan los lejanos).
    Una unión (`tdDtipDocRec`) no reporta facetas: sus miembros son alternativas distintas.
    """

    patterns: tuple[str, ...] = ()
    enumeration: tuple[str, ...] = ()
    length: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    total_digits: int | None = None
    fraction_digits: int | None = None


@dataclass(frozen=True, slots=True)
class ElementDecl:
    """Una declaración de elemento alcanzable desde una raíz global, con su ruta (nombres locales)."""

    name: str
    namespace: str
    xpath: str
    parent: str | None
    min_occurs: int
    max_occurs: int | None
    """`None` = `unbounded`."""
    type_name: str | None
    """Nombre local del tipo; `None` si es anónimo."""
    facets: Facets

    @property
    def occurrence(self) -> str:
        """Ocurrencia en el formato del Manual Técnico: `0-1`, `1-1`, `0-n`, `1-999`."""
        return f"{self.min_occurs}-{'n' if self.max_occurs is None else self.max_occurs}"


class OccurrenceCheck(NamedTuple):
    status: Literal["match", "mismatch", "not_checked"]
    detail: str


_OCCURRENCE = re.compile(r"^(\d+)\s*[-\u2013]\s*(\d+|n)$", re.IGNORECASE)


def parse_occurrence(literal: str) -> tuple[int, int | None] | None:
    """`"0-1"` -> `(0, 1)`, `"1-n"` -> `(1, None)`, `"1"` -> `(1, 1)`; `None` si no es una ocurrencia."""
    text = literal.strip()
    if text.isdigit():
        n = int(text)
        return (n, n)
    m = _OCCURRENCE.match(text)
    if not m:
        return None
    low = int(m.group(1))
    high = None if m.group(2).lower() == "n" else int(m.group(2))
    if high is not None and high < low:
        return None
    return (low, high)


def _mul_max(a: int | None, b: int | None) -> int | None:
    if a == 0 or b == 0:
        return 0
    if a is None or b is None:
        return None
    return a * b


def _simple_type_of(t: object) -> XsdSimpleType | None:
    if t is None:
        return None
    if isinstance(t, XsdSimpleType):
        return t
    content = getattr(t, "content", None)
    if getattr(t, "has_simple_content", lambda: False)() and isinstance(content, XsdSimpleType):
        return content
    return None


def _facet_int(facets: Mapping[str | None, object], key: str) -> int | None:
    facet = facets.get(key)
    value = getattr(facet, "value", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _facets_of(t: object) -> Facets:
    st = _simple_type_of(t)
    if st is None or st.is_union():
        return Facets()
    facets = st.facets
    patterns = getattr(getattr(st, "patterns", None), "regexps", None) or ()
    enumeration = getattr(st, "enumeration", None) or ()
    return Facets(
        patterns=tuple(str(p) for p in patterns),
        enumeration=tuple(str(v) for v in enumeration),
        length=_facet_int(facets, XSD_LENGTH),
        min_length=_facet_int(facets, XSD_MIN_LENGTH),
        max_length=_facet_int(facets, XSD_MAX_LENGTH),
        total_digits=_facet_int(facets, XSD_TOTAL_DIGITS),
        fraction_digits=_facet_int(facets, XSD_FRACTION_DIGITS),
    )


def _local(name: str | None) -> str | None:
    return name.rpartition("}")[2] if name else None


def _iter_particles(
    group: XsdGroup, mult_min: int, mult_max: int | None
) -> Iterator[tuple[XsdElement, int, int | None]]:
    """Elementos de un grupo con su ocurrencia EFECTIVA respecto del elemento contenedor.

    Multiplica las ocurrencias de los grupos anidados; los miembros de una `choice` con varias
    alternativas pasan a `minOccurs=0` (solo uno aparece). El XSD actual del DE no usa `choice`, pero
    el índice no debe dar un "obligatorio" falso si algún día lo usa.
    """
    gmin = mult_min * group.min_occurs
    gmax = _mul_max(mult_max, group.max_occurs)
    if group.model == "choice" and len(group) > 1:
        gmin = 0
    for particle in group:
        if isinstance(particle, XsdGroup):
            yield from _iter_particles(particle, gmin, gmax)
        elif isinstance(particle, XsdElement):
            yield particle, gmin * particle.min_occurs, _mul_max(gmax, particle.max_occurs)
        elif isinstance(particle, XsdAnyElement):  # comodín: sin declaración que indexar
            continue


class XsdIndex:
    """Declaraciones de elementos por nombre local, recorriendo cada raíz global del espacio de nombres.

    Un mismo nombre puede declararse en varias rutas (tipos compartidos): `lookup` devuelve todas.
    Los elementos de otros espacios de nombres (p. ej. `ds:Signature` y `X509Certificate`) se indexan
    por su nombre local y llevan su `namespace`. Los atributos (`DE/@Id`) no se indexan.
    """

    def __init__(self, schema: XMLSchema) -> None:
        self._by_name: dict[str, list[ElementDecl]] = {}
        target = schema.target_namespace or ""
        for qname, root in schema.maps.elements.items():
            namespace = qname[1:].partition("}")[0] if qname.startswith("{") else ""
            # las raíces globales de otros espacios (ds:Signature...) solo se alcanzan por referencia
            if namespace == target:
                self._walk(root, (), None, (1, 1), frozenset(), 0)

    def _walk(
        self,
        el: XsdElement,
        path: tuple[str, ...],
        parent: str | None,
        occurs: tuple[int, int | None],
        types_in_path: frozenset[int],
        depth: int,
    ) -> None:
        name = _local(el.name) or ""
        here = (*path, name)
        decl = ElementDecl(
            name=name,
            namespace=el.name.partition("}")[0][1:] if el.name and el.name.startswith("{") else "",
            xpath="/" + "/".join(here),
            parent=parent,
            min_occurs=occurs[0],
            max_occurs=occurs[1],
            type_name=_local(getattr(el.type, "name", None)),
            facets=_facets_of(el.type),
        )
        self._by_name.setdefault(name, []).append(decl)
        t = el.type
        content = getattr(t, "content", None)
        if t is None or not isinstance(content, XsdGroup) or id(t) in types_in_path or depth >= MAX_DEPTH:
            return
        for child, cmin, cmax in _iter_particles(content, 1, 1):
            self._walk(child, here, name, (cmin, cmax), types_in_path | {id(t)}, depth + 1)

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_name.values())

    def __contains__(self, xml_name: object) -> bool:
        return xml_name in self._by_name

    def names(self) -> frozenset[str]:
        return frozenset(self._by_name)

    def lookup(self, xml_name: str, parent: str | None = None) -> list[ElementDecl]:
        """Declaraciones de `xml_name` (nombre local); con `parent`, solo las hijas directas de ese elemento."""
        found = self._by_name.get(xml_name, [])
        return [d for d in found if parent is None or d.parent == parent]

    def check_occurrence(self, xml_name: str, parent: str | None, occurrence_literal: str) -> OccurrenceCheck:
        """Compara la "Ocurrencia" del manual (`m-n`) con `minOccurs`/`maxOccurs` del XSD.

        `match`/`mismatch` solo si el literal se interpreta y hay una única ocurrencia declarada;
        `not_checked` (con el motivo en `detail`) si el literal no se entiende (vacío, `-`), el
        elemento no está en el XSD bajo ese padre o el XSD declara ocurrencias distintas según la ruta.
        Que un elemento del manual falte en el XSD es un hallazgo del llamador, no se decide aquí.
        """
        where = f"{parent}/{xml_name}" if parent else xml_name
        parsed = parse_occurrence(occurrence_literal)
        if parsed is None:
            return OccurrenceCheck(
                "not_checked", f"literal de ocurrencia no interpretable: {occurrence_literal!r}"
            )
        decls = self.lookup(xml_name, parent)
        if not decls:
            return OccurrenceCheck("not_checked", f"{where} no está declarado en el XSD")
        declared = {(d.min_occurs, d.max_occurs) for d in decls}
        if len(declared) > 1:
            lits = ", ".join(sorted({d.occurrence for d in decls}))
            return OccurrenceCheck(
                "not_checked", f"{where}: el XSD declara ocurrencias distintas ({lits}); indique el padre"
            )
        xsd_min, xsd_max = next(iter(declared))
        xsd_lit = decls[0].occurrence
        manual_lit = f"{parsed[0]}-{'n' if parsed[1] is None else parsed[1]}"
        if parsed == (xsd_min, xsd_max):
            return OccurrenceCheck("match", f"{where}: {xsd_lit}")
        return OccurrenceCheck(
            "mismatch", f"{where}: manual {manual_lit} frente a XSD {xsd_lit} ({decls[0].xpath})"
        )


# --- Lectura segura de XML ---------------------------------------------------------------------------
def _open_xml(xml_path: str | Path) -> XMLResource:
    """Abre `xml_path` en solo lectura: sin DTD ni entidades, sin red, sin salir de su carpeta."""
    path = Path(xml_path)
    try:
        size = path.stat().st_size
    except OSError as e:
        raise XmlReadError(f"no se pudo leer {path.name}: {e.strerror or e}") from None
    if not path.is_file():
        raise XmlReadError(f"{path.name} no es un archivo")
    if size > MAX_XML_BYTES:
        raise XmlReadError(f"{path.name} excede {MAX_XML_BYTES} bytes ({size})")
    try:
        resource = XMLResource(str(path.resolve()), allow="sandbox", defuse="always", lazy=False)
        resource.root  # noqa: B018  (fuerza el análisis: un DTD o un XML mal formado falla aquí)
    except (XMLResourceError, XMLSchemaException, OSError, ValueError) as e:
        raise XmlReadError(f"XML ilegible o no permitido ({path.name}): {_first_line(e)}") from None
    return resource


def _root_of(resource: XMLResource) -> Element:
    root = resource.root
    if root is None:
        raise XmlReadError("el XML no tiene elemento raíz")
    return root


def read_xml_root(xml_path: str | Path) -> Element:
    """Raíz de un XML abierto con la lectura segura de este módulo (sin DTD, entidades ni red)."""
    return _root_of(_open_xml(xml_path))


def _first_line(e: BaseException) -> str:
    return (str(e).strip().splitlines() or [type(e).__name__])[0]


def _tag(name: str) -> str:
    return f"{{{SIFEN_NS}}}{name}"


def _parent_map(root: Element) -> dict[Element, Element]:
    return {child: parent for parent in root.iter() for child in parent}


def _find_first(
    scope: Element, parents: Mapping[Element, Element], name: str, parent: str | None
) -> Element | None:
    for el in scope.iter(_tag(name)):
        if parent is None:
            return el
        p = parents.get(el)
        if p is not None and p.tag == _tag(parent):
            return el
    return None


def _de_scope(root: Element) -> Element:
    """El primer elemento `DE` (puede ser la raíz, o estar dentro de `rDE`, `xDE`, un lote...)."""
    if root.tag == _tag("DE"):
        return root
    for el in root.iter(_tag("DE")):
        return el
    raise XmlReadError("no hay un elemento DE (espacio de nombres " + SIFEN_NS + ") en el XML")


def _text(el: Element) -> str:
    return (el.text or "").strip()


def read_values(
    xml_path: str | Path,
    mapping: Mapping[str, tuple[str, str | None]],
) -> dict[str, str | None]:
    """Valores de un XML de DE: `{field_id: (xml_name, parent_xml_name | None)}` -> `{field_id: texto | None}`.

    Toma, por cada campo, el primer elemento (en orden de documento) llamado `xml_name` cuyo padre
    directo sea `parent_xml_name` (cualquiera si es `None`) dentro del primer `DE`, solo en el espacio
    de nombres SIFEN. Devuelve su texto sin espacios laterales (`""` si existe vacío) o `None` si no
    existe: ausente y vacío son cosas distintas. Un XML sin `DE` es `XmlReadError`, no "todo ausente":
    una regla evaluada sobre un archivo equivocado daría veredictos falsos. Nunca modifica el archivo.
    """
    root = _root_of(_open_xml(xml_path))
    scope = _de_scope(root)
    parents = _parent_map(root)
    out: dict[str, str | None] = {}
    for field_id, (xml_name, parent) in mapping.items():
        el = _find_first(scope, parents, xml_name, parent)
        out[field_id] = None if el is None else _text(el)
    return out


def read_emission_date(xml_path: str | Path) -> date | None:
    """Fecha de emisión (`dFeEmiDE` bajo `gDatGralOpe`, D002) como fecha de Paraguay; `None` si falta.

    `dFeEmiDE` es `fecHhmmss` (sin zona, hora local): se toma su parte de fecha tal cual.
    """
    value = read_values(xml_path, {"D002": ("dFeEmiDE", "gDatGralOpe")})["D002"]
    return None if not value else to_paraguay_date(value)


def read_processing_date(response_xml_path: str | Path) -> date | None:
    """Fecha de procesamiento (`dFecProc` de `rProtDe`) de la respuesta de SIFEN, en fecha de Paraguay.

    Busca el `rProtDe` en cualquier parte del documento (respuesta directa `rRetEnviDe/rProtDe` o dentro
    de un sobre SOAP). `dFecProc` es `fecUTC` (ver la cabecera del módulo): lleva desplazamiento, que se
    convierte a America/Asuncion. `None` si no hay `dFecProc`; `XmlReadError` si está y no es una fecha.
    """
    root = _root_of(_open_xml(response_xml_path))
    parents = _parent_map(root)
    el = _find_first(root, parents, "dFecProc", "rProtDe")
    if el is None:
        return None
    text = _text(el)
    if not text:
        raise XmlReadError("dFecProc está vacío")
    return to_paraguay_date(text)


# --- Validación ---------------------------------------------------------------------------------------
_PREFIX_IN_PATH = re.compile(r"(?<=/)[A-Za-z_][\w.\-]*:")
_CLARK_NS = re.compile(r"\{[^}]*\}")


def validate_xml(
    schema: XMLSchema, xml_path: str | Path, *, max_errors: int = DEFAULT_MAX_ERRORS
) -> list[str]:
    """Errores de esquema de `xml_path`, como `"<ruta>: <motivo>"`, hasta `max_errors` (y un aviso si hay más).

    Rutas con nombres locales, sin prefijos. SIFEN informa solo el primer error al emisor; aquí salen
    varios (no todos: `xmlschema` informa el primer problema de cada elemento). Una lista vacía solo
    dice que el XML cumple el XSD: no que el servidor lo acepte (firma, timbrado y reglas de negocio
    no se evalúan). Un XML ilegible o con DTD produce un único error con el motivo.
    """
    try:
        resource = _open_xml(xml_path)
    except XmlReadError as e:
        return [str(e)]
    errors: list[str] = []
    for i, err in enumerate(schema.iter_errors(resource)):
        if i >= max_errors:
            errors.append(f"... hay más errores de esquema (se muestran los primeros {max_errors})")
            break
        path = _PREFIX_IN_PATH.sub("", err.path or "/")
        reason = _CLARK_NS.sub("", str(err.reason or err.message))
        errors.append(f"{path}: {reason}")
    return errors


# --- Datos personales ---------------------------------------------------------------------------------
PII_ELEMENTS: frozenset[str] = frozenset(
    {
        # §M.4 (verificados uno por uno contra la instantánea 2026-10-17):
        "dRucEm",
        "dRucRec",
        "dNumIDRec",
        "dNomEmi",
        "dNomRec",
        "dDirEmi",
        "dDirRec",
        "dTelRec",
        "dEmailRec",
        "dCarQR",  # URL del QR: lleva dRucRec/dNumIDRec y el hash con CSC
        "X509Certificate",  # certificado del firmante (ds, no sifen)
        "dCodSeg",  # junto con RUC, número y fecha reconstruye un CDC real
        # Mismas clases de dato (emisor, receptor, terceros del DE) que el XSD también declara:
        "dNomFanEmi",
        "dNomFanRec",
        "dTelEmi",
        "dEmailE",
        "dCelRec",
        "dCompDir1",
        "dCompDir2",
        "dNomRespDE",
        "dNumIDRespDE",
        "dNomChof",
        "dNumIDChof",
        "dDirChof",
        "dNomTrans",
        "dNumIDTrans",
        "dRucTrans",
        "dNombAg",
        "dRucAg",
        "dDirAge",
        "dNomVen",
        "dNumIDVen",
        "dDirVen",
        "dDirProv",
        "dNomTit",
        "dCdCDERef",  # CDC de un DE asociado
        "dCDCAnticipo",
    }
)
"""Nombres de elemento (locales) con datos personales o que reconstruyen un dato real (§M).

El CDC del propio DE es el atributo `DE/@Id` (no es un elemento) y también es confidencial.
"""

_MASK = "****"


def mask(value: str, *, keep: int = 3) -> str:
    """Enmascara un dato personal conservando como máximo los últimos `keep` caracteres.

    `"4567890"` -> `"****890"`. Nunca revela la mitad ni más del valor: `"1234"` -> `"****4"`,
    `"12"` -> `"****"`. El enmascarado no delata el largo (siempre cuatro asteriscos). `""` -> `""`.
    """
    if not value:
        return ""
    visible = min(keep, (len(value) - 1) // 2)
    return _MASK + (value[-visible:] if visible > 0 else "")

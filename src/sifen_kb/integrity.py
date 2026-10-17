"""Integridad del canónico: `sifen check` y `sifen fmt` (docs/arquitectura.md §H, §J, §K.3, §K.4).

`sifen check` es el núcleo de la garantía de evidencia: lo literal se COPIA con la herramienta y aquí
se VERIFICA; lo interpretado se acota. Cada comprobación es una función pura `check_*(kb) -> list
[Finding]` que los tests reutilizan; ninguna aborta al primer problema (`run_checks` además aísla un
fallo interno de una comprobación como un hallazgo). `Finding(check, where, message, severity)`:
`where` es la ruta del archivo (relativa a la raíz) o la clave afectada.

Salida de `sifen check --json` (contrato estable):

    {"ok": bool, "counts": {"error": n, "warning": n, "info": n},
     "checks": [nombre, ...],                      # en el orden en que corren
     "findings": [{"check", "severity", "where", "message"}, ...]}

Código de salida: 0 sin errores (avisos e informativos no fallan), 1 con algún error.

Comprobaciones (nombre → qué impide):

- `carga`: errores de `load_kb` (esquema, YAML restringido).
- `archivos`: clave == ruta del archivo, rutas únicas sin distinguir mayúsculas (Windows), y ningún
  archivo fuera del esquema de `kb/` (`load_kb` ignoraría en silencio un YAML mal ubicado).
- `formato`: `dump_kb(load(texto)) == texto` en `kb/**/*.yaml` y el manifiesto (como `fmt --check`).
- `fuentes`: `sources.verify_sources`; `current_revision` existe en el manifiesto; línea base de
  `_meta.yaml` (sin ficha de la línea base es error, salvo con `kb/documents/` vacío: punto de partida
  de la curación, info); revisiones sin curar y documentos registrados sin ficha (avisos); horizonte.
- `refs_raw`: cada `RowRef`/`CellRef` resuelve a EXACTAMENTE una fila (y su celda) de una revisión
  registrada; un `PageRef` cita una revisión registrada.
- `literales`: cada literal de una versión == `RawRow.literal(attr)` de la fila citada (MT V150: texto
  vigente sin lo tachado; NT: la celda completa, el color de una NT no tiene semántica). La fila es de
  la entidad (clave e `id` == ID, tabla de campos o de validaciones según el tipo). Una columna que la
  fila no reproduce se hereda de `based_on`; en la línea base, sin celda no hay literal.
- `destino_efecto`: el destino de un efecto (aplicado o `pending`) == ID de la fila citada.
- `citas`: `normalize_text(quote)` contenida en la página normalizada; `page_printed` == `index.json`.
- `fechas_celdas`: `DateStatement`: literal == celda; la celda es del propio documento y de su
  `current_revision`; ranura ↔ atributo (`document_date`→`fecha`, `schedule.test`→`test`,
  `schedule.prod`→`prod`) y encabezado de la columna; `value == parse(literal)`.
- `dsl`: la condición se analiza; sus nombres son campos curados; sus constantes ⊂ `observation`.
- `enumeracion`: etiquetas ⊂ `observations`; códigos sin repetir.
- `cobertura` (guardián): toda mención del vocabulario curado (IDs, códigos, `xml_name`) en el `raw/`
  de una NT está reconocida por un efecto del documento; `raw/_ledger/changes.jsonl` es oráculo de
  filas cambiadas por NT.
- `biyeccion`: efecto aplicado ↔ exactamente una versión de su destino; `pending`/`not_modeled` en
  ninguna; los efectos de una versión comparten inicio por ambiente.
- `acciones`: lápida ⇔ `remove`; primera versión sin línea base y reintroducción tras una lápida ⇒
  `add` (la reintroducción, además, con un Issue sobre la entidad).
- `inicio_unico`: dos versiones distintas no empiezan el mismo día en un ambiente.
- `predecesora`: `based_on` == predecesora temporal en producción.
- `alcance`: diff(versión, `based_on`) ⊆ `declared_scope`; con `row`, toda COLUMNA cambiada salvo la
  observación figura en `acknowledged_changes`; una lápida copia la predecesora.
- `interpretado`: un cambio de `condition`/`enumeration` exige un cambio de su literal (anti-R3).
- `inversion_ambientes`: orden test ≠ prod entre versiones ⇒ Issue `temporal` bloqueante en test que
  cubra la ventana invertida.
- `inicio_aproximado`: supuesto A1 (un documento sin calendario empieza antes de `coverage_from`).
- `integridad_temporal`: en cada punto de cambio, toda validación vigente lee campos vigentes.
- `colisiones`: un código en dos validaciones exige un Issue `code_collision` que las nombre.
- `fechas_sanas`: test ≤ prod; > 90 días entre `document_date` y test exige Issue `erratum`.
- `referencias`: `subject_field`, destinos, `introduced_by`, `based_on`, `from_revision`, sujetos de
  Issues, formato y existencia de `corrects`, documento de `superseded_by`.
- `reemplazo`: oráculo de `superseded_by` (el fin derivado en producción de lo que introdujo el
  documento es `since`).
- `corridas_llm`: `by: llm` ⇒ `curation/runs/<run>.yaml` existe y lista el archivo en `outputs`; con
  base de `main`, la interpretación nueva cita una corrida de este cambio y un archivo que editó una
  corrida de este cambio no estrena una interpretación `by: human`.
- `pasado`: contra la base de `main` (ver «Pasado justificado»).
- `casos`: frontmatter de `cases/**/*.md` (modelo `Case`), referencias, origen y PII por elemento.

Decisiones ante ambigüedades del diseño (lectura conservadora; ver también el informe del PR):

1. Guardián de cobertura, granularidad: una mención del término T en la NT D está reconocida si D tiene
   un efecto (cualquier `disposition`) cuyo destino es una entidad cuyo vocabulario contiene T, o un
   efecto `pending` sin destino (el resolvedor ya lo trata como pendiente de toda clave mencionada).
   Un `not_modeled` sin destino no reconoce nada. NO se exime una mención por estar dentro de la fila de
   otra entidad: si la observación de D208c en NT 24 nombra D208 y F014, NT 24 necesita efectos
   (típicamente `not_modeled` con nota) sobre `field:DE:D208` y `field:DE:F014`. Una NT registrada sin
   ficha que menciona el vocabulario es un error. Se lee la revisión MÁS RECIENTE del manifiesto (como
   `mentions`). Solo documentos `NT_ddd`. El libro de cambios exige un efecto sobre la entidad de cada
   fila cambiada (si está curada); su acción deducida por color NO se usa (el color de una NT no tiene
   semántica).
2. Literales con varias filas citadas: el literal debe coincidir con la celda de AL MENOS una de ellas
   (aviso si las filas discrepan entre sí). Un `CellRef` solo respalda su atributo.
3. `destino_efecto` no se aplica a `not_modeled`: su evidencia muestra la mención, no una fila del
   destino. Un `add` sobre una entidad que ya existe es solo un aviso.
4. Primera versión de una entidad agregada por una NT: `based_on: baseline` sin versión de línea base
   significa «sin predecesora» (el modelo exige `based_on`); se exige `action: add`.
5. `based_on` de una versión prospectiva en producción: la última versión fechada en producción.
6. Alcance: `acknowledged_changes` solo amplía el alcance `row`; con una lista se avisa que no cuenta.
   Con `row`, los atributos que no son columnas (`condition`, `legal_basis`, `enumeration`…) pueden
   cambiar, sujetos a `interpretado`. Con lista, `condition` sigue a `observation` y `enumeration` a
   `observations`; cualquier otro atributo debe figurar en la lista.
7. `interpretado` compara el objeto completo (también su `interpretation`: re-atribuir la condición
   sin cambio del literal falla).
8. `fechas_sanas`: diferencia ABSOLUTA en días entre `document_date` y test (producción si no hay test).
9. `inicio_aproximado`: solo documentos sin calendario que tienen efectos.
10. `reemplazo`: se verifica el fin en producción.
11. `corridas_llm`: `run` es el id de sesión (`curation/runs/<run>.yaml`); se acepta también la ruta
    `curation/runs/<x>.yaml`. No se compara el sha256 de `outputs` (el archivo puede reformatearse
    después). «Corrida del mismo PR» = archivo de `curation/runs/` agregado o modificado respecto de la
    base; una interpretación nueva (ausente en la base) `by: llm` debe citar una de esas, y en un archivo
    que una de esas editó no puede aparecer una interpretación nueva `by: human` (solo `human`, no
    `tool`, como dice §J). Sin base, solo se verifica que la corrida exista y liste el archivo.
12. Base de `main` para «pasado»: `$SIFEN_BASE_REF`, luego `main`, luego `origin/main` (el CI hace
    checkout con `fetch-depth: 0` y no siempre tiene la rama local); se compara contra el ANCESTRO
    COMÚN con HEAD (como `prscope`) y contra el árbol de trabajo. Sin git o sin esa rama: info «no
    comprobado».
13. Casos: se cargan el frontmatter y las referencias; la PII se busca por nombre de elemento
    (`xsd.PII_ELEMENTS`, como etiqueta XML o `nombre: valor`), con `tests/allowlist_pii.yaml` como
    lista de valores permitidos (si falta, ningún valor lo está; un valor con `*` se da por enmascarado)
    y una segunda capa de CDC de 44 dígitos, correos y RUC junto a «RUC».

Pasado justificado (`check_past_changes`, §K.4 `test_past_changes_justified`, §G.3):

- Siempre falla: borrar una entidad, una versión (identidad = `introduced_by`, así que cambiarlo cuenta
  como borrar), un efecto, un documento, un Issue o una fila golden; y reescribir el manifiesto
  (`sources.check_append_only`).
- Modificar un atributo de una versión existente exige un Issue `curation_error|erratum|temporal` cuyo
  `corrects` incorpora EN ESTE CAMBIO la entrada `<clave>@<baseline|NT_021#1[+…]>.<atributo>`
  (`val:DE:D208c@NT_021#1.observation`; una entrada más fina, `….condition.expr`, también cubre). Se
  admite sin Issue la re-materialización tras una curación fuera de orden (§F.2): `based_on` pasa a
  ser la predecesora temporal y las columnas que la fila no reproduce toman el valor de la nueva
  predecesora.
- Extensiones (no están en el diseño; mismas reglas): un efecto no `pending` modificado exige
  `NT_021#1.<atributo>` en `corrects`; `subject_field`/`context`/`id` de una entidad, `<clave>.<attr>`;
  el calendario de un documento (`document_date`, `change_period`, `schedule`, `superseded_by`), un
  Issue de esos tipos nuevo o modificado con el documento como sujeto (prórroga, §G.3) o
  `NT_901.schedule` en `corrects`; la expectativa de una fila golden, un Issue nuevo o modificado de
  esos tipos con la clave de la fila como sujeto. Un efecto `pending` cambia libremente; AGREGAR un
  `superseded_by` (oráculo, no altera respuestas) se informa sin exigir Issue; un cambio de
  `kb/_meta.yaml` (protegido) es un aviso para la revisión humana y borrarlo, un error.
- Cada cambio justificado se informa (severidad info): es la lista de «cambios al pasado» del informe.

`sifen fmt`: canonicidad de `kb/**/*.yaml` y `sources.manifest.yaml`. Con `--check` no escribe y sale
con 1 si alguno no es canónico. Sin `--check` reescribe los de `kb/`, salvo los PROTEGIDOS
(`sources.manifest.yaml`, `kb/_meta.yaml`), que solo se verifican; y se niega a reescribir un archivo
cuyo volcado pierde algún `#` (un comentario o un `" #"` que truncó un valor): eso se corrige a mano.

`--report` (si la CLI lo expone: `getattr(args, "report", False)`) agrega el informe de revisión del PR
(§D.3 paso 7); ver `render_report`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from sifen_kb import dsl
from sifen_kb.load import KB, find_root, load_kb
from sifen_kb.mentions import key_terms, printed_page, term_pattern
from sifen_kb.model import (
    ENVS,
    Case,
    CurationRun,
    DateStatement,
    DocumentSource,
    Effect,
    Env,
    Field,
    FieldVersion,
    Interpretation,
    Issue,
    KBMeta,
    PageRef,
    SourcesManifest,
    Validation,
    ValidationVersion,
    parse_ref,
)
from sifen_kb.normalize import normalize_text, parse_date_literal, sha12
from sifen_kb.rawio import DATE_ATTRS, RawRow, iter_ledger, page_path, read_index, rev_dir, row_from_dict
from sifen_kb.sources import MANIFEST_NAME, check_append_only, verify_sources
from sifen_kb.temporal import (
    PRE_COVERAGE,
    TemporalDataError,
    diff_versions,
    effect_start,
    timeline,
    version_start,
)
from sifen_kb.yamlio import KBYamlError, dump_kb, load_kb_text

Severity = Literal["error", "warning", "info"]
Version = FieldVersion | ValidationVersion
Entity = Field | Validation

FIELD_LITERALS: tuple[str, ...] = (
    "group",
    "parent",
    "xml_name",
    "description",
    "data_type",
    "length",
    "occurrence",
    "observations",
)
"""Columnas literales de la tabla de campos (atributo del modelo == atributo de la celda)."""
VALIDATION_LITERALS: tuple[str, ...] = ("code", "severity", "message", "observation")
"""Columnas literales de la tabla de validaciones."""
INTERPRETED_OF: dict[str, str] = {
    "condition": "observation",
    "enumeration": "observations",
    "enumeration_interpretation": "observations",
}
"""Atributo interpretado -> literal del que depende."""
NON_CONTENT = frozenset({"introduced_by", "based_on", "evidence", "kind", "open_questions"})
CORRECTING_KINDS = frozenset({"curation_error", "erratum", "temporal"})
CALENDAR_ATTRS: tuple[str, ...] = ("document_date", "change_period", "schedule", "superseded_by")
ERRATUM_DAYS = 90
PROTECTED: tuple[str, ...] = (MANIFEST_NAME, "kb/_meta.yaml")
"""Archivos que `sifen fmt` solo verifica (los escribe la herramienta o una persona, nunca fmt)."""
RUNS_DIR = "curation/runs"
GOLDEN_PATH = "tests/golden/temporal.yaml"
PII_ALLOWLIST = "tests/allowlist_pii.yaml"
BASE_REF_ENV = "SIFEN_BASE_REF"
DEFAULT_BASE_REFS: tuple[str, ...] = ("main", "origin/main")

_NT_DOC = re.compile(r"^NT_\d{3}$")
_PAGE_FILE = re.compile(r"^p(\d+)\.txt$")
_KB_LAYOUT = re.compile(
    r"^kb/(?:_meta\.yaml|documents/[^/]+\.yaml|(?:fields|validations)/[^/]+/[^/]+\.yaml|issues/[^/]+\.yaml)$"
)
_VERSION_LABEL = r"(?:baseline|[A-Z][A-Z0-9_]*#\d+(?:\+[A-Z][A-Z0-9_]*#\d+)*)"
_CORR_VERSION = re.compile(
    rf"^(?P<key>(?:field|val):[A-Z][A-Z-]*:\w+)@(?P<ver>{_VERSION_LABEL})\.(?P<attr>[a-z_]+)(?:\..+)?$"
)
_CORR_ENTITY = re.compile(r"^(?P<key>(?:field|val):[A-Z][A-Z-]*:\w+)\.(?P<attr>[a-z_]+)$")
_CORR_EFFECT = re.compile(r"^(?P<eff>[A-Z][A-Z0-9_]*#\d+)\.(?P<attr>[a-z_]+)(?:\..+)?$")
_CORR_DOC = re.compile(r"^(?P<doc>[A-Z][A-Z0-9_]*)\.(?P<attr>[a-z_]+)(?:\..+)?$")
_DATE_HEADER: dict[str, Callable[[str], bool]] = {
    "fecha": lambda h: h.startswith("fecha") and "test" not in h and "producci" not in h,
    "test": lambda h: "test" in h,
    "prod": lambda h: "producci" in h,
}
_SLOT_ATTR = {"document_date": "fecha", "schedule.test": "test", "schedule.prod": "prod"}


# --- Hallazgos -------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Finding:
    """Un hallazgo de una comprobación. `where`: ruta relativa a la raíz o clave afectada."""

    check: str
    where: str
    message: str
    severity: Severity = "error"

    def as_dict(self) -> dict[str, str]:
        return {"check": self.check, "severity": self.severity, "where": self.where, "message": self.message}


class _Out(list[Finding]):
    """Acumulador de hallazgos de UNA comprobación."""

    def __init__(self, check: str) -> None:
        super().__init__()
        self.check = check

    def error(self, where: str, message: str) -> None:
        self.append(Finding(self.check, where, message, "error"))

    def warning(self, where: str, message: str) -> None:
        self.append(Finding(self.check, where, message, "warning"))

    def info(self, where: str, message: str) -> None:
        self.append(Finding(self.check, where, message, "info"))


def errors_of(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "error"]


# --- Utilidades ------------------------------------------------------------------------------------
def _loc(kb: KB, key: str) -> str:
    """Ruta (relativa a la raíz, con `/`) del archivo de una clave; la clave si no se conoce."""
    p = kb.paths.get(key)
    if p is None:
        return key
    try:
        return p.relative_to(kb.root).as_posix()
    except ValueError:
        return p.as_posix()


def _short(s: object, n: int = 140) -> str:
    t = repr(s)
    return t if len(t) <= n else t[: n - 1] + "…"


def _intro_id(x: str | list[str] | None) -> str | frozenset[str] | None:
    """Identidad de `introduced_by`/`based_on`: el orden de los efectos no importa."""
    if x is None or isinstance(x, str):
        return x
    return frozenset(x)


def _clabel(x: str | list[str] | None) -> str:
    """Etiqueta de versión de `corrects`: `baseline` o `NT_021#1[+NT_021#2]`."""
    if x is None:
        return "—"
    return x if isinstance(x, str) else "+".join(x)


def _vlabel(v: Version) -> str:
    return _clabel(v.introduced_by)


def _based_on_version(ent: Entity, v: Version) -> Version | None:
    """La versión a la que apunta `based_on` (None si falta o si es `baseline` sin línea base)."""
    target = _intro_id(v.based_on)
    if target is None:
        return None
    for w in ent.versions:
        if w is not v and _intro_id(w.introduced_by) == target:
            return w
    return None


def _effects_of(kb: KB, v: Version) -> list[Effect] | None:
    """Efectos que introducen la versión; None si es la línea base o si alguno no existe."""
    if v.introduced_by == "baseline":
        return None
    if not all(kb.has_effect(e) for e in v.introduced_by):
        return None
    return [kb.effect(e) for e in v.introduced_by]


def _has_dangling(kb: KB, ent: Entity) -> bool:
    return any(
        isinstance(v.introduced_by, list) and not all(kb.has_effect(e) for e in v.introduced_by)
        for v in ent.versions
    )


def _placed(kb: KB, ent: Entity, env: Env) -> tuple[list[tuple[date, int]], list[int], list[str]]:
    """(versiones fechadas `(inicio, índice)` ordenadas, índices prospectivos, errores de datos)."""
    dated: list[tuple[date, int]] = []
    pros: list[int] = []
    errs: list[str] = []
    for i, v in enumerate(ent.versions):
        try:
            d, _ = version_start(kb, v, env)
        except TemporalDataError as e:
            errs.append(str(e))
            continue
        if d is None:
            pros.append(i)
        else:
            dated.append((d, i))
    dated.sort()
    return dated, pros, errs


def _day(d: date) -> str:
    return "la línea base" if d == date.min else d.isoformat()


def _temporal_predecessor(kb: KB, ent: Entity, v: Version) -> tuple[bool, str | list[str] | None]:
    """(calculable, `introduced_by` de la predecesora temporal en producción; "baseline" si no hay)."""
    dated, pros, errs = _placed(kb, ent, "prod")
    if errs or len({d for d, _ in dated}) != len(dated):
        return False, None
    order = [i for _, i in dated]
    idx = ent.versions.index(v)
    if idx in order:
        pos = order.index(idx)
        return True, (ent.versions[order[pos - 1]].introduced_by if pos > 0 else "baseline")
    return True, (ent.versions[order[-1]].introduced_by if order else "baseline")


def _subjects(kb: KB, key: str, versions: list[Version]) -> set[str]:
    """Sujetos de Issue que cubren la clave: ella, los efectos de esas versiones y sus documentos."""
    out = {key}
    for v in versions:
        if isinstance(v.introduced_by, list):
            for e in v.introduced_by:
                out.add(e)
                if kb.has_effect(e):
                    out.add(kb.doc_of(e).id)
    return out


def _date_slots(d: DocumentSource) -> Iterator[tuple[str, DateStatement]]:
    if d.document_date is not None:
        yield "document_date", d.document_date
    if d.change_period is not None:
        yield "change_period[0]", d.change_period[0]
        yield "change_period[1]", d.change_period[1]
    if d.schedule is not None:
        if d.schedule.test is not None:
            yield "schedule.test", d.schedule.test
        if d.schedule.prod is not None:
            yield "schedule.prod", d.schedule.prod


def _rev_registered(kb: KB, doc: str, rev12: str) -> bool:
    return any(r.doc == doc and r.sha256.startswith(rev12) for r in kb.manifest.revisions)


def _read_text_exact(p: Path) -> str:
    """Texto sin traducir finales de línea (un CRLF no es canónico)."""
    return p.read_bytes().decode("utf-8")


# --- Acceso a raw/ con unicidad --------------------------------------------------------------------
def _stat_key(p: Path) -> tuple[str, int, int] | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return str(p), st.st_mtime_ns, st.st_size


@lru_cache(maxsize=256)
def _load_rows(
    path: str, mtime_ns: int, size: int, doc: str, rev12: str
) -> dict[tuple[int, str, int], tuple[RawRow, ...]]:
    grouped: dict[tuple[int, str, int], list[RawRow]] = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = row_from_dict(doc, rev12, json.loads(line))
                grouped[(r.page, r.key, r.occ)].append(r)
    return {k: tuple(v) for k, v in grouped.items()}


@lru_cache(maxsize=4096)
def _load_page(path: str, mtime_ns: int, size: int) -> str:
    return normalize_text(Path(path).read_text(encoding="utf-8"))


class _Raw:
    """Lectura de raw/ que, a diferencia de `RawStore`, detecta filas duplicadas."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def rows(self, doc: str, rev12: str) -> dict[tuple[int, str, int], tuple[RawRow, ...]] | None:
        k = _stat_key(rev_dir(self.root, doc, rev12) / "tables.jsonl")
        return None if k is None else _load_rows(*k, doc, rev12)

    def resolve(self, ref: str) -> tuple[RawRow | None, str | None]:
        """(fila, None) o (None, motivo). Con `#attr`, la celda debe existir."""
        try:
            p = parse_ref(ref)
        except ValueError as e:
            return None, str(e)
        doc, rev12, attr = str(p["doc"]), str(p["sha12"]), p["attr"]
        rows = self.rows(doc, rev12)
        if rows is None:
            return None, f"no existe raw/{doc}/{rev12}/tables.jsonl"
        found = rows.get((int(p["page"]), str(p["key"]), int(p["occ"])), ())  # type: ignore[arg-type]
        if not found:
            return None, "no resuelve a ninguna fila"
        if len(found) > 1:
            return None, f"resuelve a {len(found)} filas (debe ser exactamente una)"
        row = found[0]
        if attr and attr not in row.cells:
            return None, f"la fila no tiene la celda #{attr}"
        return row, None

    def page(self, doc: str, rev12: str, page: int) -> str | None:
        k = _stat_key(page_path(self.root, doc, rev12, page))
        return None if k is None else _load_page(*k)

    def pages(self, doc: str, rev12: str) -> list[int] | None:
        d = rev_dir(self.root, doc, rev12) / "pages"
        if not d.is_dir():
            return None
        return sorted(int(m.group(1)) for p in d.iterdir() if (m := _PAGE_FILE.match(p.name)))

    def index(self, doc: str, rev12: str) -> dict[str, Any] | None:
        try:
            return read_index(self.root, doc, rev12)
        except ValueError:
            return None


def _cell(row: RawRow, attr: str) -> str | None:
    """Literal esperado de la celda (`RawRow.literal`), None si la fila no trae ese atributo."""
    if attr not in row.cells and attr not in row.raw_cells:
        return None
    try:
        return row.literal(attr)
    except KeyError:
        return row.cells.get(attr)


def _same_literal(value: str | None, cell: str) -> bool:
    if value is None:
        return cell == ""
    return normalize_text(value) == cell


# --- Recorrido de referencias ----------------------------------------------------------------------
@dataclass(frozen=True)
class _Site:
    where: str
    owner: str
    ref: str | PageRef
    kind: Literal["date", "supersession", "effect", "version", "legal", "issue"]
    doc: str | None = None
    """Documento dueño del sitio (para fechas y efectos)."""


def _ref_sites(kb: KB) -> Iterator[_Site]:
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        w = _loc(kb, doc_id)
        for slot, ds in _date_slots(d):
            yield _Site(w, f"{doc_id} {slot}", ds.stated_in, "date", doc_id)
        if d.superseded_by is not None:
            yield _Site(w, f"{doc_id} superseded_by", d.superseded_by.stated_in, "supersession", doc_id)
        for e in d.effects:
            for ev in e.evidence:
                yield _Site(w, e.id, ev, "effect", doc_id)
    for key, ent in sorted(kb.entities().items()):
        w = _loc(kb, key)
        for v in ent.versions:
            owner = f"{key} {_vlabel(v)}"
            for ev in v.evidence:
                yield _Site(w, owner, ev, "version")
            for lb in getattr(v, "legal_basis", []):
                yield _Site(w, f"{owner} legal_basis", lb.stated_in, "legal")
    for iid in sorted(kb.issues):
        for ev in kb.issues[iid].evidence:
            yield _Site(_loc(kb, iid), iid, ev, "issue")


def _row_refs(evidence: list[Any]) -> list[str]:
    return [ev for ev in evidence if isinstance(ev, str) and ev.startswith("raw:")]


# === Comprobaciones ================================================================================
def check_load(kb: KB) -> list[Finding]:
    """Errores de carga (`KB.errors`): esquema Pydantic y YAML restringido."""
    out = _Out("carga")
    for e in kb.errors:
        where, sep, msg = e.partition(": ")
        out.error(where if sep else "kb", msg if sep else e)
    return out


def check_files(kb: KB) -> list[Finding]:
    """Clave == ruta; rutas únicas sin distinguir mayúsculas; nada fuera del esquema de `kb/`."""
    out = _Out("archivos")
    kbdir = kb.root / "kb"
    if not kbdir.is_dir():
        return out
    expected: dict[str, str] = {}
    for d in kb.documents.values():
        expected[d.id] = f"kb/documents/{d.id}.yaml"
    for f in kb.fields.values():
        expected[f.key] = f"kb/fields/{f.context}/{f.id}.yaml"
    for v in kb.validations.values():
        expected[v.key] = f"kb/validations/{v.context}/{v.id}.yaml"
    for i in kb.issues.values():
        expected[i.id] = f"kb/issues/{i.id}.yaml"
    for key in sorted(expected):
        actual = _loc(kb, key)
        if key in kb.paths and actual != expected[key]:
            out.error(actual, f"{key} debe vivir en {expected[key]}")
    files = sorted(p for p in kbdir.rglob("*") if p.is_file())
    folded: dict[str, list[str]] = defaultdict(list)
    for p in files:
        rel = p.relative_to(kb.root).as_posix()
        folded[rel.lower()].append(rel)
        if not rel.endswith(".yaml"):
            out.warning(rel, "archivo ajeno al esquema de kb/ (solo YAML)")
        elif not _KB_LAYOUT.match(rel):
            out.error(rel, "YAML fuera del esquema de kb/: load_kb no lo lee (¿carpeta o nivel equivocados?)")
    for rels in folded.values():
        if len(rels) > 1:
            out.error(rels[0], f"rutas iguales sin distinguir mayúsculas (Windows): {', '.join(rels)}")
    # Issues con el mismo id en archivos distintos: load_kb conserva el último en silencio.
    seen: dict[str, str] = {}
    for p in sorted((kbdir / "issues").glob("*.yaml")):
        rel = p.relative_to(kb.root).as_posix()
        try:
            data = load_kb_text(_read_text_exact(p), source=rel)
        except KBYamlError, UnicodeDecodeError:
            continue
        iid = data.get("id") if isinstance(data, dict) else None
        if isinstance(iid, str):
            if iid in seen:
                out.error(rel, f"Issue {iid} duplicado (también en {seen[iid]})")
            seen.setdefault(iid, rel)
    return out


def canonical_targets(root: Path) -> list[Path]:
    """`kb/**/*.yaml` (orden estable) y `sources.manifest.yaml`, los que existan."""
    out: list[Path] = []
    kbdir = root / "kb"
    if kbdir.is_dir():
        out += sorted(p for p in kbdir.rglob("*.yaml") if p.is_file())
    m = root / MANIFEST_NAME
    if m.is_file():
        out.append(m)
    return out


def _canonical_form(p: Path, rel: str) -> tuple[str, str | None, str | None]:
    """(texto, volcado canónico o None, error)."""
    try:
        text = _read_text_exact(p)
    except (OSError, UnicodeDecodeError) as e:
        return "", None, f"no se puede leer: {e}"
    try:
        return text, dump_kb(load_kb_text(text, source=rel)), None
    except KBYamlError as e:
        return text, None, str(e)


def check_format(kb: KB) -> list[Finding]:
    """Formato canónico: cargar y volver a volcar da el mismo archivo (como `sifen fmt --check`)."""
    out = _Out("formato")
    for p in canonical_targets(kb.root):
        rel = p.relative_to(kb.root).as_posix()
        text, canon, err = _canonical_form(p, rel)
        if err is not None:
            out.error(rel, f"no se puede verificar el formato: {err}")
        elif canon != text:
            out.error(
                rel, "no está en formato canónico (comentario, « #» que trunca, CRLF u orden): `sifen fmt`"
            )
    return out


def check_sources(kb: KB) -> list[Finding]:
    """Hash de fuentes, `current_revision` en el manifiesto, línea base, revisiones sin curar."""
    out = _Out("fuentes")
    root = kb.root
    has_kb = (root / "kb").is_dir()
    has_manifest = (root / MANIFEST_NAME).is_file()
    if not has_kb:
        out.info("kb", "kb/ no existe todavía: solo se verificaron las fuentes y el manifiesto")
    if has_manifest:
        for e in verify_sources(root):
            out.error(MANIFEST_NAME, e)
    elif has_kb:
        out.error(MANIFEST_NAME, "falta sources.manifest.yaml: ninguna revisión curada es verificable")
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        w = _loc(kb, doc_id)
        if kb.revision(doc_id, d.current_revision) is None:
            out.error(
                w, f"current_revision {sha12(d.current_revision)} no está en el manifiesto para {doc_id}"
            )
            continue
        latest = kb.latest_revision(doc_id)
        if latest is not None and latest.sha256 != d.current_revision:
            out.warning(
                w,
                f"{doc_id}: la revisión {sha12(latest.sha256)} del manifiesto no está curada "
                f"(current_revision {sha12(d.current_revision)}): las entidades afectadas responden "
                "undetermined (revision_not_curated)",
            )
    if has_kb:
        meta_path = root / "kb" / "_meta.yaml"
        if kb.meta is None and not meta_path.exists():
            out.error("kb/_meta.yaml", "falta kb/_meta.yaml (línea base, cobertura, gracia, eje)")
        meta = kb.meta
        if meta is not None:
            if kb.revision(meta.baseline_doc, meta.baseline_sha256) is None:
                out.error(
                    "kb/_meta.yaml",
                    f"la línea base {meta.baseline_doc}@{sha12(meta.baseline_sha256)} no está en el manifiesto",
                )
            base_doc = kb.documents.get(meta.baseline_doc)
            if base_doc is None and not kb.documents:
                out.info(
                    "kb/_meta.yaml",
                    f"la línea base {meta.baseline_doc} aún no tiene ficha: kb/documents/ está vacío "
                    "(curación sin empezar)",
                )
            elif base_doc is None:
                out.error(
                    "kb/_meta.yaml", f"la línea base {meta.baseline_doc} no tiene ficha en kb/documents/"
                )
            elif base_doc.current_revision != meta.baseline_sha256:
                out.error(
                    _loc(kb, meta.baseline_doc),
                    f"current_revision {sha12(base_doc.current_revision)} ≠ línea base de _meta.yaml "
                    f"({sha12(meta.baseline_sha256)})",
                )
        if kb.documents:
            for doc_id in sorted({r.doc for r in kb.manifest.revisions} - set(kb.documents)):
                out.warning(
                    MANIFEST_NAME,
                    f"{doc_id} está registrado sin ficha en kb/documents/ (revision_not_curated desde coverage_from)",
                )
    if has_manifest:
        h = kb.horizon()
        out.info(
            MANIFEST_NAME,
            f"horizonte de fuentes: {h.isoformat()}" if h else "horizonte de fuentes: ningún chequeo limpio",
        )
    return out


def check_raw_refs(kb: KB) -> list[Finding]:
    """Cada RowRef/CellRef resuelve a exactamente una fila (y celda) de una revisión registrada."""
    out = _Out("refs_raw")
    raw = _Raw(kb.root)
    for s in _ref_sites(kb):
        if isinstance(s.ref, PageRef):
            if not _rev_registered(kb, s.ref.doc, s.ref.rev):
                out.error(s.where, f"{s.owner}: PageRef a {s.ref.doc}@{s.ref.rev}, revisión no registrada")
            continue
        if not s.ref.startswith("raw:"):
            continue  # CaseRef: lo verifica `casos`
        _row, err = raw.resolve(s.ref)
        try:
            p = parse_ref(s.ref)
        except ValueError:
            out.error(s.where, f"{s.owner}: {err}")
            continue
        doc, rev12 = str(p["doc"]), str(p["sha12"])
        if not _rev_registered(kb, doc, rev12):
            out.error(s.where, f"{s.owner}: {s.ref} cita una revisión no registrada en el manifiesto")
        if err is not None:
            out.error(s.where, f"{s.owner}: {s.ref} {err}")
        cur = kb.documents.get(doc)
        if (
            s.kind in ("version", "legal", "effect")
            and cur is not None
            and rev12 != sha12(cur.current_revision)
        ):
            out.warning(
                s.where,
                f"{s.owner}: {s.ref} cita la revisión {rev12}; la curada de {doc} es {sha12(cur.current_revision)}",
            )
    return out


def check_literals(kb: KB) -> list[Finding]:
    """Literales == celda de la fila citada; la fila es de la entidad (ID y tabla)."""
    out = _Out("literales")
    raw = _Raw(kb.root)
    for key, ent in sorted(kb.entities().items()):
        is_field = isinstance(ent, Field)
        attrs = FIELD_LITERALS if is_field else VALIDATION_LITERALS
        table = "fields" if is_field else "validations"
        w = _loc(kb, key)
        for v in ent.versions:
            label = _vlabel(v)
            refs = _row_refs(v.evidence)
            cited: list[tuple[RawRow, str, str | None]] = []
            for ref in refs:
                row, _err = raw.resolve(ref)
                if row is None:
                    continue  # lo informa refs_raw
                attr = parse_ref(ref)["attr"]
                rid = row.cells.get("id")
                if row.key != ent.id or (rid is not None and rid != ent.id):
                    out.error(w, f"{key} {label}: cita la fila {row.key} ({ref}), que no es de {ent.id}")
                    continue
                if row.table != table:
                    out.error(
                        w, f"{key} {label}: {ref} es una fila de la tabla «{row.table}», no de «{table}»"
                    )
                    continue
                cited.append((row, ref, str(attr) if attr else None))
            if not refs:
                if any(getattr(v, a) is not None for a in attrs):
                    out.error(
                        w, f"{key} {label}: ninguna fila de tabla citada: sus literales no son verificables"
                    )
                continue
            if not cited:
                continue
            if v.kind == "tombstone":
                code = getattr(v, "code", None)
                for row, ref, only in cited:
                    printed = row.cells.get("code")
                    if code and printed is not None and (only is None or only == "code") and printed != code:
                        out.error(
                            w, f"{key} {label}: la lápida conserva el código {code}; {ref} dice {printed!r}"
                        )
                continue
            pred = _based_on_version(ent, v)
            for a in attrs:
                value = getattr(v, a)
                cells = [
                    (c, ref)
                    for row, ref, only in cited
                    if (only is None or only == a) and (c := _cell(row, a)) is not None
                ]
                if cells:
                    if not any(_same_literal(value, c) for c, _ in cells):
                        c, ref = cells[0]
                        out.error(
                            w, f"{key} {label}: {a} ≠ celda {ref}#{a}: kb {_short(value)} / raw {_short(c)}"
                        )
                    elif len({c for c, _ in cells}) > 1:
                        out.warning(w, f"{key} {label}: las filas citadas discrepan en {a}")
                elif v.introduced_by == "baseline" or (pred is None and v.based_on == "baseline"):
                    if value is not None:
                        out.error(w, f"{key} {label}: {a} = {_short(value)} sin celda que lo respalde")
                elif pred is not None and value != getattr(pred, a):
                    out.error(
                        w,
                        f"{key} {label}: la fila citada no reproduce {a}: debe heredarse de based_on "
                        f"({_vlabel(pred)}: {_short(getattr(pred, a))}), no {_short(value)}",
                    )
    return out


def check_effect_targets(kb: KB) -> list[Finding]:
    """El destino de un efecto (aplicado o pending) es el ID de la fila citada, si la fila tiene ID."""
    out = _Out("destino_efecto")
    raw = _Raw(kb.root)
    for doc_id in sorted(kb.documents):
        w = _loc(kb, doc_id)
        for e in kb.documents[doc_id].effects:
            if e.target is None or e.disposition == "not_modeled":
                continue
            kind, _, tid = e.target.split(":", 2)
            table = "fields" if kind == "field" else "validations"
            for ref in _row_refs(e.evidence):
                row, _err = raw.resolve(ref)
                if row is None or row.table not in ("fields", "validations"):
                    continue
                rid = row.cells.get("id") or row.key
                if rid != tid or row.table != table:
                    out.error(
                        w,
                        f"{e.id}: destino {e.target}, pero {ref} es la fila {rid} de la tabla «{row.table}»",
                    )
    return out


def check_quotes(kb: KB) -> list[Finding]:
    """Citas de prosa: contenidas en la página normalizada; página impresa coherente con index.json."""
    out = _Out("citas")
    raw = _Raw(kb.root)
    for s in _ref_sites(kb):
        if not isinstance(s.ref, PageRef):
            continue
        pr = s.ref
        where = f"raw/{pr.doc}/{pr.rev}/pages/p{pr.page_pdf:03d}.txt"
        text = raw.page(pr.doc, pr.rev, pr.page_pdf)
        if text is None:
            out.error(s.where, f"{s.owner}: no existe {where}")
            continue
        q = normalize_text(pr.quote)
        if not q:
            out.error(s.where, f"{s.owner}: cita vacía")
        elif q not in text:
            out.error(s.where, f"{s.owner}: la cita {_short(pr.quote)} no está en {where}")
        if pr.page_printed is not None:
            idx = raw.index(pr.doc, pr.rev)
            if idx is not None and printed_page(idx, pr.page_pdf) != pr.page_printed:
                out.error(
                    s.where,
                    f"{s.owner}: page_printed {pr.page_printed} ≠ index.json "
                    f"({printed_page(idx, pr.page_pdf)}) para la página PDF {pr.page_pdf}",
                )
    return out


def check_date_cells(kb: KB) -> list[Finding]:
    """Fechas: literal == celda del encabezado correcto, del propio documento y su revisión curada."""
    out = _Out("fechas_celdas")
    raw = _Raw(kb.root)
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        w = _loc(kb, doc_id)
        for slot, ds in _date_slots(d):
            owner = f"{doc_id} {slot}"
            parsed = parse_date_literal(ds.literal)
            if parsed is not None and ds.value != parsed:
                out.error(w, f"{owner}: value {ds.value} ≠ parse({ds.literal!r}) = {parsed}")
            elif parsed is None and ds.value is not None:
                out.error(w, f"{owner}: {ds.literal!r} no es una fecha: value debe ser null")
            si = ds.stated_in
            if isinstance(si, PageRef):
                if normalize_text(ds.literal) not in normalize_text(si.quote):
                    out.error(w, f"{owner}: el literal {ds.literal!r} no está en la cita {_short(si.quote)}")
                continue
            p = parse_ref(si)
            attr = str(p["attr"])
            expected = _SLOT_ATTR.get(slot)
            if p["doc"] != doc_id:
                out.error(w, f"{owner}: {si} es una celda de {p['doc']}, no de {doc_id}")
            if p["sha12"] != sha12(d.current_revision):
                out.error(
                    w,
                    f"{owner}: {si} cita la revisión {p['sha12']}; current_revision es {sha12(d.current_revision)}",
                )
            if expected is not None and attr != expected:
                out.error(w, f"{owner}: la ranura exige la celda #{expected}; cita #{attr}")
            if expected is None and attr in ("test", "prod"):
                out.error(w, f"{owner}: un período de cambios no se toma de una fecha de vigencia (#{attr})")
            row, _err = raw.resolve(si)
            if row is None:
                continue
            if expected is not None:
                if row.table != "dates":
                    out.error(w, f"{owner}: {si} no es la tabla de fechas (tabla «{row.table}»)")
                elif attr in DATE_ATTRS:
                    i = DATE_ATTRS.index(attr)
                    header = normalize_text(row.header[i]).lower() if i < len(row.header) else ""
                    if not _DATE_HEADER[attr](header):
                        out.error(w, f"{owner}: el encabezado de la columna #{attr} es {header!r}")
            cell = _cell(row, attr)
            if cell is not None and normalize_text(ds.literal) != cell:
                out.error(w, f"{owner}: literal {ds.literal!r} ≠ celda {si} = {cell!r}")
    return out


def check_dsl(kb: KB) -> list[Finding]:
    """La condición se analiza, lee campos curados y sus constantes están en la observación."""
    out = _Out("dsl")
    for key, val in sorted(kb.validations.items()):
        w = _loc(kb, key)
        for v in val.versions:
            c = v.condition
            if c is None or not c.expr:
                continue
            label = f"{key} {_vlabel(v)}"
            try:
                node = dsl.parse(c.expr)
            except dsl.DslError as e:
                out.error(w, f"{label}: condición fuera del DSL: {e}")
                continue
            for name in sorted(dsl.fields(node)):
                if f"field:{val.context}:{name}" not in kb.fields:
                    out.error(
                        w,
                        f"{label}: la condición lee {name}, que no es un campo curado (field:{val.context}:{name})",
                    )
            obs = v.observation or ""
            for const in dsl.constants(node):
                if not dsl.literal_contains_constant(obs, const):
                    txt = const if isinstance(const, str) else format(const, "f")
                    out.error(w, f"{label}: la constante {txt!r} no aparece en la observación")
    return out


def check_enumerations(kb: KB) -> list[Finding]:
    """Etiquetas de enumeración contenidas en `observations`; códigos sin repetir."""
    out = _Out("enumeracion")
    for key, f in sorted(kb.fields.items()):
        w = _loc(kb, key)
        for v in f.versions:
            if not v.enumeration:
                continue
            label = f"{key} {_vlabel(v)}"
            obs = normalize_text(v.observations or "")
            dup = sorted(c for c, n in Counter(e.code for e in v.enumeration).items() if n > 1)
            if dup:
                out.error(w, f"{label}: códigos de enumeración repetidos: {', '.join(dup)}")
            for e in v.enumeration:
                lab = normalize_text(e.label)
                if not lab or lab not in obs:
                    out.error(w, f"{label}: la etiqueta {e.code}={e.label!r} no está en observations")
    return out


def check_coverage(kb: KB) -> list[Finding]:
    """Guardián de cobertura: toda mención del vocabulario curado en una NT está reconocida."""
    out = _Out("cobertura")
    ents = kb.entities()
    if not ents:
        return out
    vocab: dict[str, set[str]] = defaultdict(set)
    for key in sorted(ents):
        for t in key_terms(kb, key):
            vocab[t].add(key)
    patterns = {t: term_pattern(t) for t in sorted(vocab)}
    raw = _Raw(kb.root)

    def recognizes(doc: DocumentSource, keys: set[str]) -> bool:
        return any(
            (e.target in keys) or (e.disposition == "pending" and e.target is None) for e in doc.effects
        )

    for doc_id in sorted({r.doc for r in kb.manifest.revisions if _NT_DOC.match(r.doc)}):
        latest = kb.latest_revision(doc_id)
        if latest is None:
            continue
        rev12 = sha12(latest.sha256)
        doc = kb.documents.get(doc_id)
        w = _loc(kb, doc_id) if doc is not None else f"raw/{doc_id}/{rev12}"
        pages = raw.pages(doc_id, rev12)
        if pages is None:
            out.warning(w, f"{doc_id}: la revisión {rev12} no tiene raw/: cobertura no comprobada")
            continue
        hits: dict[str, list[int]] = defaultdict(list)
        for n in pages:
            text = raw.page(doc_id, rev12, n) or ""
            for t, pat in patterns.items():
                if pat.search(text):
                    hits[t].append(n)
        if not hits:
            continue
        if doc is None:
            terms = ", ".join(f"{t} (p. {', '.join(map(str, hits[t]))})" for t in sorted(hits))
            out.error(w, f"{doc_id} menciona {terms} y no tiene ficha en kb/documents/: nada lo reconoce")
            continue
        for t in sorted(hits):
            keys = vocab[t]
            if not recognizes(doc, keys):
                pg = ", ".join(map(str, hits[t]))
                out.error(
                    w,
                    f"{doc_id} menciona {t} (p. {pg}) sin un efecto que lo reconozca (aplicado, pending o "
                    f"not_modeled con nota) sobre {' o '.join(sorted(keys))}",
                )
    # Oráculo: libro de cambios NT↔MT (deducción de herramienta; su acción por color no se usa).
    for line in iter_ledger(kb.root):
        doc_id, table, rid = line.get("nt"), line.get("table"), line.get("id")
        if not isinstance(doc_id, str) or table not in ("fields", "validations") or not isinstance(rid, str):
            continue
        key = f"{'field' if table == 'fields' else 'val'}:DE:{rid}"
        doc = kb.documents.get(doc_id)
        if key not in ents or doc is None:
            continue  # sin ficha: ya lo informa la búsqueda de menciones
        if not recognizes(doc, {key}):
            out.error(
                _loc(kb, doc_id),
                f"{doc_id}: el libro de cambios registra la fila {rid} ({line.get('nt_ref')}) y ningún efecto "
                f"de {doc_id} reconoce {key}",
            )
            continue
        nt_ref = line.get("nt_ref")
        targeting = [e for e in doc.effects if e.target == key]
        try:
            same_rev = isinstance(nt_ref, str) and parse_ref(nt_ref)["sha12"] == sha12(doc.current_revision)
        except ValueError:
            same_rev = False
        if isinstance(nt_ref, str) and targeting and same_rev:
            cited = {ref.split("#")[0] for e in targeting for ref in _row_refs(e.evidence)}
            if nt_ref not in cited:
                out.warning(
                    _loc(kb, doc_id),
                    f"{doc_id}: ningún efecto sobre {key} cita la fila del libro de cambios {nt_ref}",
                )
    return out


def check_bijection(kb: KB) -> list[Finding]:
    """Efecto aplicado ↔ exactamente una versión de su destino; pending/not_modeled en ninguna."""
    out = _Out("biyeccion")
    cited: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, ent in sorted(kb.entities().items()):
        for v in ent.versions:
            if isinstance(v.introduced_by, list):
                dup = sorted(e for e, n in Counter(v.introduced_by).items() if n > 1)
                if dup:
                    out.error(_loc(kb, key), f"{key} {_vlabel(v)}: introduced_by repite {', '.join(dup)}")
                for e in dict.fromkeys(v.introduced_by):
                    cited[e].append((key, _vlabel(v)))
    for doc_id in sorted(kb.documents):
        w = _loc(kb, doc_id)
        for e in kb.documents[doc_id].effects:
            sites = cited.get(e.id, [])
            if e.disposition is None:
                if not sites:
                    out.error(
                        w, f"{e.id}: efecto aplicado sin versión que lo cite (¿falta `sifen draft {e.id}`?)"
                    )
                elif len(sites) > 1:
                    out.error(
                        w,
                        f"{e.id}: lo citan {len(sites)} versiones: {', '.join(f'{k} {lb}' for k, lb in sites)}",
                    )
                elif sites[0][0] != e.target:
                    out.error(
                        w, f"{e.id}: lo cita una versión de {sites[0][0]}, pero su destino es {e.target}"
                    )
            elif sites:
                out.error(
                    w,
                    f"{e.id}: un efecto {e.disposition} no introduce versiones; lo cita {sites[0][0]} {sites[0][1]}",
                )
    for key, ent in sorted(kb.entities().items()):
        for v in ent.versions:
            effs = _effects_of(kb, v)
            if not effs or len(effs) < 2:
                continue
            for env in ENVS:
                try:
                    starts = {e.id: effect_start(kb, e.id, env) for e in effs}
                except TemporalDataError as err:
                    out.error(_loc(kb, key), f"{key} {_vlabel(v)} ({env}): {err}")
                    continue
                if len(set(starts.values())) > 1:
                    det = ", ".join(f"{e}={s[0] or 'sin fecha'}" for e, s in starts.items())
                    out.error(
                        _loc(kb, key),
                        f"{key} {_vlabel(v)} ({env}): sus efectos tienen inicios distintos ({det})",
                    )
    return out


def check_actions(kb: KB) -> list[Finding]:
    """Acción de los efectos coherente con el tipo de versión (lápida, alta, reintroducción)."""
    out = _Out("acciones")
    for key, ent in sorted(kb.entities().items()):
        w = _loc(kb, key)
        has_baseline = any(v.introduced_by == "baseline" for v in ent.versions)
        for v in ent.versions:
            effs = _effects_of(kb, v)
            if not effs:
                continue
            label = f"{key} {_vlabel(v)}"
            actions = {e.action for e in effs}
            pred = _based_on_version(ent, v)
            if v.kind == "tombstone":
                if actions != {"remove"}:
                    out.error(
                        w, f"{label}: una lápida la introducen efectos remove (acciones: {sorted(actions)})"
                    )
                continue
            if "remove" in actions:
                out.error(w, f"{label}: un efecto remove produce una lápida (kind: tombstone)")
            if pred is None and v.based_on == "baseline" and not has_baseline and actions != {"add"}:
                out.error(w, f"{label}: la primera versión de una entidad sin línea base exige action add")
            if pred is not None and pred.kind == "tombstone":
                if "add" not in actions:
                    out.error(w, f"{label}: reintroducción tras una lápida: exige action add")
                if not any(s.subject == key for i in kb.issues.values() for s in i.affects):
                    out.error(w, f"{label}: reintroducción tras una lápida: exige un Issue que la justifique")
            elif pred is not None and "add" in actions:
                out.warning(w, f"{label}: action add sobre una entidad que ya existe (¿modify?)")
    return out


def check_unique_starts(kb: KB) -> list[Finding]:
    """Dos versiones distintas de una entidad no empiezan el mismo día en un ambiente."""
    out = _Out("inicio_unico")
    for key, ent in sorted(kb.entities().items()):
        if _has_dangling(kb, ent):
            continue  # lo informa referencias
        for env in ENVS:
            dated, _, errs = _placed(kb, ent, env)
            if errs:
                continue  # inicios distintos dentro de una versión: lo informa biyeccion
            by_day: dict[date, list[int]] = defaultdict(list)
            for d, i in dated:
                by_day[d].append(i)
            dups = {d: idx for d, idx in by_day.items() if len(idx) > 1}
            for d, idx in sorted(dups.items()):
                labels = " y ".join(_vlabel(ent.versions[i]) for i in idx)
                out.error(
                    _loc(kb, key),
                    f"{key} ({env}): dos versiones distintas empiezan en {_day(d)}: {labels}. Si comparten "
                    "inicio deben ser UNA versión con introduced_by: [ambos efectos] (G.3)",
                )
            if not dups:
                try:
                    timeline(kb, key, env)
                except TemporalDataError as e:
                    out.error(_loc(kb, key), str(e))
    return out


def check_predecessor(kb: KB) -> list[Finding]:
    """`based_on` es la predecesora TEMPORAL en producción (no la anterior en el archivo)."""
    out = _Out("predecesora")
    for key, ent in sorted(kb.entities().items()):
        if _has_dangling(kb, ent):
            continue
        for v in ent.versions:
            if v.introduced_by == "baseline":
                continue
            ok, expected = _temporal_predecessor(kb, ent, v)
            if not ok:
                break  # inicios inválidos: lo informan inicio_unico/biyeccion
            if _intro_id(v.based_on) != _intro_id(expected):
                out.error(
                    _loc(kb, key),
                    f"{key} {_vlabel(v)}: based_on {_clabel(v.based_on)} no es la predecesora temporal en "
                    f"producción ({_clabel(expected)}): re-materializa lo heredado con `sifen draft`",
                )
    return out


def _version_fields(is_field: bool) -> set[str]:
    model = FieldVersion if is_field else ValidationVersion
    return set(model.model_fields) - NON_CONTENT


def check_scope(kb: KB) -> list[Finding]:
    """diff(versión, based_on) ⊆ alcance declarado (+ acknowledged_changes con `row`)."""
    out = _Out("alcance")
    for key, ent in sorted(kb.entities().items()):
        is_field = isinstance(ent, Field)
        cols = set(FIELD_LITERALS if is_field else VALIDATION_LITERALS)
        obs = "observations" if is_field else "observation"
        names = _version_fields(is_field)
        w = _loc(kb, key)
        for v in ent.versions:
            effs = _effects_of(kb, v)
            if not effs:
                continue
            label = f"{key} {_vlabel(v)}"
            for e in effs:
                listed = e.declared_scope if isinstance(e.declared_scope, list) else []
                bad = sorted({n for n in [*listed, *e.acknowledged_changes] if n not in names})
                if bad:
                    out.error(
                        _loc(kb, kb.doc_of(e.id).id),
                        f"{e.id}: alcance con atributos desconocidos: {', '.join(bad)}",
                    )
                if isinstance(e.declared_scope, list) and e.acknowledged_changes:
                    out.warning(
                        _loc(kb, kb.doc_of(e.id).id),
                        f"{e.id}: acknowledged_changes solo cuenta con alcance row",
                    )
            pred = _based_on_version(ent, v)
            if pred is None:
                continue
            changed = diff_versions(pred, v)
            if v.kind == "tombstone":
                if changed:
                    out.error(
                        w,
                        f"{label}: una lápida copia la predecesora ({_vlabel(pred)}); cambia: {', '.join(changed)}",
                    )
                continue
            allowed: set[str] = set()
            ack: set[str] = set()
            for e in effs:
                if e.declared_scope == "row":
                    ack |= set(e.acknowledged_changes)
                    allowed |= (names - cols) | {obs} | set(e.acknowledged_changes)
                else:
                    allowed |= set(e.declared_scope)
                    allowed |= {i for i, lit in INTERPRETED_OF.items() if lit in e.declared_scope}
            bad = [a for a in changed if a not in allowed]
            if bad:
                scope = " + ".join(
                    "row" if e.declared_scope == "row" else "[" + ", ".join(e.declared_scope) + "]"
                    for e in effs
                )
                hint = (
                    " (con alcance row, toda columna cambiada salvo la observación va en acknowledged_changes)"
                    if any(e.declared_scope == "row" for e in effs)
                    else ""
                )
                out.error(w, f"{label}: cambia {', '.join(bad)} fuera del alcance declarado {scope}{hint}")
            unused = sorted(a for a in ack if a not in changed)
            if unused:
                out.warning(w, f"{label}: acknowledged_changes lista {', '.join(unused)}, que no cambia(n)")
    return out


def check_interpreted(kb: KB) -> list[Finding]:
    """Un atributo interpretado solo cambia si cambió su literal (anti-R3)."""
    out = _Out("interpretado")
    for key, ent in sorted(kb.entities().items()):
        for v in ent.versions:
            if v.introduced_by == "baseline" or v.kind == "tombstone":
                continue
            pred = _based_on_version(ent, v)
            if pred is None:
                continue
            changed = set(diff_versions(pred, v))
            for attr, lit in INTERPRETED_OF.items():
                if attr in changed and lit not in changed:
                    out.error(
                        _loc(kb, key),
                        f"{key} {_vlabel(v)}: cambia {attr} sin que cambie su literal {lit} (respecto de {_vlabel(pred)})",
                    )
    return out


def check_env_inversion(kb: KB) -> list[Finding]:
    """Orden invertido entre ambientes ⇒ Issue temporal bloqueante en test sobre la ventana."""
    out = _Out("inversion_ambientes")
    for key, ent in sorted(kb.entities().items()):
        if _has_dangling(kb, ent):
            continue
        starts: dict[str, dict[int, date]] = {}
        broken = False
        for env in ENVS:
            dated, _, errs = _placed(kb, ent, env)
            broken = broken or bool(errs)
            starts[env] = {i: d for d, i in dated}
        if broken:
            continue
        common = sorted(
            i for i in starts["prod"] if i in starts["test"] and ent.versions[i].introduced_by != "baseline"
        )
        for a, b in combinations(common, 2):
            pa, pb, ta, tb = starts["prod"][a], starts["prod"][b], starts["test"][a], starts["test"][b]
            if pa == pb or ta == tb or (pa < pb) == (ta < tb):
                continue
            first, second = (a, b) if pa < pb else (b, a)
            since, until = starts["test"][second], starts["test"][first]
            subjects = _subjects(kb, key, [ent.versions[a], ent.versions[b]])
            ok = any(
                i.kind == "temporal"
                and i.status == "open"
                and i.blocking
                and any(
                    s.subject in subjects
                    and s.env in (None, "test")
                    and (s.since is None or s.since <= since)
                    and (s.until is None or s.until >= until)
                    for s in i.affects
                )
                for i in kb.issues.values()
            )
            if not ok:
                out.error(
                    _loc(kb, key),
                    f"{key}: en producción {_vlabel(ent.versions[first])} precede a {_vlabel(ent.versions[second])} "
                    f"y en test al revés: exige un Issue temporal bloqueante en test sobre [{since}, {until})",
                )
    return out


def check_approx_starts(kb: KB) -> list[Finding]:
    """Supuesto A1: un documento sin calendario empieza (aproximadamente) antes de `coverage_from`."""
    out = _Out("inicio_aproximado")
    if kb.meta is None:
        return out
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        if d.schedule is not None or not d.effects:
            continue
        anchor = d.document_date.value if d.document_date and d.document_date.value else PRE_COVERAGE
        if anchor >= kb.meta.coverage_from:
            out.error(
                _loc(kb, doc_id),
                f"{doc_id}: sin calendario, su inicio aproximado ({anchor}) no es anterior a coverage_from "
                f"({kb.meta.coverage_from}): contradice el supuesto A1",
            )
    return out


def _at(line: list[tuple[date, Version]], t: date) -> Version | None:
    cur = None
    for d, v in line:
        if d > t:
            break
        cur = v
    return cur


def check_temporal_integrity(kb: KB) -> list[Finding]:
    """En cada punto de cambio, toda validación vigente lee campos vigentes (§K.4)."""
    out = _Out("integridad_temporal")
    for env in ENVS:
        lines: dict[str, list[tuple[date, Version]]] = {}
        for key, ent in kb.entities().items():
            if _has_dangling(kb, ent):
                continue
            dated, _, errs = _placed(kb, ent, env)
            if not errs:
                lines[key] = [(d, ent.versions[i]) for d, i in dated]
        points = sorted({d for line in lines.values() for d, _ in line})
        reported: set[tuple[str, str]] = set()
        for t in points:
            for vkey in sorted(kb.validations):
                val = kb.validations[vkey]
                v = _at(lines.get(vkey, []), t)
                if v is None or v.kind == "tombstone" or not isinstance(v, ValidationVersion):
                    continue
                refs: set[str] = {val.subject_field} if val.subject_field else set()
                if v.condition is not None and v.condition.expr:
                    try:
                        refs |= {f"field:{val.context}:{n}" for n in dsl.fields(dsl.parse(v.condition.expr))}
                    except dsl.DslError:
                        pass
                for fkey in sorted(refs):
                    if fkey not in lines or (vkey, fkey) in reported:
                        continue
                    fv = _at(lines[fkey], t)
                    if fv is None or fv.kind == "tombstone":
                        reported.add((vkey, fkey))
                        state = "todavía no existe" if fv is None else "está eliminado"
                        out.error(
                            _loc(kb, vkey),
                            f"{vkey} {_vlabel(v)} rige en {env} desde {_day(t)} y lee {fkey}, que en esa fecha {state}",
                        )
    return out


def check_code_collisions(kb: KB) -> list[Finding]:
    """Un código usado por dos validaciones exige un Issue code_collision que las nombre a todas."""
    out = _Out("colisiones")
    for code, entries in sorted(kb.code_index().items()):
        keys = sorted({k for k, _ in entries})
        if len(keys) < 2:
            continue
        ok = any(
            i.kind == "code_collision" and set(keys) <= {s.subject for s in i.affects}
            for i in kb.issues.values()
        )
        if not ok:
            out.error(
                _loc(kb, keys[0]),
                f"el código {code} lo usan {', '.join(keys)} sin un Issue code_collision que las declare",
            )
    return out


def check_dates_sane(kb: KB) -> list[Finding]:
    """test ≤ prod; > 90 días entre document_date y test exige Issue erratum; ventanas de Issue."""
    out = _Out("fechas_sanas")
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        w = _loc(kb, doc_id)
        test = d.schedule.test.value if d.schedule and d.schedule.test else None
        prod = d.schedule.prod.value if d.schedule and d.schedule.prod else None
        if test and prod and test > prod:
            out.error(w, f"{doc_id}: test ({test}) posterior a producción ({prod}): ¿celdas intercambiadas?")
        dd = d.document_date.value if d.document_date else None
        ref = test or prod
        if dd and ref and abs((ref - dd).days) > ERRATUM_DAYS:
            ok = any(
                i.kind == "erratum" and any(s.subject == doc_id for s in i.affects)
                for i in kb.issues.values()
            )
            if not ok:
                out.error(
                    w,
                    f"{doc_id}: {abs((ref - dd).days)} días entre document_date ({dd}) y "
                    f"{'test' if test else 'producción'} ({ref}): exige un Issue erratum sobre {doc_id}",
                )
        if d.change_period is not None:
            a, b = d.change_period[0].value, d.change_period[1].value
            if a and b and a > b:
                out.error(w, f"{doc_id}: change_period invertido ({a} > {b})")
    for iid in sorted(kb.issues):
        for s in kb.issues[iid].affects:
            if s.since and s.until and s.since >= s.until:
                out.error(
                    _loc(kb, iid), f"{iid}: ventana vacía o invertida [{s.since}, {s.until}) en {s.subject}"
                )
    return out


def _corrects_problem(kb: KB, entry: str) -> str | None:
    """None si la entrada de `corrects` tiene un formato conocido y apunta a algo que existe."""
    if m := _CORR_VERSION.match(entry):
        ent = kb.entity(m["key"])
        if ent is None:
            return f"{m['key']} no existe"
        if not any(_clabel(v.introduced_by) == m["ver"] for v in ent.versions):
            # el orden de los efectos no importa
            want = _intro_id(m["ver"] if m["ver"] == "baseline" else m["ver"].split("+"))
            if not any(_intro_id(v.introduced_by) == want for v in ent.versions):
                return f"{m['key']} no tiene la versión {m['ver']}"
        model = FieldVersion if isinstance(ent, Field) else ValidationVersion
        return None if m["attr"] in model.model_fields else f"{m['attr']} no es un atributo de versión"
    if m := _CORR_ENTITY.match(entry):
        ent = kb.entity(m["key"])
        if ent is None:
            return f"{m['key']} no existe"
        return None if m["attr"] in type(ent).model_fields else f"{m['attr']} no es un atributo de {m['key']}"
    if m := _CORR_EFFECT.match(entry):
        if not kb.has_effect(m["eff"]):
            return f"el efecto {m['eff']} no existe"
        return None if m["attr"] in Effect.model_fields else f"{m['attr']} no es un atributo de efecto"
    if m := _CORR_DOC.match(entry):
        if m["doc"] not in kb.documents:
            return f"el documento {m['doc']} no existe"
        return (
            None
            if m["attr"] in DocumentSource.model_fields
            else f"{m['attr']} no es un atributo de documento"
        )
    return "formato desconocido (se espera p. ej. val:DE:D208c@NT_021#1.observation)"


def check_references(kb: KB) -> list[Finding]:
    """Referencias internas existentes (§K.4 test_references_exist)."""
    out = _Out("referencias")
    manifest_docs = {r.doc for r in kb.manifest.revisions}
    for key, ent in sorted(kb.entities().items()):
        w = _loc(kb, key)
        if isinstance(ent, Validation) and ent.subject_field and ent.subject_field not in kb.fields:
            out.error(w, f"{key}: subject_field {ent.subject_field} no es un campo curado")
        intros = [_intro_id(v.introduced_by) for v in ent.versions]
        for dup in sorted(
            {_clabel(v.introduced_by) for v in ent.versions if intros.count(_intro_id(v.introduced_by)) > 1}
        ):
            out.error(w, f"{key}: dos versiones con el mismo introduced_by ({dup})")
        for v in ent.versions:
            label = f"{key} {_vlabel(v)}"
            if isinstance(v.introduced_by, list):
                for e in v.introduced_by:
                    if not kb.has_effect(e):
                        out.error(w, f"{label}: introduced_by {e} no existe en kb/documents/")
            bo = v.based_on
            if isinstance(bo, list):
                for e in bo:
                    if not kb.has_effect(e):
                        out.error(w, f"{label}: based_on {e} no existe en kb/documents/")
                if _intro_id(bo) == _intro_id(v.introduced_by):
                    out.error(w, f"{label}: based_on apunta a la propia versión")
                elif _intro_id(bo) not in intros:
                    out.error(w, f"{label}: based_on {_clabel(bo)} no es ninguna versión de {key}")
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        w = _loc(kb, doc_id)
        for e in d.effects:
            if e.target is not None and kb.entity(e.target) is None:
                out.error(w, f"{e.id}: el destino {e.target} no es una entidad curada")
            if e.from_revision and not _rev_registered(kb, doc_id, e.from_revision):
                out.error(w, f"{e.id}: from_revision {e.from_revision} no está en el manifiesto de {doc_id}")
        if d.superseded_by is not None:
            sd = d.superseded_by.doc
            if sd not in kb.documents and sd not in manifest_docs:
                out.error(w, f"{doc_id}: superseded_by apunta a {sd}, que no existe")
    for iid in sorted(kb.issues):
        iss = kb.issues[iid]
        w = _loc(kb, iid)
        for s in iss.affects:
            subj = s.subject
            if subj.startswith(("field:", "val:")):
                ok = kb.entity(subj) is not None
            elif "#" in subj:
                ok = kb.has_effect(subj)
            else:
                ok = subj in kb.documents or subj in manifest_docs
            if not ok:
                out.error(w, f"{iid}: el sujeto {subj} no existe")
        for c in iss.corrects:
            problem = _corrects_problem(kb, c)
            if problem:
                out.error(w, f"{iid}: corrects {c!r}: {problem}")
        if iss.corrects and iss.kind not in CORRECTING_KINDS:
            out.warning(
                w,
                f"{iid}: corrects solo justifica cambios al pasado en Issues curation_error|erratum|temporal",
            )
    return out


def check_supersession(kb: KB) -> list[Finding]:
    """Oráculo de `superseded_by`: lo introducido por el documento termina en producción en `since`."""
    out = _Out("reemplazo")
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        if d.superseded_by is None:
            continue
        own = {e.id for e in d.effects}
        since = d.superseded_by.since
        for key, ent in sorted(kb.entities().items()):
            if not any(
                isinstance(v.introduced_by, list) and own & set(v.introduced_by) for v in ent.versions
            ):
                continue
            try:
                tl = timeline(kb, key, "prod")
            except TemporalDataError:
                continue  # lo informa inicio_unico
            for t in tl:
                if isinstance(t.version.introduced_by, list) and own & set(t.version.introduced_by):
                    end = t.end.date if t.end is not None else None
                    if end != since:
                        out.error(
                            _loc(kb, doc_id),
                            f"{doc_id}: superseded_by.since = {since}, pero {key} {t.label} termina en producción "
                            f"{end or 'nunca (abierta)'}",
                        )
    return out


# --- Corridas LLM ----------------------------------------------------------------------------------
def _interpretation_sites(kb: KB) -> list[tuple[str, str, Interpretation]]:
    sites: list[tuple[str, str, Interpretation]] = []
    for doc_id in sorted(kb.documents):
        for e in kb.documents[doc_id].effects:
            sites.append((_loc(kb, doc_id), e.id, e.interpretation))
    for key, val in sorted(kb.validations.items()):
        for v in val.versions:
            if v.condition is not None:
                sites.append((_loc(kb, key), f"{key} {_vlabel(v)} condition", v.condition.interpretation))
    for key, f in sorted(kb.fields.items()):
        for v in f.versions:
            if v.enumeration_interpretation is not None:
                sites.append((_loc(kb, key), f"{key} {_vlabel(v)} enumeration", v.enumeration_interpretation))
    return sites


def _run_path(root: Path, run: str) -> Path:
    if run.endswith(".yaml") and "/" in run:
        return root / run
    return root / RUNS_DIR / f"{run}.yaml"


def _load_run(path: Path) -> CurationRun | str:
    if not path.is_file():
        return "no existe"
    try:
        return CurationRun.model_validate(load_kb_text(_read_text_exact(path), source=str(path)))
    except (KBYamlError, ValidationError, UnicodeDecodeError) as e:
        return f"inválida: {e}"


def check_llm_runs(kb: KB, base: BaseSnapshot | str | None = None) -> list[Finding]:
    """Corridas de curación (§J, `test_llm_runs_cover_outputs`).

    Siempre: `by: llm` ⇒ `curation/runs/<run>.yaml` existe y lista el archivo en `outputs`. Con la base
    de `main`: una interpretación `by: llm` NUEVA cita una corrida de ESTE cambio (agregada o
    modificada respecto de la base), y un archivo que una corrida de este cambio editó no estrena una
    interpretación `by: human`.
    """
    out = _Out("corridas_llm")
    sites = _interpretation_sites(kb)
    cache: dict[Path, CurationRun | str] = {}

    def rel_of(p: Path) -> str:
        return p.relative_to(kb.root).as_posix() if p.is_relative_to(kb.root) else str(p)

    for rel, owner, it in sites:
        if it.by != "llm" or not it.run:
            continue
        p = _run_path(kb.root, it.run)
        run = cache.setdefault(p, _load_run(p))
        if isinstance(run, str):
            out.error(rel, f"{owner}: la corrida {rel_of(p)} {run}")
        elif rel not in {o.path for o in run.outputs}:
            out.error(rel, f"{owner}: la corrida {rel_of(p)} no lista {rel} entre sus outputs")
    runs_dir = kb.root / RUNS_DIR
    run_files = sorted(runs_dir.glob("*.yaml")) if runs_dir.is_dir() else []
    relevant = any(it.by == "llm" for _, _, it in sites) or (
        run_files and any(it.by == "human" for _, _, it in sites)
    )
    if not relevant:
        return out
    if base is None:
        base = load_base(kb.root)
    if isinstance(base, str):
        out.info("kb", f"corridas de este cambio e interpretaciones nuevas: no comprobado ({base})")
        return out
    changed_runs: set[str] = set()
    touched: set[str] = set()
    for p in run_files:
        rel = rel_of(p)
        try:
            text = _read_text_exact(p)
        except OSError, UnicodeDecodeError:
            continue
        if base.runs.get(rel) == text:
            continue  # corrida de un cambio anterior
        changed_runs.add(rel)
        run = cache.setdefault(p, _load_run(p))
        if not isinstance(run, str):
            touched |= {o.path for o in run.outputs}
    previous = Counter((rel, it.model_dump_json()) for rel, _, it in _interpretation_sites(base.kb))
    for rel, owner, it in sites:
        k = (rel, it.model_dump_json())
        if previous[k] > 0:
            previous[k] -= 1
            continue  # ya estaba en la base: no es nueva
        if it.by == "llm" and it.run:
            run_rel = rel_of(_run_path(kb.root, it.run))
            if run_rel not in changed_runs and isinstance(cache.get(_run_path(kb.root, it.run)), CurationRun):
                out.error(
                    rel, f"{owner}: interpretación nueva con la corrida {run_rel}, que no es de este cambio"
                )
        elif it.by == "human" and rel in touched:
            out.error(
                rel, f"{owner}: interpretación nueva by: human en un archivo editado por una sesión de Claude"
            )
    return out


# --- Base de main (pasado justificado) -------------------------------------------------------------
@dataclass
class BaseSnapshot:
    """KB de la base de `main` (ancestro común con HEAD) leída con `git show`."""

    ref: str
    commit: str
    kb: KB
    golden: list[Any] | None = None
    runs: dict[str, str] = field(default_factory=dict)
    """`curation/runs/*.yaml` de la base (ruta -> texto): distingue las corridas de este cambio."""
    notes: list[str] = field(default_factory=list)


def _git(root: Path, *args: str) -> str | None:
    try:
        cp = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60, check=False)
    except OSError, subprocess.SubprocessError:
        return None
    # Bytes sin traducir finales de línea: el texto de la base se compara byte a byte con el disco.
    return cp.stdout.decode("utf-8", "replace") if cp.returncode == 0 else None


_BASE_LAYOUT: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^kb/_meta\.yaml$"), "meta"),
    (re.compile(r"^kb/documents/[^/]+\.yaml$"), "document"),
    (re.compile(r"^kb/fields/[^/]+/[^/]+\.yaml$"), "field"),
    (re.compile(r"^kb/validations/[^/]+/[^/]+\.yaml$"), "validation"),
    (re.compile(r"^kb/issues/[^/]+\.yaml$"), "issue"),
)


def load_base(root: Path, refs: tuple[str, ...] | None = None) -> BaseSnapshot | str:
    """Base de comparación o el motivo por el que no la hay (sin git, sin `main`)."""
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        return "sin repositorio git"
    env_ref = os.environ.get(BASE_REF_ENV)
    candidates = [r for r in (env_ref, *(refs or DEFAULT_BASE_REFS)) if r and not r.startswith("-")]
    ref = commit = None
    for cand in candidates:
        out = _git(root, "rev-parse", "--verify", "--quiet", f"{cand}^{{commit}}")
        if out and out.strip():
            ref, commit = cand, out.strip()
            break
    if ref is None or commit is None:
        return f"no existe la rama {' ni '.join(candidates)}"
    mb = _git(root, "merge-base", commit, "HEAD")
    base_commit = mb.strip() if mb and mb.strip() else commit
    listing = _git(
        root, "ls-tree", "-r", "--name-only", base_commit, "--", "kb", MANIFEST_NAME, GOLDEN_PATH, RUNS_DIR
    )
    if listing is None:
        return f"no se pudo listar {ref}"
    kb = KB(root=root)
    snap = BaseSnapshot(ref=ref, commit=base_commit, kb=kb)
    for rel in sorted(x for x in listing.splitlines() if x):
        text = _git(root, "show", f"{base_commit}:./{rel}")
        if text is None:
            snap.notes.append(f"{rel}: no se pudo leer de {ref}")
            continue
        if rel.startswith(RUNS_DIR + "/"):
            snap.runs[rel] = text
            continue
        try:
            data = load_kb_text(text, source=f"{ref}:{rel}")
            if rel == MANIFEST_NAME:
                kb.manifest = SourcesManifest.model_validate(data or {})
            elif rel == GOLDEN_PATH:
                snap.golden = data if isinstance(data, list) else []
            else:
                _add_base_file(kb, root, rel, data)
        except (KBYamlError, ValidationError) as e:
            snap.notes.append(f"{rel}: inválido en {ref}: {e}")
    kb.reindex()
    return snap


def _add_base_file(kb: KB, root: Path, rel: str, data: Any) -> None:
    kind = next((k for pat, k in _BASE_LAYOUT if pat.match(rel)), None)
    path = root / rel
    if kind == "meta":
        kb.meta = KBMeta.model_validate(data)
    elif kind == "document":
        d = DocumentSource.model_validate(data)
        kb.documents[d.id] = d
        kb.paths[d.id] = path
    elif kind == "field":
        f = Field.model_validate(data)
        kb.fields[f.key] = f
        kb.paths[f.key] = path
    elif kind == "validation":
        v = Validation.model_validate(data)
        kb.validations[v.key] = v
        kb.paths[v.key] = path
    elif kind == "issue":
        i = Issue.model_validate(data)
        kb.issues[i.id] = i
        kb.paths[i.id] = path


def _load_golden(root: Path) -> list[Any] | None:
    p = root / GOLDEN_PATH
    if not p.is_file():
        return None
    try:
        data = load_kb_text(_read_text_exact(p), source=GOLDEN_PATH)
    except KBYamlError, UnicodeDecodeError:
        return None
    return data if isinstance(data, list) else []


def _new_corrections(kb: KB, base: KB) -> dict[str, list[str]]:
    """Entradas de `corrects` que este cambio incorpora en Issues curation_error|erratum|temporal."""
    out: dict[str, list[str]] = defaultdict(list)
    for iid in sorted(kb.issues):
        iss = kb.issues[iid]
        if iss.kind not in CORRECTING_KINDS:
            continue
        old = base.issues.get(iid)
        before = set(old.corrects) if old is not None else set()
        for c in iss.corrects:
            if c not in before:
                out[c].append(iid)
    return out


def _changed_issues_on(kb: KB, base: KB, subject: str) -> list[str]:
    """Issues curation_error|erratum|temporal nuevos o modificados en este cambio con ese sujeto."""
    return [
        iid
        for iid, iss in sorted(kb.issues.items())
        if iss.kind in CORRECTING_KINDS
        and base.issues.get(iid) != iss
        and any(s.subject == subject for s in iss.affects)
    ]


def _reproduced_attrs(kb: KB, v: Version) -> set[str]:
    raw = _Raw(kb.root)
    out: set[str] = set()
    for ref in _row_refs(v.evidence):
        row, _ = raw.resolve(ref)
        attr = parse_ref(ref)["attr"]
        if row is not None:
            out |= {str(attr)} if attr else set(row.cells)
    return out


def _golden_id(row: Any) -> str:
    if isinstance(row, dict) and isinstance(row.get("id"), str):
        return row["id"]
    body = {k: v for k, v in row.items() if k != "expect"} if isinstance(row, dict) else row
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


def check_past_changes(kb: KB, base: BaseSnapshot | str | None = None) -> list[Finding]:
    """Pasado justificado contra la base de `main` (ver el docstring del módulo)."""
    out = _Out("pasado")
    if base is None:
        base = load_base(kb.root)
    if isinstance(base, str):
        out.info("kb", f"pasado justificado: no comprobado ({base})")
        return out
    b = base.kb
    tag = f"{base.ref} ({base.commit[:12]})"
    for n in base.notes:
        out.warning(MANIFEST_NAME if n.startswith(MANIFEST_NAME) else "kb", f"base {tag}: {n}")
    for e in check_append_only(b.manifest, kb.manifest):
        out.error(MANIFEST_NAME, f"el manifiesto es append-only respecto de {tag}: {e}")
    if b.meta is not None and kb.meta is None and not (kb.root / "kb" / "_meta.yaml").exists():
        out.error("kb/_meta.yaml", f"kb/_meta.yaml se eliminó respecto de {tag}")
    elif b.meta is not None and kb.meta is not None and b.meta != kb.meta:
        out.warning(
            "kb/_meta.yaml",
            f"kb/_meta.yaml (protegido) cambió respecto de {tag}: cobertura, gracia, eje o supuestos alteran "
            "todas las respuestas; revisión humana obligatoria",
        )
    if not (b.documents or b.fields or b.validations or b.issues or base.golden):
        out.info("kb", f"la base {tag} no tiene kb/ ni golden: no hay pasado que comparar")
        return out
    fixes = _new_corrections(kb, b)

    def justified(entry: str) -> list[str]:
        ids = list(fixes.get(entry, []))
        for c, iids in fixes.items():
            if c.startswith(entry + "."):
                ids += iids
        return sorted(set(ids))

    def need(where: str, entry: str, what: str) -> None:
        ids = justified(entry)
        if ids:
            out.info(where, f"cambio al pasado {entry} justificado por {', '.join(ids)}")
        else:
            out.error(
                where,
                f"{what}: exige un Issue curation_error|erratum|temporal de este cambio con {entry!r} en corrects",
            )

    for key in sorted(b.entities()):
        bent = b.entity(key)
        ent = kb.entity(key)
        assert bent is not None
        if ent is None:
            out.error(
                _loc(b, key), f"{key} se eliminó (nunca se borra una entidad: una eliminación es una lápida)"
            )
            continue
        w = _loc(kb, key)
        if type(ent) is not type(bent):
            out.error(w, f"{key} cambió de tipo de entidad")
            continue
        for attr in ("context", "id", "subject_field"):
            if getattr(bent, attr, None) != getattr(ent, attr, None):
                need(w, f"{key}.{attr}", f"{key}: cambia {attr}")
        current = {_intro_id(v.introduced_by): v for v in ent.versions}
        for bv in bent.versions:
            label = _vlabel(bv)
            v = current.get(_intro_id(bv.introduced_by))
            if v is None:
                out.error(
                    w,
                    f"{key}: la versión {label} se eliminó o cambió su introduced_by (nunca se borra una versión; "
                    "una corrección del pasado exige un Issue curation_error)",
                )
                continue
            bd, cd = bv.model_dump(mode="json"), v.model_dump(mode="json")
            diffs = sorted(
                k for k in bd.keys() | cd.keys() if k != "introduced_by" and bd.get(k) != cd.get(k)
            )
            if not diffs:
                continue
            ok, expected = _temporal_predecessor(kb, ent, v)
            remat = "based_on" in diffs and ok and _intro_id(v.based_on) == _intro_id(expected)
            reproduced = _reproduced_attrs(kb, v) if remat else set()
            pred = _based_on_version(ent, v)
            for attr in diffs:
                entry = f"{key}@{label}.{attr}"
                if not justified(entry):
                    if attr == "based_on" and remat:
                        out.info(
                            w, f"{entry}: re-materialización (based_on = predecesora temporal), permitida"
                        )
                        continue
                    if (
                        remat
                        and attr not in NON_CONTENT
                        and attr not in reproduced
                        and pred is not None
                        and getattr(pred, attr, None) == getattr(v, attr, None)
                    ):
                        out.info(
                            w, f"{entry}: heredado de la nueva predecesora (re-materialización), permitido"
                        )
                        continue
                need(w, entry, f"{key} {label}: modifica {attr} de una versión existente")
    for doc_id in sorted(b.documents):
        bdoc = b.documents[doc_id]
        doc = kb.documents.get(doc_id)
        if doc is None:
            out.error(_loc(b, doc_id), f"el documento {doc_id} se eliminó")
            continue
        w = _loc(kb, doc_id)
        for attr in CALENDAR_ATTRS:
            old = getattr(bdoc, attr)
            new = getattr(doc, attr)
            if _dump(old) == _dump(new):
                continue
            if attr == "superseded_by" and old is None:
                out.info(w, f"{doc_id}: agrega superseded_by (oráculo de fin; no altera respuestas pasadas)")
                continue
            ids = sorted(set(justified(f"{doc_id}.{attr}")) | set(_changed_issues_on(kb, b, doc_id)))
            if ids:
                out.info(w, f"cambio al pasado {doc_id}.{attr} justificado por {', '.join(ids)}")
            else:
                out.error(
                    w,
                    f"{doc_id}: cambia {attr}: exige un Issue temporal|erratum|curation_error de este cambio "
                    f"sobre {doc_id} (prórroga: §G.3) o {doc_id}.{attr} en corrects",
                )
        current_effects = {e.id: e for e in doc.effects}
        for be in bdoc.effects:
            e = current_effects.get(be.id)
            if e is None:
                out.error(w, f"el efecto {be.id} se eliminó (nunca se borra un efecto)")
                continue
            if be.disposition == "pending":
                continue  # un pendiente es un marcador: su curación lo completa
            bd, cd = be.model_dump(mode="json"), e.model_dump(mode="json")
            for attr in sorted(k for k in bd.keys() | cd.keys() if bd.get(k) != cd.get(k)):
                need(w, f"{be.id}.{attr}", f"{be.id}: modifica {attr} de un efecto existente")
    for iid in sorted(set(b.issues) - set(kb.issues)):
        out.error(_loc(b, iid), f"el Issue {iid} se eliminó (se resuelve con status: resolved, no se borra)")
    if base.golden is not None:
        current = {_golden_id(r): r for r in (_load_golden(kb.root) or [])}
        for r in base.golden:
            gid = _golden_id(r)
            c = current.get(gid)
            if c is None:
                out.error(GOLDEN_PATH, f"fila golden eliminada o cambiada de identidad: {_short(gid)}")
            elif c != r:
                key = r.get("key") if isinstance(r, dict) else None
                ids = _changed_issues_on(kb, b, key) if isinstance(key, str) else []
                if ids:
                    out.info(
                        GOLDEN_PATH,
                        f"expectativa golden {_short(gid)} modificada, justificada por {', '.join(ids)}",
                    )
                else:
                    out.error(
                        GOLDEN_PATH,
                        f"expectativa golden {_short(gid)} modificada sin un Issue curation_error|erratum|temporal "
                        "de este cambio sobre su clave",
                    )
    if not any(f.severity in ("error", "info") for f in out):
        out.info("kb", f"sin cambios al pasado respecto de {tag}")
    return out


def _dump(x: Any) -> str | None:
    return None if x is None else json.dumps(_jsonable(x), sort_keys=True, ensure_ascii=False)


def _show(x: Any, n: int = 300) -> str:
    """Valor legible en el informe: JSON compacto, truncado."""
    t = json.dumps(_jsonable(x), ensure_ascii=False, sort_keys=True)
    return t if len(t) <= n else t[: n - 1] + "…"


def _full_diff(a: Version, b: Version) -> list[str]:
    da, db = a.model_dump(mode="json"), b.model_dump(mode="json")
    return sorted(k for k in da.keys() | db.keys() if da.get(k) != db.get(k))


def _jsonable(x: Any) -> Any:
    if hasattr(x, "model_dump"):
        return x.model_dump(mode="json")
    if isinstance(x, tuple | list):
        return [_jsonable(i) for i in x]
    return x


# --- Casos sanitizados -----------------------------------------------------------------------------
_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n(.*))?\Z", re.DOTALL)
_CDC = re.compile(r"(?<!\d)\d{44}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RUC = re.compile(r"RUC\D{0,15}?(\d{5,8}(?:-\d)?)\b", re.IGNORECASE)


def _strings(x: Any) -> Iterator[str]:
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def _pii_allowlist(root: Path) -> set[str]:
    p = root / PII_ALLOWLIST
    if not p.is_file():
        return set()
    try:
        return set(_strings(load_kb_text(_read_text_exact(p), source=PII_ALLOWLIST)))
    except KBYamlError, UnicodeDecodeError:
        return set()


def _pii_hits(text: str, names: frozenset[str], allow: set[str]) -> list[str]:
    hits: list[str] = []
    for name in sorted(names):
        for pat in (
            rf"<(?:\w+:)?{name}\b[^>]*>\s*([^<]*?)\s*</",
            rf"(?<![\w<]){name}\b\s*[:=]\s*[\"']?([^\"'\s<>,;]+)",
        ):
            for m in re.finditer(pat, text):
                val = m.group(1).strip()
                if val and "*" not in val and val not in allow:
                    hits.append(f"valor de {name} sin sanitizar: {_short(val, 40)}")
    for pat, what in ((_CDC, "posible CDC real"), (_EMAIL, "posible correo"), (_RUC, "posible RUC")):
        for m in pat.finditer(text):
            val = m.group(1) if pat is _RUC else m.group(0)
            if val not in allow:
                hits.append(f"{what}: {_short(val, 50)}")
    return sorted(set(hits))


def check_cases(kb: KB) -> list[Finding]:
    """Casos: frontmatter `Case`, origen observado, referencias existentes y PII por elemento (§M)."""
    out = _Out("casos")
    cdir = kb.root / "cases"
    ids: dict[str, str] = {}
    if cdir.is_dir():
        from sifen_kb.xsd import PII_ELEMENTS  # import diferido: xmlschema solo si hay casos

        allow = _pii_allowlist(kb.root)
        for p in sorted(cdir.rglob("*.md")):
            rel = p.relative_to(kb.root).as_posix()
            try:
                text = _read_text_exact(p)
            except (OSError, UnicodeDecodeError) as e:
                out.error(rel, f"no se puede leer: {e}")
                continue
            m = _FRONTMATTER.match(text)
            if m is None:
                out.error(rel, "falta el frontmatter YAML (--- … ---)")
                continue
            try:
                case = Case.model_validate(load_kb_text(m.group(1), source=rel))
            except (KBYamlError, ValidationError) as e:
                out.error(rel, f"frontmatter inválido: {e}")
                continue
            if case.origin != "observed":
                out.error(rel, "un caso sintético vive en tests/fixtures/cases/, nunca en cases/")
            if case.id in ids:
                out.error(rel, f"id de caso {case.id} repetido (también en {ids[case.id]})")
            ids.setdefault(case.id, rel)
            if p.stem != case.id:
                out.warning(rel, f"el archivo debería llamarse {case.id}.md")
            for ent in case.entities:
                if kb.entity(ent) is None:
                    out.error(rel, f"la entidad {ent} no existe")
            if case.contradicts_kb and case.contradicts_kb not in kb.issues:
                out.error(rel, f"contradicts_kb {case.contradicts_kb} no existe")
            for h in _pii_hits(text, PII_ELEMENTS, allow):
                out.error(rel, h)
    for iid in sorted(kb.issues):
        for ev in kb.issues[iid].evidence:
            if isinstance(ev, str) and ev.startswith("case:") and ev[len("case:") :] not in ids:
                out.error(_loc(kb, iid), f"{iid}: {ev} no es un caso de cases/")
    return out


# --- Orquestación ----------------------------------------------------------------------------------
CheckFn = Callable[[KB], list[Finding]]
CHECKS: tuple[tuple[str, CheckFn], ...] = (
    ("carga", check_load),
    ("archivos", check_files),
    ("formato", check_format),
    ("fuentes", check_sources),
    ("refs_raw", check_raw_refs),
    ("literales", check_literals),
    ("destino_efecto", check_effect_targets),
    ("citas", check_quotes),
    ("fechas_celdas", check_date_cells),
    ("dsl", check_dsl),
    ("enumeracion", check_enumerations),
    ("cobertura", check_coverage),
    ("biyeccion", check_bijection),
    ("acciones", check_actions),
    ("inicio_unico", check_unique_starts),
    ("predecesora", check_predecessor),
    ("alcance", check_scope),
    ("interpretado", check_interpreted),
    ("inversion_ambientes", check_env_inversion),
    ("inicio_aproximado", check_approx_starts),
    ("integridad_temporal", check_temporal_integrity),
    ("colisiones", check_code_collisions),
    ("fechas_sanas", check_dates_sane),
    ("referencias", check_references),
    ("reemplazo", check_supersession),
    ("corridas_llm", check_llm_runs),
    ("pasado", check_past_changes),
    ("casos", check_cases),
)
"""Comprobaciones en orden de ejecución (y de salida)."""
_NEEDS_BASE = frozenset({"corridas_llm", "pasado"})


def run_checks(
    kb: KB, *, base: BaseSnapshot | str | None = None, only: set[str] | None = None
) -> list[Finding]:
    """Corre todas las comprobaciones (o `only`); un fallo interno es un hallazgo, nunca un aborto."""
    if base is None and (only is None or only & _NEEDS_BASE):
        base = load_base(kb.root)
    out: list[Finding] = []
    for name, fn in CHECKS:
        if only is not None and name not in only:
            continue
        try:
            res = fn(kb, base=base) if name in _NEEDS_BASE else fn(kb)  # type: ignore[call-arg]
        except Exception as e:  # noqa: BLE001 - una comprobación rota no oculta las demás
            res = [Finding(name, "-", f"fallo interno de la comprobación: {type(e).__name__}: {e}")]
        out.extend(res)
    return out


_SEV_TXT = {"error": "ERROR", "warning": "AVISO", "info": "INFO"}


def _counts(findings: list[Finding]) -> dict[str, int]:
    c = Counter(f.severity for f in findings)
    return {s: c.get(s, 0) for s in ("error", "warning", "info")}


def render_text(findings: list[Finding], root: Path) -> str:
    lines = [f"sifen check: {len(CHECKS)} comprobaciones sobre {root}"]
    for name, _ in CHECKS:
        group = [f for f in findings if f.check == name]
        if not group:
            continue
        c = _counts(group)
        parts = [f"{c['error']} error(es)"] if c["error"] else []
        parts += [f"{c['warning']} aviso(s)"] if c["warning"] else []
        parts += [f"{c['info']} info"] if c["info"] else []
        lines.append(f"[{name}] {', '.join(parts)}")
        for f in group:
            msg = f.message.replace("\n", "\n" + " " * 9)
            lines.append(f"  {_SEV_TXT[f.severity]:<6} {f.where}: {msg}")
    c = _counts(findings)
    verdict = "FALLA" if c["error"] else "OK"
    lines.append(
        f"Resumen: {c['error']} error(es), {c['warning']} aviso(s), {c['info']} informativo(s) → {verdict}"
    )
    return "\n".join(lines)


def render_json(findings: list[Finding]) -> str:
    c = _counts(findings)
    payload = {
        "ok": c["error"] == 0,
        "counts": c,
        "checks": [n for n, _ in CHECKS],
        "findings": [f.as_dict() for f in findings],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --- Informe de revisión del PR (§D.3 paso 7) ------------------------------------------------------
def render_report(kb: KB, base: BaseSnapshot | str | None, findings: list[Finding]) -> str:
    """Informe Markdown para el revisor: por entidad, versiones nuevas o modificadas con su diff y sus
    fechas por ambiente; calendarios; Issues nuevos; cambios al pasado; pendientes."""
    b = base.kb if isinstance(base, BaseSnapshot) else KB(root=kb.root)
    head = (
        f"base {base.ref} ({base.commit[:12]})"
        if isinstance(base, BaseSnapshot)
        else f"sin base ({base or 'no comprobada'}): todo se muestra como nuevo"
    )
    lines = [f"# Informe de revisión de la KB — {head}", ""]
    lines.append("## Entidades")
    any_ent = False
    for key, ent in sorted(kb.entities().items()):
        bent = b.entity(key)
        bvers = {_intro_id(v.introduced_by): v for v in bent.versions} if bent else {}
        changed = [v for v in ent.versions if bvers.get(_intro_id(v.introduced_by)) != v]
        if not changed:
            continue
        any_ent = True
        lines.append(f"### {key} ({_loc(kb, key)}){' — nueva' if bent is None else ''}")
        for v in changed:
            old = bvers.get(_intro_id(v.introduced_by))
            state = "modificada (cambio al pasado)" if old is not None else "nueva"
            starts = []
            for env in ENVS:
                try:
                    d, basis = version_start(kb, v, env)
                    starts.append(
                        f"{env} {'línea base' if basis == 'baseline' else d or 'sin fecha'} ({basis})"
                    )
                except TemporalDataError as e:
                    starts.append(f"{env} error: {e}")
            lines.append(
                f"- Versión {_vlabel(v)} · {v.kind} · {state} · based_on {_clabel(v.based_on)} · "
                + " · ".join(starts)
            )
            if old is not None:
                pred, changed, vs = old, _full_diff(old, v), "antes"
            else:
                pred = _based_on_version(ent, v)
                changed, vs = (diff_versions(pred, v), f"based_on {_vlabel(pred)}") if pred else ([], "")
            if pred is not None:
                lines.append(f"  - diff contra {vs}: {', '.join(changed) or 'sin cambios de contenido'}")
                for attr in changed:
                    lines.append(
                        f"    - {attr}: {_show(getattr(pred, attr, None))} → {_show(getattr(v, attr, None))}"
                    )
            if v.open_questions:
                lines.append(f"  - open_questions: {'; '.join(v.open_questions)}")
    if not any_ent:
        lines.append("(sin cambios)")
    lines += ["", "## Calendarios (documentos nuevos o con fechas cambiadas)"]
    any_doc = False
    for doc_id in sorted(kb.documents):
        d = kb.documents[doc_id]
        bd = b.documents.get(doc_id)
        if bd is not None and all(getattr(bd, a) == getattr(d, a) for a in CALENDAR_ATTRS):
            continue
        any_doc = True
        parts = [
            f"{slot} {ds.literal!r} → {ds.value} ({ds.stated_in if isinstance(ds.stated_in, str) else 'PageRef'})"
            for slot, ds in _date_slots(d)
        ]
        lines.append(f"- {doc_id}{' (nuevo)' if bd is None else ''}: " + ("; ".join(parts) or "sin fechas"))
    if not any_doc:
        lines.append("(sin cambios)")
    lines += ["", "## Issues nuevos"]
    new_issues = [i for iid, i in sorted(kb.issues.items()) if iid not in b.issues]
    lines += [
        f"- {i.id} ({i.kind}{', bloqueante' if i.blocking else ''}, {i.status}): {_short(i.statement, 300)}"
        for i in new_issues
    ] or ["(ninguno)"]
    lines += ["", "## Cambios al pasado"]
    past = [f for f in findings if f.check == "pasado"]
    lines += [f"- [{_SEV_TXT[f.severity]}] {f.where}: {f.message}" for f in past] or ["(ninguno)"]
    lines += ["", "## Pendientes"]
    pend = [
        (d.id, e)
        for d in sorted(kb.documents.values(), key=lambda x: x.id)
        for e in d.effects
        if e.disposition == "pending"
    ]
    lines += [f"- {e.id} → {e.target or 'sin destino'}: {e.verb_literal}" for _, e in pend] or ["(ninguno)"]
    c = _counts(findings)
    lines += ["", f"Resultado de `sifen check`: {c['error']} error(es), {c['warning']} aviso(s)."]
    return "\n".join(lines)


# --- CLI -------------------------------------------------------------------------------------------
def _root(args: argparse.Namespace) -> Path:
    given = getattr(args, "root", None)
    return Path(given).resolve() if given else find_root()


def cmd_check(args: argparse.Namespace) -> int:
    """`sifen check [--json]`: 0 sin errores, 1 con errores."""
    root = _root(args)
    kb = load_kb(root)
    base = load_base(kb.root)
    findings = run_checks(kb, base=base)
    if getattr(args, "json", False):
        print(render_json(findings))
    else:
        print(render_text(findings, kb.root))
    if getattr(args, "report", False):
        print()
        print(render_report(kb, base, findings))
    return 1 if errors_of(findings) else 0


def cmd_fmt(args: argparse.Namespace) -> int:
    """`sifen fmt [--check]`: formato canónico de kb/ (reescribe) y del manifiesto (solo verifica)."""
    root = _root(args)
    check_only = bool(getattr(args, "check", False))
    if not (root / "kb").is_dir():
        print(f"sifen fmt: kb/ no existe; solo se verifica {MANIFEST_NAME}")
    targets = canonical_targets(root)
    not_canonical: list[str] = []
    rewritten: list[str] = []
    failed: list[tuple[str, str]] = []
    for p in targets:
        rel = p.relative_to(root).as_posix()
        text, canon, err = _canonical_form(p, rel)
        if err is not None or canon is None:
            failed.append((rel, err or "error"))
            continue
        if canon == text:
            continue
        if check_only or rel in PROTECTED:
            not_canonical.append(rel)
            continue
        if canon.count("#") < text.count("#"):
            failed.append(
                (
                    rel,
                    "contiene un comentario o un « #» que trunca un valor: corrígelo a mano (fmt no borra texto)",
                )
            )
            continue
        with p.open("w", encoding="utf-8", newline="\n") as f:
            f.write(canon)
        rewritten.append(rel)
    for rel in rewritten:
        print(f"reformateado: {rel}")
    for rel in not_canonical:
        note = " (protegido: fmt no lo reescribe)" if rel in PROTECTED else ""
        print(f"no canónico: {rel}{note}")
    for rel, msg in failed:
        print(f"error: {rel}: {msg}")
    ok = not not_canonical and not failed
    print(
        f"sifen fmt: {len(targets)} archivo(s); {len(rewritten)} reformateado(s), "
        f"{len(not_canonical)} no canónico(s), {len(failed)} con error → {'OK' if ok else 'FALLA'}"
    )
    return 0 if ok else 1

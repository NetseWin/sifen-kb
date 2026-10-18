"""`sifen explain` y `sifen status` (docs/arquitectura.md §G.2, §G.4, §M, §O; guía: docs/uso.md).

Solo lectura: nunca escribe en `kb/`, `raw/`, `sources/` ni en el XML que se le pasa (con `--xml` se
verifica que el sha256 del XML, y el de la respuesta, no cambien durante la consulta).

Contrato de `explain --json` (estable; sin campos aleatorios ni dependientes de la hora, salvo los
que derivan de `--at`)::

    {
      "query": {"term": str, "at": "AAAA-MM-DD"|null, "env": "prod"|"test", "history": bool,
                "xml": str|null, "response": str|null, "processed_at": "AAAA-MM-DD"|null},
      "kb": {"revision": str|null, "documents_curated": [DocId, ...],
             "sources_checked_at": "AAAA-MM-DD"|null},
      "results": [
        {"key": str|null,                       # val:DE:D208c, field:DE:D208, DocId o null (índice)
         "kind": "field" | "validation" | "document" | "index",
         "resolution": <Resolution.model_dump(mode="json")>,
         "version": <versión elegida .model_dump(mode="json")> | null,
         "related_fields": [{"id", "key", "xml_name", "xsd": str|null}, ...],
         "xsd": {...} | null,                   # XsdCheck de la instantánea, si hay (con
                                                #   `enumeration` en campos con enumeración curada)
         "xml": {...} | null}                   # evaluación por eje (solo con --xml)
      ],
      "warnings": [str, ...]
    }

Precisiones (lo que el esqueleto dejaba abierto; documentadas también en el informe de cierre):

- `query.at`: la fecha usada (por defecto, hoy en America/Asuncion). Es `null` con `--xml`, que no
  admite `--at`: rigen la fecha de emisión del XML y la de procesamiento.
- `kb.revision`: `git describe --tags --match "kb-*" --always --dirty` cuando la raíz de la KB es la
  raíz de un repositorio git; si no (KB de fixture, copia sin git), `null`.
- `kind == "document"`: `resolution` y `version` son `null` (un documento no tiene vigencia propia) y
  el resultado agrega `"document"`: ficha (si existe), revisiones del manifiesto, calendario por
  ambiente, efectos con su estado e inicio por ambiente, Issues y, sin ficha, las fechas literales
  que `extract` dejó en `raw/` (`raw_dates`, sin curar).
- `--history`: cada resultado de campo o validación agrega `"timeline"` (tramos del ambiente pedido,
  con fuente, efectos, inicio en el otro ambiente y `changed` = `temporal.diff_versions` respecto
  del tramo anterior). `resolution` sigue siendo la de `--at`, separada de la historia.
- `resolution.source` y `resolution.history[].summary` citan la página impresa además de la PDF
  cuando `raw/` la conoce (el MT); `resolution.warnings` agrega los avisos de esta capa (XSD
  anacrónico, código que no corresponde a la versión mostrada).
- `xsd.enumeration` (decisión 8 del usuario, 2026-10-17): en un campo con `enumeration` curada,
  `documented` (códigos de la versión, MT/NT) frente a `accepted` (lo que acepta el tipo de la
  instantánea; `exhaustive` dice si es la lista completa), `only_documented`, `only_accepted` e
  `issues` (`source_conflict` del campo). Una discrepancia vuelve `xsd.status` `mismatch`, no cambia
  el estado de la regla y, sin Issue que la registre, agrega un aviso.
- `xml` (con `--xml`): `emitted_at`, `processed_at`, `processing_date_source`, `evaluated`,
  `decided`, `verdict` ("TRUE" = viola | "FALSE" | "UNKNOWN" | null si no se decide: `axis_split` o
  `processing_date_unknown`), `emission`/`processing` (`{at, state, reasons, version, verdict}`),
  `boundary`, `values` (solo los campos que usa la regla, PII enmascarada), `unreadable`, `notes`,
  `cdc` (atributo `DE/@Id`, enmascarado), `pii_masked`, `schema_validation` (XsdCheck + `errors`) y
  `warnings` (siempre con el aviso del primer error).
- Error con `--json`: stdout lleva `{"error": {"kind", "message", "details", "suggestions"}}` y el
  mismo mensaje sale por stderr.

Códigos de salida: 0 = respuesta; 1 = la KB tiene errores de carga (se muestran), error de datos
(`TemporalDataError`), XML ilegible o error de uso; 2 = término desconocido (ni curado ni mencionado
en `raw/`), con sugerencias.

Lecturas conservadoras ante ambigüedades (nunca un `in_force` ni un veredicto dudosos):

- Un campo de la condición que no se puede leer del XML (no curado, `xml_name` ausente o distinto
  entre versiones, sin instantánea XSD o sin un padre único bajo `DE` en el XSD) deja la regla en
  UNKNOWN: nunca se lo trata como ausente.
- Una regla sin formalizar (`level: none`) o no analizable por el DSL es UNKNOWN.
- `--response` sin `dFecProc` es un error (no se cae a "hoy" ni a la emisión).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from sifen_kb import dsl, xsd
from sifen_kb.load import KB, load_kb
from sifen_kb.mentions import has_raw_text, printed_page
from sifen_kb.model import (
    ENVS,
    Boundary,
    DateStatement,
    DocumentSource,
    Effect,
    Env,
    Field,
    FieldVersion,
    HistoryEntry,
    Issue,
    Mention,
    PageRef,
    Resolution,
    Validation,
    ValidationVersion,
    XsdCheck,
    XsdEnumeration,
    parse_ref,
)
from sifen_kb.normalize import parse_date_literal, sha12
from sifen_kb.rawio import iter_rows, read_index, rev_dir
from sifen_kb.temporal import (
    NOT_CURATED_WARNING,
    PRE_COVERAGE,
    TemporalDataError,
    chosen_version,
    diff_versions,
    effect_start,
    index_answer,
    resolve,
    resolve_xml_axes,
    timeline,
    version_label,
)

Version = FieldVersion | ValidationVersion
Entity = Field | Validation
Axis = Literal["processing", "emission"]

FIRST_ERROR_WARNING = "SIFEN informa el primer error; otras reglas pueden no haberse evaluado o informado"
XSD_ANACHRONISM = "instantánea posterior a la fecha consultada: referencia, no evidencia"
TZ_APPROX_WARNING = (
    "zona horaria de Paraguay aproximada (UTC-03:00 fijo, falta tzdata): la fecha de hoy y la "
    "conversión de dFecProc pueden errar un día en el invierno de 2024 y antes"
)
NO_KB_WARNING = "sin kb/: nada curado todavía; solo modo índice (not_curated) sobre raw/"

EXIT_OK, EXIT_ERROR, EXIT_UNKNOWN = 0, 1, 2

_KEY_RE = re.compile(r"^(field|val):([A-Z][A-Z-]*):(\w+)$")
_DOCID_RE = re.compile(
    r"^(MT_V150|NT_\d{3}|XSD_DIR|XSD_RAR|CHECKSUM_MT|TABLA_GEO|(GUIA|COM|NORMA)_[A-Z0-9_]+)$"
)
_CODE_RE = re.compile(r"^\d{4}$")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NT_RE = re.compile(r"^NT_(\d{3})$")
_WORD_RE = re.compile(r"^[A-Za-z0-9_]{2,40}$")

STATE_TXT: dict[str, str] = {
    "in_force": "la versión curada rige en esta fecha y ambiente",
    "removed": "la validación fue eliminada: la versión lápida conserva su código",
    "not_yet_existing": "todavía no existía en esta fecha y ambiente",
    "undetermined": "no se puede afirmar qué rige; se muestra la última versión curada solo como referencia",
    "outside_coverage": "fecha anterior a coverage_from: la KB no garantiza la respuesta; versión de referencia",
    "not_curated": "no curado: vigencia no resuelta; se listan las menciones en raw/ sin inferir la regla",
}
REASON_TXT: dict[str, str] = {
    "pending_effect": "hay una NT que afecta a la entidad y todavía no está curada (efecto pendiente)",
    "blocking_issue": "hay un Issue abierto y bloqueante cuya ventana y ambiente incluyen la consulta",
    "revision_not_curated": "el manifiesto tiene una revisión de un documento relevante sin curar",
    "beyond_horizon": "la fecha supera el horizonte de fuentes más la gracia: una NT posterior podría regir",
    "processing_date_unknown": "falta la fecha de procesamiento y la regla cambia entre la emisión y el horizonte",
    "axis_split": "la fecha de emisión y la de procesamiento caen en versiones con veredictos distintos",
    "test_date_missing": "el documento no declara fecha de test (no se usa la de producción)",
}
BASIS_TXT = {
    "baseline": "línea base",
    "approx": "aproximada",
    "stated": "declarada",
    "missing_test": "test sin fecha declarada",
    "undated": "a definir o no declarada",
}
LEVEL_TXT = {"full": "completa", "partial": "parcial", "none": "sin formalizar"}
VERDICT_TXT = {
    "TRUE": "TRUE: la regla se VIOLA",
    "FALSE": "FALSE: la regla se cumple",
    "UNKNOWN": "UNKNOWN: no se puede decidir con los datos o la formalización disponibles",
}


# --- Errores -----------------------------------------------------------------------------------------
class ExplainError(Exception):
    """Termina la consulta con un mensaje claro y un código de salida (nunca un traceback)."""

    exit_code = EXIT_ERROR
    kind = "error"

    def __init__(self, message: str, *, details: Iterable[str] = (), suggestions: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.details = list(details)
        self.suggestions = list(suggestions)


class UsageError(ExplainError):
    kind = "usage"


class KBLoadError(ExplainError):
    kind = "kb_errors"


class DataError(ExplainError):
    kind = "temporal_data"


class XmlError(ExplainError):
    kind = "xml"


class UnknownTermError(ExplainError):
    exit_code = EXIT_UNKNOWN
    kind = "unknown_term"


# --- Utilidades ----------------------------------------------------------------------------------------
def today_paraguay() -> date:
    """Hoy en America/Asuncion (con `zoneinfo`; sin tzdata, UTC-03:00 fijo: ver `xsd`)."""
    return xsd.to_paraguay_date(datetime.now(UTC).isoformat(timespec="seconds"))


def parse_day(value: str, flag: str) -> date:
    text = value.strip()
    if _ISO_DAY.match(text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    raise UsageError(f"{flag}: fecha inválida {value!r} (formato AAAA-MM-DD)")


def _iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d is not None else None


def _page_txt(printed: int | None, pdf: int) -> str:
    return f"p. {printed} impresa / {pdf} PDF" if printed else f"p. {pdf} PDF"


@lru_cache(maxsize=256)
def _index_cached(root: str, doc: str, rev12: str) -> dict[str, Any] | None:
    try:
        return read_index(Path(root), doc, rev12)
    except ValueError:  # index.json ilegible: sin página impresa
        return None


def _printed(kb: KB, doc: str, rev12: str, page: int) -> int | None:
    return printed_page(_index_cached(str(kb.root), doc, rev12), page)


def cite(kb: KB, ev: str | PageRef) -> str:
    """Documento + revisión sha12 + página impresa (si `raw/` la conoce) y PDF."""
    if isinstance(ev, PageRef):
        return f"{ev.doc} rev {ev.rev} · {_page_txt(ev.page_printed, ev.page_pdf)}"
    r = parse_ref(ev)
    doc, rev, page = str(r["doc"]), str(r["sha12"]), int(r["page"])  # type: ignore[arg-type]
    return f"{doc} rev {rev} · {_page_txt(_printed(kb, doc, rev, page), page)}"


def version_source(kb: KB, v: Version) -> str:
    """Como `temporal.version_source`, con la página impresa cuando `raw/` la conoce."""
    return f"{version_label(v)} · {cite(kb, v.evidence[0])}"


def _bd(b: Boundary | None, *, open_txt: str = "abierta") -> str:
    if b is None:
        return open_txt
    if b.basis == "baseline":
        return "línea base"
    if b.date == PRE_COVERAGE:
        return "sin fecha (anterior a toda cobertura; supuesto A1)"
    if b.basis == "approx":
        return f"~{b.date} (aproximada)"
    return f"{b.date} (declarada)"


def _bd_short(b: Boundary | None) -> str:
    if b is None:
        return "sin fecha"
    if b.basis == "baseline":
        return "base"
    if b.date == PRE_COVERAGE:
        return "sin fecha"
    return f"~{b.date}" if b.basis == "approx" else str(b.date)


def _hlabel(h: HistoryEntry) -> str:
    return "línea base" if h.introduced_by == "baseline" else "+".join(h.introduced_by)


def _axis_of(kb: KB) -> Axis:
    return kb.meta.date_axis_default if kb.meta else "processing"


def _axis_txt(kb: KB, axis: str) -> str:
    if axis == "emission":
        return "emisión"
    a2 = next((a for a in kb.meta.assumptions if a.id == "A2"), None) if kb.meta else None
    return "procesamiento" + ("" if a2 is not None and a2.status == "confirmed" else " [supuesto A2]")


def _ranges(nums: list[int]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        a, b = f"NT_{nums[i]:03d}", f"NT_{nums[j]:03d}"
        out.append(a if i == j else f"{a}–{b}")
        i = j + 1
    return out


def compress_docs(docs: Iterable[str]) -> str:
    """`MT_V150 + NT_001–NT_027 + CHECKSUM_MT + …` (el orden es de lectura, nunca temporal)."""
    ds = sorted(set(docs))
    nts = sorted(int(m.group(1)) for d in ds if (m := _NT_RE.match(d)))
    others = [d for d in ds if not _NT_RE.match(d)]
    head = [d for d in others if d.startswith("MT_")]
    tail = [d for d in others if not d.startswith("MT_")]
    return " + ".join([*head, *_ranges(nts), *tail]) or "vacío"


@lru_cache(maxsize=16)
def _git_revision(root: str) -> str | None:
    """`git describe` de la KB si su raíz es la raíz de un repositorio git (si no, None)."""

    def git(*a: str) -> str | None:
        try:
            p = subprocess.run(
                ["git", "--no-optional-locks", "-C", root, *a],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            return None
        return p.stdout.strip() if p.returncode == 0 and p.stdout.strip() else None

    top = git("rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != Path(root).resolve():
        return None
    return git("describe", "--tags", "--match", "kb-*", "--always", "--dirty")


def kb_info(kb: KB) -> dict[str, Any]:
    return {
        "revision": _git_revision(str(kb.root)),
        "documents_curated": sorted(kb.documents),
        "sources_checked_at": _iso(kb.horizon()),
    }


def _curated_txt(kb: KB) -> str:
    if not kb.documents and not kb.fields and not kb.validations:
        return "nada (sin kb/)" if not (kb.root / "kb").is_dir() else "nada"
    scopes = Counter(d.curation_scope for d in kb.documents.values())
    sc = ", ".join(f"{k} {n}" for k, n in sorted(scopes.items()))
    return (
        f"{len(kb.documents)} documentos ({sc or 'ninguno'}) · {len(kb.fields)} campos · "
        f"{len(kb.validations)} validaciones"
    )


def kb_snapshot_txt(kb: KB) -> str:
    rev = _git_revision(str(kb.root)) or "sin revisión git"
    corpus = compress_docs(r.doc for r in kb.manifest.revisions)
    return f"{rev} · corpus {corpus} · curado: {_curated_txt(kb)}"


def sources_txt(kb: KB, today: date) -> str:
    h = kb.horizon()
    if h is None:
        return "nunca verificadas: no hay un `sifen source check` limpio en el manifiesto"
    days = (today - h).days
    if days < 0:
        return f"verificadas el {h} (fecha posterior a hoy, {today}: KB de prueba o reloj desfasado)"
    grace = kb.meta.horizon_grace_days if kb.meta else 0
    txt = f"verificadas el {h} (hace {days} días)"
    if days > grace:
        txt += f" · horizonte vencido (gracia {grace} días): ejecutar `sifen source check`"
    return txt


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as e:
        raise XmlError(f"no se pudo leer {path.name}: {e.strerror or e}") from None


# --- Resolución del término ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Target:
    kind: Literal["entities", "document", "index"]
    keys: tuple[str, ...] = ()
    doc: str | None = None
    terms: tuple[str, ...] = ()
    index_key: str | None = None
    code: str | None = None


def _key_order(k: str) -> tuple[int, str]:
    return (0 if k.startswith("field:") else 1, k)


def classify(kb: KB, term: str) -> Target:
    """Código (N:M, con lápidas), clave completa, DocId, ID SIFEN, `xml_name` o, si no, modo índice."""
    t = term.strip()
    if not t:
        raise UsageError("el término está vacío")
    if m := _KEY_RE.match(t):
        if kb.is_curated(t):
            return Target("entities", keys=(t,))
        return Target("index", terms=(m.group(3),), index_key=t)
    if _DOCID_RE.match(t):
        if t in kb.documents or kb.revisions_of(t):
            return Target("document", doc=t)
        raise UnknownTermError(
            f"documento desconocido: {t} no está en kb/documents/ ni en sources.manifest.yaml",
            suggestions=suggest(kb, t),
        )
    if _CODE_RE.match(t):
        keys = sorted({k for k, _ in kb.code_index().get(t, [])})
        if keys:
            return Target("entities", keys=tuple(keys), code=t)
        return Target("index", terms=(t,))
    keys: list[str] = []
    if dsl.SIFEN_ID_RE.match(t):
        keys += kb.id_index().get(t, [])
    keys += [k for k in kb.xml_name_index().get(t, []) if k not in keys]
    if keys:
        return Target("entities", keys=tuple(sorted(set(keys), key=_key_order)))
    return Target("index", terms=(t,))


def _vocabulary(kb: KB) -> set[str]:
    """Identificadores conocidos para sugerir: curados, del manifiesto y de las tablas de `raw/`."""
    vocab: set[str] = set(kb.documents) | {r.doc for r in kb.manifest.revisions}
    for key, ent in kb.entities().items():
        vocab |= {key, ent.id}
        for v in ent.versions:
            vocab |= {x for x in (getattr(v, "code", None), getattr(v, "xml_name", None)) if x}
    for doc in sorted({r.doc for r in kb.manifest.revisions}):
        rev = kb.latest_revision(doc)
        if rev is None:
            continue
        try:
            for row in iter_rows(kb.root, doc, sha12(rev.sha256)):
                if row.table in ("fields", "validations"):
                    vocab.add(row.key)
                    vocab |= {x for x in (row.cells.get("code"), row.cells.get("xml_name")) if x}
        except OSError, ValueError, KeyError:
            continue
    return {w for w in vocab if _WORD_RE.match(w) or _KEY_RE.match(w)}


def suggest(kb: KB, term: str, n: int = 5) -> list[str]:
    """Identificadores parecidos (mayor similitud primero; empates en orden alfabético)."""
    t = term.strip()
    vocab = sorted(_vocabulary(kb))
    pool = [w for w in vocab if bool(_CODE_RE.match(w)) == bool(_CODE_RE.match(t))]
    exact_ci = [w for w in pool if w.lower() == t.lower() and w != t]
    scored = sorted(
        ((difflib.SequenceMatcher(None, t, w).ratio(), w) for w in pool if w != t),
        key=lambda sw: (-sw[0], sw[1]),
    )
    close = [w for score, w in scored if score >= 0.6]
    return list(dict.fromkeys([*exact_ci, *close]))[:n]


def _unknown(kb: KB, term: str, terms: Iterable[str]) -> UnknownTermError:
    hint: list[str] = []
    if not (kb.root / "raw").is_dir():
        hint.append("raw/ no existe en esta raíz: ejecutar `sifen extract` (o revisar --root)")
    return UnknownTermError(
        f"término desconocido: {term!r} no está curado ni se menciona en raw/ (buscado: {', '.join(terms)})",
        details=hint,
        suggestions=suggest(kb, term),
    )


# --- XSD -----------------------------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _schema_for(path: str) -> tuple[Any, xsd.XsdIndex]:
    schema = xsd.load_schema(path)
    return schema, xsd.XsdIndex(schema)


@dataclass
class Snapshot:
    """Instantánea XSD más reciente del manifiesto (carga perezosa y sin red)."""

    path: Path
    sha12: str
    retrieved_at: datetime
    schema: Any = None
    index: xsd.XsdIndex | None = None
    error: str | None = None
    _tried: bool = False

    @property
    def day(self) -> date:
        return xsd.to_paraguay_date(self.retrieved_at.isoformat())

    def load(self) -> bool:
        if not self._tried:
            self._tried = True
            try:
                self.schema, self.index = _schema_for(str(self.path))
            except xsd.XsdError as e:
                self.error = str(e)
        return self.index is not None


def find_snapshot(kb: KB) -> Snapshot | None:
    try:
        found = xsd.snapshot_from_manifest(kb.root)
    except xsd.XsdError:
        return None
    if found is None:
        return None
    folder, rev12, retrieved = found
    return Snapshot(folder, rev12, retrieved)


@dataclass(frozen=True)
class _Decl:
    parent: str | None
    paths: tuple[str, ...]
    occurrences: tuple[str, ...]
    note: str


def _decl(snap: Snapshot, xml_name: str, parent_xml: str | None) -> _Decl:
    """Declaraciones de `xml_name` bajo `DE` (con el padre, si se conoce) y su padre real único."""
    assert snap.index is not None
    decls = snap.index.lookup(xml_name, parent_xml) if parent_xml else snap.index.lookup(xml_name)
    in_de = [d for d in decls if "/DE/" in d.xpath]
    if not in_de:
        where = f"{parent_xml}/{xml_name}" if parent_xml else xml_name
        return _Decl(None, (), (), f"{where} no está declarado bajo DE en la instantánea XSD")
    parents = sorted({d.parent for d in in_de if d.parent})
    paths = tuple(sorted({d.xpath for d in in_de}))
    occs = tuple(sorted({d.occurrence for d in in_de}))
    if len(parents) != 1:
        return _Decl(None, paths, occs, f"{xml_name}: padres distintos en el XSD ({', '.join(parents)})")
    return _Decl(parents[0], paths, occs, "")


def _parent_xml(kb: KB, context: str, fv: FieldVersion) -> str | None:
    """`xml_name` del nodo padre si el padre (un ID, p. ej. D200) está curado."""
    if not fv.parent or not dsl.SIFEN_ID_RE.match(fv.parent):
        return None
    pf = kb.fields.get(f"field:{context}:{fv.parent}")
    if pf is None:
        return None
    names = {v.xml_name for v in pf.versions if v.xml_name}
    return next(iter(names)) if len(names) == 1 else None


def _occ_check(kb: KB, snap: Snapshot, context: str, fid: str, fv: FieldVersion | None) -> tuple[str, str]:
    if fv is None or not fv.xml_name:
        return "not_checked", f"{fid}: sin xml_name curado"
    assert snap.index is not None
    d = _decl(snap, fv.xml_name, _parent_xml(kb, context, fv))
    if d.note and not d.paths:
        return "not_checked", f"{fid}: {d.note}"
    if d.parent is None:
        return "not_checked", f"{fid}: {d.note}"
    if not fv.occurrence:
        return (
            "not_checked",
            f"{fid}: {' | '.join(d.paths)} ({', '.join(d.occurrences)}); sin ocurrencia curada",
        )
    c = snap.index.check_occurrence(fv.xml_name, d.parent, fv.occurrence)
    return c.status, f"{fid}: {c.detail} (manual {fv.occurrence})"


def _xsd_desc(kb: KB, snap: Snapshot | None, context: str, fv: FieldVersion | None) -> str | None:
    if snap is None or fv is None or not fv.xml_name:
        return None
    if not snap.load():
        return f"instantánea ilegible: {snap.error}"
    d = _decl(snap, fv.xml_name, _parent_xml(kb, context, fv))
    if not d.paths:
        return d.note
    txt = f"{' | '.join(d.paths)} ({', '.join(d.occurrences)})"
    if d.note:
        txt += f"; {d.note}"
    elif fv.occurrence:
        status, _ = _occ_check(kb, snap, context, "", fv)
        txt += f" · ocurrencia del manual {fv.occurrence}: {status}"
    return txt


# --- Resultados ----------------------------------------------------------------------------------------
@dataclass
class Related:
    id: str
    key: str | None
    xml_name: str | None
    xsd: str | None
    version: FieldVersion | None = None

    def as_json(self) -> dict[str, Any]:
        return {"id": self.id, "key": self.key, "xml_name": self.xml_name, "xsd": self.xsd}


@dataclass
class Item:
    key: str | None
    kind: Literal["field", "validation", "document", "index"]
    resolution: Resolution | None = None
    version: Version | None = None
    entity: Entity | None = None
    related: list[Related] = field(default_factory=list)
    xsd_check: XsdCheck | None = None
    xml: dict[str, Any] | None = None
    document: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] | None = None
    code: str | None = None
    term: str = ""

    def as_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "key": self.key,
            "kind": self.kind,
            "resolution": self.resolution.model_dump(mode="json") if self.resolution else None,
            "version": self.version.model_dump(mode="json") if self.version else None,
            "related_fields": [r.as_json() for r in self.related],
            "xsd": self.xsd_check.model_dump(mode="json") if self.xsd_check else None,
            "xml": self.xml,
        }
        if self.document is not None:
            d["document"] = self.document
        if self.timeline is not None:
            d["timeline"] = self.timeline
        return d


@dataclass
class Answer:
    query: dict[str, Any]
    kb: dict[str, Any]
    items: list[Item]
    warnings: list[str]

    def as_json(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "kb": self.kb,
            "results": [i.as_json() for i in self.items],
            "warnings": self.warnings,
        }


def _field_version_at(kb: KB, key: str, at: date, env: Env) -> FieldVersion | None:
    """Versión del campo vigente (o la mejor referencia) en `at`; si no hay, la primera futura."""
    tl = timeline(kb, key, env)
    dated = [t for t in tl if t.start is not None]
    past = [t for t in dated if t.start.basis == "baseline" or (t.start.date and t.start.date <= at)]  # type: ignore[union-attr]
    pick = past[-1] if past else (dated[0] if dated else (tl[0] if tl else None))
    v = pick.version if pick else None
    return v if isinstance(v, FieldVersion) else None


def _condition_node(v: Version | None) -> dsl.Cond | None:
    if not isinstance(v, ValidationVersion) or v.condition is None or not v.condition.expr:
        return None
    try:
        return dsl.parse(v.condition.expr)
    except dsl.DslError:
        return None


def related_fields(
    kb: KB, ent: Entity, v: Version | None, at: date, env: Env, snap: Snapshot | None
) -> list[Related]:
    """Validación: campo sujeto + campos de la condición formalizada. Campo: su nodo padre."""
    ids: list[str] = []
    if isinstance(ent, Validation):
        if ent.subject_field and (m := _KEY_RE.match(ent.subject_field)):
            ids.append(m.group(3))
        node = _condition_node(v)
        if node is not None:
            ids += sorted(dsl.fields(node))
    elif isinstance(v, FieldVersion) and v.parent and dsl.SIFEN_ID_RE.match(v.parent):
        ids.append(v.parent)
    out: list[Related] = []
    for fid in dict.fromkeys(ids):
        fkey = f"field:{ent.context}:{fid}"
        if fkey not in kb.fields:
            out.append(Related(fid, None, None, None))
            continue
        fv = _field_version_at(kb, fkey, at, env)
        xml_name = fv.xml_name if fv else None
        out.append(Related(fid, fkey, xml_name, _xsd_desc(kb, snap, ent.context, fv), fv))
    return out


def _enum_check(kb: KB, snap: Snapshot, ent: Field, fv: FieldVersion | None) -> XsdEnumeration | None:
    """Códigos documentados por la versión (MT/NT) frente a los aceptados por la instantánea (decisión 8)."""
    if fv is None or not fv.enumeration or not fv.xml_name:
        return None
    assert snap.index is not None
    documented = [e.code for e in fv.enumeration]
    issues = sorted(
        iid
        for iid, i in kb.issues.items()
        if i.kind == "source_conflict" and any(s.subject == ent.key for s in i.affects)
    )
    base: dict[str, Any] = {
        "documented": documented,
        "documented_source": version_source(kb, fv),
        "issues": issues,
    }
    d = _decl(snap, fv.xml_name, _parent_xml(kb, ent.context, fv))
    if d.parent is None:
        return XsdEnumeration(status="not_checked", detail=f"{ent.id}: {d.note}", **base)
    c = snap.index.check_enumeration(fv.xml_name, d.parent, documented)
    return XsdEnumeration(
        status=c.status,
        accepted=list(c.accepted) if c.accepted is not None else None,
        exhaustive=c.exhaustive,
        only_documented=list(c.only_documented),
        only_accepted=list(c.only_accepted),
        detail=f"{ent.id}: {c.detail}",
        **base,
    )


def xsd_check(
    kb: KB, ent: Entity, v: Version | None, related: list[Related], at: date, snap: Snapshot | None
) -> XsdCheck | None:
    """Estructura frente a la instantánea: campo = su ocurrencia (y su enumeración, si la tiene curada:
    lo documentado por MT/NT frente a lo aceptado por el XSD, decisión 8); validación = la de sus campos."""
    if snap is None:
        return None
    anach = xsd.anachronistic(at, snap.retrieved_at)
    if not snap.load():
        return XsdCheck(
            snapshot=snap.sha12,
            retrieved_at=snap.day,
            status="not_checked",
            anachronistic=anach,
            detail=f"instantánea ilegible: {snap.error}",
        )
    enum = None
    if isinstance(ent, Field):
        fv = v if isinstance(v, FieldVersion) else None
        checks = [_occ_check(kb, snap, ent.context, ent.id, fv)]
        enum = _enum_check(kb, snap, ent, fv)
    else:
        checks = [_occ_check(kb, snap, ent.context, r.id, r.version) for r in related if r.version]
    statuses = [s for s, _ in checks] + ([enum.status] if enum is not None else [])
    if not checks:
        status, detail = "not_checked", "sin campos curados con xml_name que comparar"
    else:
        status = (
            "mismatch"
            if "mismatch" in statuses
            else ("match" if all(s == "match" for s in statuses) else "not_checked")
        )
        detail = "; ".join(d for _, d in checks)
    return XsdCheck(
        snapshot=snap.sha12,
        retrieved_at=snap.day,
        status=status,  # type: ignore[arg-type]
        anachronistic=anach,
        detail=detail,
        enumeration=enum,
    )


def _enrich(kb: KB, ent: Entity, res: Resolution, extra: list[str]) -> Resolution:
    upd: dict[str, Any] = {}
    v = chosen_version(kb, res)
    if v is not None:
        upd["source"] = version_source(kb, v)
    by_label = {version_label(x): x for x in ent.versions}
    if res.history:
        upd["history"] = [
            h.model_copy(update={"summary": version_source(kb, by_label[_hlabel(h)])})
            if _hlabel(h) in by_label
            else h
            for h in res.history
        ]
    if extra:
        upd["warnings"] = [*res.warnings, *extra]
    return res.model_copy(update=upd)


def entity_item(
    kb: KB,
    key: str,
    res: Resolution,
    *,
    at: date,
    env: Env,
    snap: Snapshot | None,
    code: str | None = None,
) -> Item:
    ent = kb.entity(key)
    assert ent is not None
    v = chosen_version(kb, res)
    rel = related_fields(kb, ent, v, at, env, snap)
    check = xsd_check(kb, ent, v, rel, at, snap)
    extra: list[str] = []
    if code is not None:
        have = getattr(v, "code", None) if v is not None else None
        if v is None:
            extra.append(f"{key} no tiene versión en esta fecha; el código {code} es de otra versión")
        elif have != code:
            extra.append(
                f"el código {code} no corresponde a la versión mostrada de {key} "
                f"(código de esa versión: {have or 'ninguno'}): lo tuvo otra versión"
            )
    if check is not None and check.anachronistic:
        extra.append(f"XSD anacrónico: {XSD_ANACHRONISM} (instantánea del {check.retrieved_at})")
    enum = check.enumeration if check is not None else None
    if enum is not None and enum.status == "mismatch" and not enum.issues:
        extra.append(
            f"XSD: los códigos que documentan el MT/NT y los que acepta la instantánea difieren y ningún Issue "
            f"source_conflict lo registra ({enum.detail})"
        )
    kind: Literal["field", "validation"] = "field" if isinstance(ent, Field) else "validation"
    return Item(
        key=key,
        kind=kind,
        resolution=_enrich(kb, ent, res, extra),
        version=v,
        entity=ent,
        related=rel,
        xsd_check=check,
        code=code,
    )


# --- Historia (--history) ------------------------------------------------------------------------------
def _schedule_cell(doc: DocumentSource, env: Env) -> dict[str, Any] | None:
    if doc.schedule is None:
        return None
    st = doc.schedule.prod if env == "prod" else doc.schedule.test
    return _ds_json(st)


def _ds_json(ds: DateStatement | None) -> dict[str, Any] | None:
    if ds is None:
        return None
    stated = ds.stated_in if isinstance(ds.stated_in, str) else ds.stated_in.model_dump(mode="json")
    return {"date": _iso(ds.value), "literal": ds.literal, "stated_in": stated}


def timeline_json(kb: KB, key: str, env: Env) -> list[dict[str, Any]]:
    """Tramos del ambiente `env` (orden derivado por fecha; prospectivas al final) con su diff."""
    other: Env = "test" if env == "prod" else "prod"
    tl = timeline(kb, key, env)
    other_start = {t.index: t.start for t in timeline(kb, key, other)}
    out: list[dict[str, Any]] = []
    prev: Version | None = None
    for t in tl:
        v = t.version
        effects: list[dict[str, Any]] = []
        if v.introduced_by != "baseline":
            for eid in v.introduced_by:
                doc, eff = kb.doc_of(eid), kb.effect(eid)
                effects.append(
                    {
                        "id": eid,
                        "doc": doc.id,
                        "action": eff.action,
                        "verb_literal": eff.verb_literal,
                        "declared_scope": eff.declared_scope,
                        "from_revision": eff.from_revision,
                        "dates": {e: _schedule_cell(doc, e) for e in ENVS},
                    }
                )
        os_ = other_start.get(t.index)
        out.append(
            {
                "index": t.index,
                "label": t.label,
                "introduced_by": v.introduced_by,
                "kind": v.kind,
                "start": t.start.model_dump(mode="json") if t.start else None,
                "end": t.end.model_dump(mode="json") if t.end else None,
                "start_basis": t.start_basis,
                "other_env": {"env": other, "start": os_.model_dump(mode="json") if os_ else None},
                "source": version_source(kb, v),
                "effects": effects,
                "changed": diff_versions(prev, v) if prev is not None else None,
                "version": v.model_dump(mode="json"),
            }
        )
        prev = v
    return out


# --- Documentos ----------------------------------------------------------------------------------------
def _issue_brief(i: Issue) -> dict[str, Any]:
    return {
        "id": i.id,
        "kind": i.kind,
        "status": i.status,
        "blocking": i.blocking,
        "statement": i.statement,
    }


def _start_json(kb: KB, eid: str, env: Env) -> dict[str, Any]:
    d, basis = effect_start(kb, eid, env)
    return {"date": _iso(d), "basis": basis}


def _effect_json(kb: KB, e: Effect) -> dict[str, Any]:
    versions = [
        f"{key} · {version_label(v)}"
        for key, ent in sorted(kb.entities().items())
        for v in ent.versions
        if v.introduced_by != "baseline" and e.id in v.introduced_by
    ]
    state = "applied" if e.disposition is None else e.disposition
    return {
        "id": e.id,
        "action": e.action,
        "target": e.target,
        "verb_literal": e.verb_literal,
        "declared_scope": e.declared_scope,
        "state": state,
        "versions": versions,
        "starts": {env: _start_json(kb, e.id, env) for env in ENVS},
        "from_revision": e.from_revision,
        "note": e.note,
    }


def _raw_dates(kb: KB, doc_id: str, rev12: str | None) -> dict[str, Any] | None:
    """Fechas literales que `extract` copió en `index.json` (SIN curar: no resuelven vigencia)."""
    if rev12 is None:
        return None
    info = (_index_cached(str(kb.root), doc_id, rev12) or {}).get("nt_info")
    if not isinstance(info, dict):
        return None
    out: dict[str, Any] = {"page": info.get("page")}
    for k, name in (("fecha_literal", "fecha"), ("test_literal", "test"), ("prod_literal", "prod")):
        lit = info.get(k)
        out[name] = {
            "literal": lit if isinstance(lit, str) else None,
            "date": _iso(parse_date_literal(lit)) if isinstance(lit, str) else None,
        }
    return out


def document_card(kb: KB, doc_id: str) -> dict[str, Any]:
    doc = kb.documents.get(doc_id)
    revs = kb.revisions_of(doc_id)
    latest = revs[-1] if revs else None
    revisions = []
    for r in revs:
        s12 = sha12(r.sha256)
        revisions.append(
            {
                "sha12": s12,
                "sha256": r.sha256,
                "filename": r.filename,
                "url": r.url,
                "origin": r.origin,
                "portal_t": _iso(r.portal_t),
                "retrieved_at": _iso(r.retrieved_at),
                "note": r.note,
                "latest": r is latest,
                "curated": doc is not None and r.sha256 == doc.current_revision,
                "raw": (rev_dir(kb.root, doc_id, s12) / "pages").is_dir(),
            }
        )
    uncurated: str | None = None
    if doc is None:
        uncurated = "registrado en el manifiesto sin ficha en kb/documents/: revisión sin curar"
    elif latest is None:
        uncurated = "la ficha no tiene revisiones en el manifiesto (error de datos: ver `sifen check`)"
    elif latest.sha256 != doc.current_revision:
        uncurated = (
            f"la revisión {sha12(latest.sha256)} del manifiesto no está curada "
            f"(kb/ usa {sha12(doc.current_revision)})"
        )
    subjects = {doc_id} | ({e.id for e in doc.effects} if doc else set())
    issues = [
        _issue_brief(i)
        for i in sorted(kb.issues.values(), key=lambda i: i.id)
        if any(s.subject in subjects for s in i.affects)
    ]
    card: dict[str, Any] = {
        "id": doc_id,
        "curated": doc is not None,
        "title": doc.title if doc else None,
        "kind": doc.kind if doc else None,
        "number": doc.number if doc else None,
        "curation_scope": doc.curation_scope if doc else None,
        "current_revision": sha12(doc.current_revision) if doc else None,
        "uncurated_revision": uncurated,
        "revisions": revisions,
        "document_date": _ds_json(doc.document_date) if doc else None,
        "change_period": [_ds_json(a) for a in doc.change_period] if doc and doc.change_period else None,
        "schedule": (
            {e: _schedule_cell(doc, e) for e in ENVS}
            if doc is not None and doc.schedule is not None
            else None
        ),
        "superseded_by": doc.superseded_by.model_dump(mode="json") if doc and doc.superseded_by else None,
        "effects": [_effect_json(kb, e) for e in doc.effects] if doc else [],
        "issues": issues,
        "raw_dates": None if doc else _raw_dates(kb, doc_id, sha12(latest.sha256) if latest else None),
    }
    return card


# --- --xml ---------------------------------------------------------------------------------------------
class Pii:
    """Datos personales del XML (§M): enmascarado por defecto; `--show-pii` solo lo desactiva."""

    def __init__(self, xml_path: Path, show: bool) -> None:
        self.show = show
        self.cdc, self.values = _read_pii(xml_path)

    def display(self, xml_name: str | None, value: str | None) -> tuple[str | None, bool]:
        if value is None or self.show or not value or xml_name not in xsd.PII_ELEMENTS:
            return value, False
        return xsd.mask(value), True

    @property
    def cdc_display(self) -> str | None:
        if self.cdc is None:
            return None
        return self.cdc if self.show else xsd.mask(self.cdc)

    def scrub(self, text: str) -> str:
        """Quita de un mensaje (p. ej. un error de esquema) los valores personales del XML."""
        if self.show:
            return text
        for v in self.values:
            if len(v) >= 4:
                text = text.replace(v, xsd.mask(v))
        return re.sub(r"\d{6,}", lambda m: xsd.mask(m.group()), text)


def _read_pii(xml_path: Path) -> tuple[str | None, list[str]]:
    """CDC (`DE/@Id`) y valores de los elementos de `PII_ELEMENTS`, con la lectura segura de `xsd`."""
    root = xsd.read_xml_root(xml_path)  # la misma lectura segura que el resto de xsd (sin DTD ni red)
    ns = "{" + xsd.SIFEN_NS + "}"
    cdc: str | None = None
    vals: set[str] = set()
    for el in root.iter():
        tag = el.tag if isinstance(el.tag, str) else ""
        local = tag.rpartition("}")[2]
        if cdc is None and tag == f"{ns}DE":
            cdc = (el.get("Id") or "").strip() or None
        if local in xsd.PII_ELEMENTS and el.text and el.text.strip():
            vals.add(el.text.strip())
    if cdc:
        vals.add(cdc)
    return cdc, sorted(vals, key=lambda s: (-len(s), s))


def _vstr(v: bool | None) -> str:
    return {True: "TRUE", False: "FALSE", None: "UNKNOWN"}[v]


@dataclass
class XmlContext:
    path: Path
    emitted_at: date
    processed_at: date | None
    source: Literal["response", "flag"] | None
    pii: Pii
    schema_validation: dict[str, Any] | None


def _xml_mapping(
    kb: KB, context: str, fids: Iterable[str], snap: Snapshot | None
) -> tuple[dict[str, tuple[str, str | None]], dict[str, str], dict[str, str]]:
    """ID → (xml_name, padre real del XSD); tipos SIFEN; y los no legibles con su motivo."""
    mapping: dict[str, tuple[str, str | None]] = {}
    types: dict[str, str] = {}
    unreadable: dict[str, str] = {}
    snap_ok = snap is not None and snap.load()
    for fid in sorted(set(fids)):
        fent = kb.fields.get(f"field:{context}:{fid}")
        if fent is None:
            unreadable[fid] = "campo no curado: se desconoce su xml_name"
            continue
        content = [v for v in fent.versions if v.kind == "content"]
        names = {v.xml_name for v in content if v.xml_name}
        if len(names) != 1:
            unreadable[fid] = (
                "xml_name no curado" if not names else f"xml_name distinto entre versiones ({sorted(names)})"
            )
            continue
        xml_name = next(iter(names))
        if not snap_ok:
            why = "sin instantánea XSD registrada" if snap is None else f"instantánea ilegible: {snap.error}"
            unreadable[fid] = f"{why}: no se conoce el padre real de {xml_name}"
            continue
        assert snap is not None
        parent_hint = _parent_xml(kb, context, content[-1])
        d = _decl(snap, xml_name, parent_hint)
        if d.parent is None:
            unreadable[fid] = d.note or f"{xml_name}: sin padre único en el XSD"
            continue
        mapping[fid] = (xml_name, d.parent)
        dtypes = {v.data_type for v in content if v.data_type}
        if len(dtypes) == 1:
            types[fid] = next(iter(dtypes))
    return mapping, types, unreadable


def _all_condition_fields(ent: Validation) -> set[str]:
    out: set[str] = set()
    for v in ent.versions:
        node = _condition_node(v)
        if node is not None:
            out |= dsl.fields(node)
    return out


def _axis_json(kb: KB, ax: dict[str, Any] | None, evaluated: bool) -> dict[str, Any] | None:
    if ax is None:
        return None
    r: Resolution = ax["resolution"]
    v = chosen_version(kb, r)
    return {
        "at": _iso(ax["at"]),
        "state": r.state,
        "reasons": list(r.reasons),
        "version": version_label(v) if v is not None else None,
        "verdict": _vstr(ax["verdict"]) if evaluated else None,
    }


def xml_item(kb: KB, key: str, xc: XmlContext, *, env: Env, snap: Snapshot | None, code: str | None) -> Item:
    """Evalúa la regla con ambas fechas (G.4) y arma el bloque `xml` (solo lo que usa la regla)."""
    ent = kb.entity(key)
    assert ent is not None
    evaluated = isinstance(ent, Validation)
    fids = _all_condition_fields(ent) if isinstance(ent, Validation) else {ent.id}
    mapping, types, unreadable = _xml_mapping(kb, ent.context, fids, snap)
    try:
        values = xsd.read_values(xc.path, mapping) if mapping else {}
    except xsd.XmlReadError as e:
        raise XmlError(str(e)) from None
    used: set[str] = set() if evaluated else {ent.id}
    notes: list[str] = []

    def evaluate(v: Version) -> bool | None:
        label = version_label(v)
        if not isinstance(v, ValidationVersion):
            return None
        cond = v.condition
        if cond is None or cond.level == "none" or not cond.expr:
            notes.append(f"{label}: la regla no está formalizada: UNKNOWN")
            return None
        try:
            node = dsl.parse(cond.expr)
        except dsl.DslError as e:
            notes.append(f"{label}: condición no analizable por el DSL ({e}): UNKNOWN")
            return None
        need = dsl.fields(node)
        used.update(need)
        missing = sorted(f for f in need if f not in mapping)
        if missing:
            why = "; ".join(f"{f}: {unreadable.get(f, 'sin mapeo')}" for f in missing)
            notes.append(f"{label}: no se puede leer {', '.join(missing)} del XML ({why}): UNKNOWN")
            return None
        return dsl.evaluate(node, values, types)

    out = resolve_xml_axes(
        kb,
        key,
        xc.emitted_at,
        xc.processed_at,
        env,
        evaluate if evaluated else (lambda v: None),
        processing_date_source=xc.source or "flag",
    )
    res: Resolution = out["resolution"]
    item = entity_item(kb, key, res, at=res.at, env=env, snap=snap, code=code)
    decided = not ({"axis_split", "processing_date_unknown"} & set(out["reasons"]))
    shown: dict[str, Any] = {}
    for fid in sorted(used):
        if fid not in mapping:
            continue
        xml_name, parent = mapping[fid]
        val, masked = xc.pii.display(xml_name, values.get(fid))
        shown[fid] = {
            "xml_name": xml_name,
            "parent": parent,
            "present": values.get(fid) is not None,
            "value": val,
            "masked": masked,
        }
    item.xml = {
        "emitted_at": _iso(xc.emitted_at),
        "processed_at": _iso(xc.processed_at),
        "processing_date_source": out["processing_date_source"],
        "evaluated": evaluated,
        "decided": decided if evaluated else None,
        "verdict": _vstr(out["verdict"]) if evaluated and decided else None,
        "emission": _axis_json(kb, out["emission"], evaluated),
        "processing": _axis_json(kb, out["processing"], evaluated),
        "boundary": _iso(out["boundary"]),
        "values": shown,
        "unreadable": {f: unreadable[f] for f in sorted(used) if f in unreadable},
        "notes": list(dict.fromkeys(notes)),
        "cdc": xc.pii.cdc_display,
        "pii_masked": not xc.pii.show,
        "schema_validation": xc.schema_validation,
        "warnings": [FIRST_ERROR_WARNING],
    }
    return item


def schema_validation(
    snap: Snapshot | None, xml_path: Path, emitted_at: date, pii: Pii
) -> dict[str, Any] | None:
    """Validación XSD del XML contra la instantánea, con marca de anacronismo (por fecha de emisión)."""
    if snap is None:
        return None
    anach = xsd.anachronistic(emitted_at, snap.retrieved_at)
    suffix = f"; {XSD_ANACHRONISM}" if anach else ""
    if not snap.load():
        check = XsdCheck(
            snapshot=snap.sha12,
            retrieved_at=snap.day,
            status="not_checked",
            anachronistic=anach,
            detail=f"instantánea ilegible: {snap.error}",
        )
        return {**check.model_dump(mode="json"), "errors": []}
    errors = [pii.scrub(e) for e in xsd.validate_xml(snap.schema, xml_path)]
    detail = (
        f"{len(errors)} errores de esquema (SIFEN informa solo el primero)"
        if errors
        else "cumple el XSD de la instantánea (no implica que SIFEN lo acepte: firma y reglas no se evalúan)"
    )
    check = XsdCheck(
        snapshot=snap.sha12,
        retrieved_at=snap.day,
        status="mismatch" if errors else "match",
        anachronistic=anach,
        detail=detail + suffix,
    )
    return {**check.model_dump(mode="json"), "errors": errors}


# --- explain (biblioteca) ------------------------------------------------------------------------------
def explain(
    kb: KB,
    term: str,
    *,
    at: date | None,
    env: Env = "prod",
    history: bool = False,
    xml: str | Path | None = None,
    response: str | Path | None = None,
    processed_at: date | None = None,
    show_pii: bool = False,
    now: date | None = None,
) -> Answer:
    """Respuesta completa (contrato JSON del módulo). `now` solo agrega el aviso de antigüedad del
    horizonte; la CLI lo pasa solo cuando `--at` se omitió (entonces `now == at`)."""
    if xml is None and at is None:
        raise UsageError("falta la fecha de la consulta (--at)")
    if xml is not None and at is not None:
        raise UsageError("--xml no se combina con --at")
    if response is not None and processed_at is not None:
        raise UsageError("use --response o --processed-at, no ambos")
    if xml is None and (response is not None or processed_at is not None):
        raise UsageError("--response y --processed-at solo se usan con --xml (para una fecha, --at)")
    if xml is not None and history:
        raise UsageError("--history no se combina con --xml")

    target = classify(kb, term)
    axis = _axis_of(kb)
    warnings: list[str] = []
    if not (kb.root / "kb").is_dir():
        warnings.append(NO_KB_WARNING)
    query = {
        "term": term,
        "at": _iso(at),
        "env": env,
        "history": history,
        "xml": str(xml) if xml is not None else None,
        "response": str(response) if response is not None else None,
        "processed_at": _iso(processed_at),
    }

    if xml is None:
        assert at is not None
        items = _items_at(kb, target, term, at, env, axis, history, now)
    else:
        items = _items_xml(kb, target, term, Path(xml), response, processed_at, env, show_pii)
        warnings.append(FIRST_ERROR_WARNING)
    return Answer(query=query, kb=kb_info(kb), items=items, warnings=warnings)


def _items_at(
    kb: KB, target: Target, term: str, at: date, env: Env, axis: Axis, history: bool, now: date | None
) -> list[Item]:
    if target.kind == "index":
        res = index_answer(kb, list(target.terms), at, env, axis=axis, key=target.index_key, now=now)
        if not res.mentions:
            raise _unknown(kb, term, target.terms)
        return [Item(key=target.index_key, kind="index", resolution=res, term=term)]
    if target.kind == "document":
        assert target.doc is not None
        return [Item(key=target.doc, kind="document", document=document_card(kb, target.doc), term=term)]
    snap = find_snapshot(kb)
    items: list[Item] = []
    for key in target.keys:
        res = resolve(kb, key, at, env, axis=axis, now=now)
        it = entity_item(kb, key, res, at=at, env=env, snap=snap, code=target.code)
        it.term = term
        if history:
            it.timeline = timeline_json(kb, key, env)
        items.append(it)
    return items


def _items_xml(
    kb: KB,
    target: Target,
    term: str,
    xml_path: Path,
    response: str | Path | None,
    processed_at: date | None,
    env: Env,
    show_pii: bool,
) -> list[Item]:
    if target.kind == "document":
        raise UsageError("--xml necesita un código, un ID o un xml_name, no un documento")
    resp_path = Path(response) if response is not None else None
    before = _file_sha256(xml_path)
    resp_before = _file_sha256(resp_path) if resp_path is not None else None
    try:
        emitted = xsd.read_emission_date(xml_path)
        if emitted is None:
            raise XmlError("el XML no tiene dFeEmiDE bajo gDatGralOpe: sin fecha de emisión no se resuelve")
        processed, source = processed_at, ("flag" if processed_at is not None else None)
        if resp_path is not None:
            processed = xsd.read_processing_date(resp_path)
            if processed is None:
                raise XmlError(
                    f"{resp_path.name} no tiene dFecProc bajo rProtDe: no es una respuesta de recepción "
                    "de SIFEN; pase --processed-at si conoce la fecha (nunca se asume hoy)"
                )
            source = "response"
        pii = Pii(xml_path, show_pii)
        snap = find_snapshot(kb)
        xc = XmlContext(
            xml_path, emitted, processed, source, pii, schema_validation(snap, xml_path, emitted, pii)
        )
        if target.kind == "index":
            at = processed or emitted
            res = index_answer(kb, list(target.terms), at, env, axis=_axis_of(kb), key=target.index_key)
            if not res.mentions:
                raise _unknown(kb, term, target.terms)
            items = [
                Item(
                    key=target.index_key,
                    kind="index",
                    resolution=res,
                    term=term,
                    xml={
                        "emitted_at": _iso(emitted),
                        "processed_at": _iso(processed),
                        "processing_date_source": source or "unknown",
                        "evaluated": False,
                        "notes": ["no curado: la regla no se evalúa contra el XML"],
                        "cdc": pii.cdc_display,
                        "pii_masked": not show_pii,
                        "schema_validation": xc.schema_validation,
                        "warnings": [FIRST_ERROR_WARNING],
                    },
                )
            ]
        else:
            items = [xml_item(kb, k, xc, env=env, snap=snap, code=target.code) for k in target.keys]
    except xsd.XmlReadError as e:
        raise XmlError(str(e)) from None
    if _file_sha256(xml_path) != before or (resp_path is not None and _file_sha256(resp_path) != resp_before):
        raise XmlError("el XML (o la respuesta) cambió durante la consulta: resultado descartado")
    return items


# --- Texto ---------------------------------------------------------------------------------------------
_INDENT = " " * 14


def _line(label: str, text: str) -> str:
    return f"  {label:<11} {text}" if label else f"{_INDENT}{text}"


def _lines(label: str, texts: Iterable[str]) -> list[str]:
    out: list[str] = []
    for i, t in enumerate(texts):
        out.append(_line(label if i == 0 else "", t))
    return out


def _ident(it: Item) -> str:
    v = it.version
    parts = [it.key or it.term]
    if it.kind == "validation":
        code = getattr(v, "code", None) or it.code
        if code:
            parts.append(f"código {code}")
        sev = getattr(v, "severity", None)
        if sev:
            parts.append(sev)
    elif it.kind == "field" and isinstance(v, FieldVersion) and v.xml_name:
        parts.append(v.xml_name)
    return " · ".join(parts)


def _ctx(kb: KB, res: Resolution) -> str:
    return f"({res.at} · {res.env} · eje: {_axis_txt(kb, res.axis)})"


def _header(kb: KB, it: Item, res: Resolution) -> list[str]:
    if res.state == "in_force":
        return [f"{_ident(it)} · IN_FORCE {_ctx(kb, res)}"]
    reasons = f" [{', '.join(res.reasons)}]" if res.reasons else ""
    out = [f"{res.state.upper()}{reasons} · {_ident(it)} {_ctx(kb, res)}"]
    out.append(_line("Estado", f"{res.state.upper()}: {STATE_TXT[res.state]}"))
    out += _lines("Motivos", (f"{r}: {REASON_TXT[r]}" for r in res.reasons))
    return out


def _start_source(kb: KB, v: Version, env: Env) -> str:
    if v.introduced_by == "baseline":
        return kb.meta.baseline_doc if kb.meta else "línea base"
    parts: list[str] = []
    for eid in v.introduced_by:
        if not kb.has_effect(eid):
            continue
        doc, eff = kb.doc_of(eid), kb.effect(eid)
        st = None
        if doc.schedule is not None:
            st = doc.schedule.prod if env == "prod" else doc.schedule.test
        if st is not None:
            parts.append(f"{doc.id} «{st.literal}», {_cell_txt(kb, st.stated_in)}")
        elif doc.schedule is None and doc.document_date is not None:
            parts.append(f"{doc.id} sin calendario; fecha del documento «{doc.document_date.literal}»")
        else:
            parts.append(f"{doc.id}: sin fecha declarada para {env}")
        if eff.from_revision:
            parts.append(f"re-subida {eff.from_revision}")
    return "; ".join(parts)


def _stated_txt(stated: str | dict[str, Any]) -> str:
    """`stated_in` volcado a JSON (CellRef o PageRef) para el texto: un PageRef no sale como dict."""
    if isinstance(stated, str):
        return stated
    page = _page_txt(stated.get("page_printed"), int(stated["page_pdf"]))
    quote = f", cita «{stated['quote']}»" if stated.get("quote") else ""
    return f"{stated['doc']} rev {stated['rev']} · {page}{quote}"


def _cell_txt(kb: KB, ref: str | PageRef) -> str:
    if isinstance(ref, PageRef):
        return f"rev {ref.rev} {_page_txt(ref.page_printed, ref.page_pdf)}"
    r = parse_ref(ref)
    doc, rev, page = str(r["doc"]), str(r["sha12"]), int(r["page"])  # type: ignore[arg-type]
    return f"rev {rev} {_page_txt(_printed(kb, doc, rev, page), page)}"


def _next_label(kb: KB, key: str, env: Env, end: Boundary | None) -> str:
    if end is None:
        return ""
    for t in timeline(kb, key, env):
        if t.start is not None and t.start == end:
            return f" (inicio de {t.label})"
    return ""


def _version_lines(kb: KB, it: Item, res: Resolution) -> list[str]:
    v = it.version
    assert it.key is not None
    if v is None:
        nxt = res.interval[1] if res.interval else None
        txt = "ninguna: no existe en esta fecha y ambiente"
        if nxt is not None:
            txt += f" · la primera empieza {_bd(nxt)}{_next_label(kb, it.key, res.env, nxt)}"
        return [_line("Versión", txt)]
    label = {
        "in_force": "Versión",
        "removed": "Eliminada",
    }.get(res.state, "Referencia")
    start, end = res.interval if res.interval else (None, None)
    txt = (
        f"{version_label(v)} · desde {_bd(start)} [{_start_source(kb, v, res.env)}] · "
        f"hasta {_bd(end)}{_next_label(kb, it.key, res.env, end)}"
    )
    out = [_line(label, txt)]
    if res.state not in ("in_force", "removed"):
        out.append(_line("", f"NO es una vigencia afirmada: estado {res.state.upper()}"))
    if v.kind == "tombstone":
        out.append(_line("", "lápida: copia los literales de la versión eliminada y conserva su código"))
    return out


def _literal_lines(kb: KB, it: Item) -> list[str]:
    v = it.version
    if v is None:
        return []
    out: list[str] = []
    if isinstance(v, ValidationVersion):
        if v.message:
            out.append(_line("Mensaje", f"«{v.message}»"))
        if v.observation:
            out.append(_line("Literal", f"«{v.observation}»"))
        for lb in v.legal_basis:
            ev = lb.stated_in
            out.append(_line("Base legal", f"{lb.citation} ({cite(kb, ev)})"))
    elif isinstance(v, FieldVersion):
        if v.description:
            out.append(_line("Descripción", f"«{v.description}»"))
        fmt = [
            f"{k} {val}"
            for k, val in (
                ("grupo", v.group),
                ("padre", v.parent),
                ("tipo", v.data_type),
                ("longitud", v.length),
                ("ocurrencia", v.occurrence),
            )
            if val
        ]
        if fmt:
            out.append(_line("Formato", " · ".join(fmt)))
        if v.observations:
            out.append(_line("Observación", f"«{v.observations}»"))
        if v.enumeration:
            enum = " · ".join(f"{e.code}={e.label}" for e in v.enumeration)
            out.append(_line("Enumeración", f"[interpretación] {enum}"))
    out += _lines("Fuente", (cite(kb, ev) for ev in v.evidence))
    if v.open_questions:
        out += _lines("Preguntas", v.open_questions)
    return out


def _history_chain(res: Resolution, chosen: str | None) -> str:
    parts = []
    for h in res.history:
        lab = _hlabel(h)
        txt = f"{lab} ({_bd_short(h.start)}{', eliminación' if h.kind == 'tombstone' else ''})"
        parts.append(f"[{txt}]" if lab == chosen else txt)
    return " → ".join(parts)


def _condition_lines(it: Item) -> list[str]:
    v = it.version
    if not isinstance(v, ValidationVersion) or v.condition is None:
        return []
    c = v.condition
    lvl = LEVEL_TXT[c.level]
    if c.expr:
        try:
            expr = dsl.unparse(dsl.parse(c.expr))
        except dsl.DslError as e:
            expr = f"{c.expr}  (no analizable por el DSL: {e})"
    else:
        expr = "(sin expresión)"
    out = [_line("Violación", f"[interpretación, {lvl}] {expr}")]
    if c.gaps:
        out.append(_line("Huecos", c.gaps))
    return out


def _field_txt(r: Related) -> str:
    if r.key is None:
        return f"{r.id} (no curado)"
    fv = r.version
    bits = [b for b in (fv.data_type, fv.length) if b] if fv else []
    meta = [x for x in ("/".join(p for p in (fv.group, fv.parent) if p) if fv else "", " ".join(bits)) if x]
    if fv and fv.occurrence:
        meta.append(fv.occurrence)
    txt = f"{r.id} {r.xml_name or '(sin xml_name)'}" + (f" ({', '.join(meta)})" if meta else "")
    return txt


def _xsd_lines(it: Item) -> list[str]:
    c = it.xsd_check
    if c is None:
        return [_line("XSD", "sin instantánea XSD registrada en el manifiesto")]
    head = f"instantánea {c.retrieved_at} (rev {c.snapshot}): {c.status}"
    out = []
    if c.anachronistic:
        out.append(_line("XSD", f"{XSD_ANACHRONISM} ({head})"))
    else:
        out.append(_line("XSD", head))
    if c.detail:
        out.append(_line("", c.detail))
    if c.enumeration is not None:
        out += _enum_lines(c.enumeration)
    return out


def _codes(codes: list[str], limit: int = 20) -> str:
    shown = ", ".join(codes[:limit])
    return (shown + (f" … (+{len(codes) - limit})" if len(codes) > limit else "")) or "(ninguno)"


def _enum_lines(e: XsdEnumeration) -> list[str]:
    """Las dos dimensiones por separado (decisión 8): documentado por MT/NT frente a aceptado por el XSD."""
    out = [
        _line(
            "",
            f"Documentado por MT/NT [interpretación]: {_codes(e.documented)}"
            + (f" ({e.documented_source})" if e.documented_source else ""),
        )
    ]
    if e.accepted is not None:
        scope = "" if e.exhaustive else " (solo se probaron los códigos documentados)"
        out.append(_line("", f"Aceptado por la instantánea XSD{scope}: {_codes(e.accepted)}"))
    elif e.detail:
        out.append(_line("", e.detail))
    diff = []
    if e.only_documented:
        diff.append(f"solo documentados: {_codes(e.only_documented)}")
    if e.only_accepted:
        diff.append(f"solo en el XSD, sin etiqueta en MT/NT: {_codes(e.only_accepted)}")
    tail = f"Enumeración: {e.status}" + (f" ({'; '.join(diff)})" if diff else "")
    if e.issues:
        tail += f" · {', '.join(e.issues)} (source_conflict; no se consolidan)"
    out.append(_line("", tail))
    return out


def _tail_lines(kb: KB, res: Resolution) -> list[str]:
    out: list[str] = []
    if res.upcoming:
        out += _lines("Próximo", res.upcoming)
    if res.pending_effects:
        txt = []
        for eid in res.pending_effects:
            if kb.has_effect(eid):
                e = kb.effect(eid)
                txt.append(f"{eid} · pendiente de curar ({e.action} {e.target or 'sin destino'})")
            else:
                txt.append(eid)
        out += _lines("Pendientes", txt)
    if res.open_issues:
        txt = []
        for iid in res.open_issues:
            i = kb.issues.get(iid)
            txt.append(f"{iid} ({i.kind}, {'bloqueante' if i.blocking else 'no bloqueante'})" if i else iid)
        out.append(_line("Issues", " · ".join(txt)))
    if res.warnings:
        out += _lines("Avisos", res.warnings)
    return out


def _xml_lines(it: Item) -> list[str]:
    x = it.xml
    if not x:
        return []
    src = {"response": "respuesta de SIFEN, dFecProc", "flag": "--processed-at"}.get(
        x.get("processing_date_source") or "", ""
    )
    proc = (
        f"procesamiento {x['processed_at']} ({src})" if x.get("processed_at") else "procesamiento DESCONOCIDO"
    )
    cdc = f" · CDC {x['cdc']}" if x.get("cdc") else ""
    out = [_line("XML", f"emisión {x['emitted_at']} (dFeEmiDE) · {proc}{cdc}")]
    if x.get("evaluated"):
        if x.get("decided"):
            verdict = VERDICT_TXT[x["verdict"]]
            code = getattr(it.version, "code", None)
            if x["verdict"] == "TRUE" and code:
                verdict += f" (SIFEN devolvería {code})"
        else:
            reason = "axis_split" if x["processing"] else "processing_date_unknown"
            verdict = f"NO DECIDIDO ({reason}): ver ambos ejes"
        out.append(_line("Veredicto", verdict))
        for name, ax in (("Emisión", x["emission"]), ("Proceso", x["processing"])):
            if ax:
                st = ax["state"].upper()
                out.append(
                    _line(name, f"{ax['at']} → {ax['version'] or 'sin versión'} ({st}): {ax['verdict']}")
                )
        if x.get("boundary"):
            out.append(_line("", f"la regla cambia el {x['boundary']}: hace falta la fecha de procesamiento"))
    vals = []
    for fid, d in x.get("values", {}).items():
        shown = d["value"] if d["present"] else "(ausente)"
        vals.append(f"{fid} {d['xml_name']} = {shown}")
    if vals:
        out.append(_line("Valores", " · ".join(vals)))
    out += _lines("No legibles", (f"{f}: {why}" for f, why in x.get("unreadable", {}).items()))
    out += _lines("Notas", x.get("notes", []))
    sv = x.get("schema_validation")
    if sv:
        head = f"instantánea {sv['retrieved_at']} (rev {sv['snapshot']}): {sv['detail']}"
        out.append(_line("Esquema", head))
        out += [_line("", e) for e in sv.get("errors", [])]
    else:
        out.append(_line("Esquema", "sin instantánea XSD: el XML no se validó"))
    out += _lines("Aviso", x.get("warnings", []))
    return out


def _render_entity(kb: KB, it: Item) -> list[str]:
    res = it.resolution
    assert res is not None
    out = _header(kb, it, res)
    out += _xml_lines(it)
    out += _version_lines(kb, it, res)
    out += _literal_lines(kb, it)
    if res.history:
        chosen = version_label(it.version) if it.version is not None else None
        out.append(_line("Historia", _history_chain(res, chosen)))
    out += _condition_lines(it)
    if it.related:
        out.append(_line("Campos", " · ".join(_field_txt(r) for r in it.related)))
        out += [_line("", f"{r.id}: XSD {r.xsd}") for r in it.related if r.xsd]
    if it.kind == "field" and it.key:
        users = sorted(
            k
            for k, val in kb.validations.items()
            if val.subject_field == it.key
            or any(
                (n := _condition_node(x)) is not None
                and it.entity is not None
                and it.entity.id in dsl.fields(n)
                for x in val.versions
            )
        )
        if users:
            out.append(_line("Validaciones", " · ".join(users)))
    out += _xsd_lines(it)
    out += _tail_lines(kb, res)
    return out


_TOKEN_RE = re.compile(r"\s*(?:[\w.,]+|[^\w\s])")


def word_diff(a: str, b: str, ctx: int = 6) -> str:
    """Diferencia por palabras con el espaciado original: `… igual a [-60.000.000-]{+35.000.000+} (F023 …`."""
    ta, tb = _TOKEN_RE.findall(a), _TOKEN_RE.findall(b)
    ka, kb_ = [t.strip() for t in ta], [t.strip() for t in tb]
    ops = difflib.SequenceMatcher(a=ka, b=kb_, autojunk=False).get_opcodes()
    out = ""
    for n, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            seg = ta[i1:i2]
            first, last = n == 0, n == len(ops) - 1
            if first and len(seg) > ctx:
                out += "…" + "".join(seg[-ctx:])
            elif last and len(seg) > ctx:
                out += "".join(seg[:ctx]) + " …"
            elif not first and not last and len(seg) > 2 * ctx:
                out += "".join(seg[:ctx]) + " …" + "".join(seg[-ctx:])
            else:
                out += "".join(seg)
            continue
        old, new_ = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        lead = (old or new_)[: len(old or new_) - len((old or new_).lstrip())]
        out += lead
        if old.strip():
            out += "[-" + old.strip() + "-]"
        if new_.strip():
            out += "{+" + new_.strip() + "+}"
    return out.strip()


def _attr_change(attr: str, a: Any, b: Any) -> str:
    if isinstance(a, str) and isinstance(b, str):
        if len(a) <= 40 and len(b) <= 40:
            return f"{attr}: «{a}» → «{b}»"
        return f"{attr}: {word_diff(a, b)}"
    if attr == "condition" and isinstance(a, dict) and isinstance(b, dict):
        bits = []
        if a.get("expr") != b.get("expr"):
            bits.append(word_diff(str(a.get("expr") or ""), str(b.get("expr") or "")))
        if a.get("level") != b.get("level"):
            bits.append(f"nivel {a.get('level')} → {b.get('level')}")
        if a.get("gaps") != b.get("gaps"):
            bits.append("huecos modificados")
        return f"condition: {'; '.join(bits) or 'interpretación modificada'}"

    def j(x: Any) -> str:
        s = json.dumps(x, ensure_ascii=False, sort_keys=True)
        return s if len(s) <= 120 else s[:117] + "…"

    return f"{attr}: {j(a)} → {j(b)}"


def _render_history(kb: KB, it: Item) -> list[str]:
    assert it.key is not None and it.timeline is not None and it.resolution is not None
    env = it.resolution.env
    out = [
        f"HISTORIA · {_ident(it)} ({env}; fronteras derivadas con su fuente) — no es la resolución en una "
        "fecha: para eso, sin --history"
    ]
    prev_dump: dict[str, Any] | None = None
    for n, t in enumerate(it.timeline, start=1):
        start = Boundary.model_validate(t["start"]) if t["start"] else None
        end = Boundary.model_validate(t["end"]) if t["end"] else None
        kind = "eliminación" if t["kind"] == "tombstone" else "versión"
        when = (
            f"desde {_bd(start, open_txt='sin fecha')} · hasta {_bd(end)}"
            if start
            else "prospectiva: sin fecha"
        )
        out.append(f"  {n}. {t['label']} · {kind} · {when}")
        oth = t["other_env"]
        ostart = Boundary.model_validate(oth["start"]) if oth["start"] else None
        out.append(_line("", f"{oth['env']}: desde {_bd(ostart, open_txt='sin fecha')}"))
        for e in t["effects"]:
            dates = (
                " · ".join(f"{k} «{d['literal']}»" for k, d in e["dates"].items() if d) or "sin calendario"
            )
            out.append(_line("", f"efecto {e['id']} ({e['action']}) «{e['verb_literal']}» · {dates}"))
        out.append(_line("", f"fuente {t['source']}"))
        cur = t["version"]
        if prev_dump is not None and t["changed"] is not None:
            if not t["changed"]:
                out.append(_line("", "cambia: nada en el contenido"))
            for attr in t["changed"]:
                out.append(_line("", "cambia " + _attr_change(attr, prev_dump.get(attr), cur.get(attr))))
        prev_dump = cur
    pend = [e for e in kb.effects_targeting(it.key) if e.disposition == "pending"]
    if pend:
        out += _lines("Pendientes", (f"{e.id} · pendiente de curar ({e.action})" for e in pend))
    ent = it.entity
    subjects = {it.key}
    if ent is not None:
        for v in ent.versions:
            if v.introduced_by != "baseline":
                for eid in v.introduced_by:
                    subjects.add(eid)
                    if kb.has_effect(eid):
                        subjects.add(kb.doc_of(eid).id)
    iss = [
        i
        for i in sorted(kb.issues.values(), key=lambda i: i.id)
        if any(s.subject in subjects for s in i.affects)
    ]
    if iss:
        out += _lines(
            "Issues",
            (
                f"{i.id} ({i.kind}, {i.status}, {'bloqueante' if i.blocking else 'no bloqueante'}): {i.statement}"
                for i in iss
            ),
        )
    return out


def _render_index(kb: KB, it: Item) -> list[str]:
    res = it.resolution
    assert res is not None
    out = [f"NOT_CURATED · {it.key or it.term} {_ctx(kb, res)}"]
    out.append(_line("Estado", f"NOT_CURATED: {STATE_TXT['not_curated']}"))
    out.append(_line("Aviso", NOT_CURATED_WARNING))
    out += _xml_lines(it)
    out.append(
        _line(
            "Menciones",
            f"{len(res.mentions)} en raw/, por fecha de producción del documento "
            "(la más reciente primero; nunca por número de NT):",
        )
    )
    for n, m in enumerate(res.mentions, start=1):
        out.append(_line("", f"{n}. {_mention_head(kb, m)}"))
        out.append(_line("", f"   «{m.excerpt}»"))
    rest = [w for w in res.warnings if w != NOT_CURATED_WARNING]
    out += _lines("Avisos", rest)
    return out


def _mention_head(kb: KB, m: Mention) -> str:
    if m.prod_date is None:
        when = "sin fecha de producción"
    else:
        when = f"producción {m.prod_date}"
        if m.doc not in kb.documents:
            when += " (literal de raw/, sin curar)"
    return f"{m.doc} rev {m.rev} · {_page_txt(m.page_printed, m.page_pdf)} · {when}"


def _render_document(kb: KB, it: Item) -> list[str]:
    c = it.document
    assert c is not None
    if c["curated"]:
        head = f"{c['id']} · {c['title']} ({c['kind']}) · ficha curada (alcance: {c['curation_scope']})"
        out = [head] if not c["uncurated_revision"] else [f"REVISIÓN SIN CURAR · {head}"]
    else:
        out = [f"SIN CURAR · {c['id']} · registrado en el manifiesto, sin ficha en kb/documents/"]
    if c["uncurated_revision"]:
        out.append(_line("Estado", c["uncurated_revision"]))
    revs = []
    for r in c["revisions"]:
        flags = [x for x, on in (("curada", r["curated"]), ("última", r["latest"])) if on]
        if not r["curated"]:
            flags.append("sin curar")
        up = (
            f"subida {r['portal_t'][:10]} (?t= del portal: subida, no vigencia)"
            if r["portal_t"]
            else "sin ?t="
        )
        revs.append(
            f"{r['sha12']} · {', '.join(flags)} · {up} · descargada {r['retrieved_at'][:10]} · "
            f"raw/: {'sí' if r['raw'] else 'no'}" + (f" · {r['note']}" if r["note"] else "")
        )
    out += _lines("Revisiones", revs or ["ninguna en el manifiesto"])
    if c["curated"]:
        dd = c["document_date"]
        if dd:
            out.append(
                _line(
                    "Fecha", f"«{dd['literal']}» → {dd['date']} (informativa; {_stated_txt(dd['stated_in'])})"
                )
            )
        if c["change_period"]:
            a, b = c["change_period"]
            out.append(
                _line("Cambios", f"desde «{a['literal']}» al «{b['literal']}» (rango del inicio aproximado)")
            )
        if c["schedule"]:
            cal = []
            for env in ENVS:
                s = c["schedule"][env]
                cal.append(
                    f"{env} {s['date'] or 'a definir'} «{s['literal']}» ({_stated_txt(s['stated_in'])})"
                    if s
                    else f"{env}: no declarada"
                )
            out += _lines("Calendario", cal)
        else:
            out.append(
                _line("Calendario", "sin calendario: inicio aproximado (MT y NT 001–012; supuesto A1)")
            )
        if c["superseded_by"]:
            s = c["superseded_by"]
            out.append(_line("Reemplazo", f"{s['doc']} desde {s['since']} (declarado en el documento)"))
        effs = []
        for e in c["effects"]:
            state = {"applied": "aplicado", "pending": "PENDIENTE de curar", "not_modeled": "no modelado"}[
                e["state"]
            ]
            if e["state"] == "applied":
                state += (
                    f" → {', '.join(e['versions'])}"
                    if e["versions"]
                    else " SIN versión que lo cite (ver `sifen check`)"
                )
            starts = " · ".join(
                f"{env} {s['date'] or 'sin fecha'} ({BASIS_TXT.get(s['basis'], s['basis'])})"
                for env, s in e["starts"].items()
            )
            effs.append(
                f"{e['id']} · {e['action']} {e['target'] or 'sin destino'} · {state} · inicio: {starts}"
            )
            effs.append(f"   «{e['verb_literal']}»" + (f" · nota: {e['note']}" if e["note"] else ""))
        out += _lines("Efectos", effs or ["ninguno"])
    else:
        rd = c["raw_dates"]
        if rd:
            lits = " · ".join(
                f"{k} «{rd[k]['literal']}»" for k in ("fecha", "test", "prod") if rd[k]["literal"]
            )
            out.append(_line("Fechas raw", f"{lits or 'sin fechas'} (p. {rd['page']} PDF)"))
            out.append(
                _line("", "literales extraídos de raw/, SIN CURAR: no resuelven vigencia (`sifen draft`)")
            )
        out.append(_line("Efectos", "ninguno curado"))
    if c["issues"]:
        out += _lines(
            "Issues",
            (
                f"{i['id']} ({i['kind']}, {i['status']}, {'bloqueante' if i['blocking'] else 'no bloqueante'}): "
                f"{i['statement']}"
                for i in c["issues"]
            ),
        )
    return out


def render_explain(kb: KB, ans: Answer, today: date) -> str:
    blocks: list[list[str]] = []
    for it in ans.items:
        if it.kind == "index":
            blocks.append(_render_index(kb, it))
        elif it.kind == "document":
            blocks.append(_render_document(kb, it))
        elif it.timeline is not None:
            blocks.append(_render_history(kb, it))
        else:
            blocks.append(_render_entity(kb, it))
    footer = _lines("Generales", ans.warnings) if ans.warnings else []
    footer += [_line("Fuentes", sources_txt(kb, today)), _line("KB", kb_snapshot_txt(kb))]
    text = "\n\n".join("\n".join(b) for b in blocks)
    return text + "\n" + "\n".join(footer) + "\n"


# --- status --------------------------------------------------------------------------------------------
def status(kb: KB, *, today: date) -> dict[str, Any]:
    """Qué sabe y qué no sabe la KB (funciona sin `kb/`: entregable 0)."""
    h = kb.horizon()
    grace = kb.meta.horizon_grace_days if kb.meta else None
    limit = h + timedelta(days=grace or 0) if h else None
    clean = [c for c in kb.manifest.checks if not c.unregistered]
    last_clean = max((c.at for c in clean), default=None)
    unregistered = [
        {
            "at": _iso(c.at),
            "scope": list(c.scope),
            "unregistered": list(c.unregistered),
            "pending": last_clean is None or c.at > last_clean,
        }
        for c in kb.manifest.checks
        if c.unregistered
    ]
    docs = sorted({r.doc for r in kb.manifest.revisions})
    uncurated: list[dict[str, Any]] = []
    warnings: list[str] = []
    for d in docs:
        latest = kb.latest_revision(d)
        assert latest is not None
        ficha = kb.documents.get(d)
        raw = has_raw_text(kb, d)
        if ficha is None:
            uncurated.append(
                {"doc": d, "reason": "no_card", "latest": sha12(latest.sha256), "current": None, "raw": raw}
            )
        elif latest.sha256 != ficha.current_revision:
            uncurated.append(
                {
                    "doc": d,
                    "reason": "new_revision",
                    "latest": sha12(latest.sha256),
                    "current": sha12(ficha.current_revision),
                    "raw": raw,
                }
            )
    for d, ficha in sorted(kb.documents.items()):
        if not any(r.sha256 == ficha.current_revision for r in kb.revisions_of(d)):
            warnings.append(f"{d}: current_revision no está en el manifiesto (ver `sifen check`)")
    pending = []
    for d in sorted(kb.documents.values(), key=lambda x: x.id):
        for e in d.effects:
            if e.disposition != "pending":
                continue
            starts: dict[str, Any] = {}
            for env in ENVS:
                try:
                    starts[env] = _start_json(kb, e.id, env)
                except TemporalDataError as err:
                    starts[env] = {"date": None, "basis": f"error de datos: {err}"}
            pending.append({"id": e.id, "action": e.action, "target": e.target, "starts": starts})
    issues = sorted(kb.issues.values(), key=lambda i: i.id)
    snap = find_snapshot(kb)
    meta = kb.meta
    return {
        "today": _iso(today),
        "kb": kb_info(kb),
        "horizon": {
            "sources_checked_at": _iso(h),
            "days_since": (today - h).days if h else None,
            "grace_days": grace,
            "limit": _iso(limit),
            "expired": (today > limit) if limit else True,
        },
        "checks": {
            "total": len(kb.manifest.checks),
            "last_clean": _iso(last_clean),
            "unregistered": unregistered,
        },
        "manifest": {"documents": len(docs), "revisions": len(kb.manifest.revisions)},
        "revisions_uncurated": uncurated,
        "raw_missing": [d for d in docs if not has_raw_text(kb, d)],
        "xsd_snapshot": (
            {
                "sha12": snap.sha12,
                "retrieved_at": _iso(snap.day),
                "path": snap.path.relative_to(kb.root).as_posix(),
            }
            if snap and snap.path.is_relative_to(kb.root)
            else None
        ),
        "pending_effects": pending,
        "blocking_issues": [_issue_brief(i) for i in issues if i.status == "open" and i.blocking],
        "open_issues": [i.id for i in issues if i.status == "open"],
        "coverage": {
            "coverage_from": _iso(meta.coverage_from) if meta else None,
            "date_axis_default": meta.date_axis_default if meta else None,
            "baseline": f"{meta.baseline_doc} {sha12(meta.baseline_sha256)}" if meta else None,
        },
        "assumptions_unverified": (
            [{"id": a.id, "text": a.text} for a in meta.assumptions if a.status == "unverified"]
            if meta
            else []
        ),
        "documents_curated": [
            {"id": d.id, "curation_scope": d.curation_scope, "current_revision": sha12(d.current_revision)}
            for d in sorted(kb.documents.values(), key=lambda x: x.id)
        ],
        "entities": {"fields": len(kb.fields), "validations": len(kb.validations)},
        "has_kb_dir": (kb.root / "kb").is_dir(),
        "errors": list(kb.errors),
        "warnings": warnings,
    }


def render_status(kb: KB, st: dict[str, Any]) -> str:
    today = date.fromisoformat(st["today"])
    hz = st["horizon"]
    out = [f"sifen status · {today} (America/Asuncion)"]
    src = sources_txt(kb, today)
    if hz["grace_days"] is not None and hz["limit"]:
        src += f" · gracia {hz['grace_days']} días (hasta {hz['limit']})"
    elif hz["sources_checked_at"]:
        src += " · gracia: sin kb/_meta.yaml (0 días)"
    out.append(_line("Fuentes", src))
    ck = st["checks"]
    pend_ck = [c for c in ck["unregistered"] if c["pending"]]
    ck_txt = f"{ck['total']} registrados · último limpio {ck['last_clean'] or 'ninguno'}"
    ck_txt += (
        f" · {len(pend_ck)} con URLs sin registrar posteriores al último limpio"
        if pend_ck
        else " · sin URLs sin registrar pendientes"
    )
    out.append(_line("Chequeos", ck_txt))
    for c in pend_ck:
        out += _lines("", (f"{c['at']}: {u}" for u in c["unregistered"]))
    mf = st["manifest"]
    out.append(_line("Manifiesto", f"{mf['documents']} documentos, {mf['revisions']} revisiones"))
    no_card = [u["doc"] for u in st["revisions_uncurated"] if u["reason"] == "no_card"]
    newrev = [u for u in st["revisions_uncurated"] if u["reason"] == "new_revision"]
    if not st["revisions_uncurated"]:
        out.append(
            _line("Sin curar", "ninguna revisión: todo el manifiesto tiene ficha con su revisión vigente")
        )
    if no_card:
        out.append(_line("Sin curar", f"{len(no_card)} sin ficha en kb/documents/: {compress_docs(no_card)}"))
    for u in newrev:
        out.append(
            _line(
                "Sin curar",
                f"{u['doc']}: revisión {u['latest']} del manifiesto sin curar (kb/ usa {u['current']})",
            )
        )
    missing = st["raw_missing"]
    with_raw = mf["documents"] - len(missing)
    raw_txt = f"{with_raw} de {mf['documents']} documentos con texto extraído"
    if missing:
        raw_txt += f" · sin raw/: {', '.join(missing)}"
    out.append(_line("raw/", raw_txt))
    xs = st["xsd_snapshot"]
    out.append(
        _line(
            "XSD",
            f"instantánea {xs['retrieved_at']} (rev {xs['sha12']}, {xs['path']})"
            if xs
            else "sin instantánea registrada",
        )
    )
    if st["pending_effects"]:
        out += _lines(
            "Pendientes",
            (
                f"{p['id']} · {p['action']} {p['target'] or 'sin destino'} · "
                + " · ".join(f"{env} {s['date'] or 'sin fecha'}" for env, s in p["starts"].items())
                for p in st["pending_effects"]
            ),
        )
    else:
        out.append(_line("Pendientes", "ningún efecto pendiente"))
    if st["blocking_issues"]:
        out += _lines(
            "Issues",
            (f"{i['id']} ({i['kind']}, bloqueante): {i['statement']}" for i in st["blocking_issues"]),
        )
    else:
        out.append(
            _line("Issues", f"ningún Issue bloqueante abierto ({len(st['open_issues'])} abiertos en total)")
        )
    cov = st["coverage"]
    if cov["coverage_from"]:
        out.append(
            _line(
                "Cobertura",
                f"desde {cov['coverage_from']} · eje por defecto: {cov['date_axis_default']} · línea base {cov['baseline']}",
            )
        )
    else:
        out.append(
            _line("Cobertura", "sin kb/_meta.yaml: no hay coverage_from ni gracia del horizonte declarados")
        )
    if st["assumptions_unverified"]:
        out += _lines(
            "Supuestos", (f"{a['id']} (sin verificar): {a['text']}" for a in st["assumptions_unverified"])
        )
    elif not cov["coverage_from"]:
        out.append(_line("Supuestos", "sin kb/_meta.yaml: A1 y A2 del diseño todavía no están registrados"))
    else:
        out.append(_line("Supuestos", "ninguno sin verificar"))
    if st["documents_curated"]:
        scopes = Counter(d["curation_scope"] for d in st["documents_curated"])
        out.append(
            _line(
                "Curado",
                f"{len(st['documents_curated'])} documentos ("
                + ", ".join(f"{k} {n}" for k, n in sorted(scopes.items()))
                + f") · {st['entities']['fields']} campos · {st['entities']['validations']} validaciones",
            )
        )
    else:
        nokb = "sin kb/" if not st["has_kb_dir"] else "kb/ sin fichas"
        out.append(
            _line("Curado", f"nada ({nokb}): solo modo índice (not_curated) sobre raw/ — entregable 0")
        )
    out += _lines("Avisos", st["warnings"])
    if st["errors"]:
        out += _lines("ERRORES", [f"{len(st['errors'])} errores de carga de la KB:", *st["errors"]])
    out.append(_line("KB", kb_snapshot_txt(kb)))
    return "\n".join(out) + "\n"


# --- CLI -----------------------------------------------------------------------------------------------
def _load(args: argparse.Namespace) -> KB:
    root = getattr(args, "root", None)
    if root is not None and not Path(root).is_dir():
        raise UsageError(f"--root: {root} no es una carpeta")
    return load_kb(Path(root) if root else None)


def _fail(e: ExplainError, as_json: bool, prog: str) -> int:
    print(f"{prog}: {e.message}", file=sys.stderr)
    for d in e.details:
        print(f"  {d}", file=sys.stderr)
    if e.suggestions:
        print(f"  ¿Quiso decir?: {', '.join(e.suggestions)}", file=sys.stderr)
    if as_json:
        err = {"kind": e.kind, "message": e.message, "details": e.details, "suggestions": e.suggestions}
        print(json.dumps({"error": err}, ensure_ascii=False, indent=2))
    return e.exit_code


def _guard(prog: str, as_json: bool, fn: Callable[[], int]) -> int:
    try:
        return fn()
    except ExplainError as e:
        return _fail(e, as_json, prog)
    except TemporalDataError as e:
        msg = f"error de datos en la KB: {e}. Corregir kb/ (ver `sifen check`); no se responde"
        return _fail(DataError(msg), as_json, prog)
    except xsd.XsdError as e:
        return _fail(XmlError(str(e)), as_json, prog)
    except Exception as e:  # nunca un traceback (SIFEN_DEBUG=1 lo muestra)
        if os.environ.get("SIFEN_DEBUG"):
            raise
        return _fail(ExplainError(f"error interno inesperado ({type(e).__name__}): {e}"), as_json, prog)


def cmd_explain(args: argparse.Namespace) -> int:
    """Punto de entrada de `sifen explain`."""
    as_json = bool(getattr(args, "json", False))

    def run() -> int:
        if args.xml and args.at:
            raise UsageError(
                "--xml no se combina con --at: con un XML rigen su fecha de emisión (dFeEmiDE) y la de "
                "procesamiento (--response o --processed-at)"
            )
        at = parse_day(args.at, "--at") if args.at else None
        processed = parse_day(args.processed_at, "--processed-at") if args.processed_at else None
        kb = _load(args)
        if kb.errors:
            raise KBLoadError(
                f"la KB tiene {len(kb.errors)} errores de carga: corregirlos antes de consultar (`sifen check`)",
                details=kb.errors,
            )
        today = today_paraguay()
        defaulted = at is None and not args.xml
        if defaulted:
            at = today
        ans = explain(
            kb,
            args.term,
            at=at,
            env=args.env,
            history=bool(args.history),
            xml=args.xml,
            response=args.response,
            processed_at=processed,
            show_pii=bool(args.show_pii),
            now=at if defaulted else None,
        )
        if (defaulted or args.xml) and not xsd.paraguay_tz_is_exact():
            ans.warnings.append(TZ_APPROX_WARNING)
        if as_json:
            print(json.dumps(ans.as_json(), ensure_ascii=False, indent=2))
        else:
            print(render_explain(kb, ans, today), end="")
        return EXIT_OK

    return _guard("sifen explain", as_json, run)


def cmd_status(args: argparse.Namespace) -> int:
    """Punto de entrada de `sifen status` (con errores de carga: muestra el estado y sale con 1)."""
    as_json = bool(getattr(args, "json", False))

    def run() -> int:
        kb = _load(args)
        st = status(kb, today=today_paraguay())
        if as_json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
        else:
            print(render_status(kb, st), end="")
        return EXIT_ERROR if kb.errors else EXIT_OK

    return _guard("sifen status", as_json, run)

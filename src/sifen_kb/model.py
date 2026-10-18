"""Modelos del canónico (`kb/`), del manifiesto de fuentes y del contrato de salida.

Referencia de diseño: docs/arquitectura.md §F. Regla: cada concepto existe porque un caso
real de SIFEN lo exige. Lo derivable (inicio/fin de vigencia, "aplicado", índices) NO se
almacena: lo calcula `temporal` / `load`.

Convenciones:
- Todos los escalares llegan como `str` desde el `KBLoader`; Pydantic es la única
  autoridad de tipos (fechas, enteros). Los identificadores y códigos son SIEMPRE `str`.
- Los literales (mensaje, observación, longitud…) se copian con `sifen draft` desde
  `raw/` y un test exige igualdad con la celda citada.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from sifen_kb.normalize import parse_date_literal


class M(BaseModel):
    """Base: clave desconocida = error; inmutable; sin strip (el literal se conserva intacto)."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


def _pat(pattern: str) -> type[str]:
    return Annotated[str, StringConstraints(pattern=pattern)]  # type: ignore[return-value]


# --- Identificadores -------------------------------------------------------------------------
CORE = r"[A-Z][A-Z0-9_]*"
"""Alfabeto único del DocId dentro de RowRef, CellRef y EffectId."""

Sha256 = _pat(r"^[0-9a-f]{64}$")
Sha12 = _pat(r"^[0-9a-f]{12}$")
Md5 = _pat(r"^[0-9a-fA-F]{32}$")
DocId = _pat(r"^(MT_V150|NT_\d{3}|XSD_DIR|XSD_RAR|CHECKSUM_MT|TABLA_GEO|(GUIA|COM|NORMA)_[A-Z0-9_]+)$")
Ctx = Literal["DE"]
SifenId = _pat(r"^[A-Z][A-Za-z]{0,6}\d{1,3}[a-z]?$")
SifenCode = _pat(r"^\d{4}$")
FieldKey = _pat(r"^field:[A-Z][A-Z-]*:\w+$")
ValKey = _pat(r"^val:[A-Z][A-Z-]*:\w+$")
EffectId = _pat(rf"^{CORE}#\d+$")
RowRef = _pat(rf"^raw:{CORE}@[0-9a-f]{{12}}:p\d+:[^:#~]+(~\d+)?$")
CellRef = _pat(rf"^raw:{CORE}@[0-9a-f]{{12}}:p\d+:[^:#~]+(~\d+)?#[a-z_]+$")
CaseRef = _pat(r"^case:\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
IssueId = _pat(r"^ISS-\d{4}$")
Env = Literal["test", "prod"]
ENVS: tuple[Env, ...] = ("test", "prod")

ROWREF_RE = re.compile(
    rf"^raw:(?P<doc>{CORE})@(?P<sha12>[0-9a-f]{{12}}):p(?P<page>\d+):(?P<key>[^:#~]+)(?:~(?P<occ>\d+))?"
    rf"(?:#(?P<attr>[a-z_]+))?$"
)


def parse_ref(ref: str) -> dict[str, str | int | None]:
    """Descompone un RowRef/CellRef: doc, sha12, page (int), key, occ (int, 1 por defecto), attr."""
    m = ROWREF_RE.match(ref)
    if not m:
        raise ValueError(f"referencia raw inválida: {ref!r}")
    d = m.groupdict()
    return {
        "doc": d["doc"],
        "sha12": d["sha12"],
        "page": int(d["page"]),
        "key": d["key"],
        "occ": int(d["occ"]) if d["occ"] else 1,
        "attr": d["attr"],
    }


# --- Provenance / Evidence -------------------------------------------------------------------
class PageRef(M):
    """Cita de prosa (sin fila de tabla). Test: normalize_text(quote) contenida en la página de raw/."""

    doc: DocId
    rev: Sha12
    page_pdf: int
    page_printed: int | None = None
    quote: str


Evidence = RowRef | CellRef | PageRef


class Interpretation(M):
    """Solo para afirmaciones interpretadas (nunca literales). La revisión humana es el merge, no un campo."""

    by: Literal["tool", "llm", "human"]
    run: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _llm_needs_run(self) -> Interpretation:
        if self.by == "llm" and not self.run:
            raise ValueError("una interpretación by=llm exige `run` (curation/runs/<sesión>.yaml)")
        return self


# --- Manifiesto de fuentes (sources.manifest.yaml; lo escribe SOLO la herramienta) ----------
class SourceRevision(M):
    doc: DocId
    sha256: Sha256
    md5: Md5
    size: int
    url: str
    filename: str
    portal_t: datetime | None = None
    """Sello ?t= del portal = SUBIDA del archivo; nunca publicación ni vigencia."""
    retrieved_at: datetime
    origin: Literal["portal", "offline"]
    path: str
    """Ruta relativa en el repo: sources/<DocId>/<sha12>.<ext> (o carpeta para XSD_DIR)."""
    note: str | None = None


class SourceCheck(M):
    at: datetime
    scope: list[Literal["nt", "xsd", "tablas", "guias", "manual"]]
    unregistered: list[str] = []
    """URLs con hash nuevo o enlaces nuevos; vacío => chequeo limpio (avanza el horizonte)."""


class SourcesManifest(M):
    revisions: list[SourceRevision] = []
    checks: list[SourceCheck] = []


# --- DocumentSource ----------------------------------------------------------------------------
_A_DEFINIR = re.compile(r"(?i)a\s+definir|a\s+comunicar")


class DateStatement(M):
    """Una fecha TAL COMO la declara una fuente concreta."""

    value: date | None
    literal: str
    stated_in: CellRef | PageRef

    @model_validator(mode="after")
    def _value_matches_literal(self) -> DateStatement:
        parsed = parse_date_literal(self.literal)
        if parsed is not None:
            if self.value != parsed:
                raise ValueError(f"value {self.value} ≠ parse({self.literal!r}) = {parsed}")
        elif self.value is not None and not _A_DEFINIR.search(self.literal):
            raise ValueError(
                f"literal {self.literal!r} no es una fecha (dd/mm/aaaa, dd-mm-aaaa o «dd de mes de aaaa»): "
                "value debe ser null"
            )
        elif _A_DEFINIR.search(self.literal) and self.value is not None:
            raise ValueError("una fecha 'a definir' debe tener value: null")
        return self


class Schedule(M):
    """Calendario por ambiente: el ambiente lo da la ranura, no un campo."""

    test: DateStatement | None = None
    prod: DateStatement | None = None


class Supersession(M):
    """Reemplazo declarado A NIVEL DE DOCUMENTO (p. ej. marca de agua de NT 21 → NT 24)."""

    doc: DocId
    since: date
    stated_in: PageRef


class LegalRef(M):
    citation: str
    stated_in: Evidence


class Effect(M):
    """El "patch" de una NT: declarativo y NO ejecutable. Se verifica, no se reproduce."""

    id: EffectId
    verb_literal: str
    action: Literal["add", "modify", "remove"]
    target: FieldKey | ValKey | None = None
    declared_scope: Literal["row"] | list[str]
    acknowledged_changes: list[str] = []
    evidence: list[Evidence]
    from_revision: Sha12 | None = None
    disposition: Literal["pending", "not_modeled"] | None = None
    """None => aplicado: lo cita exactamente UNA versión (test de biyección)."""
    interpretation: Interpretation
    note: str | None = None

    @model_validator(mode="after")
    def _checks(self) -> Effect:
        if self.disposition == "not_modeled" and not self.note:
            raise ValueError(f"{self.id}: not_modeled exige `note`")
        if not self.evidence:
            raise ValueError(f"{self.id}: un efecto exige evidencia")
        if self.disposition is None and self.target is None:
            raise ValueError(f"{self.id}: un efecto aplicado exige `target`")
        return self


DocKind = Literal[
    "manual", "technical_note", "xsd_bundle", "codelist", "checksum_list", "guide", "communication", "legal"
]


class DocumentSource(M):
    """kb/documents/<DocId>.yaml: documento lógico + revisión curada + calendario por ambiente."""

    id: DocId
    kind: DocKind
    number: int | None = None
    """Identificador; NUNCA orden temporal."""
    title: str
    current_revision: Sha256
    official_md5: Md5 | None = None
    document_date: DateStatement | None = None
    change_period: tuple[DateStatement, DateStatement] | None = None
    schedule: Schedule | None = None
    """None: MT y NT 001–012 (no declaran vigencia)."""
    superseded_by: Supersession | None = None
    effects: list[Effect] = []
    curation_scope: Literal["dates_only", "pilot", "full"]

    @model_validator(mode="after")
    def _effect_ids_belong(self) -> DocumentSource:
        for e in self.effects:
            if not e.id.startswith(f"{self.id}#"):
                raise ValueError(f"efecto {e.id} no pertenece al documento {self.id}")
        ids = [e.id for e in self.effects]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.id}: ids de efecto repetidos")
        return self


# --- Condiciones -------------------------------------------------------------------------------
class Formalization(M):
    """Interpretación de la regla en el DSL. Polaridad FIJA: True => la validación se VIOLA."""

    expr: str | None
    level: Literal["full", "partial", "none"]
    gaps: str | None = None
    interpretation: Interpretation

    @model_validator(mode="after")
    def _checks(self) -> Formalization:
        if self.level != "full" and not self.gaps:
            raise ValueError("level != full exige `gaps` (qué no captura)")
        if self.level != "none" and not self.expr:
            raise ValueError("level full/partial exige `expr`")
        if self.level == "none" and self.expr:
            raise ValueError("level none no admite `expr`")
        return self


# --- Versiones materializadas (RuleVersion ≡ ValidationVersion) -------------------------------
class VersionBase(M):
    introduced_by: Literal["baseline"] | list[EffectId]
    """1..n efectos con el MISMO inicio por ambiente."""
    based_on: Literal["baseline"] | list[EffectId] | None = None
    """Predecesora TEMPORAL en producción (None solo en la versión base)."""
    kind: Literal["content", "tombstone"] = "content"
    evidence: list[Evidence]
    open_questions: list[str] = []

    @model_validator(mode="after")
    def _base_checks(self) -> VersionBase:
        if not self.evidence:
            raise ValueError("una versión exige ≥ 1 evidencia")
        if isinstance(self.introduced_by, list) and not self.introduced_by:
            raise ValueError("introduced_by no puede ser una lista vacía")
        if self.introduced_by == "baseline" and self.based_on is not None:
            raise ValueError("la versión base no tiene based_on")
        if self.introduced_by != "baseline" and self.based_on is None:
            raise ValueError("una versión introducida por un efecto exige based_on")
        return self


class EnumValue(M):
    code: str
    label: str


class FieldVersion(VersionBase):
    """Columnas LITERALES de la tabla de campos, copiadas por `sifen draft`."""

    group: str | None = None
    parent: str | None = None
    xml_name: str | None = None
    description: str | None = None
    data_type: str | None = None
    length: str | None = None
    occurrence: str | None = None
    observations: str | None = None
    enumeration: list[EnumValue] | None = None
    enumeration_interpretation: Interpretation | None = None

    @model_validator(mode="after")
    def _enum_needs_interp(self) -> FieldVersion:
        if self.enumeration and self.enumeration_interpretation is None:
            raise ValueError("enumeration es interpretación: exige enumeration_interpretation")
        return self


class Field(M):
    key: FieldKey
    context: Ctx
    id: SifenId
    versions: list[FieldVersion]

    @model_validator(mode="after")
    def _key_consistent(self) -> Field:
        if self.key != f"field:{self.context}:{self.id}":
            raise ValueError(f"key {self.key} ≠ field:{self.context}:{self.id}")
        if not self.versions:
            raise ValueError(f"{self.key}: sin versiones")
        return self


class ValidationVersion(VersionBase):
    code: SifenCode | None = None
    severity: Literal["R", "AO", "A", "N"] | None = None
    message: str | None = None
    observation: str | None = None
    condition: Formalization | None = None
    legal_basis: list[LegalRef] = []


class Validation(M):
    key: ValKey
    context: Ctx
    id: SifenId
    subject_field: FieldKey | None = None
    versions: list[ValidationVersion]

    @model_validator(mode="after")
    def _key_consistent(self) -> Validation:
        if self.key != f"val:{self.context}:{self.id}":
            raise ValueError(f"key {self.key} ≠ val:{self.context}:{self.id}")
        if not self.versions:
            raise ValueError(f"{self.key}: sin versiones")
        return self


EntityKey = FieldKey | ValKey


# --- Issue, Case, corrida LLM, metadatos -------------------------------------------------------
class IssueScope(M):
    subject: FieldKey | ValKey | EffectId | DocId
    env: Env | None = None
    since: date | None = None
    until: date | None = None


IssueKind = Literal[
    "source_conflict",
    "undeclared_change",
    "ambiguity",
    "temporal",
    "erratum",
    "observed_vs_documented",
    "code_collision",
    "curation_error",
]


class Issue(M):
    """kb/issues/ISS-NNNN.yaml. Un conflicto es un dato, no un fallo."""

    id: IssueId
    kind: IssueKind
    affects: list[IssueScope]
    statement: str
    evidence: list[Evidence | CaseRef] = []
    blocking: bool
    policy: str | None = None
    corrects: list[str] = []
    status: Literal["open", "resolved"]
    resolution: str | None = None

    @model_validator(mode="after")
    def _checks(self) -> Issue:
        if self.status == "resolved" and not self.resolution:
            raise ValueError(f"{self.id}: resolved exige `resolution`")
        if not self.affects:
            raise ValueError(f"{self.id}: affects vacío")
        return self


class Case(M):
    """Frontmatter de cases/AAAA/*.md. Evidencia observada del servidor; NUNCA normativa."""

    id: str
    origin: Literal["observed", "synthetic"]
    env: Env
    document_type: str
    kb_snapshot: str
    emitted_at: date | None = None
    processed_at: date | None = None
    codes_received: list[SifenCode]
    """NO exhaustivo: en el rechazo SIFEN informa el primer error (MT §12)."""
    entities: list[FieldKey | ValKey] = []
    status: Literal["open", "solved", "unexplained"]
    contradicts_kb: IssueId | None = None
    sanitized: Literal[True]


class FileHash(M):
    path: str
    sha256: Sha256


class CurationRun(M):
    """curation/runs/<sesión>.yaml: lo arman hooks de Claude Code, no el agente."""

    session_id: str
    started_at: datetime
    base_commit: str | None = None
    tool: str
    model: str | None = None
    prompt_path: str | None = None
    instructions_sha256: Sha256 | None = None
    inputs: list[FileHash] = []
    outputs: list[FileHash] = []


class Assumption(M):
    id: str
    text: str
    status: Literal["unverified", "confirmed", "refuted"]


class KBMeta(M):
    """kb/_meta.yaml (protegido: el LLM no lo edita)."""

    baseline_doc: DocId
    baseline_sha256: Sha256
    coverage_from: date
    horizon_grace_days: int
    date_axis_default: Literal["processing", "emission"]
    assumptions: list[Assumption] = []


# --- Salida del resolvedor (contrato de `explain --json`; no se almacena) --------------------
Basis = Literal["baseline", "approx", "stated"]

ResolutionState = Literal[
    "in_force", "removed", "not_yet_existing", "undetermined", "outside_coverage", "not_curated"
]
Reason = Literal[
    "pending_effect",
    "blocking_issue",
    "revision_not_curated",
    "beyond_horizon",
    "processing_date_unknown",
    "axis_split",
    "test_date_missing",
]


class Boundary(M):
    date: date | None
    """None = línea base (sin fecha)."""
    basis: Basis


class HistoryEntry(M):
    introduced_by: Literal["baseline"] | list[EffectId]
    kind: Literal["content", "tombstone"]
    start: Boundary | None
    """None = prospectiva (fecha 'a definir' o sin fecha en ese ambiente)."""
    code: str | None = None
    summary: str | None = None


class XsdEnumeration(M):
    """Dos dimensiones separadas (decisión 8 del usuario, 2026-10-17): lo que DOCUMENTAN el MT/NT
    (códigos de la `enumeration` interpretada de la versión) y lo que ACEPTA la instantánea XSD. No
    se consolidan ni se inventan etiquetas para los valores que solo acepta el XSD."""

    status: Literal["match", "mismatch", "not_checked"]
    documented: list[str]
    documented_source: str | None = None
    accepted: list[str] | None = None
    """None: la instantánea no permite enumerarlos (ver `detail`)."""
    exhaustive: bool = False
    only_documented: list[str] = []
    only_accepted: list[str] = []
    issues: list[IssueId] = []
    """Issues `source_conflict` del campo (la discrepancia es un dato, no un fallo)."""
    detail: str | None = None


class XsdCheck(M):
    snapshot: Sha12
    retrieved_at: date
    status: Literal["match", "mismatch", "not_checked"]
    """`mismatch` si difiere la ocurrencia o la enumeración."""
    anachronistic: bool
    detail: str | None = None
    enumeration: XsdEnumeration | None = None
    """Solo campos con `enumeration` curada (C002, D208…)."""


class Mention(M):
    doc: DocId
    rev: Sha12
    page_pdf: int
    page_printed: int | None = None
    excerpt: str
    prod_date: date | None = None


class Resolution(M):
    key: str | None
    """FieldKey | ValKey; None en modo índice (término no curado)."""
    at: date
    env: Env
    axis: Literal["processing", "emission"]
    state: ResolutionState
    reasons: list[Reason] = []
    version_index: int | None = None
    """Índice de la versión elegida en `versions` de la entidad (None si no hay)."""
    interval: tuple[Boundary | None, Boundary | None] | None = None
    source: str | None = None
    history: list[HistoryEntry] = []
    upcoming: list[str] = []
    pending_effects: list[str] = []
    open_issues: list[str] = []
    mentions: list[Mention] = []
    warnings: list[str] = []
    sources_checked_at: date | None = None
    processing_date_source: Literal["response", "flag", "unknown"] | None = None


# --- Event / Service / Code: definidos, NO implementados en el MVP (Fase 4) ------------------
class EventTypeVersion(VersionBase):
    actor: Literal["emisor", "receptor", "set", "automatico"]
    deadline_literal: str | None = None


class EventType(M):
    context: str
    versions: list[EventTypeVersion]


class ServiceVersion(VersionBase):
    name: str
    mode: Literal["sync", "async", "query"]
    path_literal: str
    limits_literal: str | None = None


class Service(M):
    key: str
    versions: list[ServiceVersion]


class Code(M):
    """Canónico SOLO para códigos sin fila de validación (p. ej. 0364, 0422)."""

    code: SifenCode
    kind: Literal["documented_outside_tables", "observed_only"]
    meaning: str
    evidence: list[Evidence | CaseRef]

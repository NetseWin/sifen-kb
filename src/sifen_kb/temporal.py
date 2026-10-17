"""Resolvedor temporal (docs/arquitectura.md §G): qué versión rige en una fecha y un ambiente.

Es la pieza donde un error silencioso produce un "vigente" falso. Reglas que lo garantizan:

- Funciones puras sobre `KB`; nada de lo que se calcula aquí se almacena.
- Solo ordenan las FECHAS derivadas (G.2). El número de NT nunca participa.
- Intervalos semiabiertos `[desde, hasta)`: el día del cambio ya rige lo nuevo.
- Ante la duda, `undetermined` con motivos explícitos (`reasons`); nada futuro queda oculto
  (`upcoming` lista versiones futuras, prospectivas y pendientes futuros o sin fecha).
- Una inconsistencia de datos (dos versiones distintas con el mismo inicio, un efecto que no
  existe, una `from_revision` fuera del manifiesto) es una excepción, nunca una respuesta.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from sifen_kb.load import KB
from sifen_kb.mentions import find_mentions, has_raw_text, key_terms, mentioning_docs
from sifen_kb.model import (
    Boundary,
    DocumentSource,
    Effect,
    Env,
    Field,
    FieldVersion,
    HistoryEntry,
    Issue,
    IssueScope,
    KBMeta,
    PageRef,
    Resolution,
    SourceCheck,
    SourceRevision,
    SourcesManifest,
    Validation,
    ValidationVersion,
    parse_ref,
)
from sifen_kb.normalize import sha12

PRE_COVERAGE = date(1900, 1, 1)
"""Inicio aproximado de un documento sin fecha ni calendario: anterior a todo (supuesto A1)."""
BASELINE_START = date.min
"""Solo para ordenar la línea base; la salida dice "línea base", nunca 0001-01-01."""

StartBasis = Literal["baseline", "approx", "stated", "missing_test", "undated"]
"""Base de un inicio: las tres de `Basis` y, sin fecha, `missing_test` (test no declarado) o
`undated` ("a definir" o producción no declarada)."""
Start = tuple[date | None, StartBasis]
Axis = Literal["processing", "emission"]
Version = FieldVersion | ValidationVersion
Entity = Field | Validation

NOT_CURATED_WARNING = "vigencia no resuelta: una mención posterior puede modificar o eliminar la regla"

_BASIS_TXT: dict[str, str] = {
    "baseline": "línea base",
    "approx": "aproximada",
    "stated": "declarada",
    "missing_test": "test sin fecha declarada",
    "undated": "fecha a definir o no declarada",
}
_NON_CONTENT = {"introduced_by", "based_on", "evidence", "kind", "open_questions"}


class TemporalDataError(ValueError):
    """Inconsistencia de datos que impide resolver: se corrige la KB, no se responde."""


# --- Construcción --------------------------------------------------------------------------------
def build_kb(
    root: Path | str,
    *,
    meta: KBMeta | None,
    documents: Iterable[DocumentSource] = (),
    fields: Iterable[Field] = (),
    validations: Iterable[Validation] = (),
    issues: Iterable[Issue] = (),
    manifest: SourcesManifest | None = None,
    errors: Iterable[str] = (),
    paths: dict[str, Path] | None = None,
) -> KB:
    """Arma una `KB` en memoria con su índice de efectos (el mismo que construye `load_kb`).

    El orden de los iterables es el "orden de archivos": el resolvedor no debe depender de él.
    """
    docs: dict[str, DocumentSource] = {}
    effects: dict[str, tuple[DocumentSource, Effect]] = {}
    for d in documents:
        if d.id in docs:
            raise TemporalDataError(f"documento {d.id} duplicado")
        docs[d.id] = d
        for e in d.effects:
            effects[e.id] = (d, e)
    fmap: dict[str, Field] = {}
    vmap: dict[str, Validation] = {}
    for target, items in ((fmap, fields), (vmap, validations)):
        for ent in items:
            if ent.key in target:
                raise TemporalDataError(f"entidad {ent.key} duplicada")
            target[ent.key] = ent  # type: ignore[assignment]
    return KB(
        root=Path(root),
        meta=meta,
        documents=docs,
        fields=fmap,
        validations=vmap,
        issues={i.id: i for i in issues},
        manifest=manifest or SourcesManifest(),
        errors=list(errors),
        paths=dict(paths or {}),
        _effects=effects,
    )


# --- Utilidades ------------------------------------------------------------------------------------
def version_label(v: Version) -> str:
    """`línea base` o los efectos que introducen la versión, unidos con `+`."""
    return "línea base" if v.introduced_by == "baseline" else "+".join(v.introduced_by)


def _effect(kb: KB, effect_id: str) -> tuple[DocumentSource, Effect]:
    if not kb.has_effect(effect_id):
        raise TemporalDataError(f"el efecto {effect_id} no existe en kb/documents/")
    return kb.doc_of(effect_id), kb.effect(effect_id)


def _meta(kb: KB) -> KBMeta:
    if kb.meta is None:
        raise TemporalDataError("kb/_meta.yaml ausente o inválido: no hay cobertura ni gracia de horizonte")
    return kb.meta


def document_anchor(doc: DocumentSource) -> date | None:
    """Desde cuándo existe el documento: su `document_date` o, si falta, su menor fecha declarada."""
    if doc.document_date is not None and doc.document_date.value is not None:
        return doc.document_date.value
    vals = []
    if doc.schedule is not None:
        vals = [s.value for s in (doc.schedule.test, doc.schedule.prod) if s is not None and s.value]
    return min(vals) if vals else None


def _upload_start(kb: KB, doc: DocumentSource, rev12: str) -> tuple[date, StartBasis]:
    revs = [r for r in kb.manifest.revisions if r.doc == doc.id and r.sha256.startswith(rev12)]
    if not revs:
        raise TemporalDataError(f"{doc.id}: from_revision {rev12} no está en el manifiesto")
    r = revs[0]
    if r.portal_t is not None:
        return r.portal_t.date(), "stated"
    # Sin ?t= del portal: la descarga es la cota superior conocida de la subida.
    return r.retrieved_at.date(), "approx"


# --- G.2: inicios ----------------------------------------------------------------------------------
def effect_start(kb: KB, effect_id: str, env: Env) -> Start:
    """Inicio de un efecto en `env` según G.2 (nunca usa la fecha de otro ambiente)."""
    doc, eff = _effect(kb, effect_id)
    if doc.schedule is None:  # MT y NT 001–012: sin calendario
        d = doc.document_date.value if doc.document_date else None
        return (d or PRE_COVERAGE, "approx")
    st = doc.schedule.prod if env == "prod" else doc.schedule.test
    if st is None:  # sin respaldo silencioso en la fecha del otro ambiente
        return (None, "missing_test" if env == "test" else "undated")
    if st.value is None:  # "a definir": prospectiva, nunca vigente
        return (None, "undated")
    if eff.from_revision:
        # G.3: la re-subida que cambió filas rige desde la subida (nunca retroactivamente); si la
        # subida fue anterior a la fecha declarada, rige desde la fecha declarada.
        up, basis = _upload_start(kb, doc, eff.from_revision)
        if up > st.value:
            return (up, basis)
    return (st.value, "stated")


def version_start(kb: KB, version: Version, env: Env) -> Start:
    """Inicio de una versión: el de sus efectos, que deben coincidir (si no, error de datos)."""
    if version.introduced_by == "baseline":
        return (BASELINE_START, "baseline")
    starts = {effect_start(kb, e, env) for e in version.introduced_by}
    if len(starts) != 1:
        detail = ", ".join(f"{e}={effect_start(kb, e, env)}" for e in version.introduced_by)
        raise TemporalDataError(
            f"versión {version_label(version)} ({env}): sus efectos tienen inicios distintos ({detail})"
        )
    return next(iter(starts))


@dataclass(frozen=True)
class _Placed:
    index: int
    version: Version
    start: date | None
    basis: StartBasis

    @property
    def label(self) -> str:
        return version_label(self.version)


def _boundary(d: date | None, basis: StartBasis) -> Boundary | None:
    if basis == "baseline":
        return Boundary(date=None, basis="baseline")
    if d is None:
        return None
    return Boundary(date=d, basis=basis)  # type: ignore[arg-type]


def _place(kb: KB, ent: Entity, env: Env) -> tuple[list[_Placed], list[_Placed]]:
    """(versiones con inicio, ordenadas por fecha; prospectivas, ordenadas por etiqueta)."""
    dated: list[_Placed] = []
    pros: list[_Placed] = []
    for i, v in enumerate(ent.versions):
        d, basis = version_start(kb, v, env)
        (dated if d is not None else pros).append(_Placed(i, v, d, basis))
    dated.sort(key=lambda p: p.start)  # type: ignore[arg-type, return-value]
    for a, b in pairwise(dated):
        if a.start == b.start:
            when = "la línea base" if a.basis == "baseline" else str(a.start)
            raise TemporalDataError(
                f"{ent.key} ({env}): dos versiones distintas empiezan en {when}: {a.label} y {b.label}. "
                "Si comparten inicio deben ser UNA versión con introduced_by: [ambos efectos] (G.3)"
            )
    pros.sort(key=lambda p: p.label)
    return dated, pros


@dataclass(frozen=True)
class TimelineEntry:
    """Tramo derivado de la línea de tiempo de una entidad en un ambiente."""

    index: int
    """Índice de la versión en `versions` de la entidad."""
    version: Version
    start: Boundary | None
    """None = prospectiva (sin fecha en ese ambiente)."""
    end: Boundary | None
    """Inicio de la siguiente versión; None = abierto (o prospectiva)."""
    start_basis: StartBasis

    @property
    def label(self) -> str:
        return version_label(self.version)

    @property
    def prospective(self) -> bool:
        return self.start is None


def timeline(kb: KB, key: str, env: Env = "prod") -> list[TimelineEntry]:
    """Línea de tiempo ordenada por inicio; fin = inicio de la siguiente; prospectivas al final."""
    ent = kb.entity(key)
    if ent is None:
        return []
    dated, pros = _place(kb, ent, env)
    out: list[TimelineEntry] = []
    for j, p in enumerate(dated):
        nxt = dated[j + 1] if j + 1 < len(dated) else None
        end = _boundary(nxt.start, nxt.basis) if nxt else None
        out.append(TimelineEntry(p.index, p.version, _boundary(p.start, p.basis), end, p.basis))
    out.extend(TimelineEntry(p.index, p.version, None, None, p.basis) for p in pros)
    return out


def diff_versions(a: Version, b: Version) -> list[str]:
    """Atributos de contenido que cambian de `a` a `b` (sin introduced_by, based_on, evidencia…)."""
    da = a.model_dump(mode="json", exclude=_NON_CONTENT)
    db = b.model_dump(mode="json", exclude=_NON_CONTENT)
    return sorted(k for k in da.keys() | db.keys() if da.get(k) != db.get(k))


def version_source(v: Version) -> str:
    """Efecto + documento + revisión sha12 + página de la primera evidencia de la versión."""
    ev = v.evidence[0]
    if isinstance(ev, PageRef):
        doc, rev = ev.doc, ev.rev
        page = (
            f"p. {ev.page_printed} impresa / {ev.page_pdf} PDF"
            if ev.page_printed
            else f"p. {ev.page_pdf} PDF"
        )
    else:
        r = parse_ref(ev)
        doc, rev, page = r["doc"], r["sha12"], f"p. {r['page']} PDF"
    return f"{version_label(v)} · {doc} rev {rev} · {page}"


def chosen_version(kb: KB, res: Resolution) -> Version | None:
    """La versión que muestra una resolución (vigente, eliminada o mejor referencia)."""
    if res.key is None or res.version_index is None:
        return None
    ent = kb.entity(res.key)
    return ent.versions[res.version_index] if ent is not None else None


# --- Relaciones de una clave ---------------------------------------------------------------------
def _issue_subjects(kb: KB, key: str, ent: Entity) -> set[str]:
    """Sujetos de Issue que afectan la clave: ella, sus efectos y los documentos de esos efectos."""
    subjects = {key}
    for d in kb.documents.values():
        for e in d.effects:
            if e.target == key:
                subjects |= {e.id, d.id}
    for v in ent.versions:
        if v.introduced_by != "baseline":
            for eid in v.introduced_by:
                subjects.add(eid)
                if kb.has_effect(eid):
                    subjects.add(kb.doc_of(eid).id)
    return subjects


def _scope_active(s: IssueScope, at: date, env: Env) -> bool:
    return (
        (s.env is None or s.env == env)
        and (s.since is None or s.since <= at)
        and (s.until is None or at < s.until)
    )


def _relevant_issues(kb: KB, subjects: set[str]) -> list[Issue]:
    return sorted(
        (i for i in kb.issues.values() if any(s.subject in subjects for s in i.affects)),
        key=lambda i: i.id,
    )


def _issue_blocks(iss: Issue, subjects: set[str], at: date, env: Env) -> bool:
    return (
        iss.status == "open"
        and iss.blocking
        and any(s.subject in subjects and _scope_active(s, at, env) for s in iss.affects)
    )


def _pending_on(kb: KB, key: str, mentioned: set[str]) -> list[Effect]:
    """Efectos `pending` sobre la clave y pendientes sin destino de documentos que la mencionan.

    Un documento sin `raw/` no puede descartarse: su pendiente sin destino cuenta para toda clave.
    """
    out: list[Effect] = []
    for doc in kb.documents.values():
        for e in doc.effects:
            if e.disposition != "pending":
                continue
            if e.target == key or (
                e.target is None and (doc.id in mentioned or not has_raw_text(kb, doc.id))
            ):
                out.append(e)
    return out


def _doc_existed(doc: DocumentSource, at: date) -> bool:
    a = document_anchor(doc)
    return a is None or a <= at  # sin fecha conocida: conservador, ya existía


def _uncurated(kb: KB, key: str, mentioned: set[str], coverage_from: date) -> list[tuple[str, date, str]]:
    """Revisiones del manifiesto sin curar que afectan la clave: (doc, desde, descripción).

    - Con ficha: la última revisión ≠ `current_revision`, desde la fecha del documento, si el
      documento tiene efectos sobre la clave, la menciona en `raw/` o su revisión nueva no tiene
      `raw/` todavía (no se sabe qué dice: afecta a toda clave).
    - Sin ficha: sin curar desde `coverage_from` (sus fechas aún no se conocen), si la menciona o
      no tiene `raw/`.
    """
    targeting = {d.id for d in kb.documents.values() for e in d.effects if e.target == key}
    out: list[tuple[str, date, str]] = []
    for doc_id in sorted({r.doc for r in kb.manifest.revisions}):
        latest = kb.latest_revision(doc_id)
        if latest is None:  # imposible: doc_id sale del propio manifiesto
            continue
        no_raw = not has_raw_text(kb, doc_id)
        doc = kb.documents.get(doc_id)
        if doc is None:
            if doc_id in mentioned or no_raw:
                out.append(
                    (
                        doc_id,
                        coverage_from,
                        f"{doc_id} rev {sha12(latest.sha256)}: registrado sin ficha en kb/",
                    )
                )
            continue
        if latest.sha256 == doc.current_revision:
            continue
        if doc_id in targeting or doc_id in mentioned or no_raw:
            since = document_anchor(doc) or coverage_from
            out.append(
                (
                    doc_id,
                    since,
                    f"{doc_id}: la revisión {sha12(latest.sha256)} del manifiesto no está curada "
                    f"(kb/ usa {sha12(doc.current_revision)}); afecta desde {since}",
                )
            )
    return out


def _missing_test_anchor(kb: KB, v: Version) -> date | None:
    """Desde cuándo una versión sin fecha de test puede estar ya en test: lo antes entre la fecha
    de sus documentos y su inicio en producción (test suele adelantarse a producción, G.3)."""
    cands: list[date] = []
    d, _ = version_start(kb, v, "prod")
    if d is not None:
        cands.append(d)
    if v.introduced_by != "baseline":
        for eid in v.introduced_by:
            a = document_anchor(kb.doc_of(eid))
            if a is not None:
                cands.append(a)
    return min(cands) if cands else None


def _temporal_issue_ids(kb: KB, v: Version, env: Env) -> list[str]:
    if v.introduced_by == "baseline":
        return []
    subj = set(v.introduced_by) | {kb.doc_of(e).id for e in v.introduced_by if kb.has_effect(e)}
    return [
        i.id
        for i in sorted(kb.issues.values(), key=lambda i: i.id)
        if i.kind == "temporal" and any(s.subject in subj and s.env in (None, env) for s in i.affects)
    ]


def _describe(kb: KB, p: _Placed, env: Env) -> str:
    what = "eliminación" if p.version.kind == "tombstone" else "versión"
    if p.start is None:
        txt = f"{p.label} · {what} · sin fecha ({_BASIS_TXT[p.basis]})"
    else:
        txt = f"{p.label} · {what} · desde {p.start.isoformat()} ({_BASIS_TXT[p.basis]})"
    issues = _temporal_issue_ids(kb, p.version, env)
    return txt + (f" · ver {', '.join(issues)}" if issues else "")


def _describe_pending(e: Effect, start: Start) -> str:
    target = e.target or "sin destino"
    d, basis = start
    when = f"desde {d.isoformat()} ({_BASIS_TXT[basis]})" if d else f"sin fecha ({_BASIS_TXT[basis]})"
    return f"{e.id} · pendiente de curar ({e.action} {target}) · {when}"


def _horizon(kb: KB) -> tuple[date | None, date | None]:
    """(horizonte = último chequeo limpio, límite = horizonte + gracia). None = nunca verificado."""
    h = kb.horizon()
    grace = kb.meta.horizon_grace_days if kb.meta else 0
    return h, (h + timedelta(days=grace) if h else None)


def _horizon_warnings(kb: KB, at: date, now: date | None) -> tuple[bool, list[str]]:
    """(¿más allá del horizonte?, avisos)."""
    h, limit = _horizon(kb)
    if h is None or limit is None:
        return True, ["fuentes nunca verificadas: no hay un `sifen source check` limpio en el manifiesto"]
    warns: list[str] = []
    beyond = at > limit
    if beyond:
        warns.append(
            f"más allá del horizonte: fuentes verificadas el {h} (+{(limit - h).days} días de gracia); "
            "la versión mostrada es la mejor referencia, no una vigencia"
        )
    elif h < at:
        warns.append(
            f"fuentes verificadas el {h}: una NT posterior podría regir (NT 25 y 27 rigieron el día de su subida)"
        )
    if now is not None and now > limit:
        warns.append(
            f"fuentes verificadas el {h} (hace {(now - h).days} días): ejecutar `sifen source check`"
        )
    return beyond, warns


# --- Resolución --------------------------------------------------------------------------------------
def index_answer(
    kb: KB,
    terms: list[str],
    at: date,
    env: Env = "prod",
    *,
    axis: Axis = "processing",
    key: str | None = None,
    now: date | None = None,
) -> Resolution:
    """Modo índice: `not_curated` + menciones en `raw/` (producción desc.). Nunca infiere la regla."""
    mentions = find_mentions(kb, terms)
    warnings = [NOT_CURATED_WARNING]
    if not mentions:
        warnings.append(f"sin menciones de {', '.join(terms)} en raw/ (o raw/ todavía no extraído)")
    _, hw = _horizon_warnings(kb, at, now)
    h, _ = _horizon(kb)
    return Resolution(
        key=key,
        at=at,
        env=env,
        axis=axis,
        state="not_curated",
        mentions=mentions,
        warnings=warnings + hw,
        sources_checked_at=h,
    )


def resolve(
    kb: KB,
    key: str,
    at: date,
    env: Env = "prod",
    axis: Axis = "processing",
    now: date | None = None,
) -> Resolution:
    """Estado de `key` en la fecha `at` y el ambiente `env` (G.2 + definiciones implícitas).

    `key` no curada (o un término suelto) ⇒ `not_curated` con menciones. `now` solo agrega el
    aviso de antigüedad del horizonte; nunca sustituye a `at`.
    """
    ent = kb.entity(key)
    if ent is None:
        is_key = key.startswith(("field:", "val:"))
        return index_answer(kb, key_terms(kb, key), at, env, axis=axis, key=key if is_key else None, now=now)
    meta = _meta(kb)

    dated, pros = _place(kb, ent, env)
    past = [p for p in dated if p.start <= at]  # type: ignore[operator]
    chosen = past[-1] if past else None
    future = [p for p in dated if p.start > at]  # type: ignore[operator]

    mentioned = mentioning_docs(kb, key_terms(kb, key))
    warnings: list[str] = []
    reasons: list[str] = []

    # Pendientes: con fecha <= at bloquean; sin fecha bloquean si su documento ya existía y
    # además quedan siempre visibles en upcoming.
    # Orden por (inicio, id): nunca por orden de archivos (propiedad de Hypothesis).
    pend = sorted(
        ((e, effect_start(kb, e.id, env)) for e in _pending_on(kb, key, mentioned)),
        key=lambda es: (es[1][0] or date.max, es[0].id),
    )
    pend_now: list[str] = []
    pend_later: list[tuple[Effect, Start]] = []
    for e, s in pend:
        if s[0] is None:
            pend_later.append((e, s))
            if _doc_existed(kb.doc_of(e.id), at):
                pend_now.append(e.id)
        elif s[0] <= at:
            pend_now.append(e.id)
        else:
            pend_later.append((e, s))
    if pend_now:
        reasons.append("pending_effect")

    subjects = _issue_subjects(kb, key, ent)
    issues = _relevant_issues(kb, subjects)
    blocking = [i for i in issues if _issue_blocks(i, subjects, at, env)]
    if blocking:
        reasons.append("blocking_issue")

    uncurated = [u for u in _uncurated(kb, key, mentioned, meta.coverage_from) if u[1] <= at]
    if uncurated:
        reasons.append("revision_not_curated")

    if env == "test":
        for p in pros:
            if p.basis != "missing_test":
                continue
            anchor = _missing_test_anchor(kb, p.version)
            if anchor is None:
                warnings.append(f"{p.label}: test sin fecha declarada y sin otra fecha de referencia")
            elif anchor <= at:
                reasons.append("test_date_missing")
                warnings.append(
                    f"{p.label}: test sin fecha declarada (desde {anchor} pudo regir en test); "
                    "no se usa la de producción"
                )
                break

    beyond, hwarn = _horizon_warnings(kb, at, now)
    if beyond:
        reasons.append("beyond_horizon")

    if at < meta.coverage_from:
        state = "outside_coverage"
    elif reasons:
        state = "undetermined"
    elif chosen is None:
        state = "not_yet_existing"
    elif chosen.version.kind == "tombstone":
        state = "removed"
    else:
        state = "in_force"

    # Avisos no bloqueantes (G.2) ----------------------------------------------------------------
    if state == "outside_coverage":
        warnings.append(
            f"fuera de cobertura: la KB garantiza respuestas desde {meta.coverage_from}; "
            "la versión mostrada es solo referencia"
        )
    if chosen is not None:
        v = chosen.version
        if chosen.basis == "approx" and v.introduced_by != "baseline":
            for eid in v.introduced_by:
                doc = kb.doc_of(eid)
                txt = f"inicio aproximado: {doc.id} no declara calendario"
                if doc.document_date is not None and doc.document_date.value is not None:
                    txt += f"; se usa su fecha de documento {doc.document_date.value}"
                if doc.change_period is not None:
                    a, b = doc.change_period
                    txt += f" (cambios desde {a.literal} al {b.literal})"
                warnings.append(txt)
        if (
            v.kind == "content"
            and isinstance(v, ValidationVersion)
            and v.condition is not None
            and v.condition.gaps
        ):
            warnings.append(f"gap de la formalización ({v.condition.level}): {v.condition.gaps}")
        warnings.extend(f"needs_review: {q}" for q in v.open_questions)
        if state == "removed":
            code = getattr(v, "code", None)
            if code:
                warnings.append(f"recibir {code} contradice la KB (eliminada): registrar un caso")
        if env == "prod" and v.introduced_by != "baseline":
            # Oráculo de la marca de agua (G.3): el fin derivado debe ser `superseded_by.since`.
            nxt = future[0] if future else None
            for eid in v.introduced_by:
                sup = kb.doc_of(eid).superseded_by
                if sup is not None and (nxt is None or nxt.start != sup.since):
                    end = nxt.start if nxt else "abierto"
                    warnings.append(
                        f"{kb.doc_of(eid).id} declara que {sup.doc} la reemplaza desde {sup.since}, "
                        f"pero el fin derivado es {end}"
                    )
    for i in blocking:
        warnings.append(
            f"{i.id} ({i.kind}, bloqueante): {i.statement}" + (f" Política: {i.policy}" if i.policy else "")
        )
    for i in issues:
        if i in blocking or not any(s.subject in subjects and s.env in (None, env) for s in i.affects):
            continue
        if i.status == "open":
            tag = "bloqueante fuera de esta fecha o ambiente" if i.blocking else "no bloqueante"
            warnings.append(f"{i.id} ({i.kind}, {tag}): {i.statement}")
        elif i.kind == "temporal":
            warnings.append(f"{i.id} (temporal, resuelto): {i.statement}")
    warnings.extend(desc for _, _, desc in uncurated)
    warnings.extend(hwarn)

    upcoming = (
        [_describe(kb, p, env) for p in future]
        + [_describe(kb, p, env) for p in pros]
        + [_describe_pending(e, s) for e, s in pend_later]
    )

    interval: tuple[Boundary | None, Boundary | None]
    if chosen is not None:
        nxt = future[0] if future else None
        interval = (_boundary(chosen.start, chosen.basis), _boundary(nxt.start, nxt.basis) if nxt else None)
    else:
        interval = (None, _boundary(future[0].start, future[0].basis) if future else None)

    history = [
        HistoryEntry(
            introduced_by=p.version.introduced_by,
            kind=p.version.kind,
            start=_boundary(p.start, p.basis),
            code=getattr(p.version, "code", None),
            summary=version_source(p.version),
        )
        for p in (*dated, *pros)
    ]
    pend_ids = [e.id for e, _ in pend]
    h, _ = _horizon(kb)
    return Resolution(
        key=key,
        at=at,
        env=env,
        axis=axis,
        state=state,  # type: ignore[arg-type]
        reasons=reasons,  # type: ignore[arg-type]
        version_index=chosen.index if chosen else None,
        interval=interval,
        source=version_source(chosen.version) if chosen else None,
        history=history,
        upcoming=upcoming,
        pending_effects=pend_ids,
        open_issues=[i.id for i in issues if i.status == "open"],
        warnings=warnings,
        sources_checked_at=h,
    )


# --- G.4: eje de emisión frente a procesamiento ---------------------------------------------------
def _verdict(kb: KB, res: Resolution, evaluate: Callable[[Version], bool | None]) -> bool | None:
    """Veredicto TRUE = viola. Sin versión o con lápida: la regla no existe en esa fecha ⇒ False."""
    if res.state == "not_curated":
        return None
    v = chosen_version(kb, res)
    if v is None or v.kind == "tombstone":
        return False
    return evaluate(v)


def _first_boundary_after(kb: KB, key: str, env: Env, after: date) -> date | None:
    """Primera frontera (inicio de versión o de pendiente) en `(after, horizonte + gracia]`."""
    ent = kb.entity(key)
    if ent is None:
        return None
    _, limit = _horizon(kb)
    dated, _ = _place(kb, ent, env)
    starts = [p.start for p in dated if p.start is not None]
    mentioned = mentioning_docs(kb, key_terms(kb, key))
    starts += [d for e in _pending_on(kb, key, mentioned) if (d := effect_start(kb, e.id, env)[0])]
    cands = sorted(d for d in starts if d > after and (limit is None or d <= limit))
    return cands[0] if cands else None


def resolve_xml_axes(
    kb: KB,
    key: str,
    emitted_at: date,
    processed_at: date | None,
    env: Env,
    evaluate: Callable[[Version], bool | None],
    *,
    processing_date_source: Literal["response", "flag"] = "flag",
    now: date | None = None,
) -> dict[str, Any]:
    """Resuelve un XML por fecha de emisión y de procesamiento (G.4). `evaluate(versión)` es el
    evaluador del DSL (True = viola, None = UNKNOWN); se llama a lo sumo una vez por versión.

    Devuelve `state`, `reasons`, `resolution` (la definitiva), `verdict` (None si el eje no
    permite decidir), `emission`/`processing` (`{at, resolution, verdict}`),
    `processing_date_source` y `boundary` (frontera que impide decidir sin fecha de proceso).
    """
    default_axis = _meta(kb).date_axis_default
    r_emit = resolve(kb, key, emitted_at, env, axis="emission", now=now)
    v_emit = _verdict(kb, r_emit, evaluate)
    emission = {"at": emitted_at, "resolution": r_emit, "verdict": v_emit}

    if processed_at is None:
        b = _first_boundary_after(kb, key, env, emitted_at)
        if b is not None:
            final = r_emit.model_copy(
                update={
                    "state": "undetermined",
                    "reasons": [*r_emit.reasons, "processing_date_unknown"],
                    "processing_date_source": "unknown",
                    "warnings": [
                        *r_emit.warnings,
                        f"sin fecha de procesamiento: la regla cambia el {b}, entre la emisión y el horizonte; "
                        "se muestra la resolución por emisión como referencia (nunca 'hoy' por defecto)",
                    ],
                }
            )
            verdict = None
        else:
            final = r_emit.model_copy(update={"processing_date_source": "unknown"})
            verdict = v_emit
        return {
            "state": final.state,
            "reasons": list(final.reasons),
            "resolution": final,
            "verdict": verdict,
            "emission": emission,
            "processing": None,
            "processing_date_source": "unknown",
            "boundary": b,
        }

    r_proc = resolve(kb, key, processed_at, env, axis="processing", now=now)
    same_version = r_proc.version_index == r_emit.version_index and r_proc.state == r_emit.state
    v_proc = v_emit if same_version else _verdict(kb, r_proc, evaluate)
    processing = {"at": processed_at, "resolution": r_proc, "verdict": v_proc}
    base = r_proc if default_axis == "processing" else r_emit
    if v_emit != v_proc:
        final = base.model_copy(
            update={
                "state": "undetermined",
                "reasons": [*base.reasons, "axis_split"],
                "processing_date_source": processing_date_source,
                "warnings": [
                    *base.warnings,
                    f"axis_split: por emisión ({emitted_at}) {_vtxt(v_emit)}; "
                    f"por procesamiento ({processed_at}) {_vtxt(v_proc)}",
                ],
            }
        )
        verdict = None
    else:
        final = base.model_copy(update={"processing_date_source": processing_date_source})
        verdict = v_proc
    return {
        "state": final.state,
        "reasons": list(final.reasons),
        "resolution": final,
        "verdict": verdict,
        "emission": emission,
        "processing": processing,
        "processing_date_source": processing_date_source,
        "boundary": None,
    }


def _vtxt(v: bool | None) -> str:
    return {True: "TRUE (viola)", False: "FALSE", None: "UNKNOWN"}[v]


# --- Corte: "lo que una KB de entonces podía decir" (G.5, fila 6) ----------------------------------
def cut_kb(kb: KB, cutoff: date) -> KB:
    """Copia de la KB sin los documentos posteriores a `cutoff` (por `document_date` o, si falta,
    su menor fecha declarada), sin los efectos y versiones que introducen, y con el horizonte
    fijado en `cutoff`.

    Aproximación del tiempo de transacción (el real vive en Git): las fichas que quedan se usan tal
    como están hoy (no se reconstruye un calendario anterior a una prórroga).
    """
    removed_docs = {
        d.id for d in kb.documents.values() if (a := document_anchor(d)) is not None and a > cutoff
    }
    removed_effects = {e.id for d in kb.documents.values() if d.id in removed_docs for e in d.effects}
    gone = removed_docs | removed_effects

    docs: list[DocumentSource] = []
    for d in kb.documents.values():
        if d.id in removed_docs:
            continue
        if d.superseded_by is not None and d.superseded_by.doc in removed_docs:
            d = d.model_copy(update={"superseded_by": None})
        docs.append(d)

    def keep(v: Version) -> bool:
        return v.introduced_by == "baseline" or not set(v.introduced_by) & removed_effects

    fields = [
        f.model_copy(update={"versions": vs})
        for f in kb.fields.values()
        if (vs := [v for v in f.versions if keep(v)])
    ]
    validations = [
        v.model_copy(update={"versions": vs})
        for v in kb.validations.values()
        if (vs := [x for x in v.versions if keep(x)])
    ]
    issues = [
        i.model_copy(update={"affects": aff})
        for i in kb.issues.values()
        if (aff := [s for s in i.affects if s.subject not in gone])
    ]
    revisions: list[SourceRevision] = [
        r
        for r in kb.manifest.revisions
        if r.doc not in removed_docs and (r.doc in kb.documents or r.retrieved_at.date() <= cutoff)
    ]
    manifest = SourcesManifest(
        revisions=revisions,
        checks=[
            SourceCheck(
                at=datetime.combine(cutoff, time.min),
                scope=["nt", "xsd", "tablas", "guias", "manual"],
                unregistered=[],
            )
        ],
    )
    keys = (
        {d.id for d in docs} | {f.key for f in fields} | {v.key for v in validations} | {i.id for i in issues}
    )
    return build_kb(
        kb.root,
        meta=kb.meta,
        documents=docs,
        fields=fields,
        validations=validations,
        issues=issues,
        manifest=manifest,
        errors=kb.errors,
        paths={k: p for k, p in kb.paths.items() if k in keys},
    )

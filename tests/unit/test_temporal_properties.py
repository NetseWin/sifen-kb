"""Propiedades del resolvedor con Hypothesis (docs/arquitectura.md §K.2).

Historiales aleatorios de `val:DE:D208c` con fechas por ambiente, lápidas, prospectivas ("a
definir"), test sin fecha, pendientes (con y sin fecha) y orden de archivos barajado. Además de
las cinco propiedades de §K.2 se compara el resolvedor con un oráculo independiente y mínimo.

Perfiles: `sifen-ci` (derandomize=True, determinista) se usa cuando existe la variable `CI`;
si no, `sifen-dev` (aleatorio). `SIFEN_HYPOTHESIS_PROFILE` fuerza uno u otro.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sifen_kb.load import KB
from sifen_kb.model import (
    DateStatement,
    DocumentSource,
    Effect,
    Interpretation,
    KBMeta,
    Resolution,
    Schedule,
    SourceCheck,
    SourceRevision,
    SourcesManifest,
    Validation,
    ValidationVersion,
)
from sifen_kb.temporal import TemporalDataError, build_kb, chosen_version, resolve, timeline

settings.register_profile(
    "sifen-ci",
    derandomize=True,
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "sifen-dev", max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
PROFILE = settings.get_profile(
    os.environ.get("SIFEN_HYPOTHESIS_PROFILE") or ("sifen-ci" if os.environ.get("CI") else "sifen-dev")
)

KEY = "val:DE:D208c"
BASE = date(2024, 1, 1)
COV = date(2023, 6, 17)
HORIZON = date(2027, 1, 1)
GRACE = 7
LIMIT = HORIZON + timedelta(days=GRACE)
ROOT = Path("/nonexistent/sifen-kb-props")  # sin raw/
TBD = "tbd"
ENVS = ("test", "prod")

Slot = int | str | None
"""Desplazamiento en días desde BASE; "tbd" = "a definir"; None = ranura ausente."""


@dataclass(frozen=True)
class VSpec:
    n: int
    test: Slot
    prod: Slot
    tombstone: bool
    ddate: int

    @property
    def doc(self) -> str:
        return f"NT_9{self.n:02d}"

    @property
    def label(self) -> str:
        return f"{self.doc}#1"


@dataclass(frozen=True)
class PSpec:
    n: int
    test: Slot
    prod: Slot
    ddate: int

    @property
    def doc(self) -> str:
        return f"NT_8{self.n:02d}"

    @property
    def label(self) -> str:
        return f"{self.doc}#1"


@dataclass(frozen=True)
class History:
    baseline: bool
    versions: tuple[VSpec, ...]
    pendings: tuple[PSpec, ...]
    order: tuple[int, ...]
    doc_order: tuple[int, ...]


def day(off: int) -> date:
    return BASE + timedelta(days=off)


def start(slot: Slot) -> int | None:
    return slot if isinstance(slot, int) else None


def slot_of(spec: VSpec | PSpec, env: str) -> Slot:
    return spec.test if env == "test" else spec.prod


# --- Estrategias -------------------------------------------------------------------------------------
OFF = st.integers(min_value=-250, max_value=1250)
AT = st.integers(min_value=-260, max_value=1260)


@st.composite
def histories(draw: st.DrawFn, *, dup: bool = False) -> History:
    n = draw(st.integers(0, 5))
    pool = st.integers(0, 4) if dup else OFF  # dup: pocas fechas posibles ⇒ colisiones
    prods = draw(st.lists(pool, min_size=n, max_size=n, unique=not dup))
    tests = draw(st.lists(pool, min_size=n, max_size=n, unique=not dup))
    versions = []
    for i in range(n):
        prod: Slot = TBD if draw(st.integers(0, 5)) == 0 else prods[i]
        tk = draw(st.integers(0, 6))
        test: Slot = None if tk == 0 else TBD if tk == 1 else tests[i]
        dated = [x for x in (prod, test) if isinstance(x, int)]
        ddate = (min(dated) if dated else draw(OFF)) - draw(st.integers(0, 60))
        versions.append(VSpec(i + 1, test, prod, draw(st.booleans()), ddate))
    pendings = []
    for j in range(draw(st.integers(0, 2))):
        prod = draw(st.one_of(st.just(TBD), OFF))
        test = draw(st.one_of(st.none(), st.just(TBD), OFF))
        dated = [x for x in (prod, test) if isinstance(x, int)]
        ddate = (min(dated) if dated else draw(OFF)) - draw(st.integers(0, 60))
        pendings.append(PSpec(j + 1, test, prod, ddate))
    baseline = n == 0 or draw(st.booleans())
    order = tuple(draw(st.permutations(range(n + int(baseline)))))
    doc_order = tuple(draw(st.permutations(range(n + len(pendings)))))
    return History(baseline, tuple(versions), tuple(pendings), order, doc_order)


# --- Construcción de la KB -------------------------------------------------------------------------
def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _stmt(doc: str, attr: str, slot: Slot) -> DateStatement | None:
    if slot is None:
        return None
    ref = f"raw:{doc}@{_sha(doc)[:12]}:p1:fechas#{attr}"
    if slot == TBD:
        return DateStatement(value=None, literal="a definir", stated_in=ref)
    d = day(slot)  # type: ignore[arg-type]
    return DateStatement(value=d, literal=d.strftime("%d/%m/%Y"), stated_in=ref)


def _doc(spec: VSpec | PSpec) -> DocumentSource:
    pending = isinstance(spec, PSpec)
    tomb = isinstance(spec, VSpec) and spec.tombstone
    e = Effect(
        id=spec.label,
        verb_literal="Se elimina" if tomb else "Se modifica",
        action="remove" if tomb else "modify",
        target=KEY,
        declared_scope="row",
        evidence=[f"raw:{spec.doc}@{_sha(spec.doc)[:12]}:p2:D208c"],
        interpretation=Interpretation(by="human"),
        disposition="pending" if pending else None,
    )
    return DocumentSource(
        id=spec.doc,
        kind="technical_note",
        title=spec.doc,
        current_revision=_sha(spec.doc),
        document_date=_stmt(spec.doc, "fecha", spec.ddate),
        schedule=Schedule(test=_stmt(spec.doc, "test", spec.test), prod=_stmt(spec.doc, "prod", spec.prod)),
        effects=[e],
        curation_scope="pilot",
    )


def _ver(spec: VSpec | None) -> ValidationVersion:
    return ValidationVersion(
        introduced_by="baseline" if spec is None else [spec.label],
        based_on=None if spec is None else "baseline",
        kind="tombstone" if spec is not None and spec.tombstone else "content",
        evidence=["raw:MT_V150@000000000000:p167:D208c"],
        code="1321",
        severity="R",
        observation=f"observación {spec.label if spec else 'base'}",
    )


META = KBMeta(
    baseline_doc="MT_V150",
    baseline_sha256=_sha("MT_V150"),
    coverage_from=COV,
    horizon_grace_days=GRACE,
    date_axis_default="processing",
)


def build(h: History, order: tuple[int, ...] | None = None, doc_order: tuple[int, ...] | None = None) -> KB:
    docs = [_doc(v) for v in h.versions] + [_doc(p) for p in h.pendings]
    docs = [docs[i] for i in (doc_order or h.doc_order)]
    vers = ([_ver(None)] if h.baseline else []) + [_ver(v) for v in h.versions]
    vers = [vers[i] for i in (order or h.order)]
    revs = [
        SourceRevision(
            doc=d.id,
            sha256=d.current_revision,
            md5="0" * 32,
            size=1,
            url=f"https://fixture.invalid/{d.id}.pdf",
            filename=f"{d.id}.pdf",
            retrieved_at=datetime(2020, 1, 1),
            origin="portal",
            path=f"sources/{d.id}/x.pdf",
        )
        for d in docs
    ]
    return build_kb(
        ROOT,
        meta=META,
        documents=docs,
        validations=[Validation(key=KEY, context="DE", id="D208c", versions=vers)],
        manifest=SourcesManifest(
            revisions=revs, checks=[SourceCheck(at=datetime.combine(HORIZON, time()), scope=["nt"])]
        ),
    )


# --- Oráculo independiente ---------------------------------------------------------------------------
def oracle(h: History, at: int, env: str) -> tuple[str, set[str], str | None]:
    """(estado, motivos, versión elegida) calculados directamente desde la especificación."""
    dated: list[tuple[float, VSpec | None]] = [(float("-inf"), None)] if h.baseline else []
    dated += [(s, v) for v in h.versions if (s := start(slot_of(v, env))) is not None]
    past = [x for x in dated if x[0] <= at]
    chosen = max(past, key=lambda x: x[0]) if past else None
    reasons: set[str] = set()
    for p in h.pendings:
        s = start(slot_of(p, env))
        if (s is not None and s <= at) or (s is None and p.ddate <= at):
            reasons.add("pending_effect")
    if env == "test":
        for v in h.versions:
            if v.test is None:
                anchor = min([v.ddate] + ([v.prod] if isinstance(v.prod, int) else []))
                if anchor <= at:
                    reasons.add("test_date_missing")
    if day(at) > LIMIT:
        reasons.add("beyond_horizon")
    label = None if chosen is None else ("baseline" if chosen[1] is None else chosen[1].label)
    tomb = chosen is not None and chosen[1] is not None and chosen[1].tombstone
    if day(at) < COV:
        state = "outside_coverage"
    elif reasons:
        state = "undetermined"
    elif chosen is None:
        state = "not_yet_existing"
    else:
        state = "removed" if tomb else "in_force"
    return state, reasons, label


def chosen_label(kb: KB, res: Resolution) -> str | None:
    v = chosen_version(kb, res)
    if v is None:
        return None
    return "baseline" if v.introduced_by == "baseline" else "+".join(v.introduced_by)


def summary(kb: KB, res: Resolution) -> tuple[object, ...]:
    return (
        res.state,
        tuple(res.reasons),
        chosen_label(kb, res),
        tuple(res.upcoming),
        tuple(res.pending_effects),
        res.interval,
    )


def boundaries(h: History, env: str) -> set[int]:
    """Días en que el resultado PUEDE cambiar (superconjunto): inicios, fechas de documento,
    cobertura y fin de la gracia del horizonte."""
    out = {(COV - BASE).days, (LIMIT - BASE).days + 1}
    for s in (*h.versions, *h.pendings):
        out.add(s.ddate)
        for slot in (s.test, s.prod):
            if isinstance(slot, int):
                out.add(slot)
    return out


# --- Propiedades ------------------------------------------------------------------------------------
@PROFILE
@given(h=histories(dup=True), at=AT, env=st.sampled_from(ENVS))
def test_at_most_one_version_per_date(h: History, at: int, env: str) -> None:
    kb = build(h)
    starts = [s for v in h.versions if (s := start(slot_of(v, env))) is not None]
    if len(starts) != len(set(starts)):
        try:
            resolve(kb, KEY, day(at), env)  # type: ignore[arg-type]
        except TemporalDataError as e:
            assert "dos versiones distintas" in str(e)
        else:
            raise AssertionError("dos versiones con el mismo inicio no fueron rechazadas")
    else:
        resolve(kb, KEY, day(at), env)  # type: ignore[arg-type]
        dates = [
            t.start.date for t in timeline(kb, KEY, env) if t.start is not None and t.start.date is not None
        ]
        assert dates == sorted(set(dates))


@PROFILE
@given(h=histories(), at=AT, env=st.sampled_from(ENVS))
def test_resolver_matches_oracle(h: History, at: int, env: str) -> None:
    kb = build(h)
    res = resolve(kb, KEY, day(at), env)  # type: ignore[arg-type]
    state, reasons, label = oracle(h, at, env)
    assert (res.state, set(res.reasons), chosen_label(kb, res)) == (state, reasons, label)


@PROFILE
@given(h=histories(), at=AT, env=st.sampled_from(ENVS))
def test_result_changes_only_at_boundaries(h: History, at: int, env: str) -> None:
    if at + 1 in boundaries(h, env):
        return
    kb = build(h)
    a = resolve(kb, KEY, day(at), env)  # type: ignore[arg-type]
    b = resolve(kb, KEY, day(at + 1), env)  # type: ignore[arg-type]
    assert summary(kb, a) == summary(kb, b)


@PROFILE
@given(h=histories(), data=st.data(), at=AT, env=st.sampled_from(ENVS))
def test_file_order_irrelevant(h: History, data: st.DataObject, at: int, env: str) -> None:
    order = tuple(data.draw(st.permutations(range(len(h.order)))))
    doc_order = tuple(data.draw(st.permutations(range(len(h.doc_order)))))
    kb1, kb2 = build(h), build(h, order, doc_order)
    r1 = resolve(kb1, KEY, day(at), env)  # type: ignore[arg-type]
    r2 = resolve(kb2, KEY, day(at), env)  # type: ignore[arg-type]
    assert summary(kb1, r1) == summary(kb2, r2)
    assert [x.introduced_by for x in r1.history] == [x.introduced_by for x in r2.history]
    assert r1.warnings == r2.warnings


@PROFILE
@given(h=histories(), at=AT, env=st.sampled_from(ENVS))
def test_after_tombstone_removed(h: History, at: int, env: str) -> None:
    kb = build(h)
    res = resolve(kb, KEY, day(at), env)  # type: ignore[arg-type]
    v = chosen_version(kb, res)
    if v is not None and v.kind == "tombstone":
        assert res.state != "in_force"
        if not res.reasons and day(at) >= COV:
            assert res.state == "removed"
    if res.state == "removed":
        assert v is not None and v.kind == "tombstone"


@PROFILE
@given(h=histories(), at=AT, env=st.sampled_from(ENVS))
def test_prospective_and_future_pending_always_upcoming_never_in_force(h: History, at: int, env: str) -> None:
    kb = build(h)
    res = resolve(kb, KEY, day(at), env)  # type: ignore[arg-type]
    label = chosen_label(kb, res)
    for v in h.versions:
        s = start(slot_of(v, env))
        if s is None or s > at:  # prospectiva o futura
            assert any(u.startswith(f"{v.label} · ") for u in res.upcoming), (v, res.upcoming)
            assert label != v.label
    for p in h.pendings:
        s = start(slot_of(p, env))
        if s is None or s > at:  # pendiente futuro o sin fecha
            assert any(u.startswith(f"{p.label} · pendiente") for u in res.upcoming), (p, res.upcoming)
        assert p.label in res.pending_effects
    if res.state == "in_force":
        assert "pending_effect" not in res.reasons and label is not None
        assert all(start(slot_of(v, env)) is not None for v in h.versions if v.label == label)

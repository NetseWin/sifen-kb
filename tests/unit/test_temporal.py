"""Unitarios del resolvedor temporal (docs/arquitectura.md §K.1) y del índice de menciones.

Las KB se construyen en memoria con los modelos (`build_kb`); solo los tests de menciones
escriben un `raw/` mínimo en `tmp_path`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time
from pathlib import Path

import pytest

from sifen_kb.load import KB
from sifen_kb.mentions import find_mentions, key_terms, printed_page
from sifen_kb.model import (
    DateStatement,
    DocumentSource,
    Effect,
    Interpretation,
    Issue,
    IssueScope,
    KBMeta,
    PageRef,
    Resolution,
    Schedule,
    SourceCheck,
    SourceRevision,
    SourcesManifest,
    Supersession,
    Validation,
    ValidationVersion,
)
from sifen_kb.rawio import page_path, write_index, write_text
from sifen_kb.temporal import (
    PRE_COVERAGE,
    TemporalDataError,
    build_kb,
    chosen_version,
    cut_kb,
    diff_versions,
    effect_start,
    resolve,
    resolve_xml_axes,
    timeline,
    version_start,
)

KEY = "val:DE:D208c"
COV = date(2023, 6, 17)
ROOT = Path("/nonexistent/sifen-kb-unit")  # sin raw/: find_mentions devuelve []
TBD = "a definir"


# --- Constructores -------------------------------------------------------------------------------
def sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def stmt(doc_id: str, attr: str, d: date | None) -> DateStatement:
    ref = f"raw:{doc_id}@{sha(doc_id)[:12]}:p1:fechas#{attr}"
    if d is None:
        return DateStatement(value=None, literal=TBD, stated_in=ref)
    return DateStatement(value=d, literal=d.strftime("%d/%m/%Y"), stated_in=ref)


def _slot(doc_id: str, attr: str, v: date | str | None) -> DateStatement | None:
    if v is None:  # ranura ausente: el documento no declara ese ambiente
        return None
    return stmt(doc_id, attr, None if v == TBD else v)  # type: ignore[arg-type]


def doc(
    doc_id: str,
    *,
    test: date | str | None = None,
    prod: date | str | None = None,
    ddate: date | None = None,
    effects: Sequence[Effect] = (),
    schedule: bool = True,
    superseded_by: Supersession | None = None,
    change_period: tuple[DateStatement, DateStatement] | None = None,
    current: str | None = None,
) -> DocumentSource:
    return DocumentSource(
        id=doc_id,
        kind="technical_note",
        number=int(doc_id[3:]) if doc_id.startswith("NT_") else None,
        title=f"Nota Técnica {doc_id}",
        current_revision=current or sha(doc_id),
        document_date=stmt(doc_id, "fecha", ddate) if ddate else None,
        change_period=change_period,
        schedule=Schedule(test=_slot(doc_id, "test", test), prod=_slot(doc_id, "prod", prod))
        if schedule
        else None,
        superseded_by=superseded_by,
        effects=list(effects),
        curation_scope="pilot",
    )


def eff(
    doc_id: str,
    n: int = 1,
    *,
    target: str | None = KEY,
    action: str = "modify",
    disposition: str | None = None,
    from_revision: str | None = None,
) -> Effect:
    return Effect(
        id=f"{doc_id}#{n}",
        verb_literal="Se modifica la siguiente validación",
        action=action,  # type: ignore[arg-type]
        target=target,
        declared_scope="row",
        evidence=[f"raw:{doc_id}@{sha(doc_id)[:12]}:p2:D208c"],
        interpretation=Interpretation(by="human"),
        disposition=disposition,  # type: ignore[arg-type]
        from_revision=from_revision,
        note="nota" if disposition == "not_modeled" else None,
    )


def ver(
    intro: str | list[str],
    *,
    based_on: str | list[str] | None = None,
    kind: str = "content",
    severity: str = "R",
    code: str = "1321",
    obs: str | None = None,
    open_questions: Iterable[str] = (),
) -> ValidationVersion:
    label = intro if isinstance(intro, str) else "+".join(intro)
    return ValidationVersion(
        introduced_by=intro,  # type: ignore[arg-type]
        based_on=None if intro == "baseline" else (based_on or "baseline"),  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        evidence=[f"raw:MT_V150@{sha('MT_V150')[:12]}:p167:D208c"],
        code=code,
        severity=severity,  # type: ignore[arg-type]
        message="Tipo de documento de identidad del receptor incorrecto",
        observation=obs or f"observación {label}",
        open_questions=list(open_questions),
    )


def val(versions: Sequence[ValidationVersion], vid: str = "D208c") -> Validation:
    return Validation(key=f"val:DE:{vid}", context="DE", id=vid, versions=list(versions))


def meta(*, coverage: date = COV, grace: int = 7, axis: str = "processing") -> KBMeta:
    return KBMeta(
        baseline_doc="MT_V150",
        baseline_sha256=sha("MT_V150"),
        coverage_from=coverage,
        horizon_grace_days=grace,
        date_axis_default=axis,  # type: ignore[arg-type]
    )


def rev(doc_id: str, sha256: str, *, retrieved: datetime, portal: datetime | None = None) -> SourceRevision:
    return SourceRevision(
        doc=doc_id,
        sha256=sha256,
        md5=hashlib.md5(sha256.encode()).hexdigest(),  # noqa: S324 - marcador
        size=1000,
        url=f"https://fixture.invalid/{doc_id}.pdf",
        filename=f"{doc_id}.pdf",
        portal_t=portal,
        retrieved_at=retrieved,
        origin="portal",
        path=f"sources/{doc_id}/{sha256[:12]}.pdf",
    )


def check(at: date, unregistered: Sequence[str] = ()) -> SourceCheck:
    return SourceCheck(at=datetime.combine(at, time()), scope=["nt"], unregistered=list(unregistered))


def make(
    docs: Sequence[DocumentSource],
    vals: Sequence[Validation] = (),
    *,
    issues: Sequence[Issue] = (),
    horizon: date | None = date(2030, 1, 1),
    checks: Sequence[SourceCheck] | None = None,
    extra_revs: Sequence[SourceRevision] = (),
    root: Path = ROOT,
    kbmeta: KBMeta | None = None,
) -> KB:
    given = {(r.doc, r.sha256) for r in extra_revs}
    revs = [
        rev(d.id, d.current_revision, retrieved=datetime(2020, 1, 1))
        for d in docs
        if (d.id, d.current_revision) not in given
    ]
    if checks is None:
        checks = [check(horizon)] if horizon else []
    return build_kb(
        root,
        meta=kbmeta or meta(),
        documents=docs,
        validations=vals,
        issues=issues,
        manifest=SourcesManifest(revisions=[*revs, *extra_revs], checks=list(checks)),
    )


def label(kb: KB, res: Resolution) -> str | None:
    v = chosen_version(kb, res)
    if v is None:
        return None
    return "baseline" if v.introduced_by == "baseline" else "+".join(v.introduced_by)


def at(kb: KB, d: str, env: str = "prod", key: str = KEY) -> Resolution:
    return resolve(kb, key, date.fromisoformat(d), env)  # type: ignore[arg-type]


def three_versions(*, reverse: bool = False) -> KB:
    """Línea base → NT_101 (2024-01-01) → NT_102 (2025-01-01), test = prod."""
    docs = [
        doc(
            "NT_101",
            test=date(2024, 1, 1),
            prod=date(2024, 1, 1),
            ddate=date(2023, 12, 29),
            effects=[eff("NT_101")],
        ),
        doc(
            "NT_102",
            test=date(2025, 1, 1),
            prod=date(2025, 1, 1),
            ddate=date(2024, 12, 17),
            effects=[eff("NT_102")],
        ),
    ]
    vs = [ver("baseline"), ver(["NT_101#1"]), ver(["NT_102#1"], based_on=["NT_101#1"])]
    if reverse:
        docs, vs = docs[::-1], vs[::-1]
    return make(docs, [val(vs)])


# --- §K.1 -----------------------------------------------------------------------------------------------
def test_resolver_semiopen_boundary():
    kb = three_versions()
    r = at(kb, "2023-12-31")
    assert (r.state, label(kb, r)) == ("in_force", "baseline")
    assert r.interval is not None and r.interval[0].basis == "baseline" and r.interval[0].date is None
    assert r.interval[1].date == date(2024, 1, 1)
    r = at(kb, "2024-01-01")  # el día del cambio ya rige lo nuevo
    assert (r.state, label(kb, r)) == ("in_force", "NT_101#1")
    assert [b.date for b in r.interval] == [date(2024, 1, 1), date(2025, 1, 1)]  # type: ignore[union-attr]
    assert label(kb, at(kb, "2024-12-31")) == "NT_101#1"
    r = at(kb, "2025-01-01")
    assert label(kb, r) == "NT_102#1" and r.interval[1] is None  # type: ignore[index]
    assert r.source is not None and r.source.startswith("NT_102#1 · MT_V150 rev ")


def test_resolver_tombstone():
    d = doc("NT_110", test=date(2025, 1, 1), prod=date(2025, 1, 1), effects=[eff("NT_110", action="remove")])
    kb = make([d], [val([ver("baseline"), ver(["NT_110#1"], kind="tombstone")])])
    assert at(kb, "2024-12-31").state == "in_force"
    r = at(kb, "2025-01-01")
    assert r.state == "removed"
    v = chosen_version(kb, r)
    assert v is not None and v.kind == "tombstone" and v.code == "1321"  # la lápida conserva el código
    assert any("recibir 1321 contradice la KB" in w for w in r.warnings)
    assert at(kb, "2029-06-01").state == "removed"


def test_resolver_prospective_in_upcoming_never_in_force():
    d = doc("NT_120", test=date(2024, 5, 1), prod=TBD, ddate=date(2024, 4, 1), effects=[eff("NT_120")])
    kb = make([d], [val([ver("baseline"), ver(["NT_120#1"])])])
    for day in ("2024-04-30", "2024-05-01", "2026-01-01", "2029-12-31"):
        r = at(kb, day)
        assert (r.state, label(kb, r)) == ("in_force", "baseline"), day
        assert any(u.startswith("NT_120#1 · versión · sin fecha (fecha a definir") for u in r.upcoming)
        assert r.history[-1].start is None  # prospectiva al final del historial
    assert effect_start(kb, "NT_120#1", "prod") == (None, "undated")
    assert label(kb, at(kb, "2024-05-01", "test")) == "NT_120#1"  # en test sí tiene fecha


def test_resolver_pending_without_date_is_visible():
    pend = doc(
        "NT_130", prod=TBD, test=TBD, ddate=date(2025, 3, 1), effects=[eff("NT_130", disposition="pending")]
    )
    kb = make([pend], [val([ver("baseline")])])
    r = at(kb, "2025-02-28")  # el documento todavía no existía: no bloquea, pero se ve
    assert (r.state, r.reasons) == ("in_force", [])
    assert r.pending_effects == ["NT_130#1"]
    assert any(
        u.startswith("NT_130#1 · pendiente de curar (modify val:DE:D208c) · sin fecha") for u in r.upcoming
    )
    r = at(kb, "2025-03-01")  # ya existía y no se sabe desde cuándo rige: conservador
    assert (r.state, r.reasons) == ("undetermined", ["pending_effect"])
    assert any(u.startswith("NT_130#1 · pendiente") for u in r.upcoming)
    assert label(kb, r) == "baseline"


def test_resolver_pending_with_date_blocks_from_its_start():
    pend = doc(
        "NT_131", test=date(2025, 6, 1), prod=date(2025, 7, 1), effects=[eff("NT_131", disposition="pending")]
    )
    kb = make([pend], [val([ver("baseline")])])
    r = at(kb, "2025-06-30")
    assert r.state == "in_force" and any(
        "NT_131#1 · pendiente" in u and "2025-07-01" in u for u in r.upcoming
    )
    assert at(kb, "2025-07-01").reasons == ["pending_effect"]
    assert at(kb, "2025-06-01", "test").reasons == ["pending_effect"]
    # Un efecto not_modeled no es pendiente ni bloquea.
    nm = doc(
        "NT_132",
        test=date(2025, 1, 1),
        prod=date(2025, 1, 1),
        effects=[eff("NT_132", disposition="not_modeled")],
    )
    kb2 = make([nm], [val([ver("baseline")])])
    assert at(kb2, "2025-02-01").state == "in_force" and at(kb2, "2025-02-01").pending_effects == []


def test_resolver_duplicate_start_is_error():
    docs = [
        doc("NT_140", test=date(2024, 12, 1), prod=date(2025, 1, 1), effects=[eff("NT_140")]),
        doc("NT_141", test=date(2024, 12, 2), prod=date(2025, 1, 1), effects=[eff("NT_141")]),
    ]
    two = make(docs, [val([ver("baseline"), ver(["NT_140#1"]), ver(["NT_141#1"], based_on=["NT_140#1"])])])
    with pytest.raises(TemporalDataError, match="dos versiones distintas empiezan en 2025-01-01"):
        at(two, "2025-06-01")
    with pytest.raises(TemporalDataError):
        timeline(two, KEY, "prod")
    assert at(two, "2024-12-15", "test").state == "in_force"  # en test los inicios difieren
    # Dos efectos con el mismo inicio = UNA versión: correcto (NT 19 y NT 20).
    same = [doc("NT_142", prod=date(2025, 1, 1), test=date(2024, 12, 1), effects=[eff("NT_142")]),
            doc("NT_143", prod=date(2025, 1, 1), test=date(2024, 12, 1), effects=[eff("NT_143")])]  # fmt: skip
    one = make(same, [val([ver("baseline"), ver(["NT_142#1", "NT_143#1"])])])
    assert label(one, at(one, "2025-01-01")) == "NT_142#1+NT_143#1"
    # ... pero si sus inicios difieren es error de datos.
    with pytest.raises(TemporalDataError, match="inicios distintos"):
        at(make(docs, [val([ver("baseline"), ver(["NT_140#1", "NT_141#1"])])]), "2025-06-01", "test")
    with pytest.raises(TemporalDataError, match="línea base"):
        at(make([], [val([ver("baseline"), ver("baseline")])]), "2025-06-01")


def test_resolver_test_date_missing_is_undetermined():
    d = doc("NT_150", prod=date(2026, 1, 1), ddate=date(2025, 11, 15), effects=[eff("NT_150")])
    kb = make([d], [val([ver("baseline"), ver(["NT_150#1"])])])
    assert effect_start(kb, "NT_150#1", "test") == (None, "missing_test")
    r = at(kb, "2025-11-14", "test")
    assert (r.state, label(kb, r)) == ("in_force", "baseline")
    assert any("sin fecha (test sin fecha declarada)" in u for u in r.upcoming)
    for day in ("2025-11-15", "2026-01-01", "2026-06-01"):  # nunca se usa la fecha de producción
        r = at(kb, day, "test")
        assert (r.state, r.reasons) == ("undetermined", ["test_date_missing"]), day
        assert any("test sin fecha declarada" in w for w in r.warnings)
    assert label(kb, at(kb, "2026-01-01", "prod")) == "NT_150#1"
    assert at(kb, "2026-01-01", "prod").reasons == []


def test_resolver_file_order_irrelevant():
    a, b = three_versions(), three_versions(reverse=True)
    for env in ("test", "prod"):
        for day in ("2023-06-16", "2023-12-31", "2024-01-01", "2024-12-31", "2025-01-01", "2030-01-08"):
            ra, rb = at(a, day, env), at(b, day, env)
            assert (ra.state, ra.reasons, label(a, ra), ra.upcoming, ra.interval) == (
                rb.state,
                rb.reasons,
                label(b, rb),
                rb.upcoming,
                rb.interval,
            )
            assert [h.introduced_by for h in ra.history] == [h.introduced_by for h in rb.history]
    assert [t.label for t in timeline(a, KEY)] == [t.label for t in timeline(b, KEY)]


def test_resolver_nt_number_never_orders():
    docs = [
        doc("NT_160", test=date(2025, 6, 1), prod=date(2025, 6, 1), effects=[eff("NT_160")]),
        doc("NT_159", test=date(2025, 9, 1), prod=date(2025, 9, 1), effects=[eff("NT_159")]),
    ]
    kb = make(docs, [val([ver("baseline"), ver(["NT_159#1"], based_on=["NT_160#1"]), ver(["NT_160#1"])])])
    assert label(kb, at(kb, "2025-07-01")) == "NT_160#1"
    assert label(kb, at(kb, "2025-09-01")) == "NT_159#1"
    assert [t.label for t in timeline(kb, KEY)] == ["línea base", "NT_160#1", "NT_159#1"]


def test_resolver_issue_window():
    base = [doc("NT_101", test=date(2024, 1, 1), prod=date(2024, 1, 1), effects=[eff("NT_101")])]
    vals = [val([ver("baseline"), ver(["NT_101#1"])])]

    def issue(iid: str, subject: str, **kw: object) -> Issue:
        scope = IssueScope(
            subject=subject, env=kw.pop("env", None), since=kw.pop("since", None), until=kw.pop("until", None)
        )  # type: ignore[arg-type]
        return Issue(
            id=iid,
            kind="undeclared_change",
            affects=[scope],
            statement=f"enunciado {iid}",
            blocking=kw.pop("blocking", True),  # type: ignore[arg-type]
            status=kw.pop("status", "open"),  # type: ignore[arg-type]
            resolution=kw.pop("resolution", None),  # type: ignore[arg-type]
            policy=None,
        )

    win = issue("ISS-0010", KEY, env="prod", since=date(2025, 2, 1), until=date(2025, 3, 1))
    kb = make(base, vals, issues=[win])
    r = at(kb, "2025-01-31")
    assert r.state == "in_force" and "ISS-0010" in r.open_issues
    assert any(
        "ISS-0010 (undeclared_change, bloqueante fuera de esta fecha o ambiente)" in w for w in r.warnings
    )
    for day in ("2025-02-01", "2025-02-28"):
        r = at(kb, day)
        assert (r.state, r.reasons) == ("undetermined", ["blocking_issue"]), day
        assert label(kb, r) == "NT_101#1"  # muestra la última curada
    assert at(kb, "2025-03-01").state == "in_force"  # [since, until)
    assert at(kb, "2025-02-15", "test").state == "in_force"  # otro ambiente

    # Sujetos indirectos: el efecto que apunta a la clave o su documento.
    for subject in ("NT_101#1", "NT_101"):
        kb2 = make(base, vals, issues=[issue("ISS-0011", subject)])
        assert at(kb2, "2025-02-01").reasons == ["blocking_issue"], subject
    # Otra clave, resuelto o no bloqueante: no bloquea.
    others = [
        issue("ISS-0012", "val:DE:D208b"),
        issue("ISS-0013", KEY, status="resolved", resolution="hecho"),
        issue("ISS-0014", KEY, blocking=False),
    ]
    r = at(make(base, vals, issues=others), "2025-02-01")
    assert (r.state, r.open_issues) == ("in_force", ["ISS-0014"])
    assert any(w.startswith("ISS-0014 (undeclared_change, no bloqueante)") for w in r.warnings)
    assert not any("ISS-0013" in w or "ISS-0012" in w for w in r.warnings)


def test_resolver_beyond_horizon():
    kb = make([], [val([ver("baseline")])], horizon=date(2026, 10, 17))
    r = at(kb, "2026-10-17")
    assert r.state == "in_force" and r.sources_checked_at == date(2026, 10, 17)
    assert not any("fuentes verificadas" in w for w in r.warnings)
    for day in ("2026-10-18", "2026-10-24"):  # gracia: estado normal + aviso
        r = at(kb, day)
        assert r.state == "in_force" and any("fuentes verificadas el 2026-10-17" in w for w in r.warnings)
    r = at(kb, "2026-10-25")
    assert (r.state, r.reasons) == ("undetermined", ["beyond_horizon"])
    assert label(kb, r) == "baseline"  # mejor versión
    # Un chequeo con URL sin registrar no avanza el horizonte.
    dirty = make(
        [], [val([ver("baseline")])], checks=[check(date(2026, 10, 17)), check(date(2027, 1, 1), ["u"])]
    )
    assert at(dirty, "2026-12-01").reasons == ["beyond_horizon"]
    # Sin ningún chequeo limpio: nada puede afirmarse.
    never = make([], [val([ver("baseline")])], horizon=None)
    r = at(never, "2024-01-01")
    assert r.reasons == ["beyond_horizon"] and any("nunca verificadas" in w for w in r.warnings)
    # `now` solo agrega el aviso de antigüedad; no cambia el estado.
    r = resolve(kb, KEY, date(2026, 10, 1), "prod", now=date(2026, 12, 1))
    assert r.state == "in_force" and any("hace 45 días" in w for w in r.warnings)


def test_resolver_revision_not_curated(tmp_path: Path):
    d = doc(
        "NT_170",
        test=date(2025, 6, 1),
        prod=date(2025, 6, 1),
        ddate=date(2025, 5, 10),
        effects=[eff("NT_170")],
    )
    vals = [val([ver("baseline"), ver(["NT_170#1"])])]
    newer = rev("NT_170", sha("NT_170:rev2"), retrieved=datetime(2025, 7, 1))
    kb = make([d], vals, extra_revs=[newer])
    assert at(kb, "2025-05-09").state == "in_force"
    r = at(kb, "2025-05-10")  # desde la fecha del documento, sin Issue manual
    assert (r.state, r.reasons) == ("undetermined", ["revision_not_curated"])
    assert any("NT_170: la revisión" in w and "no está curada" in w for w in r.warnings)

    # Documento registrado sin ficha: sin curar desde coverage_from; sin raw/ afecta a toda clave.
    loose = rev("NT_171", sha("NT_171"), retrieved=datetime(2025, 7, 1))
    kb2 = make([], [val([ver("baseline")]), val([ver("baseline")], vid="D210a")], extra_revs=[loose])
    assert at(kb2, "2023-06-16").reasons == []  # antes de coverage_from no cuenta
    assert at(kb2, "2023-06-17").state == "undetermined"
    assert at(kb2, "2024-01-01", key="val:DE:D210a").reasons == ["revision_not_curated"]

    # Con raw/: solo afecta a las claves que menciona.
    raw = make(
        [],
        [val([ver("baseline")]), val([ver("baseline", code="1323")], vid="D210a")],
        extra_revs=[loose],
        root=tmp_path,
    )
    write_text(
        page_path(tmp_path, "NT_171", sha("NT_171")[:12], 1), "Se modifica la validación D208c (1321).\n"
    )
    assert at(raw, "2024-01-01").reasons == ["revision_not_curated"]
    assert at(raw, "2024-01-01", key="val:DE:D210a").state == "in_force"


def test_resolver_processing_date_unknown():
    kb = three_versions()
    calls: list[str] = []

    def evaluate(v):
        calls.append("+".join(v.introduced_by) if v.introduced_by != "baseline" else "baseline")
        return {"NT_101#1": False, "NT_102#1": True}.get(calls[-1])

    out = resolve_xml_axes(kb, KEY, date(2024, 12, 30), None, "prod", evaluate)
    assert (out["state"], out["reasons"]) == ("undetermined", ["processing_date_unknown"])
    assert out["boundary"] == date(2025, 1, 1) and out["verdict"] is None
    assert out["processing"] is None and out["processing_date_source"] == "unknown"
    assert out["emission"]["verdict"] is False and label(kb, out["resolution"]) == "NT_101#1"
    assert calls == ["NT_101#1"]
    # Sin frontera entre la emisión y el horizonte: se resuelve normalmente.
    out = resolve_xml_axes(kb, KEY, date(2025, 2, 1), None, "prod", evaluate)
    assert (out["state"], out["reasons"], out["verdict"]) == ("in_force", [], True)
    assert out["resolution"].processing_date_source == "unknown"


def test_resolver_axis_split():
    kb = three_versions()

    def evaluate(v):
        return {"NT_101#1": False, "NT_102#1": True}["+".join(v.introduced_by)]

    out = resolve_xml_axes(
        kb, KEY, date(2024, 12, 30), date(2025, 1, 2), "prod", evaluate, processing_date_source="response"
    )
    assert (out["state"], out["reasons"], out["verdict"]) == ("undetermined", ["axis_split"], None)
    assert out["emission"]["verdict"] is False and out["processing"]["verdict"] is True
    assert label(kb, out["resolution"]) == "NT_102#1"  # eje por defecto: procesamiento (A2)
    assert out["resolution"].processing_date_source == "response"
    assert any(w.startswith("axis_split:") for w in out["resolution"].warnings)
    # Mismo veredicto en ambas versiones: no hay división.
    out = resolve_xml_axes(kb, KEY, date(2024, 12, 30), date(2025, 1, 2), "prod", lambda v: False)
    assert (out["state"], out["verdict"]) == ("in_force", False)
    # Misma versión por ambos ejes: el evaluador se llama una sola vez.
    n: list[int] = []
    out = resolve_xml_axes(kb, KEY, date(2025, 2, 1), date(2025, 2, 3), "prod", lambda v: n.append(1) or True)
    assert out["verdict"] is True and n == [1]
    # Con date_axis_default = emission, la resolución definitiva es la de emisión.
    emi = make(list(kb.documents.values()), list(kb.validations.values()), kbmeta=meta(axis="emission"))
    out = resolve_xml_axes(emi, KEY, date(2024, 12, 30), date(2025, 1, 2), "prod", lambda v: False)
    assert label(emi, out["resolution"]) == "NT_101#1"


def test_resolver_outside_coverage_and_approx_start():
    # Eliminación real sin calendario (patrón de NT 2 sobre D208d): inicio aproximado.
    nt2 = doc(
        "NT_002",
        schedule=False,
        ddate=date(2020, 7, 16),
        effects=[eff("NT_002", action="remove", target="val:DE:D208d")],
        change_period=(stmt("NT_002", "desde", date(2020, 2, 1)), stmt("NT_002", "hasta", date(2020, 7, 1))),
    )
    kb = make(
        [nt2],
        [val([ver("baseline", code="1322"), ver(["NT_002#1"], kind="tombstone", code="1322")], vid="D208d")],
    )
    key = "val:DE:D208d"
    assert effect_start(kb, "NT_002#1", "prod") == (date(2020, 7, 16), "approx")
    r = at(kb, "2020-08-01", key=key)
    assert r.state == "outside_coverage" and label(kb, r) == "NT_002#1"
    assert any("fuera de cobertura" in w for w in r.warnings)
    r = at(kb, "2023-06-16", key=key)
    assert r.state == "outside_coverage"
    r = at(kb, "2025-03-01", key=key)
    assert r.state == "removed" and r.interval[0].basis == "approx"  # type: ignore[index]
    assert any("inicio aproximado: NT_002" in w and "01/02/2020" in w for w in r.warnings)
    # Documento sin fecha ni calendario: anterior a todo.
    nodate = make(
        [doc("NT_003", schedule=False, effects=[eff("NT_003")])], [val([ver("baseline"), ver(["NT_003#1"])])]
    )
    assert effect_start(nodate, "NT_003#1", "test") == (PRE_COVERAGE, "approx")


def test_resolver_severity_versioned():
    """[HIP] Un cambio AO → R no declarado como el de GED003: la severidad es por versión."""
    d = doc("NT_903", test=date(2027, 4, 1), prod=date(2027, 5, 1), effects=[eff("NT_903")])
    kb = make([d], [val([ver("baseline", severity="AO"), ver(["NT_903#1"], severity="R")], vid="GED003")])
    key = "val:DE:GED003"
    for day, env, sev in (
        ("2027-04-30", "prod", "AO"),
        ("2027-05-01", "prod", "R"),
        ("2027-04-01", "test", "R"),
    ):
        v = chosen_version(kb, at(kb, day, env, key=key))
        assert v is not None and v.severity == sev, (day, env)
    assert diff_versions(*kb.validations[key].versions) == ["observation", "severity"]


# --- Inicios y casos de G.3 -----------------------------------------------------------------------
def test_effect_start_from_revision():
    r1, r2 = sha("NT_180:rev1"), sha("NT_180:rev2")
    d = doc(
        "NT_180",
        test=date(2024, 1, 1),
        prod=date(2024, 1, 1),
        current=r2,
        effects=[eff("NT_180", from_revision=r2[:12])],
    )
    revs = [
        rev("NT_180", r1, retrieved=datetime(2023, 12, 1), portal=datetime(2023, 12, 1)),
        rev("NT_180", r2, retrieved=datetime(2024, 6, 7), portal=datetime(2024, 6, 6, 15, 30)),
    ]
    kb = make([d], [val([ver("baseline"), ver(["NT_180#1"])])], extra_revs=revs)
    # La re-subida que cambió filas rige desde la subida, nunca retroactivamente (G.3).
    assert effect_start(kb, "NT_180#1", "prod") == (date(2024, 6, 6), "stated")
    assert label(kb, at(kb, "2024-06-05")) == "baseline"
    assert label(kb, at(kb, "2024-06-06")) == "NT_180#1"
    # Subida anterior a la fecha declarada: rige la fecha declarada.
    early = d.model_copy(
        update={
            "schedule": Schedule(
                test=stmt("NT_180", "test", date(2024, 9, 1)), prod=stmt("NT_180", "prod", date(2024, 9, 1))
            )
        }
    )
    kb2 = make([early], list(kb.validations.values()), extra_revs=revs)
    assert effect_start(kb2, "NT_180#1", "prod") == (date(2024, 9, 1), "stated")
    # Sin ?t= del portal: la descarga acota la subida (aproximada).
    revs_np = [revs[0], revs[1].model_copy(update={"portal_t": None})]
    kb3 = make([d], list(kb.validations.values()), extra_revs=revs_np)
    assert effect_start(kb3, "NT_180#1", "prod") == (date(2024, 6, 7), "approx")
    # from_revision fuera del manifiesto: error de datos.
    with pytest.raises(TemporalDataError, match="from_revision"):
        effect_start(build_kb(ROOT, meta=meta(), documents=[d]), "NT_180#1", "prod")


def test_version_start_unknown_effect_is_error():
    kb = make([], [val([ver("baseline"), ver(["NT_199#1"])])])
    with pytest.raises(TemporalDataError, match="NT_199#1 no existe"):
        at(kb, "2025-01-01")
    assert version_start(kb, ver("baseline"), "prod")[1] == "baseline"


def test_resolver_supersession_oracle_warns_on_mismatch():
    sup = Supersession(
        doc="NT_102",
        since=date(2025, 1, 1),
        stated_in=PageRef(doc="NT_101", rev=sha("NT_101")[:12], page_pdf=1, quote="VER NOTA TÉCNICA N° 102"),
    )
    kb = three_versions()
    ok = make(
        [kb.documents["NT_101"].model_copy(update={"superseded_by": sup}), kb.documents["NT_102"]],
        list(kb.validations.values()),
    )
    assert not any("la reemplaza" in w for w in at(ok, "2024-06-01").warnings)
    # Sin la versión de NT_102 la KB no puede afirmar que NT_101 sigue vigente sin decirlo.
    only = make([ok.documents["NT_101"]], [val([ver("baseline"), ver(["NT_101#1"])])])
    r = at(only, "2025-06-01")
    assert any(
        "NT_101 declara que NT_102 la reemplaza desde 2025-01-01, pero el fin derivado es abierto" in w
        for w in r.warnings
    )


def test_resolver_not_yet_existing():
    d = doc("NT_190", test=date(2025, 1, 1), prod=date(2025, 1, 1), effects=[eff("NT_190", action="add")])
    kb = make([d], [val([ver(["NT_190#1"])])])
    r = at(kb, "2024-12-31")
    assert (r.state, r.version_index) == ("not_yet_existing", None)
    assert r.interval == (None, r.interval[1]) and r.interval[1].date == date(2025, 1, 1)  # type: ignore[index, union-attr]
    assert at(kb, "2025-01-01").state == "in_force"


def test_timeline_and_history():
    kb = three_versions()
    tl = timeline(kb, KEY, "prod")
    assert [(t.label, t.start.date if t.start else None, t.end.date if t.end else None) for t in tl] == [
        ("línea base", None, date(2024, 1, 1)),
        ("NT_101#1", date(2024, 1, 1), date(2025, 1, 1)),
        ("NT_102#1", date(2025, 1, 1), None),
    ]
    assert tl[0].start is not None and tl[0].start.basis == "baseline"
    assert timeline(kb, "val:DE:NOEXISTE") == []
    r = at(kb, "2024-06-01")
    assert [h.introduced_by for h in r.history] == ["baseline", ["NT_101#1"], ["NT_102#1"]]


def test_cut_kb():
    kb = three_versions()
    sup = Supersession(
        doc="NT_102",
        since=date(2025, 1, 1),
        stated_in=PageRef(doc="NT_101", rev=sha("NT_101")[:12], page_pdf=1, quote="q"),
    )
    iss = Issue(
        id="ISS-0020",
        kind="temporal",
        affects=[IssueScope(subject="NT_102")],
        statement="s",
        blocking=True,
        status="open",
    )
    full = make(
        [kb.documents["NT_101"].model_copy(update={"superseded_by": sup}), kb.documents["NT_102"]],
        list(kb.validations.values()),
        issues=[iss],
    )
    cut = cut_kb(full, date(2024, 6, 1))
    assert set(cut.documents) == {"NT_101"} and cut.documents["NT_101"].superseded_by is None
    assert [v.introduced_by for v in cut.validations[KEY].versions] == ["baseline", ["NT_101#1"]]
    assert cut.issues == {} and cut.horizon() == date(2024, 6, 1)
    assert {r.doc for r in cut.manifest.revisions} == {"NT_101"}
    assert at(cut, "2024-06-08").state == "in_force"
    assert at(cut, "2024-06-09").reasons == ["beyond_horizon"]
    assert full.documents["NT_102"] is not None and len(full.validations[KEY].versions) == 3  # sin mutar


def test_build_kb_rejects_duplicates():
    d = doc("NT_101", prod=date(2024, 1, 1))
    with pytest.raises(TemporalDataError, match="duplicado"):
        make([d, d])


# --- Menciones (modo índice: not_curated) -----------------------------------------------------------
def _raw_kb(tmp_path: Path) -> KB:
    docs = [
        doc("NT_205", test=date(2026, 1, 1), prod=date(2026, 2, 1), ddate=date(2025, 12, 1)),
        doc("NT_210", test=date(2023, 9, 1), prod=date(2023, 10, 1), ddate=date(2023, 8, 1)),
        doc("NT_207", schedule=False, ddate=date(2021, 1, 1)),
        doc("NT_208", schedule=False),
    ]
    old = rev("NT_205", sha("NT_205:old"), retrieved=datetime(2019, 1, 1))  # revisión anterior: no se lee
    kb = make(docs, [val([ver("baseline")])], extra_revs=[old], root=tmp_path)
    pages = {
        ("NT_205", 1): "Fechas de la NT\n",
        ("NT_205", 2): "Se modifica D208c (código 1321) en la\nobservación del receptor.\n",
        ("NT_210", 3): "El código 1321 ya no aplica.\n",
        ("NT_210", 4): "Solo D2080 y 13210 aparecen aquí.\n",
        ("NT_207", 1): "iTipIDRec y 1321\n",
        ("NT_208", 5): "Mención 1321 sin fecha alguna.\n",
    }
    for (d, p), text in pages.items():
        write_text(page_path(tmp_path, d, sha(d)[:12], p), text)
    write_text(page_path(tmp_path, "NT_205", sha("NT_205:old")[:12], 9), "1321 en la revisión vieja\n")
    write_index(tmp_path, "NT_205", sha("NT_205")[:12], {"pages": [{"page": 2, "page_printed": 166}]})
    write_text(tmp_path / "raw" / "_ledger" / "changes.jsonl", '{"doc": "NT_299", "text": "1321"}\n')
    return kb


def test_find_mentions_order_whole_word_and_printed_page(tmp_path: Path):
    kb = _raw_kb(tmp_path)
    ms = find_mentions(kb, ["1321"])
    # Producción desc. (NT_205 2026 antes que NT_210 2023, aunque su número sea menor); sin
    # calendario al final, por fecha de documento; nunca por número de NT.
    assert [(m.doc, m.page_pdf) for m in ms] == [("NT_205", 2), ("NT_210", 3), ("NT_207", 1), ("NT_208", 5)]
    assert ms[0].page_printed == 166 and ms[0].prod_date == date(2026, 2, 1)
    assert ms[0].rev == sha("NT_205")[:12]  # solo la revisión más reciente
    assert "D208c (código 1321) en la observación" in ms[0].excerpt  # texto normalizado
    assert [m.doc for m in find_mentions(kb, ["D208"])] == []  # ni D208c ni D2080
    assert [m.doc for m in find_mentions(kb, ["D2080"])] == ["NT_210"]
    assert find_mentions(make([], root=Path("/nonexistent")), ["1321"]) == []


def test_resolve_not_curated_returns_mentions(tmp_path: Path):
    kb = _raw_kb(tmp_path)
    r = resolve(kb, "1321", date(2026, 3, 1))
    assert (r.state, r.key, r.version_index) == ("not_curated", None, None)
    assert r.mentions[0].doc == "NT_205" and r.warnings[0].startswith("vigencia no resuelta")
    r = resolve(kb, "val:DE:D999", date(2026, 3, 1))
    assert (r.state, r.key, r.mentions) == ("not_curated", "val:DE:D999", [])
    assert key_terms(kb, KEY) == ["D208c", "1321"]


def test_find_mentions_without_ficha_orders_by_extracted_dates(tmp_path: Path):
    """Sin ficha en kb/documents (entregable 0) ordena por los literales `nt_info` de index.json,
    nunca por número de NT; las fechas en palabras (NT 013) se entienden y un literal que no es una
    fecha ("a definir") cuenta como sin fecha."""
    docs = ("NT_021", "NT_024", "NT_013", "NT_099", "MT_V150")
    revs = [rev(d, sha(d), retrieved=datetime(2026, 1, 1)) for d in docs]
    kb = make([], [val([ver("baseline")])], extra_revs=revs, root=tmp_path)
    infos = {
        "NT_021": {"fecha_literal": "29/12/2023", "prod_literal": "01/01/2024"},
        "NT_024": {"fecha_literal": "17/12/2024", "prod_literal": "01/01/2025"},
        "NT_013": {"fecha_literal": "20/03/2023", "prod_literal": "17 de Junio del 2023"},
        "NT_099": {"fecha_literal": "a definir", "prod_literal": "a definir"},
    }
    for d in docs:
        write_text(page_path(tmp_path, d, sha(d)[:12], 1), "Código 1321\n")
        write_index(tmp_path, d, sha(d)[:12], {"nt_info": infos.get(d), "pages": []})
    ms = find_mentions(kb, ["1321"])
    # Sin fecha al final; entre dos sin fecha desempata el DocId (determinismo), no el número.
    assert [m.doc for m in ms] == ["NT_024", "NT_021", "NT_013", "MT_V150", "NT_099"]
    assert ms[0].prod_date == date(2025, 1, 1) and ms[2].prod_date == date(2023, 6, 17)
    assert ms[4].prod_date is None


def test_pending_untargeted_mentioning(tmp_path: Path):
    pend = doc(
        "NT_220",
        test=date(2025, 1, 1),
        prod=date(2025, 1, 1),
        effects=[eff("NT_220", target=None, disposition="pending")],
    )
    vals = [val([ver("baseline")]), val([ver("baseline", code="1323")], vid="D210a")]
    kb = make([pend], vals, root=tmp_path)
    # Sin raw/ no puede descartarse: cuenta para toda clave.
    assert at(kb, "2025-02-01", key="val:DE:D210a").reasons == ["pending_effect"]
    write_text(page_path(tmp_path, "NT_220", sha("NT_220")[:12], 1), "Se modifica la validación D208c.\n")
    assert at(kb, "2025-02-01").reasons == ["pending_effect"]
    assert at(kb, "2025-02-01", key="val:DE:D210a").reasons == []


@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (None, None),
        ({"pages": [{"page": 3, "printed_page": "166"}]}, 166),
        ({"pages": {"3": {"printed": 166}}}, 166),
        ({"pages": {"3": 166}}, 166),
        ({"pages": [{"page_pdf": 3, "page_printed": None}]}, None),
        ({"pages": [{"page": 4, "page_printed": 1}]}, None),
    ],
)
def test_printed_page_variants(index, expected):
    assert printed_page(index, 3) == expected

"""Golden temporal declarativo (docs/arquitectura.md §K.5).

- `tests/fixtures/golden_hyp.yaml` contra la KB de fixture [HIP] (`tests/fixtures/kb_hyp/` y su
  variante `kb_hyp_rev2/`), más la verificación de la propia fixture (carga, formato canónico,
  regeneración idéntica y oráculo de la marca de agua).
- `tests/golden/temporal.yaml` contra la KB real del repositorio, si existe (si no, skip limpio).

Formato de fila: ver la cabecera de `tests/fixtures/golden_hyp.yaml`.
"""

from __future__ import annotations

import importlib.util
import shutil
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from sifen_kb.load import KB, load_kb
from sifen_kb.model import Boundary, FieldVersion, Resolution
from sifen_kb.temporal import (
    Version,
    chosen_version,
    cut_kb,
    diff_versions,
    resolve,
    resolve_xml_axes,
    timeline,
    version_label,
)
from sifen_kb.yamlio import is_canonical, load_kb_file, write_kb_file

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
GOLDEN_HYP = FIXTURES / "golden_hyp.yaml"
GOLDEN_REAL = TESTS / "golden" / "temporal.yaml"
BASES = {
    "hyp": FIXTURES / "kb_hyp",
    "hyp_rev2_pendiente": FIXTURES / "kb_hyp_rev2",
    "real": TESTS.parent,
}
ENVS = ("test", "prod")


# --- KB por fila ---------------------------------------------------------------------------------------
@cache
def base_kb(name: str) -> KB:
    kb = load_kb(BASES[name])
    assert kb.root == BASES[name].resolve(), f"find_root no reconoce {BASES[name]}"
    assert not kb.errors, kb.errors
    return kb


@cache
def kb_for(spec: str, default: str) -> KB:
    """`hyp`, `hyp_rev2_pendiente`, `real` o `corte:AAAA-MM-DD` (corte de la KB base del archivo)."""
    if spec.startswith("corte:"):
        return cut_kb(base_kb(default), date.fromisoformat(spec.removeprefix("corte:")))
    return base_kb(spec)


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = load_kb_file(path) or []
    assert isinstance(data, list), f"{path}: se esperaba una lista de filas"
    return data


def row_id(i: int, row: dict[str, Any] | None) -> str:
    if row is None:
        return "sin-golden"
    return str(row.get("id") or f"{i:02d}-{row.get('key')}-{row.get('at')}-{row.get('env', 'prod')}")


# --- Comprobaciones ------------------------------------------------------------------------------------
def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _ctx(res: Resolution) -> str:
    return (
        f"state={res.state} reasons={res.reasons} version={res.version_index} interval={res.interval}\n"
        f"  upcoming={res.upcoming}\n  warnings={res.warnings}"
    )


def _boundary_txt(b: Boundary | None) -> str | None:
    if b is None:
        return None
    return "baseline" if b.basis == "baseline" else (b.date.isoformat() if b.date else None)


def check_resolution(kb: KB, res: Resolution, exp: dict[str, Any]) -> None:
    """Consume de `exp` las claves que verifica sobre una `Resolution`."""
    ctx = _ctx(res)
    assert res.state == exp.pop("state"), ctx
    assert sorted(res.reasons) == sorted(exp.pop("reasons", [])), ctx
    v = chosen_version(kb, res)
    if "introduced_by" in exp:
        assert (v.introduced_by if v else None) == exp.pop("introduced_by"), ctx
    if "kind" in exp:
        assert v is not None and v.kind == exp.pop("kind"), ctx
    for attr in ("code", "severity"):
        if attr in exp:
            assert getattr(v, attr, None) == exp.pop(attr), ctx
    for name, pos in (("interval_from", 0), ("interval_to", 1)):
        if name in exp:
            want = exp.pop(name)
            got = _boundary_txt(res.interval[pos]) if res.interval else None
            assert got == want, f"{name}: {got} ≠ {want}\n{ctx}"
    for s in exp.pop("upcoming_includes", []):
        assert any(s in u for u in res.upcoming), f"upcoming sin {s!r}\n{ctx}"
    for s in exp.pop("upcoming_excludes", []):
        assert not any(s in u for u in res.upcoming), f"upcoming con {s!r}\n{ctx}"
    if exp.pop("upcoming_empty", False):
        assert res.upcoming == [], ctx
    for s in exp.pop("warnings_includes", []):
        assert any(s in w for w in res.warnings), f"warnings sin {s!r}\n{ctx}"
    for s in exp.pop("open_issues_includes", []):
        assert s in res.open_issues, ctx
    if "pending_effects" in exp:
        assert res.pending_effects == exp.pop("pending_effects"), ctx
    if "history" in exp:
        labels = [
            "línea base" if h.introduced_by == "baseline" else "+".join(h.introduced_by) for h in res.history
        ]
        assert labels == exp.pop("history"), ctx
    for name, present in (("enum_includes", True), ("enum_excludes", False)):
        if name in exp:
            assert isinstance(v, FieldVersion), ctx
            codes = {e.code for e in v.enumeration or []}
            assert (exp.pop(name) in codes) is present, ctx
    if "mentions_first" in exp:
        assert res.mentions and res.mentions[0].doc == exp.pop("mentions_first"), ctx


def declared_scope_check(kb: KB, key: str, frm: str, to: str) -> tuple[list[str], list[str]]:
    """(atributos que cambian, violaciones del alcance declarado) de la versión `frm` a `to`.

    Un atributo interpretado solo puede cambiar si cambió su literal (anti-R3); con alcance `row`,
    todo cambio distinto de la observación debe estar en `acknowledged_changes`.
    """
    ent = kb.entity(key)
    assert ent is not None
    by_label: dict[str, Version] = {version_label(v): v for v in ent.versions}
    a, b = by_label[frm], by_label[to]
    changed = diff_versions(a, b)
    allowed: set[str] = set()
    effects = [] if b.introduced_by == "baseline" else [kb.effect(e) for e in b.introduced_by]
    for e in effects:
        if e.declared_scope == "row":
            allowed |= {"observation", "observations", *e.acknowledged_changes}
        else:
            allowed |= set(e.declared_scope)
    literal_of = {
        "condition": "observation",
        "enumeration": "observations",
        "enumeration_interpretation": "observations",
    }
    violations = []
    for attr in changed:
        if attr in literal_of:
            if literal_of[attr] not in changed:
                violations.append(f"{attr} cambia sin que cambie su literal {literal_of[attr]}")
        elif attr not in allowed:
            violations.append(f"{attr} fuera del alcance declarado {sorted(allowed)}")
    return changed, violations


def _verdicts_evaluator(verdicts: dict[str, Any]) -> Any:
    """Evaluador de la fila: el veredicto por versión lo declara el golden (el DSL se prueba aparte)."""

    def evaluate(v: Version) -> bool | None:
        label = version_label(v)
        assert label in verdicts, f"la fila no declara el veredicto de {label}"
        return verdicts[label]

    return evaluate


def run_row(row: dict[str, Any], default_kb: str) -> None:
    kb = kb_for(row.get("kb", default_kb), default_kb)
    exp = dict(row["expect"])
    key = row["key"]
    if "diff" in row:
        frm, to = row["diff"]
        changed, violations = declared_scope_check(kb, key, frm, to)
        if "changed" in exp:
            assert changed == sorted(exp.pop("changed"))
        if "within_declared_scope" in exp:
            assert (not violations) is exp.pop("within_declared_scope"), violations
    else:
        at = date.fromisoformat(row["at"])
        env = row.get("env", "prod")
        if "processed_at" in row:
            out = resolve_xml_axes(
                kb, key, at, _d(row["processed_at"]), env, _verdicts_evaluator(row.get("verdicts") or {})
            )
            res = out["resolution"]
            assert out["state"] == res.state and out["reasons"] == list(res.reasons)
            if "verdict" in exp:
                assert out["verdict"] is exp.pop("verdict"), out
            if "emission_verdict" in exp:
                assert out["emission"]["verdict"] is exp.pop("emission_verdict"), out
            if "processing_verdict" in exp:
                assert out["processing"]["verdict"] is exp.pop("processing_verdict"), out
            if "boundary" in exp:
                assert out["boundary"] == _d(exp.pop("boundary")), out
        else:
            res = resolve(kb, key, at, env)
        check_resolution(kb, res, exp)
    assert not exp, f"claves de expect desconocidas: {sorted(exp)}"


# --- Golden [HIP] -----------------------------------------------------------------------------------
HYP_ROWS = load_rows(GOLDEN_HYP)


@pytest.mark.parametrize("row", HYP_ROWS, ids=[row_id(i, r) for i, r in enumerate(HYP_ROWS)])
def test_golden_hyp(row: dict[str, Any]) -> None:
    run_row(row, default_kb="hyp")


def _blocking_windows(kb: KB) -> list[tuple[str, date, str | None]]:
    """(clave curada, día de frontera, ambiente o None) de cada ventana de un Issue bloqueante abierto.

    Sujeto clave de entidad, o efecto (cuenta su destino); un documento como sujeto no se expande.
    """
    out = []
    for issue in kb.issues.values():
        if issue.status != "open" or not issue.blocking:
            continue
        for s in issue.affects:
            key = kb.effect(s.subject).target if kb.has_effect(s.subject) else s.subject
            if key is None or not kb.is_curated(key):
                continue
            out += [(key, d, s.env) for d in (s.since, s.until) if d is not None]
    return out


def boundary_gaps(kb: KB, rows: list[dict[str, Any]]) -> list[str]:
    """Regla de completitud: por frontera, filas el día anterior y el día del cambio, en cada
    ambiente donde las fechas difieran (si coinciden, basta un ambiente). Incluye cobertura,
    horizonte (en cualquier clave) y los bordes de la ventana de cada Issue bloqueante abierto
    (`since`/`until`, en su ambiente; defecto menor del paso A de docs/traspaso-curacion-piloto.md)."""
    plain = [r for r in rows if "diff" not in r and "processed_at" not in r]
    have = {(r["key"], date.fromisoformat(r["at"]), r.get("env", "prod")) for r in plain}

    def has(key: str | None, day: date, env: str | None) -> bool:
        return any((k == key or key is None) and d == day and (env is None or e == env) for k, d, e in have)

    missing: list[str] = []
    for key in sorted({r["key"] for r in plain if kb.is_curated(r["key"])}):
        starts = {
            env: {t.index: t.start.date for t in timeline(kb, key, env) if t.start and t.start.date}
            for env in ENVS
        }
        for env in ENVS:
            other = "prod" if env == "test" else "test"
            for idx, d in starts[env].items():
                same = starts[other].get(idx) == d
                for day in (d - timedelta(days=1), d):
                    if not has(key, day, None if same else env):
                        missing.append(f"{key} {day} {'cualquier ambiente' if same else env}")
    for key, d, env in _blocking_windows(kb):
        for day in (d - timedelta(days=1), d):
            if not has(key, day, env):
                missing.append(f"{key} {day} {env or 'cualquier ambiente'} (ventana de Issue bloqueante)")
    assert kb.meta is not None
    cov = kb.meta.coverage_from
    horizon = kb.horizon()
    days = [cov - timedelta(days=1), cov]
    if horizon is not None:
        limit = horizon + timedelta(days=kb.meta.horizon_grace_days)
        days += [limit, limit + timedelta(days=1)]
    missing += [f"(cobertura/horizonte) {d}" for d in days if not has(None, d, None)]
    return sorted(set(missing))


def test_golden_hyp_completeness() -> None:
    rows = [r for r in HYP_ROWS if r.get("kb", "hyp") == "hyp"]
    assert boundary_gaps(base_kb("hyp"), rows) == []


def test_completeness_requires_rows_at_blocking_issue_windows(tmp_path: Path) -> None:
    """Un Issue bloqueante abierto abre una frontera: hacen falta filas el día anterior y el día de su
    `since`/`until`, en su ambiente (un Issue no bloqueante o resuelto no la abre)."""
    root = tmp_path / "kb_hyp"
    shutil.copytree(BASES["hyp"], root)
    issue = {
        "id": "ISS-0003",
        "kind": "ambiguity",
        "affects": [{"subject": "NT_024#1", "env": "test", "since": "2026-03-02"}],
        "statement": "[fixture] ventana bloqueante",
        "blocking": True,
        "status": "open",
    }
    write_kb_file(root / "kb" / "issues" / "ISS-0003.yaml", issue)
    rows = [r for r in HYP_ROWS if r.get("kb", "hyp") == "hyp"]
    gaps = boundary_gaps(load_kb(root), rows)
    assert gaps == [
        "val:DE:D208c 2026-03-01 test (ventana de Issue bloqueante)",
        "val:DE:D208c 2026-03-02 test (ventana de Issue bloqueante)",
    ]
    write_kb_file(root / "kb" / "issues" / "ISS-0003.yaml", issue | {"blocking": False})
    assert boundary_gaps(load_kb(root), rows) == []


def test_golden_hyp_covers_g5_rows() -> None:
    ids = {r.get("id") for r in HYP_ROWS}
    want = {f"G5-{n:02d}" for n in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20)}
    assert want <= ids, sorted(want - ids)


def test_diff_scope_detects_out_of_scope_message_change() -> None:
    """G5-19, mitad negativa: si el curador también tocara `message`, el alcance [observation] falla."""
    kb = base_kb("hyp")
    ent = kb.validations["val:DE:D208c"]
    v3 = ent.versions[3]
    assert version_label(v3) == "NT_901#1"
    bad = ent.model_copy(
        update={"versions": [*ent.versions[:3], v3.model_copy(update={"message": v3.message + " (editado)"})]}
    )
    kb2 = cut_kb(kb, date(2100, 1, 1))  # copia sin cortar nada
    kb2.validations["val:DE:D208c"] = bad
    changed, violations = declared_scope_check(kb2, "val:DE:D208c", "NT_024#1", "NT_901#1")
    assert changed == ["condition", "message", "observation"]
    assert violations == ["message fuera del alcance declarado ['observation']"]


# --- La fixture ------------------------------------------------------------------------------------
def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_kb_hyp", FIXTURES / "make_kb_hyp.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("name", ["hyp", "hyp_rev2_pendiente"])
def test_fixture_loads_and_is_canonical(name: str) -> None:
    kb = base_kb(name)
    assert set(kb.documents) == {"MT_V150", "NT_021", "NT_024", "NT_901", "NT_902"}
    assert kb.horizon() == date(2027, 12, 31)
    for p in sorted((kb.root / "kb").rglob("*.yaml")) + [kb.root / "sources.manifest.yaml"]:
        assert is_canonical(p.read_text(encoding="utf-8"), source=str(p)), p


def test_fixture_regenerates_identically(tmp_path: Path) -> None:
    assert _generator().main(base=tmp_path) == 0
    for name in ("kb_hyp", "kb_hyp_rev2"):
        mine = sorted(p.relative_to(tmp_path / name) for p in (tmp_path / name).rglob("*") if p.is_file())
        theirs = sorted(p.relative_to(FIXTURES / name) for p in (FIXTURES / name).rglob("*") if p.is_file())
        assert mine == theirs, f"{name}: ejecutar `uv run python tests/fixtures/make_kb_hyp.py`"
        for rel in mine:
            assert (tmp_path / name / rel).read_bytes() == (FIXTURES / name / rel).read_bytes(), rel


def test_fixture_rev2_differs_only_in_nt901_curation() -> None:
    a, b = base_kb("hyp"), base_kb("hyp_rev2_pendiente")
    assert a.manifest == b.manifest
    assert a.latest_revision("NT_901").sha256 == a.documents["NT_901"].current_revision  # type: ignore[union-attr]
    assert b.latest_revision("NT_901").sha256 != b.documents["NT_901"].current_revision  # type: ignore[union-attr]
    assert "ISS-0001" in a.issues and "ISS-0001" not in b.issues


def test_watermark_oracle() -> None:
    """El fin derivado (producción) de todo lo que introdujo un documento con `superseded_by` es
    `superseded_by.since` (NT 21 → NT 24 desde 2025-01-01)."""
    kb = base_kb("hyp")
    checked = 0
    for doc in kb.documents.values():
        if doc.superseded_by is None:
            continue
        mine = {e.id for e in doc.effects}
        for key in kb.entities():
            for t in timeline(kb, key, "prod"):
                if t.version.introduced_by != "baseline" and set(t.version.introduced_by) & mine:
                    assert t.end is not None and t.end.date == doc.superseded_by.since, (key, t.label)
                    checked += 1
    assert checked >= 1


# --- Golden de la KB real ---------------------------------------------------------------------------
REAL_ROWS: list[dict[str, Any] | None] = list(load_rows(GOLDEN_REAL)) if GOLDEN_REAL.exists() else [None]


@pytest.mark.skipif(not GOLDEN_REAL.exists(), reason="tests/golden/temporal.yaml todavía no existe")
@pytest.mark.parametrize("row", REAL_ROWS, ids=[row_id(i, r) for i, r in enumerate(REAL_ROWS)])
def test_golden_real(row: dict[str, Any]) -> None:
    assert row is not None
    run_row(row, default_kb="real")


@pytest.mark.skipif(not GOLDEN_REAL.exists(), reason="tests/golden/temporal.yaml todavía no existe")
def test_golden_real_completeness() -> None:
    rows = [r for r in REAL_ROWS if r is not None and r.get("kb", "real") == "real"]
    assert boundary_gaps(base_kb("real"), rows) == []

"""Tests de `sifen explain` y `sifen status` (docs/arquitectura.md §G.2, §G.4, §K.1, §K.6, §K.7, §M, §O).

KB usadas (todas de solo lectura; las variantes se arman en `tmp_path`):

- `tests/fixtures/kb_hyp` y `kb_hyp_rev2`: escenario [HIP] de D208c (sin `raw/` ni XSD).
- `tests/fixtures/explain/kb_index`: sin `kb/`, con manifiesto y `raw/` sintético (modo índice).
- `kb_xml` (sesión): copia de `kb_hyp` + campos D011/F014/F023/D210 + ficha de XSD_DIR + la
  instantánea XSD oficial de `sources/XSD_DIR/2026-10-17` (se omite si no existe).
- `kb_multi`: copia de `kb_hyp` + validaciones de fixture (D208 = campo y validación, colisión de
  código 1321, código que cambia 1777 → 1778).
- El repositorio real (entregable 0): solo si 1321 todavía no está curado.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from sifen_kb import cli
from sifen_kb.explain import FIRST_ERROR_WARNING, XSD_ANACHRONISM, today_paraguay, word_diff
from sifen_kb.load import load_kb
from sifen_kb.temporal import NOT_CURATED_WARNING
from sifen_kb.yamlio import load_kb_file, write_kb_file

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures"
KB_HYP = FIX / "kb_hyp"
KB_REV2 = FIX / "kb_hyp_rev2"
EXPLAIN = FIX / "explain"
KB_INDEX = EXPLAIN / "kb_index"
XML = FIX / "xml"
XSD_SNAPSHOT = REPO / "sources" / "XSD_DIR" / "2026-10-17"
GOLDEN_HYP = FIX / "golden_hyp.yaml"
UPDATE = bool(os.environ.get("SIFEN_UPDATE_SNAPSHOTS"))


# --- Helpers -------------------------------------------------------------------------------------------
def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def run_json(capsys: pytest.CaptureFixture[str], *argv: str, expect: int = 0) -> dict[str, Any]:
    code, out, err = run(capsys, *argv, "--json")
    assert code == expect, (code, out, err)
    assert "Traceback" not in out + err
    return json.loads(out)


def explain_json(
    capsys: pytest.CaptureFixture[str], root: Path, *args: str, expect: int = 0
) -> dict[str, Any]:
    return run_json(capsys, "--root", str(root), "explain", *args, expect=expect)


def copy_kb(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def tree_state(root: Path) -> dict[str, tuple[int, str]]:
    return {
        p.relative_to(root).as_posix(): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture(scope="session")
def kb_xml(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not XSD_SNAPSHOT.is_dir():
        pytest.skip("no está la instantánea XSD oficial en sources/XSD_DIR/2026-10-17")
    root = copy_kb(KB_HYP, tmp_path_factory.mktemp("kb_xml") / "kb_root")
    for p in sorted((EXPLAIN / "fields" / "DE").glob("*.yaml")):
        shutil.copy(p, root / "kb" / "fields" / "DE" / p.name)
    shutil.copy(EXPLAIN / "documents" / "XSD_DIR.yaml", root / "kb" / "documents" / "XSD_DIR.yaml")
    shutil.copytree(XSD_SNAPSHOT, root / "sources" / "XSD_DIR" / "2026-10-17")
    manifest = load_kb_file(root / "sources.manifest.yaml")
    manifest["revisions"].append(load_kb_file(EXPLAIN / "xsd_dir_revision.yaml"))
    write_kb_file(root / "sources.manifest.yaml", manifest)
    kb = load_kb(root)
    assert not kb.errors, kb.errors
    return root


@pytest.fixture
def kb_multi(tmp_path: Path) -> Path:
    root = copy_kb(KB_HYP, tmp_path / "kb_multi")
    for p in sorted((EXPLAIN / "validations" / "DE").glob("*.yaml")):
        shutil.copy(p, root / "kb" / "validations" / "DE" / p.name)
    assert not load_kb(root).errors
    return root


def only(ans: dict[str, Any]) -> dict[str, Any]:
    assert len(ans["results"]) == 1, [r["key"] for r in ans["results"]]
    return ans["results"][0]


# --- Contrato ------------------------------------------------------------------------------------------
QUERY_KEYS = ["term", "at", "env", "history", "xml", "response", "processed_at"]
RESULT_KEYS = ["key", "kind", "resolution", "version", "related_fields", "xsd", "xml"]


def test_json_contract_shape(capsys: pytest.CaptureFixture[str]) -> None:
    ans = explain_json(capsys, KB_HYP, "1321", "--at", "2025-01-10")
    assert list(ans) == ["query", "kb", "results", "warnings"]
    assert list(ans["query"]) == QUERY_KEYS
    assert list(ans["kb"]) == ["revision", "documents_curated", "sources_checked_at"]
    r = only(ans)
    assert list(r) == RESULT_KEYS
    assert ans["query"] == {
        "term": "1321",
        "at": "2025-01-10",
        "env": "prod",
        "history": False,
        "xml": None,
        "response": None,
        "processed_at": None,
    }
    assert ans["kb"] == {
        "revision": None,  # kb_hyp no es la raíz de un repositorio git
        "documents_curated": ["MT_V150", "NT_021", "NT_024", "NT_901", "NT_902"],
        "sources_checked_at": "2027-12-31",
    }
    res = r["resolution"]
    for k in ("key", "at", "env", "axis", "state", "reasons", "interval", "source", "history", "upcoming"):
        assert k in res
    assert all(set(f) == {"id", "key", "xml_name", "xsd"} for f in r["related_fields"])


def test_explain_json_snapshot(capsys: pytest.CaptureFixture[str]) -> None:
    """§K.7: protege el contrato (a Claude, a los scripts y al futuro MCP) de cambios involuntarios.

    Regenerar a propósito: `SIFEN_UPDATE_SNAPSHOTS=1 uv run pytest tests/unit/test_explain.py`.
    """
    cases = {
        "snapshot_1321_2025-01-10_prod.json": ("1321", "--at", "2025-01-10", "--env", "prod"),
        "snapshot_NT_901_2027-01-20_prod.json": ("NT_901", "--at", "2027-01-20"),
    }
    for name, args in cases.items():
        ans = explain_json(capsys, KB_HYP, *args)
        again = explain_json(capsys, KB_HYP, *args)
        assert ans == again, "salida no determinista"
        text = json.dumps(ans, ensure_ascii=False, indent=2) + "\n"
        path = EXPLAIN / name
        if UPDATE:
            path.write_text(text, encoding="utf-8", newline="\n")
        assert path.exists(), f"falta {path.name}: generarlo con SIFEN_UPDATE_SNAPSHOTS=1 y revisarlo"
        assert text == path.read_text(encoding="utf-8"), f"el contrato JSON cambió ({name})"


def test_default_at_is_today_in_paraguay(capsys: pytest.CaptureFixture[str]) -> None:
    ans = explain_json(capsys, KB_HYP, "1321")
    assert ans["query"]["at"] == today_paraguay().isoformat()


# --- Resolución del término ----------------------------------------------------------------------------
def test_code_resolves_validation(capsys: pytest.CaptureFixture[str]) -> None:
    r = only(explain_json(capsys, KB_HYP, "1321", "--at", "2025-01-10"))
    assert (r["key"], r["kind"]) == ("val:DE:D208c", "validation")
    res = r["resolution"]
    assert (res["state"], res["reasons"]) == ("in_force", [])
    assert r["version"]["introduced_by"] == ["NT_024#1"] and r["version"]["code"] == "1321"
    assert res["interval"] == [
        {"date": "2025-01-01", "basis": "stated"},
        {"date": "2027-04-01", "basis": "stated"},
    ]
    assert res["source"] == "NT_024#1 · NT_024 rev 3c345a4412bc · p. 2 PDF"
    assert [f["id"] for f in r["related_fields"]] == ["D208", "D011", "F014", "F023"]
    assert r["related_fields"][0] == {
        "id": "D208",
        "key": "field:DE:D208",
        "xml_name": "iTipIDRec",
        "xsd": None,
    }
    assert r["related_fields"][1]["key"] is None  # D011 no está curado en kb_hyp
    assert r["xsd"] is None and r["xml"] is None  # kb_hyp no registra instantánea XSD


@pytest.mark.parametrize("term", ["val:DE:D208c", "D208c", "1321"])
def test_key_id_and_code_are_equivalent(capsys: pytest.CaptureFixture[str], term: str) -> None:
    r = only(explain_json(capsys, KB_HYP, term, "--at", "2024-06-01"))
    assert r["key"] == "val:DE:D208c" and r["version"]["introduced_by"] == ["NT_021#1"]


def test_xml_name_and_field_id(capsys: pytest.CaptureFixture[str]) -> None:
    for term in ("iTipIDRec", "D208", "field:DE:D208"):
        r = only(explain_json(capsys, KB_HYP, term, "--at", "2027-06-01", "--env", "test"))
        assert (r["key"], r["kind"]) == ("field:DE:D208", "field")
        assert r["resolution"]["state"] == "in_force" and r["version"]["xml_name"] == "iTipIDRec"
        assert r["related_fields"] == [{"id": "D200", "key": None, "xml_name": None, "xsd": None}]


def test_id_that_is_field_and_validation_returns_both(
    capsys: pytest.CaptureFixture[str], kb_multi: Path
) -> None:
    ans = explain_json(capsys, kb_multi, "D208", "--at", "2025-01-10")
    assert [(r["key"], r["kind"]) for r in ans["results"]] == [
        ("field:DE:D208", "field"),
        ("val:DE:D208", "validation"),
    ]
    code, out, _ = run(capsys, "--root", str(kb_multi), "explain", "D208", "--at", "2025-01-10")
    assert code == 0 and out.startswith("field:DE:D208 · iTipIDRec · IN_FORCE")
    assert "\n\nval:DE:D208 · código 1310 · R · IN_FORCE" in out


def test_code_lists_every_validation_that_had_it(capsys: pytest.CaptureFixture[str], kb_multi: Path) -> None:
    ans = explain_json(capsys, kb_multi, "1321", "--at", "2027-10-05")
    keys = [r["key"] for r in ans["results"]]
    assert keys == ["val:DE:D208c", "val:DE:D208y"]  # N:M, incluida la lápida de D208c
    assert ans["results"][0]["resolution"]["state"] == "removed"
    assert ans["results"][0]["version"]["kind"] == "tombstone"


def test_code_not_in_force_for_shown_version_is_flagged(
    capsys: pytest.CaptureFixture[str], kb_multi: Path
) -> None:
    before = only(explain_json(capsys, kb_multi, "1777", "--at", "2024-12-31"))
    assert before["version"]["code"] == "1777"
    assert not any("no corresponde" in w for w in before["resolution"]["warnings"])
    after = only(explain_json(capsys, kb_multi, "1777", "--at", "2025-01-01"))
    assert after["version"]["code"] == "1778"
    assert any(
        "el código 1777 no corresponde a la versión mostrada" in w for w in after["resolution"]["warnings"]
    )


# --- Golden [HIP] a través de la CLI -------------------------------------------------------------------
def _golden_cli_rows() -> list[dict[str, Any]]:
    rows = load_kb_file(GOLDEN_HYP) or []
    return [
        r
        for r in rows
        if "diff" not in r
        and "processed_at" not in r
        and r.get("kb", "hyp") in ("hyp", "hyp_rev2_pendiente")
        and r["key"].startswith(("val:", "field:"))
    ]


GOLDEN_ROWS = _golden_cli_rows()


def _bd(b: dict[str, Any] | None) -> str | None:
    if b is None:
        return None
    return "baseline" if b["basis"] == "baseline" else b["date"]


@pytest.mark.parametrize(
    "row",
    GOLDEN_ROWS,
    ids=[r.get("id") or f"{r['key']}-{r['at']}-{r.get('env', 'prod')}" for r in GOLDEN_ROWS],
)
def test_golden_hyp_rows_through_cli(capsys: pytest.CaptureFixture[str], row: dict[str, Any]) -> None:
    root = KB_REV2 if row.get("kb") == "hyp_rev2_pendiente" else KB_HYP
    r = only(explain_json(capsys, root, row["key"], "--at", row["at"], "--env", row.get("env", "prod")))
    res, v, exp = r["resolution"], r["version"], dict(row["expect"])
    assert res["state"] == exp.pop("state")
    assert sorted(res["reasons"]) == sorted(exp.pop("reasons", []))
    if "introduced_by" in exp:
        assert (v["introduced_by"] if v else None) == exp.pop("introduced_by")
    for attr in ("kind", "code", "severity"):
        if attr in exp:
            assert v[attr] == exp.pop(attr)
    for name, pos in (("interval_from", 0), ("interval_to", 1)):
        if name in exp:
            assert _bd(res["interval"][pos]) == exp.pop(name)
    for s in exp.pop("upcoming_includes", []):
        assert any(s in u for u in res["upcoming"]), s
    for s in exp.pop("upcoming_excludes", []):
        assert not any(s in u for u in res["upcoming"]), s
    if exp.pop("upcoming_empty", False):
        assert res["upcoming"] == []
    for s in exp.pop("warnings_includes", []):
        assert any(s in w for w in res["warnings"]), s
    if "history" in exp:
        labels = [
            "línea base" if h["introduced_by"] == "baseline" else "+".join(h["introduced_by"])
            for h in res["history"]
        ]
        assert labels == exp.pop("history")
    assert not exp, f"claves de expect sin verificar: {sorted(exp)}"


def test_golden_hyp_not_curated_row_without_raw_is_unknown(capsys: pytest.CaptureFixture[str]) -> None:
    """La fila `1400` del golden (resolvedor: not_curated) por la CLI: kb_hyp no tiene raw/, así que
    no hay menciones y el término es desconocido (exit 2)."""
    err = explain_json(capsys, KB_HYP, "1400", "--at", "2027-01-01", expect=2)["error"]
    assert err["kind"] == "unknown_term"
    assert any("raw/ no existe" in d for d in err["details"])


# --- Texto ---------------------------------------------------------------------------------------------
def test_text_in_force_layout(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "--root", str(KB_HYP), "explain", "1321", "--at", "2025-01-10")
    assert code == 0
    lines = out.splitlines()
    assert (
        lines[0]
        == "val:DE:D208c · código 1321 · R · IN_FORCE (2025-01-10 · prod · eje: procesamiento [supuesto A2])"
    )
    labels = [ln[2:13].strip() for ln in lines[1:] if ln.startswith("  ") and ln[2] != " "]
    for want in (
        "Versión",
        "Literal",
        "Fuente",
        "Historia",
        "Violación",
        "Campos",
        "XSD",
        "Avisos",
        "Fuentes",
        "KB",
    ):
        assert want in labels, want
    assert "NT_024#1 · desde 2025-01-01 (declarada) [NT_024 «01/01/2025», rev 3c345a4412bc p. 1 PDF]" in out
    assert "es mayor o igual a 7.000.000 (F023 >= 7.000.000 o F014 >= 7.000.000)»" in out
    assert "[interpretación, parcial] (not exists(D011) or D011 != 13)" in out
    assert "→ [NT_024#1 (2025-01-01)] →" in out
    assert "NO es una vigencia afirmada" not in out


def test_text_not_in_force_goes_first_with_reasons(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "--root", str(KB_HYP), "explain", "1321", "--at", "2028-01-08")
    assert code == 0
    first = out.splitlines()[0]
    assert first.startswith("UNDETERMINED [beyond_horizon] · val:DE:D208c")
    assert "  Motivos     beyond_horizon:" in out
    assert "  Referencia  NT_902#1" in out and "NO es una vigencia afirmada" in out
    assert "IN_FORCE" not in out


def test_text_removed_and_not_yet_existing(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(capsys, "--root", str(KB_HYP), "explain", "D208c", "--at", "2027-10-05")
    assert out.startswith("REMOVED · val:DE:D208c")
    assert "  Eliminada   NT_902#1" in out and "recibir 1321 contradice la KB" in out


def test_text_outside_coverage(capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = run(capsys, "--root", str(KB_HYP), "explain", "D208c", "--at", "2023-06-16")
    assert out.startswith("OUTSIDE_COVERAGE · val:DE:D208c")
    assert "  Referencia  línea base" in out


# --- --history -----------------------------------------------------------------------------------------
def test_history_json_and_text(capsys: pytest.CaptureFixture[str]) -> None:
    r = only(explain_json(capsys, KB_HYP, "D208c", "--history", "--at", "2025-01-10"))
    tl = r["timeline"]
    assert [t["label"] for t in tl] == ["línea base", "NT_021#1", "NT_024#1", "NT_901#1", "NT_902#1"]
    assert tl[0]["changed"] is None
    assert tl[3]["changed"] == ["condition", "observation"]  # G5-19
    assert tl[3]["start"] == {"date": "2027-04-01", "basis": "stated"}
    assert tl[3]["other_env"] == {"env": "test", "start": {"date": "2027-02-01", "basis": "stated"}}
    assert tl[3]["effects"][0]["dates"]["prod"]["literal"] == "01/04/2027"
    assert tl[4]["kind"] == "tombstone" and tl[4]["end"] is None
    assert r["resolution"]["state"] == "in_force"  # la resolución de --at queda aparte

    code, out, _ = run(capsys, "--root", str(KB_HYP), "explain", "D208c", "--history")
    assert code == 0 and out.startswith("HISTORIA · val:DE:D208c")
    assert "IN_FORCE" not in out and "Versión" not in out  # sin mezclar con la resolución vigente
    assert "cambia observation: …) es mayor o igual a [-35.000.000-]{+7.000.000+}" in out
    assert "test: desde 2027-02-01 (declarada)" in out


def test_word_diff() -> None:
    a = "es mayor o igual a 60.000.000 (F023 >= 60.000.000)"
    b = "es mayor o igual a 35.000.000 (F023 >= 35.000.000)"
    assert (
        word_diff(a, b)
        == "es mayor o igual a [-60.000.000-]{+35.000.000+} (F023 >= [-60.000.000-]{+35.000.000+})"
    )


# --- Documentos ----------------------------------------------------------------------------------------
def test_document_card(capsys: pytest.CaptureFixture[str]) -> None:
    r = only(explain_json(capsys, KB_HYP, "NT_901", "--at", "2027-01-20"))
    assert (r["key"], r["kind"], r["resolution"], r["version"]) == ("NT_901", "document", None, None)
    doc = r["document"]
    assert doc["curated"] and doc["uncurated_revision"] is None
    assert [(x["sha12"], x["curated"], x["latest"]) for x in doc["revisions"]] == [
        ("a164e57654f7", False, False),
        ("439b24135f19", True, True),
    ]
    assert (
        doc["schedule"]["prod"]["date"] == "2027-04-01" and doc["schedule"]["test"]["literal"] == "01/02/2027"
    )
    (eff,) = doc["effects"]
    assert eff["state"] == "applied" and eff["versions"] == ["val:DE:D208c · NT_901#1"]
    assert eff["starts"] == {
        "test": {"date": "2027-02-01", "basis": "stated"},
        "prod": {"date": "2027-04-01", "basis": "stated"},
    }
    assert [i["id"] for i in doc["issues"]] == ["ISS-0001"]

    rev2 = only(explain_json(capsys, KB_REV2, "NT_901", "--at", "2027-01-20"))["document"]
    assert "439b24135f19 del manifiesto no está curada" in rev2["uncurated_revision"]
    _, out, _ = run(capsys, "--root", str(KB_REV2), "explain", "NT_901")
    assert out.startswith("REVISIÓN SIN CURAR · NT_901")


def test_document_without_card_shows_raw_dates(capsys: pytest.CaptureFixture[str]) -> None:
    r = only(explain_json(capsys, KB_INDEX, "NT_023", "--at", "2025-01-10"))
    doc = r["document"]
    assert not doc["curated"] and "sin ficha" in doc["uncurated_revision"]
    assert doc["raw_dates"]["prod"] == {"literal": "27 de setiembre de 2024", "date": "2024-09-27"}
    _, out, _ = run(capsys, "--root", str(KB_INDEX), "explain", "NT_023")
    assert out.startswith("SIN CURAR · NT_023") and "SIN CURAR: no resuelven vigencia" in out


# --- Modo índice y términos desconocidos ---------------------------------------------------------------
def test_index_mode_orders_by_production_date_never_by_number(capsys: pytest.CaptureFixture[str]) -> None:
    ans = explain_json(capsys, KB_INDEX, "1321", "--at", "2025-01-10")
    r = only(ans)
    assert (r["key"], r["kind"], r["version"]) == (None, "index", None)
    res = r["resolution"]
    assert res["state"] == "not_curated" and res["key"] is None
    # NT_018 (prod 2024-01-08) va antes que NT_021 (prod 2024-01-01) aunque su número sea menor.
    assert [m["doc"] for m in res["mentions"]] == ["NT_025", "NT_023", "NT_018", "NT_021", "MT_V150"]
    mt = res["mentions"][-1]
    assert (mt["page_pdf"], mt["page_printed"], mt["prod_date"]) == (167, 166, None)
    assert res["warnings"][0] == NOT_CURATED_WARNING
    assert any("sin kb/" in w for w in ans["warnings"])

    code, out, _ = run(capsys, "--root", str(KB_INDEX), "explain", "1321", "--at", "2025-01-10")
    assert code == 0 and out.startswith("NOT_CURATED · 1321")
    assert f"  Aviso       {NOT_CURATED_WARNING}" in out
    assert "1. NT_025 rev 8e8a63aa2d86 · p. 1 PDF · producción 2025-04-28 (literal de raw/, sin curar)" in out
    assert "5. MT_V150 rev 4b1f6f838adc · p. 166 impresa / 167 PDF · sin fecha de producción" in out


def test_index_mode_for_uncurated_key_and_xml_name(capsys: pytest.CaptureFixture[str]) -> None:
    r = only(explain_json(capsys, KB_INDEX, "val:DE:D208c", "--at", "2025-01-10"))
    assert r["key"] == "val:DE:D208c" and r["resolution"]["key"] == "val:DE:D208c"
    assert [m["doc"] for m in r["resolution"]["mentions"]] == ["NT_021", "MT_V150"]
    r = only(explain_json(capsys, KB_INDEX, "iTipIDRec", "--at", "2025-01-10"))
    assert [m["doc"] for m in r["resolution"]["mentions"]] == ["NT_023"]


def test_unknown_term_exit_2_with_suggestions(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "--root", str(KB_INDEX), "explain", "D208x", "--at", "2025-01-10")
    assert code == 2 and out == ""
    assert "término desconocido" in err and "D208c" in err and "Traceback" not in err
    e = explain_json(capsys, KB_INDEX, "D208x", expect=2)["error"]
    assert e["kind"] == "unknown_term" and "D208c" in e["suggestions"]
    e = explain_json(capsys, KB_INDEX, "d208c", expect=2)["error"]
    assert e["suggestions"][0] == "D208c"  # mayúsculas/minúsculas primero
    e = explain_json(capsys, KB_HYP, "NT_099", expect=2)["error"]
    assert "documento desconocido" in e["message"]


# --- --xml ---------------------------------------------------------------------------------------------
VERDICTS = [
    # (archivo, fecha de procesamiento, versión por emisión, veredicto)  §K.6
    ("de_innominado_pyg_f014_7000000_emision_2025-02-10.xml", "2025-02-11", "NT_024#1", "TRUE"),
    ("de_innominado_pyg_f014_6999999_emision_2025-02-10.xml", "2025-02-11", "NT_024#1", "FALSE"),
    ("de_innominado_pyg_f014_8000000_emision_2024-06-10.xml", "2024-06-11", "NT_021#1", "FALSE"),
    ("de_innominado_usd_f023_8000000_emision_2025-02-10.xml", "2025-02-11", "NT_024#1", "TRUE"),
    ("de_innominado_usd_f014_7500000_f023_6000000_emision_2025-02-10.xml", "2025-02-11", "NT_024#1", "TRUE"),
    (
        "de_receptor_sin_tipo_documento_pyg_f014_10000000_emision_2025-02-10.xml",
        "2025-02-11",
        "NT_024#1",
        "FALSE",
    ),
    ("de_receptor_cedula_pyg_f014_5000000_emision_2025-02-10.xml", "2025-02-11", "NT_024#1", "FALSE"),
]


@pytest.mark.parametrize(
    ("name", "processed", "version", "verdict"), VERDICTS, ids=[v[0][:40] for v in VERDICTS]
)
def test_xml_fixture_verdicts(
    capsys: pytest.CaptureFixture[str], kb_xml: Path, name: str, processed: str, version: str, verdict: str
) -> None:
    ans = explain_json(capsys, kb_xml, "1321", "--xml", str(XML / name), "--processed-at", processed)
    r = only(ans)
    x = r["xml"]
    assert r["resolution"]["state"] == "in_force", r["resolution"]["warnings"]
    assert r["resolution"]["processing_date_source"] == "flag"
    assert (x["evaluated"], x["decided"], x["verdict"]) == (True, True, verdict)
    assert x["emission"]["version"] == x["processing"]["version"] == version
    assert x["processing_date_source"] == "flag" and x["unreadable"] == {}
    assert set(x["values"]) == {"D011", "D208", "F014", "F023"}
    assert x["values"]["D208"]["parent"] == "gDatRec" and x["values"]["F014"]["parent"] == "gTotSub"
    assert FIRST_ERROR_WARNING in x["warnings"] and FIRST_ERROR_WARNING in ans["warnings"]
    assert ans["query"]["at"] is None and ans["query"]["processed_at"] == processed


def test_xml_gap_is_visible_when_paren_and_prose_differ(
    capsys: pytest.CaptureFixture[str], kb_xml: Path
) -> None:
    name = "de_innominado_usd_f014_7500000_f023_6000000_emision_2025-02-10.xml"
    r = only(explain_json(capsys, kb_xml, "1321", "--xml", str(XML / name), "--processed-at", "2025-02-11"))
    assert r["xml"]["verdict"] == "TRUE"
    assert any(w.startswith("gap de la formalización (partial)") for w in r["resolution"]["warnings"])


def test_xml_axis_split_with_response(capsys: pytest.CaptureFixture[str], kb_xml: Path) -> None:
    de = XML / "de_innominado_pyg_f014_10000000_emision_2024-12-30.xml"
    for resp in (
        "respuesta_recepcion_dfecproc_2025-01-02.xml",
        "respuesta_recepcion_soap_dfecproc_utc_cruza_medianoche.xml",
    ):
        r = only(explain_json(capsys, kb_xml, "1321", "--xml", str(de), "--response", str(XML / resp)))
        res, x = r["resolution"], r["xml"]
        assert (res["state"], res["reasons"]) == ("undetermined", ["axis_split"])
        assert res["processing_date_source"] == "response"
        assert x["processed_at"] == "2025-01-02"  # el SOAP en UTC cae el 2 de enero en Asunción
        assert (x["decided"], x["verdict"]) == (False, None)
        assert x["emission"] == {
            "at": "2024-12-30",
            "state": "in_force",
            "reasons": [],
            "version": "NT_021#1",
            "verdict": "FALSE",
        }
        assert (x["processing"]["version"], x["processing"]["verdict"]) == ("NT_024#1", "TRUE")
    code, out, _ = run(
        capsys,
        *("--root", str(kb_xml), "explain", "1321", "--xml", str(de)),
        *("--response", str(XML / "respuesta_recepcion_dfecproc_2025-01-02.xml")),
    )
    assert code == 0 and out.startswith("UNDETERMINED [axis_split] · val:DE:D208c")
    assert "  Veredicto   NO DECIDIDO (axis_split)" in out
    assert "  Emisión     2024-12-30 → NT_021#1 (IN_FORCE): FALSE" in out
    assert "  Proceso     2025-01-02 → NT_024#1 (IN_FORCE): TRUE" in out


def test_xml_processing_date_unknown(capsys: pytest.CaptureFixture[str], kb_xml: Path) -> None:
    de = XML / "de_innominado_pyg_f014_10000000_emision_2024-12-30.xml"
    r = only(explain_json(capsys, kb_xml, "1321", "--xml", str(de)))
    res, x = r["resolution"], r["xml"]
    assert (res["state"], res["reasons"]) == ("undetermined", ["processing_date_unknown"])
    assert res["processing_date_source"] == "unknown" and res["axis"] == "emission"
    assert (x["processed_at"], x["processing"], x["boundary"], x["verdict"]) == (
        None,
        None,
        "2025-01-01",
        None,
    )
    assert x["emission"]["verdict"] == "FALSE"
    _, out, _ = run(capsys, "--root", str(kb_xml), "explain", "1321", "--xml", str(de))
    assert "procesamiento DESCONOCIDO" in out and "NO DECIDIDO (processing_date_unknown)" in out


def test_xml_pii_masked_cdc_and_file_untouched(capsys: pytest.CaptureFixture[str], kb_xml: Path) -> None:
    de = XML / "de_receptor_cedula_pyg_f014_5000000_emision_2025-02-10.xml"
    before = (hashlib.sha256(de.read_bytes()).hexdigest(), de.stat().st_mtime_ns)
    cdc = "01800000005001001000000822025021011234567892"
    for args in (("D210",), ("1321",)):
        code, out, err = run(
            capsys, "--root", str(kb_xml), "explain", *args, "--xml", str(de), "--processed-at", "2025-02-11"
        )
        assert code == 0, err
        assert "4567890" not in out and cdc not in out and "RECEPTOR DE PRUEBA" not in out
        assert "CDC ****892" in out and f"  Aviso       {FIRST_ERROR_WARNING}" in out
    assert (
        "D210 dNumIDRec = ****890"
        in run(
            capsys, "--root", str(kb_xml), "explain", "D210", "--xml", str(de), "--processed-at", "2025-02-11"
        )[1]
    )
    x = only(explain_json(capsys, kb_xml, "D210", "--xml", str(de), "--processed-at", "2025-02-11"))["xml"]
    assert x["values"]["D210"] == {
        "xml_name": "dNumIDRec",
        "parent": "gDatRec",
        "present": True,
        "value": "****890",
        "masked": True,
    }
    assert (x["cdc"], x["pii_masked"], x["evaluated"], x["verdict"]) == ("****892", True, False, None)
    shown = only(
        explain_json(capsys, kb_xml, "D210", "--xml", str(de), "--processed-at", "2025-02-11", "--show-pii")
    )["xml"]
    assert shown["values"]["D210"]["value"] == "4567890" and shown["cdc"] == cdc
    assert (hashlib.sha256(de.read_bytes()).hexdigest(), de.stat().st_mtime_ns) == before


def test_xml_schema_validation_is_anachronistic(capsys: pytest.CaptureFixture[str], kb_xml: Path) -> None:
    de = XML / "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml"
    r = only(explain_json(capsys, kb_xml, "1321", "--xml", str(de), "--processed-at", "2025-02-11"))
    sv = r["xml"]["schema_validation"]
    assert (sv["snapshot"], sv["retrieved_at"], sv["status"], sv["anachronistic"]) == (
        "cdd1f03f1d29",
        "2026-10-17",
        "mismatch",
        True,
    )
    assert len(sv["errors"]) == 7 and XSD_ANACHRONISM in sv["detail"]
    xs = r["xsd"]  # estructura de los campos de la regla frente a la instantánea
    assert (xs["status"], xs["anachronistic"]) == ("match", True)
    assert [f["xsd"].split(" ")[0] for f in r["related_fields"]] == [
        "/rDE/DE/gDatGralOpe/gDatRec/iTipIDRec",
        "/rDE/DE/gDatGralOpe/gOpeCom/iTipTra",
        "/rDE/DE/gTotSub/dTotGralOpe",
        "/rDE/DE/gTotSub/dTotalGs",
    ]


def test_xsd_anachronism_flag_does_not_change_state(capsys: pytest.CaptureFixture[str], kb_xml: Path) -> None:
    old = only(explain_json(capsys, kb_xml, "1321", "--at", "2025-01-10"))
    new = only(explain_json(capsys, kb_xml, "1321", "--at", "2026-10-17"))
    assert old["resolution"]["state"] == new["resolution"]["state"] == "in_force"
    assert old["xsd"]["anachronistic"] is True and new["xsd"]["anachronistic"] is False
    assert any(XSD_ANACHRONISM in w for w in old["resolution"]["warnings"])
    assert not any(XSD_ANACHRONISM in w for w in new["resolution"]["warnings"])
    _, out, _ = run(capsys, "--root", str(kb_xml), "explain", "1321", "--at", "2025-01-10")
    assert f"  XSD         {XSD_ANACHRONISM}" in out


def _kb_with_c002(kb_xml: Path, dst: Path, *, issue: bool) -> Path:
    root = copy_kb(kb_xml, dst)
    labels = [
        "Factura",
        "Exportación",
        "Importación",
        "Autofactura",
        "Crédito",
        "Débito",
        "Remisión",
        "Retención",
    ]
    write_kb_file(
        root / "kb" / "fields" / "DE" / "C002.yaml",
        {
            "key": "field:DE:C002",
            "context": "DE",
            "id": "C002",
            "versions": [
                {
                    "introduced_by": "baseline",
                    "evidence": ["raw:MT_V150@acb2499a93b3:p64:C002"],
                    "group": "C",
                    "parent": "C001",
                    "xml_name": "iTiDE",
                    "description": "[fixture] Tipo de Documento Electrónico",
                    "data_type": "N",
                    "length": "1-2",
                    "occurrence": "1-1",
                    "observations": " ".join(f"{n}= {t}" for n, t in enumerate(labels, 1)),
                    "enumeration": [{"code": str(n), "label": t} for n, t in enumerate(labels, 1)],
                    "enumeration_interpretation": {"by": "human", "note": "fixture"},
                }
            ],
        },
    )
    if issue:
        write_kb_file(
            root / "kb" / "issues" / "ISS-0003.yaml",
            {
                "id": "ISS-0003",
                "kind": "source_conflict",
                "affects": [{"subject": "field:DE:C002"}],
                "statement": "[fixture] el XSD acepta otros códigos que el MT",
                "blocking": False,
                "status": "open",
            },
        )
    assert not load_kb(root).errors
    return root


def test_enumeration_documented_vs_accepted_by_xsd(
    capsys: pytest.CaptureFixture[str], kb_xml: Path, tmp_path: Path
) -> None:
    """Decisión 8 del usuario (2026-10-17): C002 muestra lo documentado por MT/NT (1–8) y lo aceptado por
    la instantánea XSD (1, 4–7, 9, 10) por separado, con `status: mismatch` y su Issue; sin etiquetas
    inventadas para 9 y 10 y sin cambiar el estado de la regla."""
    root = _kb_with_c002(kb_xml, tmp_path / "kbc", issue=True)
    r = only(explain_json(capsys, root, "C002", "--at", "2026-10-17"))
    assert r["resolution"]["state"] == "in_force"
    xs = r["xsd"]
    assert xs["status"] == "mismatch" and "1-1" in xs["detail"]
    e = xs["enumeration"]
    assert e["documented"] == [str(n) for n in range(1, 9)]
    assert e["accepted"] == ["1", "4", "5", "6", "7", "9", "10"] and e["exhaustive"] is True
    assert (e["only_documented"], e["only_accepted"], e["issues"]) == (
        ["2", "3", "8"],
        ["9", "10"],
        ["ISS-0003"],
    )
    assert e["documented_source"].startswith("línea base · MT_V150 rev acb2499a93b3")
    assert not any("ningún Issue source_conflict" in w for w in r["resolution"]["warnings"])
    _, out, _ = run(capsys, "--root", str(root), "explain", "C002", "--at", "2026-10-17")
    assert "Documentado por MT/NT [interpretación]: 1, 2, 3, 4, 5, 6, 7, 8" in out
    assert "Aceptado por la instantánea XSD: 1, 4, 5, 6, 7, 9, 10" in out
    assert "solo en el XSD, sin etiqueta en MT/NT: 9, 10" in out and "ISS-0003 (source_conflict" in out
    assert "9=" not in out and "10=" not in out

    bare = only(explain_json(capsys, _kb_with_c002(kb_xml, tmp_path / "kbd", issue=False), "C002"))
    assert bare["xsd"]["enumeration"]["issues"] == []
    assert any("ningún Issue source_conflict lo registra" in w for w in bare["resolution"]["warnings"])


def test_xml_without_mapping_is_unknown_never_absent(capsys: pytest.CaptureFixture[str]) -> None:
    """kb_hyp no cura D011/F014/F023 ni registra XSD: la regla queda UNKNOWN (nunca 'ausente' = FALSE)."""
    de = XML / "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml"
    x = only(explain_json(capsys, KB_HYP, "1321", "--xml", str(de), "--processed-at", "2025-02-11"))["xml"]
    assert x["verdict"] == "UNKNOWN" and x["schema_validation"] is None
    assert set(x["unreadable"]) == {"D011", "D208", "F014", "F023"}
    assert "sin instantánea XSD" in x["unreadable"]["D208"]


def test_xml_unformalized_rule_is_unknown(
    capsys: pytest.CaptureFixture[str], kb_xml: Path, tmp_path: Path
) -> None:
    root = copy_kb(kb_xml, tmp_path / "kbx")
    shutil.copy(
        EXPLAIN / "validations" / "DE" / "D208y.yaml", root / "kb" / "validations" / "DE" / "D208y.yaml"
    )
    de = XML / "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml"
    ans = explain_json(capsys, root, "1321", "--xml", str(de), "--processed-at", "2025-02-11")
    by_key = {r["key"]: r["xml"] for r in ans["results"]}
    assert by_key["val:DE:D208c"]["verdict"] == "TRUE"
    assert by_key["val:DE:D208y"]["verdict"] == "UNKNOWN"
    assert any("no está formalizada" in n for n in by_key["val:DE:D208y"]["notes"])


@pytest.mark.parametrize(
    ("extra", "msg"),
    [
        (("--at", "2025-01-01"), "--xml no se combina con --at"),
        (("--processed-at", "2025-01-01", "--response", "x.xml"), "no ambos"),
        (("--history",), "--history no se combina con --xml"),
    ],
)
def test_xml_usage_errors(capsys: pytest.CaptureFixture[str], extra: tuple[str, ...], msg: str) -> None:
    de = XML / "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml"
    code, out, err = run(capsys, "--root", str(KB_HYP), "explain", "1321", "--xml", str(de), *extra)
    assert code == 1 and out == "" and msg in err and "Traceback" not in err


def test_xml_read_errors(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    de = XML / "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml"
    e = explain_json(
        capsys, KB_HYP, "1321", "--xml", str(tmp_path / "no.xml"), "--processed-at", "2025-02-11", expect=1
    )
    assert e["error"]["kind"] == "xml"
    e = explain_json(capsys, KB_HYP, "1321", "--xml", str(de), "--response", str(de), expect=1)
    assert "dFecProc" in e["error"]["message"] and "nunca se asume hoy" in e["error"]["message"]
    code, _, err = run(capsys, "--root", str(KB_HYP), "explain", "1321", "--processed-at", "2025-01-01")
    assert code == 1 and "solo se usan con --xml" in err


# --- status --------------------------------------------------------------------------------------------
def test_status_without_kb_is_deliverable_0(capsys: pytest.CaptureFixture[str]) -> None:
    st = run_json(capsys, "--root", str(KB_INDEX), "status")
    assert st["has_kb_dir"] is False and st["documents_curated"] == []
    assert st["horizon"]["sources_checked_at"] == "2026-10-17"
    assert [u["doc"] for u in st["revisions_uncurated"]] == [
        "MT_V150",
        "NT_018",
        "NT_021",
        "NT_023",
        "NT_025",
    ]
    assert {u["reason"] for u in st["revisions_uncurated"]} == {"no_card"}
    assert st["coverage"]["coverage_from"] is None and st["raw_missing"] == []
    code, out, _ = run(capsys, "--root", str(KB_INDEX), "status")
    assert code == 0 and "entregable 0" in out and "sin kb/_meta.yaml" in out


def test_status_curated_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    st = run_json(capsys, "--root", str(KB_HYP), "status")
    assert st["coverage"]["coverage_from"] == "2023-06-17"
    assert [a["id"] for a in st["assumptions_unverified"]] == ["A1", "A2", "FIX"]
    assert [d["id"] for d in st["documents_curated"]] == ["MT_V150", "NT_021", "NT_024", "NT_901", "NT_902"]
    assert st["revisions_uncurated"] == [] and st["pending_effects"] == []
    assert st["blocking_issues"] == [] and st["open_issues"] == ["ISS-0002"]
    assert st["entities"] == {"fields": 1, "validations": 1} and st["horizon"]["grace_days"] == 7
    rev2 = run_json(capsys, "--root", str(KB_REV2), "status")
    assert rev2["revisions_uncurated"] == [
        {
            "doc": "NT_901",
            "reason": "new_revision",
            "latest": "439b24135f19",
            "current": "a164e57654f7",
            "raw": False,
        }
    ]
    _, out, _ = run(capsys, "--root", str(KB_REV2), "status")
    assert "NT_901: revisión 439b24135f19 del manifiesto sin curar (kb/ usa a164e57654f7)" in out


def test_status_pending_effects_and_blocking_issues(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = copy_kb(KB_HYP, tmp_path / "kbp")
    nt = root / "kb" / "documents" / "NT_024.yaml"
    data = load_kb_file(nt)
    data["effects"].append(
        {
            "id": "NT_024#2",
            "verb_literal": "[HIP] Se modifica",
            "action": "modify",
            "target": "field:DE:D208",
            "declared_scope": "row",
            "evidence": ["raw:NT_024@3c345a4412bc:p3:D208"],
            "disposition": "pending",
            "interpretation": {"by": "human", "note": "[HIP] fixture"},
        }
    )
    write_kb_file(nt, data)
    iss = load_kb_file(root / "kb" / "issues" / "ISS-0002.yaml")
    iss["blocking"] = "true"
    write_kb_file(root / "kb" / "issues" / "ISS-0002.yaml", iss)
    st = run_json(capsys, "--root", str(root), "status")
    assert [p["id"] for p in st["pending_effects"]] == ["NT_024#2"]
    assert st["pending_effects"][0]["starts"]["prod"] == {"date": "2025-01-01", "basis": "stated"}
    assert [i["id"] for i in st["blocking_issues"]] == ["ISS-0002"]
    r = only(explain_json(capsys, root, "D208", "--at", "2025-01-10"))
    assert r["resolution"]["state"] == "undetermined" and "pending_effect" in r["resolution"]["reasons"]
    assert r["resolution"]["pending_effects"] == ["NT_024#2"]


# --- Errores -------------------------------------------------------------------------------------------
def test_kb_load_errors_exit_1(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    root = copy_kb(KB_HYP, tmp_path / "kbe")
    (root / "kb" / "issues" / "ISS-0003.yaml").write_text("id: ISS-0003\nkind: nada\n", encoding="utf-8")
    code, out, err = run(capsys, "--root", str(root), "explain", "1321", "--at", "2025-01-10")
    assert code == 1 and out == "" and "errores de carga" in err and "ISS-0003.yaml" in err
    assert "Traceback" not in err
    e = explain_json(capsys, root, "1321", "--at", "2025-01-10", expect=1)["error"]
    assert e["kind"] == "kb_errors" and any("ISS-0003.yaml" in d for d in e["details"])
    code, out, _ = run(capsys, "--root", str(root), "status")
    assert code == 1 and "ERRORES" in out and "ISS-0003.yaml" in out


def test_temporal_data_error_exit_1(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    root = copy_kb(KB_HYP, tmp_path / "kbt")
    nt = root / "kb" / "documents" / "NT_024.yaml"
    nt.write_text(
        nt.read_text(encoding="utf-8")
        .replace("value: 2025-01-01", "value: 2024-01-01")
        .replace("literal: 01/01/2025", "literal: 01/01/2024"),
        encoding="utf-8",
    )
    code, out, err = run(capsys, "--root", str(root), "explain", "D208c", "--at", "2025-01-10")
    assert code == 1 and out == "" and "error de datos en la KB" in err and "dos versiones distintas" in err
    assert "Traceback" not in err
    (root / "kb" / "_meta.yaml").unlink()
    nt.write_text((KB_HYP / "kb" / "documents" / "NT_024.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    e = explain_json(capsys, root, "D208c", "--at", "2025-01-10", expect=1)["error"]
    assert e["kind"] == "temporal_data" and "_meta.yaml" in e["message"]


def test_bad_dates_and_root(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, _, err = run(capsys, "--root", str(KB_HYP), "explain", "1321", "--at", "2025-13-01")
    assert code == 1 and "fecha inválida" in err
    code, _, err = run(capsys, "--root", str(KB_HYP), "explain", "1321", "--at", "20250110")
    assert code == 1 and "AAAA-MM-DD" in err
    code, _, err = run(capsys, "--root", str(tmp_path / "nada"), "explain", "1321")
    assert code == 1 and "no es una carpeta" in err


def test_explain_is_read_only(capsys: pytest.CaptureFixture[str], kb_xml: Path) -> None:
    before = tree_state(kb_xml)
    de = XML / "de_innominado_pyg_f014_10000000_emision_2024-12-30.xml"
    for args in (
        ("explain", "1321", "--at", "2025-01-10"),
        ("explain", "D208c", "--history"),
        ("explain", "NT_024"),
        (
            "explain",
            "1321",
            "--xml",
            str(de),
            "--response",
            str(XML / "respuesta_recepcion_dfecproc_2025-01-02.xml"),
        ),
        ("status",),
    ):
        assert run(capsys, "--root", str(kb_xml), *args)[0] == 0
    assert tree_state(kb_xml) == before


# --- Salida UTF-8 por tubería (§K.1, §M.7) -------------------------------------------------------------
@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_cli_output_utf8_piped(extra: tuple[str, ...]) -> None:
    """`explain 1321` en un subproceso con PYTHONIOENCODING=cp1252 y salida por tubería: «≠» y «≥»
    salen en UTF-8 con LF (el error medido en Windows, detectado también en Linux)."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    env.pop("PYTHONUTF8", None)
    outs = {}
    for root in (KB_INDEX, KB_HYP):
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "sifen_kb.cli",
                "--root",
                str(root),
                "explain",
                "1321",
                "--at",
                "2025-01-10",
                *extra,
            ],
            capture_output=True,
            env=env,
            check=False,
            timeout=120,
        )
        assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
        assert b"\r\n" not in p.stdout
        outs[root] = p.stdout.decode("utf-8")
    assert "≠" in outs[KB_INDEX] and "≥" in outs[KB_INDEX]
    assert "D011≠13" in outs[KB_HYP] and "≠" in outs[KB_HYP]


# --- Repositorio real (entregable 0) -------------------------------------------------------------------
def _real_1321_curated() -> bool:
    kb = load_kb(REPO)
    return bool(kb.code_index().get("1321"))


@pytest.mark.skipif(_real_1321_curated(), reason="1321 ya está curado en kb/: deja de ser modo índice")
def test_real_repo_1321_index_mode(capsys: pytest.CaptureFixture[str]) -> None:
    if not (REPO / "raw" / "MT_V150").is_dir():
        pytest.skip("raw/ no está extraído")
    ans = explain_json(capsys, REPO, "1321", "--at", "2025-01-10")
    res = only(ans)["resolution"]
    assert res["state"] == "not_curated"
    assert [m["doc"] for m in res["mentions"]] == ["NT_024", "NT_021", "MT_V150"]
    assert [m["prod_date"] for m in res["mentions"]] == ["2025-01-01", "2024-01-01", None]
    mt = res["mentions"][-1]
    assert (mt["rev"], mt["page_printed"], mt["page_pdf"]) == ("976cd88c05c3", 166, 167)
    assert NOT_CURATED_WARNING in res["warnings"]


def test_real_repo_status(capsys: pytest.CaptureFixture[str]) -> None:
    st = run_json(capsys, "--root", str(REPO), "status")
    assert st["horizon"]["sources_checked_at"] is not None
    assert st["manifest"]["documents"] >= 32
    assert st["xsd_snapshot"] is not None and st["xsd_snapshot"]["path"].startswith("sources/XSD_DIR/")
    assert st["errors"] == []
    assert date.fromisoformat(st["today"]) == today_paraguay()


def test_document_date_pageref_is_rendered_as_text() -> None:
    """La fecha de una NT 001–012 cita un PageRef: el texto lo muestra como cita, no como dict de Python."""
    from sifen_kb.explain import _stated_txt

    page_ref = {
        "doc": "NT_001",
        "rev": "4c47b667084d",
        "page_pdf": 1,
        "page_printed": None,
        "quote": "Fecha: 14-10-2019",
    }
    assert _stated_txt(page_ref) == "NT_001 rev 4c47b667084d · p. 1 PDF, cita «Fecha: 14-10-2019»"
    assert _stated_txt("raw:NT_024@ccc2d1550e92:p1:fechas#test") == "raw:NT_024@ccc2d1550e92:p1:fechas#test"

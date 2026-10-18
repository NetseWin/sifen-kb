"""Tests de `sifen draft` (src/sifen_kb/draft.py; docs/arquitectura.md §D.3, §F, §G.3, §K.7).

Todo corre sobre KB temporales en `tmp_path`: `raw/` sintético escrito con `rawio`, o copias de las
filas REALES de `raw/NT_0xx` y `raw/MT_V150` con su entrada del manifiesto. Nunca se escribe en el
repositorio real.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from sifen_kb.cli import main as cli_main
from sifen_kb.draft import DraftError, cmd_draft, draft_baseline, draft_document, draft_effect
from sifen_kb.load import KB, load_kb
from sifen_kb.model import PageRef
from sifen_kb.rawio import page_path, write_index, write_rows, write_text
from sifen_kb.temporal import diff_versions, resolve
from sifen_kb.yamlio import is_canonical, load_kb_file, write_kb_file

REPO = Path(__file__).resolve().parents[2]
KB_HYP = REPO / "tests" / "fixtures" / "kb_hyp"
DATE_HEADER = [
    "Fecha:",
    "Fecha puesta a disposición para el Ambiente de Test",
    "Fecha puesta a disposición para el Ambiente de Producción",
]
VAL_HEADER = ["ID", "Mensaje de la Validación", "Código", "Observación", "E"]
FIELD_HEADER = [
    "Grupo",
    "ID",
    "Campo",
    "Descripción",
    "Nodo Padre",
    "Tipo Dato",
    "Longitud",
    "Ocurrencia",
    "Observaciones",
]
INTERP = {"by": "llm", "run": "test-draft"}


# --- Constructores ---------------------------------------------------------------------------------
def sha(label: str) -> str:
    return hashlib.sha256(f"draft:{label}".encode()).hexdigest()


def s12(label: str) -> str:
    return sha(label)[:12]


def rev(doc: str, label: str | None = None, *, retrieved: str = "2026-10-17T10:00:00") -> dict[str, Any]:
    s = sha(label or doc)
    return {
        "doc": doc,
        "sha256": s,
        "md5": hashlib.md5(s.encode()).hexdigest(),  # noqa: S324 - marcador sintético
        "size": 1000,
        "url": f"https://fixture.invalid/{doc}.pdf",
        "filename": f"{doc}_fixture.pdf",
        "retrieved_at": retrieved,
        "origin": "portal",
        "path": f"sources/{doc}/{s[:12]}.pdf",
    }


def meta(baseline_sha256: str) -> dict[str, Any]:
    return {
        "baseline_doc": "MT_V150",
        "baseline_sha256": baseline_sha256,
        "coverage_from": "2023-06-17",
        "horizon_grace_days": "7",
        "date_axis_default": "processing",
    }


def make_root(tmp_path: Path, revisions: list[dict[str, Any]], *, baseline: str | None = None) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    manifest = {
        "revisions": revisions,
        "checks": [{"at": "2027-12-31T00:00:00", "scope": ["nt"], "unregistered": []}],
    }
    write_kb_file(root / "sources.manifest.yaml", manifest)
    write_kb_file(root / "kb" / "_meta.yaml", meta(baseline or sha("MT_V150")))
    return root


def raw_row(
    page: int,
    key: str,
    table: str,
    cells: dict[str, str],
    *,
    header: list[str] | None = None,
    marks: list[dict[str, Any]] | None = None,
    raw_cells: dict[str, str] | None = None,
) -> dict[str, Any]:
    if header is None:
        header = {"validations": VAL_HEADER, "fields": FIELD_HEADER}.get(table, [])
    return {
        "page": page,
        "key": key,
        "occ": 1,
        "table": table,
        "header": header,
        "cells": cells,
        "raw_cells": raw_cells or dict(cells),
        "pages": [page],
        "fix_ids": [],
        "changes": {},
        "row_change": None,
        "marks": marks or [],
    }


def fechas(fecha: str | None, test: str | None, prod: str | None, page: int = 1) -> dict[str, Any]:
    cells = {k: v for k, v in (("fecha", fecha), ("test", test), ("prod", prod)) if v is not None}
    header = [h for h, v in zip(DATE_HEADER, (fecha, test, prod), strict=True) if v is not None]
    return raw_row(page, "fechas", "dates", cells, header=header)


def val_cells(
    vid: str, *, code: str = "1001", sev: str = "R", msg: str = "Mensaje base", obs: str
) -> dict[str, str]:
    return {"id": vid, "message": msg, "code": code, "observation": obs, "severity": sev}


def field_cells(fid: str, **over: str) -> dict[str, str]:
    base = {
        "group": "G1",
        "id": fid,
        "xml_name": "dF001",
        "description": "Campo uno",
        "parent": "F000",
        "data_type": "N",
        "length": "1-3",
        "occurrence": "0-1",
        "observations": "Obs base 1= Uno 2= Dos",
    }
    return base | over


def write_raw(
    root: Path,
    doc: str,
    sha256: str,
    rows: list[dict[str, Any]],
    *,
    pages: dict[int, str] | None = None,
    nt_info: dict[str, Any] | None = None,
) -> None:
    code12 = sha256[:12]
    write_rows(root, doc, code12, rows)
    pages = pages or {1: "texto de la página"}
    for n, text in pages.items():
        write_text(page_path(root, doc, code12, n), text)
    write_index(
        root,
        doc,
        code12,
        {
            "doc": doc,
            "sha256": sha256,
            "pages": [
                {"page_pdf": n, "page_printed": None, "sha256": "0" * 64, "chars": len(t)}
                for n, t in pages.items()
            ],
            "nt_info": nt_info,
            "tables": {},
            "anomalies": [],
        },
    )


OBS_BASE = "Si A es igual a 1 (A=1) la validación falla"
MT_ROWS = [
    raw_row(5, "F001", "fields", field_cells("F001")),
    raw_row(10, "V001", "validations", val_cells("V001", obs=OBS_BASE)),
    raw_row(10, "V003", "validations", val_cells("V003", code="1003", obs="Otra regla (B=1)")),
]


def mt_ref(key: str) -> str:
    page = 5 if key.startswith("F") else 10
    return f"raw:MT_V150@{s12('MT_V150')}:p{page}:{key}"


def nt_ref(doc: str, key: str, page: int = 1) -> str:
    return f"raw:{doc}@{s12(doc)}:p{page}:{key}"


def build(tmp_path: Path, docs: dict[str, list[dict[str, Any]]]) -> Path:
    """KB con MT_V150 sintético + las NT dadas (filas de raw/), fichas creadas con `draft_document`."""
    root = make_root(tmp_path, [rev("MT_V150"), *(rev(d) for d in docs)])
    write_raw(root, "MT_V150", sha("MT_V150"), MT_ROWS)
    for d, rows in docs.items():
        write_raw(root, d, sha(d), rows)
    kb = load_kb(root)
    for d in ["MT_V150", *docs]:
        draft_document(kb, d)
    return root


def add_effect(
    root: Path,
    doc: str,
    n: int,
    target: str,
    evidence: list[Any],
    *,
    action: str = "modify",
    scope: Any = "row",
    acknowledged: list[str] | None = None,
    pending: bool = True,
) -> str:
    path = root / "kb" / "documents" / f"{doc}.yaml"
    data = load_kb_file(path)
    eff: dict[str, Any] = {
        "id": f"{doc}#{n}",
        "verb_literal": {"modify": "se modifica", "add": "se agrega", "remove": "se elimina"}[action],
        "action": action,
        "target": target,
        "declared_scope": scope,
    }
    if acknowledged:
        eff["acknowledged_changes"] = acknowledged
    eff["evidence"] = evidence
    if pending:
        eff["disposition"] = "pending"
    eff["interpretation"] = INTERP
    scope_ = data.pop("curation_scope")
    data["effects"] = [*data.get("effects", []), eff]
    data["curation_scope"] = scope_
    write_kb_file(path, data)
    return eff["id"]


def set_version_attr(root: Path, rel: str, idx: int, attr: str, value: Any) -> None:
    path = root / "kb" / rel
    data = load_kb_file(path)
    ev = data["versions"][idx].pop("evidence")
    data["versions"][idx][attr] = value
    data["versions"][idx]["evidence"] = ev
    write_kb_file(path, data)


def assert_kb_ok(root: Path) -> KB:
    """Todo YAML escrito es canónico y la KB carga sin errores."""
    for p in sorted((root / "kb").rglob("*.yaml")):
        assert is_canonical(p.read_text(encoding="utf-8"), source=str(p)), p
    kb = load_kb(root)
    assert kb.errors == []
    return kb


CONDITION = {"expr": "A == 1", "level": "full", "interpretation": {"by": "human"}}


# --- sifen draft <DocId> ------------------------------------------------------------------------------
def test_document_numeric_calendar_creates_minimal_ficha(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_101")])
    write_raw(root, "NT_101", sha("NT_101"), [fechas("17/12/2024", "01/01/2025", "02/01/2025")])
    res = draft_document(load_kb(root), "NT_101")
    assert res.changed
    data = load_kb_file(root / "kb" / "documents" / "NT_101.yaml")
    ref = f"raw:NT_101@{s12('NT_101')}:p1:fechas"
    assert data == {
        "id": "NT_101",
        "kind": "technical_note",
        "number": "101",
        "title": "Nota Técnica N° 101",
        "current_revision": sha("NT_101"),
        "document_date": {"value": "2024-12-17", "literal": "17/12/2024", "stated_in": f"{ref}#fecha"},
        "schedule": {
            "test": {"value": "2025-01-01", "literal": "01/01/2025", "stated_in": f"{ref}#test"},
            "prod": {"value": "2025-01-02", "literal": "02/01/2025", "stated_in": f"{ref}#prod"},
        },
        "curation_scope": "dates_only",
    }
    out = res.render(root)
    assert "REVISIÓN HUMANA OBLIGATORIA" in out and f"{ref}#prod" in out
    kb = assert_kb_ok(root)
    assert kb.documents["NT_101"].schedule.prod.value == date(2025, 1, 2)  # type: ignore[union-attr]


def test_document_dates_in_words(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_102")])
    write_raw(
        root,
        "NT_102",
        sha("NT_102"),
        [fechas("27/08/2024", "30 de agosto de 2024", "27 de Setiembre del 2024")],
    )
    draft_document(load_kb(root), "NT_102")
    doc = assert_kb_ok(root).documents["NT_102"]
    assert doc.schedule is not None and doc.schedule.test is not None and doc.schedule.prod is not None
    assert (doc.schedule.test.value, doc.schedule.test.literal) == (date(2024, 8, 30), "30 de agosto de 2024")
    assert (doc.schedule.prod.value, doc.schedule.prod.literal) == (
        date(2024, 9, 27),
        "27 de Setiembre del 2024",
    )


def test_document_a_definir_is_null(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_103")])
    write_raw(root, "NT_103", sha("NT_103"), [fechas("01/12/2024", "15/12/2024", "A definir")])
    res = draft_document(load_kb(root), "NT_103")
    doc = assert_kb_ok(root).documents["NT_103"]
    assert doc.schedule is not None and doc.schedule.prod is not None
    assert (doc.schedule.prod.value, doc.schedule.prod.literal) == (None, "A definir")
    assert any("a definir" in ln for ln in res.lines)


def test_document_without_calendar_uses_verified_pageref(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_005")])
    page = "NOTA TÉCNICA N° 5\nFecha: 09/02/2021\nCambios desde la fecha: 01/02/2021 al\n09/02/2021\nReferencia: …\n"
    write_raw(
        root,
        "NT_005",
        sha("NT_005"),
        [],
        pages={1: page},
        nt_info={
            "numero": 5,
            "fecha_literal": "09/02/2021",
            "page": 1,
            "test_literal": None,
            "prod_literal": None,
        },
    )
    draft_document(load_kb(root), "NT_005")
    doc = assert_kb_ok(root).documents["NT_005"]
    assert doc.schedule is None
    dd = doc.document_date
    assert dd is not None and dd.value == date(2021, 2, 9) and dd.literal == "09/02/2021"
    assert dd.stated_in == PageRef(doc="NT_005", rev=s12("NT_005"), page_pdf=1, quote="Fecha: 09/02/2021")
    assert doc.change_period is not None
    a, b = doc.change_period
    assert (a.value, b.value) == (date(2021, 2, 1), date(2021, 2, 9))
    assert (
        isinstance(a.stated_in, PageRef)
        and a.stated_in.quote == "Cambios desde la fecha: 01/02/2021 al 09/02/2021"
    )
    path = root / "kb" / "documents" / "NT_005.yaml"
    before = path.read_bytes()
    again = draft_document(load_kb(root), "NT_005")  # idempotente también con PageRef
    assert not again.changed and path.read_bytes() == before and not any("⇒" in ln for ln in again.lines)


def test_document_quote_not_in_page_leaves_null(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_004")])
    write_raw(
        root,
        "NT_004",
        sha("NT_004"),
        [],
        pages={1: "NOTA TÉCNICA N° 4\nsin la fecha impresa\n"},
        nt_info={
            "numero": 4,
            "fecha_literal": "29/12/2020",
            "page": 1,
            "test_literal": None,
            "prod_literal": None,
        },
    )
    res = draft_document(load_kb(root), "NT_004")
    doc = assert_kb_ok(root).documents["NT_004"]
    assert doc.document_date is None and doc.change_period is None and doc.schedule is None
    assert any("no se inventa" in w for w in res.warnings)


def test_document_single_date_change_period_is_null(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_006")])
    write_raw(
        root,
        "NT_006",
        sha("NT_006"),
        [],
        pages={1: "Fecha: 25/03/2021\nCambios desde la fecha: 25/03/2021\n"},
        nt_info={
            "numero": 6,
            "fecha_literal": "25/03/2021",
            "page": 1,
            "test_literal": None,
            "prod_literal": None,
        },
    )
    res = draft_document(load_kb(root), "NT_006")
    doc = assert_kb_ok(root).documents["NT_006"]
    assert doc.document_date is not None and doc.change_period is None
    assert any("change_period null" in w for w in res.warnings)


def test_document_nt13_plus_without_fechas_row_is_error(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_030")])
    write_raw(
        root, "NT_030", sha("NT_030"), [], nt_info={"numero": 30, "fecha_literal": "01/01/2026", "page": 1}
    )
    with pytest.raises(DraftError, match="fila `fechas`"):
        draft_document(load_kb(root), "NT_030")
    assert not (root / "kb" / "documents" / "NT_030.yaml").exists()


def test_document_without_raw_is_error(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_031")])
    with pytest.raises(DraftError, match="raw/ no extraído"):
        draft_document(load_kb(root), "NT_031")


def test_document_header_mismatch_not_copied(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_104")])
    bad = fechas("01/12/2024", "01/01/2025", "01/02/2025")
    bad["header"] = [DATE_HEADER[0], DATE_HEADER[2], DATE_HEADER[1]]  # columnas cruzadas
    write_raw(root, "NT_104", sha("NT_104"), [bad])
    res = draft_document(load_kb(root), "NT_104")
    doc = assert_kb_ok(root).documents["NT_104"]
    assert doc.document_date is not None and doc.schedule is None
    assert sum("no corresponde" in w for w in res.warnings) == 2


def test_document_non_nt_minimal(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("MT_V150"), rev("XSD_DIR"), rev("NORMA_DECRETO_872_2023")])
    kb = load_kb(root)
    for d in ("MT_V150", "XSD_DIR", "NORMA_DECRETO_872_2023"):
        draft_document(kb, d)
    kb = assert_kb_ok(root)
    assert {d: kb.documents[d].kind for d in kb.documents} == {
        "MT_V150": "manual",
        "XSD_DIR": "xsd_bundle",
        "NORMA_DECRETO_872_2023": "legal",
    }
    mt = kb.documents["MT_V150"]
    assert (mt.number, mt.document_date, mt.schedule, mt.effects) == (None, None, None, [])
    assert mt.title == "MT_V150_fixture" and mt.curation_scope == "dates_only"


def test_document_update_only_dates_keeps_revision_and_warns(tmp_path: Path) -> None:
    root = make_root(
        tmp_path, [rev("NT_105", "NT_105:r1"), rev("NT_105", "NT_105:r2", retrieved="2026-10-18T10:00:00")]
    )
    write_raw(root, "NT_105", sha("NT_105:r1"), [fechas("01/12/2024", "01/01/2025", "01/02/2025")])
    write_raw(root, "NT_105", sha("NT_105:r2"), [fechas("01/12/2024", "01/01/2025", "01/03/2025")])
    path = root / "kb" / "documents" / "NT_105.yaml"
    old_ref = f"raw:NT_105@{sha('NT_105:r1')[:12]}:p1:fechas"
    write_kb_file(
        path,
        {
            "id": "NT_105",
            "kind": "technical_note",
            "number": "105",
            "title": "Título editado a mano",
            "current_revision": sha("NT_105:r1"),
            "schedule": {
                "prod": {"value": "2025-01-15", "literal": "15/01/2025", "stated_in": f"{old_ref}#prod"}
            },
            "effects": [
                {
                    "id": "NT_105#1",
                    "verb_literal": "se modifica",
                    "action": "modify",
                    "target": "val:DE:V001",
                    "declared_scope": "row",
                    "evidence": [f"raw:NT_105@{sha('NT_105:r1')[:12]}:p1:V001"],
                    "disposition": "pending",
                    "interpretation": INTERP,
                }
            ],
            "curation_scope": "pilot",
        },
    )
    res = draft_document(load_kb(root), "NT_105")
    data = load_kb_file(path)
    assert data["current_revision"] == sha("NT_105:r1")  # no cambia sin pedirlo
    assert data["title"] == "Título editado a mano" and data["curation_scope"] == "pilot"
    assert data["effects"][0]["id"] == "NT_105#1"
    assert (
        data["schedule"]["prod"]["literal"] == "01/02/2025"
        and data["document_date"]["literal"] == "01/12/2024"
    )
    assert list(data) == [
        "id",
        "kind",
        "number",
        "title",
        "current_revision",
        "document_date",
        "schedule",
        "effects",
        "curation_scope",
    ]
    assert any("revisión más nueva" in w for w in res.warnings)
    assert any("schedule.prod" in ln and "⇒" in ln for ln in res.lines)

    res2 = draft_document(load_kb(root), "NT_105", update_revision=True)
    data = load_kb_file(path)
    assert data["current_revision"] == sha("NT_105:r2")
    assert data["schedule"]["prod"]["stated_in"] == f"raw:NT_105@{sha('NT_105:r2')[:12]}:p1:fechas#prod"
    assert data["schedule"]["prod"]["value"] == "2025-03-01"
    assert any("Issue `temporal`" in w for w in res2.warnings)
    assert_kb_ok(root)


def test_document_idempotent(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_106")])
    write_raw(root, "NT_106", sha("NT_106"), [fechas("01/12/2024", "01/01/2025", "01/01/2025")])
    draft_document(load_kb(root), "NT_106")
    path = root / "kb" / "documents" / "NT_106.yaml"
    before = path.read_bytes()
    res = draft_document(load_kb(root), "NT_106")
    assert not res.changed and path.read_bytes() == before


def test_document_keeps_date_stated_in_other_document(tmp_path: Path) -> None:
    root = make_root(tmp_path, [rev("NT_107"), rev("COM_PRORROGA")])
    write_raw(root, "NT_107", sha("NT_107"), [fechas("01/12/2024", "01/01/2025", "01/02/2025")])
    draft_document(load_kb(root), "NT_107")
    path = root / "kb" / "documents" / "NT_107.yaml"
    data = load_kb_file(path)
    com = {
        "doc": "COM_PRORROGA",
        "rev": s12("COM_PRORROGA"),
        "page_pdf": 1,
        "quote": "se prorroga al 01/04/2025",
    }
    data["schedule"]["prod"] = {"value": "2025-04-01", "literal": "01/04/2025", "stated_in": com}
    write_kb_file(path, data)
    res = draft_document(load_kb(root), "NT_107")
    assert load_kb_file(path)["schedule"]["prod"]["stated_in"] == {**com, "page_pdf": "1"}  # KBLoader: str
    assert any("COM_PRORROGA" in w for w in res.warnings)


def test_document_not_in_manifest_is_error(tmp_path: Path) -> None:
    root = make_root(tmp_path, [])
    with pytest.raises(DraftError, match="source add"):
        draft_document(load_kb(root), "NT_199")


def _copy_real(tmp_path: Path, docs: list[str], *, mt: bool = False) -> Path:
    """Copia a `tmp_path` las filas reales de raw/ y su entrada del manifiesto (nunca escribe en el repo)."""
    manifest = load_kb_file(REPO / "sources.manifest.yaml")
    keep = set(docs) | ({"MT_V150"} if mt else set())
    revisions = [r for r in manifest["revisions"] if r["doc"] in keep]
    mt_sha = next(r["sha256"] for r in manifest["revisions"] if r["doc"] == "MT_V150")
    root = make_root(tmp_path, revisions, baseline=mt_sha)
    for d in docs:
        for src in (REPO / "raw" / d).iterdir():
            shutil.copytree(src, root / "raw" / d / src.name)
    if mt:
        dst = root / "raw" / "MT_V150" / mt_sha[:12]
        dst.mkdir(parents=True)
        for name in ("tables.jsonl", "index.json"):
            shutil.copy2(REPO / "raw" / "MT_V150" / mt_sha[:12] / name, dst / name)
    return root


def test_real_nt023_nt024_nt001_nt006_documents(tmp_path: Path) -> None:
    root = _copy_real(tmp_path, ["NT_001", "NT_006", "NT_023", "NT_024"])
    kb = load_kb(root)
    results = {d: draft_document(kb, d) for d in ("NT_001", "NT_006", "NT_023", "NT_024")}
    kb = assert_kb_ok(root)

    n23 = load_kb_file(root / "kb" / "documents" / "NT_023.yaml")
    ref23 = "raw:NT_023@9cb063673358:p1:fechas"
    assert n23["document_date"] == {
        "value": "2024-08-27",
        "literal": "27/08/2024",
        "stated_in": f"{ref23}#fecha",
    }
    assert n23["schedule"] == {
        "test": {"value": "2024-08-30", "literal": "30 de agosto de 2024", "stated_in": f"{ref23}#test"},
        "prod": {"value": "2024-09-27", "literal": "27 de setiembre de 2024", "stated_in": f"{ref23}#prod"},
    }
    n24 = load_kb_file(root / "kb" / "documents" / "NT_024.yaml")
    ref24 = "raw:NT_024@ccc2d1550e92:p1:fechas"
    assert n24["current_revision"].startswith("ccc2d1550e92")
    assert n24["document_date"] == {
        "value": "2024-12-17",
        "literal": "17/12/2024",
        "stated_in": f"{ref24}#fecha",
    }
    assert n24["schedule"] == {
        "test": {"value": "2025-01-01", "literal": "01/01/2025", "stated_in": f"{ref24}#test"},
        "prod": {"value": "2025-01-01", "literal": "01/01/2025", "stated_in": f"{ref24}#prod"},
    }
    n01 = kb.documents["NT_001"]
    assert n01.schedule is None and n01.document_date is not None
    assert (n01.document_date.value, n01.document_date.literal) == (date(2019, 10, 14), "14-10-2019")
    assert (
        isinstance(n01.document_date.stated_in, PageRef)
        and n01.document_date.stated_in.quote == "Fecha: 14-10-2019"
    )
    assert n01.change_period is not None
    assert [s.value for s in n01.change_period] == [date(2019, 9, 10), date(2019, 10, 14)]
    n06 = kb.documents["NT_006"]
    assert n06.document_date is not None and n06.document_date.value == date(2021, 3, 25)
    assert n06.change_period is None and results["NT_006"].warnings


# --- sifen draft <EffectId> ---------------------------------------------------------------------------
def test_effect_missing_is_error(tmp_path: Path) -> None:
    root = build(tmp_path, {"NT_201": [fechas("01/12/2023", "01/01/2024", "01/01/2024")]})
    with pytest.raises(DraftError, match="no existe"):
        draft_effect(load_kb(root), "NT_201#1")


def test_modify_without_entity_points_to_baseline_row(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_201": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "V001", "validations", val_cells("V001", obs="Si A es igual a 2 (A=2) falla")),
            ]
        },
    )
    add_effect(root, "NT_201", 1, "val:DE:V001", [nt_ref("NT_201", "V001")])
    with pytest.raises(DraftError, match=r"draft_baseline.*") as e:
        draft_effect(load_kb(root), "NT_201#1")
    assert mt_ref("V001") in str(e.value)
    assert not (root / "kb" / "validations").exists()


def test_draft_baseline(tmp_path: Path) -> None:
    root = build(tmp_path, {})
    kb = load_kb(root)
    res = draft_baseline(kb, "val:DE:V001", mt_ref("V001"))
    assert res.changed
    data = load_kb_file(root / "kb" / "validations" / "DE" / "V001.yaml")
    assert data == {
        "key": "val:DE:V001",
        "context": "DE",
        "id": "V001",
        "versions": [
            {
                "introduced_by": "baseline",
                "code": "1001",
                "severity": "R",
                "message": "Mensaje base",
                "observation": OBS_BASE,
                "evidence": [mt_ref("V001")],
            }
        ],
    }
    path = root / "kb" / "validations" / "DE" / "V001.yaml"
    before = path.read_bytes()
    assert not draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001")).changed
    assert path.read_bytes() == before
    with pytest.raises(DraftError, match="ID de la entidad"):
        draft_baseline(load_kb(root), "val:DE:V003", mt_ref("V001"))
    with pytest.raises(DraftError, match="tabla"):
        draft_baseline(load_kb(root), "field:DE:V001", mt_ref("V001"))
    draft_baseline(load_kb(root), "field:DE:F001", mt_ref("F001"))
    kb = assert_kb_ok(root)
    assert kb.fields["field:DE:F001"].versions[0].length == "1-3"


def test_draft_baseline_rejects_non_baseline_rows(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_201": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "V009", "validations", val_cells("V009", obs="x")),
            ]
        },
    )
    with pytest.raises(DraftError, match="línea base"):
        draft_baseline(load_kb(root), "val:DE:V009", nt_ref("NT_201", "V009"))
    with pytest.raises(DraftError, match="RowRef"):
        draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001") + "#observation")


def test_new_version_copies_row_and_inherits_missing_columns(tmp_path: Path) -> None:
    partial = raw_row(
        2,
        "F001",
        "fields",
        {"id": "F001", "length": "1-5", "occurrence": "1-1"},
        header=["ID", "Longitud", "Ocurrencia"],
    )
    root = build(tmp_path, {"NT_202": [fechas("01/12/2023", "01/01/2024", "01/01/2024"), partial]})
    draft_baseline(load_kb(root), "field:DE:F001", mt_ref("F001"))
    enum = [{"code": "1", "label": "Uno"}, {"code": "2", "label": "Dos"}]
    set_version_attr(root, "fields/DE/F001.yaml", 0, "enumeration", enum)
    set_version_attr(root, "fields/DE/F001.yaml", 0, "enumeration_interpretation", {"by": "human"})
    add_effect(
        root, "NT_202", 1, "field:DE:F001", [nt_ref("NT_202", "F001", 2)], scope=["length", "occurrence"]
    )
    res = draft_effect(load_kb(root), "NT_202#1")
    kb = assert_kb_ok(root)
    base, new = kb.fields["field:DE:F001"].versions
    assert new.introduced_by == ["NT_202#1"] and new.based_on == "baseline"
    assert new.evidence == [nt_ref("NT_202", "F001", 2)]
    assert (new.length, new.occurrence) == ("1-5", "1-1")
    for attr in ("group", "parent", "xml_name", "description", "data_type", "observations"):
        assert getattr(new, attr) == getattr(base, attr), attr
    assert new.enumeration == base.enumeration  # su literal (observations) no cambió
    assert diff_versions(base, new) == ["length", "occurrence"]
    assert not any("FUERA" in w for w in res.warnings)
    assert any("heredado de línea base" in ln for ln in res.lines)


def test_condition_dropped_when_observation_changes(tmp_path: Path) -> None:
    obs2 = "Si A es igual a 2 (A=2) la validación falla"
    root = build(
        tmp_path,
        {
            "NT_203": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "V001", "validations", val_cells("V001", obs=obs2)),
            ]
        },
    )
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    set_version_attr(root, "validations/DE/V001.yaml", 0, "condition", CONDITION)
    add_effect(root, "NT_203", 1, "val:DE:V001", [nt_ref("NT_203", "V001")])
    res = draft_effect(load_kb(root), "NT_203#1")
    base, new = assert_kb_ok(root).validations["val:DE:V001"].versions
    assert new.observation == obs2 and new.condition is None
    assert diff_versions(base, new) == ["condition", "observation"]
    assert any("formalizar de nuevo" in w for w in res.warnings)
    assert not any("FUERA" in w for w in res.warnings)  # row: la observación no necesita reconocimiento


def test_condition_inherited_when_observation_unchanged_and_scope_warning(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_204": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "V001", "validations", val_cells("V001", sev="AO", obs=OBS_BASE)),
            ]
        },
    )
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    set_version_attr(root, "validations/DE/V001.yaml", 0, "condition", CONDITION)
    add_effect(root, "NT_204", 1, "val:DE:V001", [nt_ref("NT_204", "V001")], scope=["message"])
    res = draft_effect(load_kb(root), "NT_204#1")
    base, new = assert_kb_ok(root).validations["val:DE:V001"].versions
    assert new.condition == base.condition
    assert diff_versions(base, new) == ["severity"]
    assert any("FUERA de declared_scope" in w and "severity" in w for w in res.warnings)


def test_based_on_is_temporal_predecessor_not_file_order(tmp_path: Path) -> None:
    def nt(obs: str, f: str, d: str) -> list[dict[str, Any]]:
        return [fechas(f, d, d), raw_row(1, "V001", "validations", val_cells("V001", obs=obs))]

    root = build(
        tmp_path,
        {
            "NT_211": nt("Regla 2024 (A=1)", "01/12/2023", "01/01/2024"),
            "NT_212": nt("Regla 2025 (A=2)", "01/12/2024", "01/01/2025"),
            "NT_213": nt("Regla 2026 (A=3)", "01/12/2025", "01/01/2026"),
        },
    )
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    for d in ("NT_211", "NT_212", "NT_213"):
        add_effect(root, d, 1, "val:DE:V001", [nt_ref(d, "V001")])
    draft_effect(load_kb(root), "NT_212#1")  # se cura primero la de 2025
    res = draft_effect(load_kb(root), "NT_211#1")  # luego la de 2024: fuera de orden
    assert any("fuera de orden" in w and "NT_212#1" in w for w in res.warnings)
    draft_effect(load_kb(root), "NT_213#1")
    vs = assert_kb_ok(root).validations["val:DE:V001"].versions
    by = {tuple(v.introduced_by) if v.introduced_by != "baseline" else "baseline": v for v in vs}
    assert by[("NT_211#1",)].based_on == "baseline"
    # El último del archivo es NT_211#1, pero la predecesora temporal de NT_213 es NT_212#1.
    assert vs[-2].introduced_by == ["NT_211#1"]
    assert by[("NT_213#1",)].based_on == ["NT_212#1"]


def test_tombstone(tmp_path: Path) -> None:
    deleted = raw_row(1, "V001", "validations", val_cells("V001", obs=OBS_BASE))
    root = build(tmp_path, {"NT_205": [fechas("01/12/2024", "01/01/2025", "01/01/2025"), deleted]})
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    set_version_attr(root, "validations/DE/V001.yaml", 0, "condition", CONDITION)
    legal = [
        {
            "citation": "Decreto X",
            "stated_in": {"doc": "MT_V150", "rev": s12("MT_V150"), "page_pdf": 10, "quote": "x"},
        }
    ]
    set_version_attr(root, "validations/DE/V001.yaml", 0, "legal_basis", legal)
    add_effect(root, "NT_205", 1, "val:DE:V001", [nt_ref("NT_205", "V001")], action="remove")
    res = draft_effect(load_kb(root), "NT_205#1")
    kb = assert_kb_ok(root)
    base, tomb = kb.validations["val:DE:V001"].versions
    assert tomb.kind == "tombstone" and tomb.introduced_by == ["NT_205#1"] and tomb.based_on == "baseline"
    assert (tomb.code, tomb.severity, tomb.message, tomb.observation) == (
        base.code,
        base.severity,
        base.message,
        base.observation,
    )
    assert tomb.evidence == [nt_ref("NT_205", "V001")]
    assert tomb.condition == base.condition and tomb.legal_basis == []
    assert diff_versions(base, tomb) == ["legal_basis"]
    assert any("legal_basis" in w for w in res.warnings)
    r = resolve(kb, "val:DE:V001", date(2025, 1, 1), "prod")
    assert r.state == "undetermined"  # el efecto sigue `pending` hasta que una persona lo cierre
    assert "1001" in kb.code_index()


def test_tombstone_from_prose_pageref(tmp_path: Path) -> None:
    root = build(tmp_path, {"NT_206": [fechas("01/12/2024", "01/01/2025", "01/01/2025")]})
    write_text(page_path(root, "NT_206", s12("NT_206"), 1), "Se elimina la validación V001\n")
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    quote = {"doc": "NT_206", "rev": s12("NT_206"), "page_pdf": 1, "quote": "Se elimina la validación V001"}
    add_effect(root, "NT_206", 1, "val:DE:V001", [quote], action="remove")
    draft_effect(load_kb(root), "NT_206#1")
    tomb = assert_kb_ok(root).validations["val:DE:V001"].versions[1]
    assert tomb.kind == "tombstone" and tomb.evidence == [PageRef(**quote)]


def test_effect_idempotent(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_207": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "V001", "validations", val_cells("V001", obs="Nueva (A=9)")),
            ]
        },
    )
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    add_effect(root, "NT_207", 1, "val:DE:V001", [nt_ref("NT_207", "V001")])
    assert draft_effect(load_kb(root), "NT_207#1").changed
    path = root / "kb" / "validations" / "DE" / "V001.yaml"
    before = path.read_bytes()
    res = draft_effect(load_kb(root), "NT_207#1")
    assert not res.changed and path.read_bytes() == before
    assert any("ya está aplicado" in ln for ln in res.lines)


def test_two_effects_same_start_single_version(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_208": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "F001", "fields", field_cells("F001", length="1-9")),
                raw_row(2, "F001", "fields", field_cells("F001", occurrence="1-1")),
            ]
        },
    )
    draft_baseline(load_kb(root), "field:DE:F001", mt_ref("F001"))
    add_effect(root, "NT_208", 1, "field:DE:F001", [nt_ref("NT_208", "F001", 1)], scope=["length"])
    add_effect(root, "NT_208", 2, "field:DE:F001", [nt_ref("NT_208", "F001", 2)], scope=["occurrence"])
    draft_effect(load_kb(root), "NT_208#1")
    res = draft_effect(load_kb(root), "NT_208#2")
    base, v = assert_kb_ok(root).fields["field:DE:F001"].versions
    assert v.introduced_by == ["NT_208#1", "NT_208#2"]
    assert (v.length, v.occurrence) == ("1-9", "1-1")
    assert v.evidence == [nt_ref("NT_208", "F001", 1), nt_ref("NT_208", "F001", 2)]
    assert diff_versions(base, v) == ["length", "occurrence"]
    assert not any("FUERA" in w for w in res.warnings)  # alcance efectivo = unión
    assert not draft_effect(load_kb(root), "NT_208#2").changed


def test_two_effects_conflicting_rows_same_start_is_error(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_209": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "F001", "fields", field_cells("F001", length="1-9")),
                raw_row(2, "F001", "fields", field_cells("F001", length="1-7")),
            ]
        },
    )
    draft_baseline(load_kb(root), "field:DE:F001", mt_ref("F001"))
    add_effect(root, "NT_209", 1, "field:DE:F001", [nt_ref("NT_209", "F001", 1)])
    add_effect(root, "NT_209", 2, "field:DE:F001", [nt_ref("NT_209", "F001", 2)])
    draft_effect(load_kb(root), "NT_209#1")
    with pytest.raises(DraftError, match="discrepan"):
        draft_effect(load_kb(root), "NT_209#2")


def test_same_prod_start_different_test_start_is_error(tmp_path: Path) -> None:
    def nt(test: str, obs: str) -> list[dict[str, Any]]:
        return [
            fechas("01/12/2024", test, "01/02/2025"),
            raw_row(1, "V001", "validations", val_cells("V001", obs=obs)),
        ]

    root = build(tmp_path, {"NT_210": nt("01/01/2025", "R1 (A=1)"), "NT_214": nt("15/01/2025", "R2 (A=2)")})
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    add_effect(root, "NT_210", 1, "val:DE:V001", [nt_ref("NT_210", "V001")])
    add_effect(root, "NT_214", 1, "val:DE:V001", [nt_ref("NT_214", "V001")])
    draft_effect(load_kb(root), "NT_210#1")
    with pytest.raises(DraftError, match="distinto en test"):
        draft_effect(load_kb(root), "NT_214#1")


def test_add_creates_entity_and_rejects_contradictions(tmp_path: Path) -> None:
    def nt(f: str, d: str, vid: str) -> list[dict[str, Any]]:
        return [
            fechas(f, d, d),
            raw_row(1, vid, "validations", val_cells(vid, code="1002", obs="Nueva (C=1)")),
        ]

    root = build(
        tmp_path,
        {
            "NT_215": nt("01/12/2024", "01/01/2025", "V002"),
            "NT_216": nt("01/12/2025", "01/01/2026", "V002"),
            "NT_217": nt("01/12/2025", "01/01/2026", "V001"),
        },
    )
    add_effect(root, "NT_215", 1, "val:DE:V002", [nt_ref("NT_215", "V002")], action="add")
    add_effect(root, "NT_216", 1, "val:DE:V002", [nt_ref("NT_216", "V002")], action="add")
    add_effect(root, "NT_217", 1, "val:DE:V001", [nt_ref("NT_217", "V001")], action="add")
    res = draft_effect(load_kb(root), "NT_215#1")
    (v,) = assert_kb_ok(root).validations["val:DE:V002"].versions
    assert v.introduced_by == ["NT_215#1"] and v.based_on == "baseline" and v.code == "1002"
    assert any("versión inicial" in ln for ln in res.lines)
    with pytest.raises(DraftError, match="vigente"):
        draft_effect(load_kb(root), "NT_216#1")
    with pytest.raises(DraftError, match="línea base ya tiene"):
        draft_effect(load_kb(root), "NT_217#1")


def test_effect_row_must_match_entity_and_revision(tmp_path: Path) -> None:
    root = build(
        tmp_path,
        {
            "NT_218": [
                fechas("01/12/2023", "01/01/2024", "01/01/2024"),
                raw_row(1, "V003", "validations", val_cells("V003", obs="otra")),
            ]
        },
    )
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    add_effect(root, "NT_218", 1, "val:DE:V001", [nt_ref("NT_218", "V003")])
    with pytest.raises(DraftError, match="ID de la entidad"):
        draft_effect(load_kb(root), "NT_218#1")
    add_effect(root, "NT_218", 2, "val:DE:V001", ["raw:NT_218@0123456789ab:p1:V001"])
    with pytest.raises(DraftError, match="revisión"):
        draft_effect(load_kb(root), "NT_218#2")


def test_cmd_draft_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_root(tmp_path, [rev("NT_219")])
    write_raw(root, "NT_219", sha("NT_219"), [fechas("01/12/2024", "01/01/2025", "01/01/2025")])

    def run(target: str) -> int:
        return cmd_draft(argparse.Namespace(root=str(root), target=target))

    assert run("NT_219") == 0
    out = capsys.readouterr().out
    assert "kb/documents/NT_219.yaml: escrito" in out and "REVISIÓN HUMANA OBLIGATORIA" in out
    assert run("no-es-un-objetivo") == 2
    assert run("NT_219#3") == 1
    assert "no existe" in capsys.readouterr().err


def test_cli_draft_baseline_and_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`sifen draft val:DE:D208c --baseline <RowRef>` y `--dry-run` por la CLI real (cli.main)."""
    root = _copy_real(tmp_path, ["NT_024"], mt=True)
    base = ["--root", str(root), "draft"]
    ref = "raw:MT_V150@976cd88c05c3:p167:D208c"
    assert cli_main([*base, "val:DE:D208c", "--baseline", ref, "--dry-run"]) == 0
    assert not (root / "kb" / "validations" / "DE" / "D208c.yaml").exists()
    out = capsys.readouterr().out
    assert "se escribiría (--dry-run: no se escribió nada)" in out and ": escrito" not in out
    assert cli_main([*base, "val:DE:D208c", "--baseline", ref]) == 0
    assert (root / "kb" / "validations" / "DE" / "D208c.yaml").exists()
    assert cli_main([*base, "NT_024", "--baseline", ref]) == 2
    assert "clave de entidad" in capsys.readouterr().err
    assert cli_main([*base, "NT_024", "--dry-run"]) == 0
    assert not (root / "kb" / "documents" / "NT_024.yaml").exists()


# --- datos reales ----------------------------------------------------------------------------------
def test_real_nt024_d208c_drops_red_text(tmp_path: Path) -> None:
    """La fila real de NT 24 marca en rojo «(D011≠13)», «o igual» y el «=»: el rojo es contenido
    eliminado también en una NT (decisión 3 del usuario, 2026-10-17; antes se copiaba la celda
    completa), así que el literal copiado es `effective_literal`, sin la excepción y con «>»."""
    root = _copy_real(tmp_path, ["NT_024", "NT_023"], mt=True)
    kb = load_kb(root)
    draft_document(kb, "NT_024")
    draft_document(kb, "NT_023")
    draft_baseline(kb, "val:DE:D208c", "raw:MT_V150@976cd88c05c3:p167:D208c")
    draft_baseline(kb, "field:DE:D208", "raw:MT_V150@976cd88c05c3:p72:D208")
    add_effect(root, "NT_024", 1, "val:DE:D208c", ["raw:NT_024@ccc2d1550e92:p1:D208c"])
    add_effect(root, "NT_023", 1, "field:DE:D208", ["raw:NT_023@9cb063673358:p1:D208"])
    res = draft_effect(load_kb(root), "NT_024#1")
    res23 = draft_effect(load_kb(root), "NT_023#1")
    kb = assert_kb_ok(root)
    row = kb.raw.row("raw:NT_024@ccc2d1550e92:p1:D208c")
    assert row is not None
    base, v24 = kb.validations["val:DE:D208c"].versions
    assert v24.observation == row.effective_literal("observation") != row.rendered_literal("observation")
    assert v24.observation is not None
    assert "(D011≠13)" not in v24.observation and "o igual" not in v24.observation
    assert v24.observation.startswith(
        "El Tipo de documento de identidad del receptor no puede ser Innominado"
    )
    assert "es mayor a 7.000.000 (F023 > 7.000.000 o F014 > 7.000.000)" in v24.observation
    assert (v24.code, v24.severity, v24.message) == ("1321", "R", base.message)
    assert diff_versions(base, v24) == ["observation"]
    assert any("tramos en rojo" in w and "(D011≠13)" in w for w in res.warnings)
    assert not any("marcado (" in w for w in res.warnings)  # verbo, color y acción coinciden
    f_base, f23 = kb.fields["field:DE:D208"].versions
    nt23 = kb.raw.row("raw:NT_023@9cb063673358:p1:D208")
    assert nt23 is not None and f23.observations == nt23.effective_literal("observations")
    assert f23.observations is not None and f23.observations.startswith(
        "Obligatorio si D201 = 2 No informar si D201 = 1 1= Cédula paraguaya"
    )
    assert diff_versions(f_base, f23) == ["observations"]
    assert any("«y D202 ≠ 4»" in w for w in res23.warnings)


def test_real_nt002_tombstone_is_compared_with_rendered_row(tmp_path: Path) -> None:
    """NT 2 elimina D208d con la fila entera en rojo: la lápida copia la predecesora sin avisos de
    diferencia (la fila que elimina se compara por lo visible) y el marcado coincide con `remove`."""
    root = _copy_real(tmp_path, ["NT_002"], mt=True)
    kb = load_kb(root)
    draft_document(kb, "NT_002")
    draft_baseline(kb, "val:DE:D208d", "raw:MT_V150@976cd88c05c3:p167:D208d")
    add_effect(root, "NT_002", 1, "val:DE:D208d", ["raw:NT_002@6aaf4a8f4797:p1:D208d"], action="remove")
    res = draft_effect(load_kb(root), "NT_002#1")
    kb = assert_kb_ok(root)
    base, tomb = kb.validations["val:DE:D208d"].versions
    assert tomb.kind == "tombstone" and (tomb.code, tomb.observation) == (base.code, base.observation)
    assert not any("difiere de la predecesora" in w for w in res.warnings), res.warnings
    assert not any("marcado (" in w for w in res.warnings), res.warnings


def green_row(vid: str, cells: dict[str, str]) -> dict[str, Any]:
    """Fila entera en verde (un alta según el marcado)."""
    marks = [{"attr": a, "change": "added", "start": 0, "end": len(t), "text": t} for a, t in cells.items()]
    return raw_row(1, vid, "validations", cells, marks=marks) | {
        "changes": dict.fromkeys(cells, "added"),
        "row_change": "added",
    }


def _set_verb(root: Path, doc: str, verb: str) -> None:
    path = root / "kb" / "documents" / f"{doc}.yaml"
    data = load_kb_file(path)
    data["effects"][0]["verb_literal"] = verb
    write_kb_file(path, data)


def test_marking_color_against_verb_is_warned_as_traceability(tmp_path: Path) -> None:
    """Alta en verde, `add`, bajo «se modifica» (como NT 23 #5–#7): draft escribe y avisa que exige un
    Issue de trazabilidad (regla «mixta» del usuario, 2026-10-17); no decide."""
    row = green_row("V009", val_cells("V009", code="1009", obs="Nueva regla (Z=1)"))
    root = build(tmp_path, {"NT_230": [fechas("01/12/2024", "01/01/2025", "01/01/2025"), row]})
    add_effect(root, "NT_230", 1, "val:DE:V009", [nt_ref("NT_230", "V009")], action="add")
    _set_verb(root, "NT_230", "se modifica la siguiente validación")
    res = draft_effect(load_kb(root), "NT_230#1")
    assert res.changed
    (w,) = [w for w in res.warnings if w.startswith("marcado (")]
    assert "color_verbo" in w and "Issue de trazabilidad (no bloqueante)" in w and "draft no decide" in w


def test_marking_color_against_action_is_warned_as_blocking(tmp_path: Path) -> None:
    """Fila entera en verde curada como `modify` de una regla existente: exige un Issue bloqueante."""
    row = green_row("V001", val_cells("V001", obs="Nueva (A=9)"))
    root = build(tmp_path, {"NT_231": [fechas("01/12/2024", "01/01/2025", "01/01/2025"), row]})
    draft_baseline(load_kb(root), "val:DE:V001", mt_ref("V001"))
    add_effect(root, "NT_231", 1, "val:DE:V001", [nt_ref("NT_231", "V001")])
    res = draft_effect(load_kb(root), "NT_231#1")
    assert res.changed
    (w,) = [w for w in res.warnings if w.startswith("marcado (")]
    assert "color_accion" in w and "Issue BLOQUEANTE" in w


def test_replay_nt024(tmp_path: Path) -> None:
    """§K.7: KB fixture sin NT 24 + raw/ real de NT 24 + efecto escrito a mano → `draft NT_024#1`: el
    diff contra la versión de NT 21 toca solo `observation` (y `condition` queda para re-formalizar)
    y ninguna resolución anterior al 2025-01-01 cambia."""
    root = tmp_path / "kb_hyp"
    shutil.copytree(KB_HYP, root)
    for rel in (
        "documents/NT_024.yaml",
        "documents/NT_901.yaml",
        "documents/NT_902.yaml",
        "issues/ISS-0001.yaml",
    ):
        (root / "kb" / rel).unlink()
    d208c = root / "kb" / "validations" / "DE" / "D208c.yaml"
    data = load_kb_file(d208c)
    data["versions"] = data["versions"][:2]  # línea base y NT_021#1
    write_kb_file(d208c, data)
    real = next(r for r in load_kb_file(REPO / "sources.manifest.yaml")["revisions"] if r["doc"] == "NT_024")
    manifest = load_kb_file(root / "sources.manifest.yaml")
    manifest["revisions"] = [
        real if r["doc"] == "NT_024" else r
        for r in manifest["revisions"]
        if r["doc"] not in ("NT_901", "NT_902")
    ]
    write_kb_file(root / "sources.manifest.yaml", manifest)
    shutil.copytree(REPO / "raw" / "NT_024" / "ccc2d1550e92", root / "raw" / "NT_024" / "ccc2d1550e92")
    assert load_kb(root).errors == []

    draft_document(load_kb(root), "NT_024")
    add_effect(root, "NT_024", 1, "val:DE:D208c", ["raw:NT_024@ccc2d1550e92:p1:D208c"])
    key = "val:DE:D208c"
    days = [date(2023, 12, 31), date(2024, 1, 1), date(2024, 6, 1), date(2024, 12, 31)]

    def snapshot(kb: KB) -> dict[tuple[date, str], tuple[Any, ...]]:
        out = {}
        for d in days:
            for env in ("test", "prod"):
                r = resolve(kb, key, d, env)  # type: ignore[arg-type]
                out[(d, env)] = (
                    r.state,
                    tuple(r.reasons),
                    r.version_index,
                    r.interval[0] if r.interval else None,
                )
        return out

    before = snapshot(load_kb(root))
    res = draft_effect(load_kb(root), "NT_024#1")
    kb = assert_kb_ok(root)
    _, v21, v24 = kb.validations[key].versions
    assert v24.introduced_by == ["NT_024#1"] and v24.based_on == ["NT_021#1"]
    assert diff_versions(v21, v24) == ["condition", "observation"]
    assert v24.condition is None and any("formalizar de nuevo" in w for w in res.warnings)
    assert "7.000.000" in v24.observation  # type: ignore[operator]
    assert snapshot(kb) == before

    # Cuando una persona cierra el efecto (quita `pending`), NT 24 rige desde el 2025-01-01.
    doc = load_kb_file(root / "kb" / "documents" / "NT_024.yaml")
    del doc["effects"][0]["disposition"]
    write_kb_file(root / "kb" / "documents" / "NT_024.yaml", doc)
    kb = load_kb(root)
    r = resolve(kb, key, date(2025, 1, 1), "prod")
    assert (r.state, r.version_index) == ("in_force", 2)
    assert resolve(kb, key, date(2024, 12, 31), "prod").version_index == 1

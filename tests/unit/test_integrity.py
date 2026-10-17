"""Unitarios de `sifen_kb.integrity`: `sifen check` y `sifen fmt` (docs/arquitectura.md §H, §K.3, §K.4, §K.7).

La KB de prueba (`spec()`) es mínima pero COHERENTE: fuentes con hash real en `sources/`, manifiesto,
`raw/` sintético (filas, páginas e `index.json`), libro de cambios, y `val:DE:D208c` en tres versiones
(MT V150 ≥ 60 M → NT 21 ≥ 35 M → NT 24 ≥ 7 M) con los campos D208 y F014 que lee su condición. Como la
observación de D208c nombra D208 y F014, cada NT reconoce esas menciones con efectos `not_modeled`
(redundantes con la regla laxa acotada del guardián, que ya las exime por estar dentro de la fila citada
por NT_0xx#1; los tests de cobertura los quitan). NADA de esto es evidencia real: los PDF son marcadores.

El fixture limpio es el «caso que pasa» de todas las comprobaciones (`test_clean_fixture_passes`); cada
test siembra un error con una mutación del `spec` y verifica que su comprobación lo detecta.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sifen_kb import integrity
from sifen_kb.integrity import (
    BaseSnapshot,
    Finding,
    check_llm_runs,
    check_past_changes,
    cmd_check,
    cmd_fmt,
    errors_of,
    load_base,
    run_checks,
)
from sifen_kb.load import KB, load_kb
from sifen_kb.rawio import index_text, ledger_dir, page_path, rev_dir, rows_text, write_text
from sifen_kb.yamlio import dump_kb, write_kb_file

NOBASE = "sin base en este test"
MSG = "Tipo de documento de identidad del receptor incorrecto para el total general de la operación en guaraníes"
DOCS = ("MT_V150", "NT_021", "NT_024", "NT_023")
"""NT_023 solo se registra en los tests que lo piden (`add_nt023`)."""
HUMAN = {"by": "human", "note": "fixture"}
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
DATE_HEADER = [
    "Fecha:",
    "Fecha puesta a disposición para el Ambiente de Test",
    "Fecha puesta a disposición para el Ambiente de Producción",
]
STRUCK = "(D208≠5)"


def source_bytes(doc: str) -> bytes:
    return f"%PDF-1.7\n% fixture sifen-kb integrity {doc}\n".encode()


REV = {d: hashlib.sha256(source_bytes(d)).hexdigest() for d in DOCS}
S12 = {d: REV[d][:12] for d in DOCS}


def ref(doc: str, page: int, key: str, attr: str | None = None) -> str:
    return f"raw:{doc}@{S12[doc]}:p{page}:{key}" + (f"#{attr}" if attr else "")


def obs(amount: str) -> str:
    return (
        "El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total "
        f"general de la operación es mayor o igual a {amount} (F014 >= {amount})"
    )


def cond(n: int) -> dict[str, Any]:
    return {
        "expr": f"exists(D208) and D208 == 5 and exists(F014) and F014 >= {n}",
        "level": "full",
        "interpretation": dict(HUMAN),
    }


def row(page: int, key: str, table: str, cells: dict[str, str], **extra: Any) -> dict[str, Any]:
    header = {"fields": FIELD_HEADER, "validations": VAL_HEADER, "dates": DATE_HEADER}[table]
    return {
        "page": page,
        "key": key,
        "occ": 1,
        "table": table,
        "header": list(header),
        "cells": cells,
        "pages": [page],
        "fix_ids": [],
        "changes": {},
        "row_change": None,
        "marks": [],
        **extra,
    }


def text_of(*rows_: dict[str, Any], prefix: str = "") -> str:
    parts = [prefix] if prefix else []
    for r in rows_:
        parts += [*r["header"], *r["cells"].values()]
    return "\n".join(parts)


D208_CELLS = {
    "group": "D3",
    "id": "D208",
    "xml_name": "iTipIDRec",
    "description": "Tipo de documento de identidad del receptor",
    "parent": "D200",
    "data_type": "N",
    "length": "1",
    "occurrence": "0-1",
    "observations": "1= Cédula paraguaya 2= Pasaporte 5= Innominado",
}
F014_CELLS = {
    "group": "F1",
    "id": "F014",
    "xml_name": "dTotGralOpe",
    "description": "Total general de la operación",
    "parent": "F001",
    "data_type": "N",
    "length": "1-15p(0-8)",
    "occurrence": "1-1",
    "observations": "Suma de los subtotales",
}


def val_cells(
    key: str, code: str, observation: str, message: str = MSG, severity: str = "R"
) -> dict[str, str]:
    return {"id": key, "message": message, "code": code, "observation": observation, "severity": severity}


def nt_doc(doc: str, number: int, fecha: str, test: str, prod: str) -> dict[str, Any]:
    def ds(literal: str, attr: str) -> dict[str, Any]:
        d, m, y = literal.split("/")
        return {"value": f"{y}-{m}-{d}", "literal": literal, "stated_in": ref(doc, 1, "fechas", attr)}

    def mention(n: int, field: str) -> dict[str, Any]:
        return {
            "id": f"{doc}#{n}",
            "verb_literal": "(mención en la observación de D208c)",
            "action": "modify",
            "target": f"field:DE:{field}",
            "declared_scope": "row",
            "evidence": [ref(doc, 2, "D208c", "observation")],
            "disposition": "not_modeled",
            "interpretation": dict(HUMAN),
            "note": f"Solo se nombra {field} en la observación de D208c; el campo no cambia.",
        }

    return {
        "id": doc,
        "kind": "technical_note",
        "number": str(number),
        "title": f"Nota Técnica N° {number} [fixture]",
        "current_revision": REV[doc],
        "document_date": ds(fecha, "fecha"),
        "schedule": {"test": ds(test, "test"), "prod": ds(prod, "prod")},
        "effects": [
            {
                "id": f"{doc}#1",
                "verb_literal": "Se modifica la siguiente validación",
                "action": "modify",
                "target": "val:DE:D208c",
                "declared_scope": "row",
                "evidence": [ref(doc, 2, "D208c")],
                "interpretation": dict(HUMAN),
            },
            mention(2, "D208"),
            mention(3, "F014"),
        ],
        "curation_scope": "pilot",
    }


def spec() -> dict[str, Any]:
    """KB limpia como diccionarios (se muta en cada test y se escribe con `build`)."""
    mt_rows = [
        row(100, "F014", "fields", dict(F014_CELLS)),
        row(166, "D208", "fields", dict(D208_CELLS)),
        row(
            167,
            "D208b",
            "validations",
            val_cells("D208b", "1319", "Si D202 = 3 el receptor informa su documento"),
        ),
        row(167, "D208c", "validations", val_cells("D208c", "1321", obs("60.000.000"))),
        row(
            167,
            "D208",
            "validations",
            val_cells("D208", "1310", "Es obligatorio informar el tipo de documento"),
        ),
    ]
    nt_rows: dict[str, list[dict[str, Any]]] = {}
    for doc, fechas, amount in (
        ("NT_021", ("29/12/2023", "01/01/2024", "01/01/2024"), "35.000.000"),
        ("NT_024", ("17/12/2024", "01/01/2025", "01/01/2025"), "7.000.000"),
    ):
        o = obs(amount)
        start = o.index(STRUCK)
        nt_rows[doc] = [
            row(1, "fechas", "dates", dict(zip(("fecha", "test", "prod"), fechas, strict=True))),
            # Un tramo rojo («deleted» según la leyenda del MT): en una NT el color no elimina texto.
            row(
                2,
                "D208c",
                "validations",
                val_cells("D208c", "1321", o),
                marks=[
                    {
                        "attr": "observation",
                        "change": "deleted",
                        "start": start,
                        "end": start + len(STRUCK),
                        "text": STRUCK,
                    }
                ],
                changes={"observation": "modified"},
            ),
        ]
    raw = {
        "MT_V150": {
            "rows": mt_rows,
            "pages": {100: text_of(mt_rows[0]), 166: text_of(mt_rows[1]), 167: text_of(*mt_rows[2:])},
            "printed": {100: 99, 166: 165, 167: 166},
        },
        "NT_021": {
            "rows": nt_rows["NT_021"],
            "pages": {
                1: text_of(nt_rows["NT_021"][0], prefix="Nota Técnica N° 21")
                + "\nVER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025",
                2: text_of(nt_rows["NT_021"][1], prefix="Se modifica la siguiente validación:"),
            },
        },
        "NT_024": {
            "rows": nt_rows["NT_024"],
            "pages": {
                1: text_of(nt_rows["NT_024"][0], prefix="Nota Técnica N° 24"),
                2: text_of(nt_rows["NT_024"][1], prefix="Se modifica la siguiente validación:")
                + "\nBase legal: Decreto 872/2023, art. 6",
            },
        },
    }
    nt021 = nt_doc("NT_021", 21, "29/12/2023", "01/01/2024", "01/01/2024")
    nt021["superseded_by"] = {
        "doc": "NT_024",
        "since": "2025-01-01",
        "stated_in": {
            "doc": "NT_021",
            "rev": S12["NT_021"],
            "page_pdf": "1",
            "quote": "VER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025",
        },
    }
    common = {"code": "1321", "severity": "R", "message": MSG}
    return {
        "sources": ["MT_V150", "NT_021", "NT_024"],
        "raw": raw,
        "ledger": [
            {
                "nt": "NT_021",
                "table": "validations",
                "id": "D208c",
                "action": "modified",
                "nt_ref": ref("NT_021", 2, "D208c"),
            },
            {
                "nt": "NT_024",
                "table": "validations",
                "id": "D208c",
                "action": "modified",
                "nt_ref": ref("NT_024", 2, "D208c"),
            },
        ],
        "checks": [{"at": "2026-10-17T12:00:00Z", "scope": ["nt"], "unregistered": []}],
        "meta": {
            "baseline_doc": "MT_V150",
            "baseline_sha256": REV["MT_V150"],
            "coverage_from": "2023-06-17",
            "horizon_grace_days": "7",
            "date_axis_default": "processing",
            "assumptions": [
                {"id": "A1", "text": "NT 001–012 rigieron antes de coverage_from.", "status": "unverified"}
            ],
        },
        "documents": {
            "MT_V150": {
                "id": "MT_V150",
                "kind": "manual",
                "title": "Manual Técnico v150 [fixture]",
                "current_revision": REV["MT_V150"],
                "curation_scope": "pilot",
            },
            "NT_021": nt021,
            "NT_024": nt_doc("NT_024", 24, "17/12/2024", "01/01/2025", "01/01/2025"),
        },
        "validations": {
            "D208c": {
                "key": "val:DE:D208c",
                "context": "DE",
                "id": "D208c",
                "subject_field": "field:DE:D208",
                "versions": [
                    {"introduced_by": "baseline", **common, "observation": obs("60.000.000")}
                    | {"condition": cond(60000000), "evidence": [ref("MT_V150", 167, "D208c")]},
                    {
                        "introduced_by": ["NT_021#1"],
                        "based_on": "baseline",
                        **common,
                        "observation": obs("35.000.000"),
                    }
                    | {"condition": cond(35000000), "evidence": [ref("NT_021", 2, "D208c")]},
                    {
                        "introduced_by": ["NT_024#1"],
                        "based_on": ["NT_021#1"],
                        **common,
                        "observation": obs("7.000.000"),
                    }
                    | {
                        "condition": cond(7000000),
                        "legal_basis": [
                            {
                                "citation": "Decreto 872/2023, art. 6",
                                "stated_in": {
                                    "doc": "NT_024",
                                    "rev": S12["NT_024"],
                                    "page_pdf": "2",
                                    "quote": "Decreto 872/2023, art. 6",
                                },
                            }
                        ],
                        "evidence": [ref("NT_024", 2, "D208c")],
                    },
                ],
            }
        },
        "fields": {
            "D208": {
                "key": "field:DE:D208",
                "context": "DE",
                "id": "D208",
                "versions": [
                    {"introduced_by": "baseline", "evidence": [ref("MT_V150", 166, "D208")]}
                    | {k: v for k, v in D208_CELLS.items() if k != "id"}
                    | {
                        "enumeration": [
                            {"code": "1", "label": "Cédula paraguaya"},
                            {"code": "2", "label": "Pasaporte"},
                            {"code": "5", "label": "Innominado"},
                        ],
                        "enumeration_interpretation": dict(HUMAN),
                    }
                ],
            },
            "F014": {
                "key": "field:DE:F014",
                "context": "DE",
                "id": "F014",
                "versions": [
                    {"introduced_by": "baseline", "evidence": [ref("MT_V150", 100, "F014")]}
                    | {k: v for k, v in F014_CELLS.items() if k != "id"}
                ],
            },
        },
        "issues": {
            "ISS-0001": {
                "id": "ISS-0001",
                "kind": "ambiguity",
                "affects": [{"subject": "val:DE:D208c"}],
                "statement": "[fixture] La condición formaliza el paréntesis.",
                "evidence": [ref("NT_024", 2, "D208c", "observation")],
                "blocking": False,
                "status": "open",
            }
        },
        "runs": {},
        "files": {},
    }


def build(root: Path, s: dict[str, Any], *, with_kb: bool = True) -> KB:
    """Escribe el `spec` en `root` y devuelve `load_kb(root)`."""
    s = copy.deepcopy(s)
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    revisions = []
    for doc in s["sources"]:
        data = source_bytes(doc)
        path = f"sources/{doc}/{S12[doc]}.pdf"
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data)
        revisions.append(
            {
                "doc": doc,
                "sha256": REV[doc],
                "md5": hashlib.md5(data).hexdigest(),
                "size": str(len(data)),
                "url": f"https://www.dnit.gov.py/documents/fixture/{doc}.pdf",
                "filename": f"{doc}.pdf",
                "retrieved_at": "2026-10-17T10:00:00Z",
                "origin": "portal",
                "path": path,
            }
        )
    write_kb_file(root / "sources.manifest.yaml", {"revisions": revisions, "checks": s["checks"]})
    for doc, r in s["raw"].items():
        rows = []
        for rw in r["rows"]:
            rw.setdefault("raw_cells", dict(rw["cells"]))
            rows.append(rw)
        write_text(rev_dir(root, doc, S12[doc]) / "tables.jsonl", rows_text(rows))
        pages = []
        for n, text in sorted(r["pages"].items()):
            body = text + "\n"
            write_text(page_path(root, doc, S12[doc], n), body)
            pages.append(
                {
                    "page_pdf": n,
                    "page_printed": r.get("printed", {}).get(n),
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "chars": len(body),
                }
            )
        write_text(
            rev_dir(root, doc, S12[doc]) / "index.json",
            index_text({"doc": doc, "sha256": REV[doc], "pages": pages}),
        )
    if s["ledger"]:
        write_text(ledger_dir(root) / "changes.jsonl", rows_text(s["ledger"]))
    if with_kb:
        kb = root / "kb"
        if s["meta"] is not None:
            write_kb_file(kb / "_meta.yaml", s["meta"])
        for doc_id, d in s["documents"].items():
            write_kb_file(kb / "documents" / f"{doc_id}.yaml", d)
        for name, f in s["fields"].items():
            write_kb_file(kb / "fields" / "DE" / f"{name}.yaml", f)
        for name, v in s["validations"].items():
            write_kb_file(kb / "validations" / "DE" / f"{name}.yaml", v)
        for iid, i in s["issues"].items():
            write_kb_file(kb / "issues" / f"{iid}.yaml", i)
    for name, run in s["runs"].items():
        write_kb_file(root / "curation" / "runs" / f"{name}.yaml", run)
    for rel, text in s["files"].items():
        write_text(root / rel, text)
    return load_kb(root)


def make(tmp_path: Path, mutate: Callable[[dict[str, Any]], None] | None = None, name: str = "repo") -> KB:
    s = spec()
    if mutate is not None:
        mutate(s)
    return build(tmp_path / name, s)


def found(kb: KB, check: str, *, severity: str = "error", base: Any = NOBASE) -> list[Finding]:
    return [f for f in run_checks(kb, base=base, only={check}) if f.severity == severity]


def has(findings: list[Finding], *fragments: str) -> bool:
    return any(all(fr in f.message or fr in f.where for fr in fragments) for f in findings)


def versions(s: dict[str, Any]) -> list[dict[str, Any]]:
    return s["validations"]["D208c"]["versions"]


def raw_row(s: dict[str, Any], doc: str, key: str, page: int | None = None) -> dict[str, Any]:
    return next(r for r in s["raw"][doc]["rows"] if r["key"] == key and (page is None or r["page"] == page))


def effect(s: dict[str, Any], eid: str) -> dict[str, Any]:
    doc = eid.split("#")[0]
    return next(e for e in s["documents"][doc]["effects"] if e["id"] == eid)


def drop_effect(s: dict[str, Any], eid: str) -> None:
    doc = eid.split("#")[0]
    s["documents"][doc]["effects"] = [e for e in s["documents"][doc]["effects"] if e["id"] != eid]


def set_nt_obs(s: dict[str, Any], doc: str, text: str) -> None:
    """Cambia la observación de la fila D208c de una NT (celda, marcas y página) de forma coherente."""
    r = raw_row(s, doc, "D208c")
    r["cells"]["observation"] = text
    r["marks"] = []
    r["changes"] = {}
    s["raw"][doc]["pages"][2] = text_of(r) + (
        "\nBase legal: Decreto 872/2023, art. 6" if doc == "NT_024" else ""
    )


# === Fixture limpio y CLI ===========================================================================
def test_clean_fixture_passes(tmp_path: Path) -> None:
    kb = make(tmp_path)
    assert kb.errors == []
    findings = run_checks(kb, base=NOBASE)
    assert errors_of(findings) == []
    assert [f for f in findings if f.severity == "warning"] == []
    assert {f.check for f in findings} <= {"fuentes", "pasado"}  # solo informativos


def test_every_check_is_registered_once() -> None:
    names = [n for n, _ in integrity.CHECKS]
    assert len(names) == len(set(names))
    assert {"literales", "cobertura", "pasado", "alcance", "biyeccion", "casos"} <= set(names)


def test_check_without_kb_passes_with_info(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "repo"
    build(root, spec(), with_kb=False)
    rc = cmd_check(argparse.Namespace(root=str(root), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert any(f["check"] == "fuentes" and "kb/ no existe" in f["message"] for f in payload["findings"])
    assert all(f["severity"] == "info" for f in payload["findings"])


def test_starting_state_only_meta_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Punto de partida de la curación: `kb/` solo con `_meta.yaml` (sin documentos ni entidades)."""
    s = spec()
    for k in ("documents", "fields", "validations", "issues"):
        s[k] = {}
    kb = build(tmp_path / "repo", s)
    fs = run_checks(kb, base=NOBASE)
    assert errors_of(fs) == [] and has(fs, "aún no tiene ficha")
    meta = kb.root / "kb" / "_meta.yaml"
    before = meta.read_bytes()
    assert _fmt(kb.root, True) == 0 and _fmt(kb.root, False) == 0
    assert meta.read_bytes() == before


def test_past_meta_change_is_flagged(tmp_path: Path, base: BaseSnapshot) -> None:
    fs = past(tmp_path, base, lambda s: s["meta"].update(horizon_grace_days="30"))
    assert has([f for f in fs if f.severity == "warning"], "kb/_meta.yaml (protegido) cambió")


def test_check_json_contract_and_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make(tmp_path)
    root = tmp_path / "repo"
    assert cmd_check(argparse.Namespace(root=str(root), json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"ok", "counts", "checks", "findings"}
    assert set(payload["counts"]) == {"error", "warning", "info"}
    assert payload["checks"] == [n for n, _ in integrity.CHECKS]
    for f in payload["findings"]:
        assert set(f) == {"check", "severity", "where", "message"}
        assert f["severity"] in ("error", "warning", "info")
    # un error sembrado: exit 1 y salida de texto agrupada por comprobación
    p = root / "kb" / "validations" / "DE" / "D208c.yaml"
    p.write_text(
        p.read_text(encoding="utf-8").replace("7.000.000 (F014", "7.000.001 (F014"), encoding="utf-8"
    )
    assert cmd_check(argparse.Namespace(root=str(root), json=False)) == 1
    out = capsys.readouterr().out
    assert "[literales]" in out and "ERROR" in out and "→ FALLA" in out


def test_internal_failure_is_a_finding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kb = make(tmp_path)

    def boom(kb: KB) -> list[Finding]:
        raise RuntimeError("roto")

    monkeypatch.setattr(integrity, "CHECKS", (("carga", boom), *integrity.CHECKS[1:]))
    fs = run_checks(kb, base=NOBASE)
    assert has([f for f in fs if f.check == "carga"], "fallo interno", "roto")


# === carga, archivos, formato ======================================================================
def test_load_errors_are_reported(tmp_path: Path) -> None:
    kb = make(
        tmp_path, lambda s: s["files"].update({"kb/issues/ISS-0002.yaml": "id: ISS-0002\nid: ISS-0002\n"})
    )
    assert has(found(kb, "carga"), "kb/issues/ISS-0002.yaml", "duplicada")


def test_key_must_match_path(tmp_path: Path) -> None:
    kb = make(tmp_path)
    assert found(kb, "archivos") == []
    src = kb.root / "kb" / "validations" / "DE" / "D208c.yaml"
    src.rename(src.with_name("D208x.yaml"))
    assert has(found(load_kb(kb.root), "archivos"), "debe vivir en kb/validations/DE/D208c.yaml")


def test_misplaced_and_case_colliding_files(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["files"]["kb/fields/D208.yaml"] = "key: field:DE:D208\n"
        s["files"]["kb/Issues/ISS-0001.yaml"] = "id: ISS-0001\n"

    errs = found(make(tmp_path, mutate), "archivos")
    assert has(errs, "kb/fields/D208.yaml", "fuera del esquema")
    assert has(errs, "sin distinguir mayúsculas")


def test_format_detects_comment(tmp_path: Path) -> None:
    kb = make(tmp_path)
    assert found(kb, "formato") == []
    p = kb.root / "kb" / "issues" / "ISS-0001.yaml"
    p.write_text(p.read_text(encoding="utf-8") + "# comentario\n", encoding="utf-8")
    kb = load_kb(kb.root)
    assert kb.errors == []
    assert has(found(kb, "formato"), "ISS-0001.yaml", "canónico")


# === fuentes y referencias raw ======================================================================
def test_sources_hash_and_current_revision(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: s["documents"]["NT_024"].update(current_revision="a" * 64))
    (kb.root / f"sources/NT_021/{S12['NT_021']}.pdf").write_bytes(b"%PDF-1.7 alterado")
    errs = found(kb, "fuentes")
    assert has(errs, "sha256", "NT_021")
    assert has(errs, "current_revision aaaaaaaaaaaa no está en el manifiesto")


def test_sources_baseline_meta(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: s["meta"].update(baseline_sha256=REV["NT_021"]))
    assert has(found(kb, "fuentes"), "kb/_meta.yaml", "no está en el manifiesto")


def test_uncurated_revision_is_a_warning(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["sources"].append("NT_023")
        s["documents"]["NT_023"] = {
            "id": "NT_023",
            "kind": "technical_note",
            "title": "NT 23 [fixture]",
            "current_revision": REV["NT_023"],
            "curation_scope": "dates_only",
        }

    kb = make(tmp_path, mutate)
    # Registrar otra revisión de NT_023 en el manifiesto sin curarla.
    m = kb.root / "sources.manifest.yaml"
    data = integrity.load_kb_text(m.read_text(encoding="utf-8"))
    extra = dict(data["revisions"][-1])
    extra.update(sha256=REV["NT_021"], retrieved_at="2026-10-18T10:00:00Z")
    data["revisions"].append(extra)
    m.write_text(dump_kb(data), encoding="utf-8")
    warns = found(load_kb(kb.root), "fuentes", severity="warning")
    assert has(warns, "NT_023", "no está curada")


def test_refs_must_resolve_to_exactly_one_row(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        effect(s, "NT_024#1")["evidence"] = [ref("NT_024", 9, "D208c")]
        s["raw"]["NT_021"]["rows"].append(copy.deepcopy(raw_row(s, "NT_021", "D208c")))
        s["issues"]["ISS-0001"]["evidence"] = ["raw:NT_024@000000000000:p2:D208c"]

    errs = found(make(tmp_path, mutate), "refs_raw")
    assert has(errs, "NT_024#1", "no resuelve a ninguna fila")
    assert has(errs, ref("NT_021", 2, "D208c"), "resuelve a 2 filas")
    assert has(errs, "ISS-0001", "revisión no registrada")


def test_cellref_needs_the_cell(tmp_path: Path) -> None:
    kb = make(
        tmp_path, lambda s: s["issues"]["ISS-0001"].update(evidence=[ref("NT_024", 2, "D208c", "length")])
    )
    assert has(found(kb, "refs_raw"), "no tiene la celda #length")


# === literales y destino de efectos =================================================================
def test_literal_must_equal_cell(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: versions(s)[2].update(message=MSG + " (parafraseado)"))
    assert has(found(kb, "literales"), "NT_024#1", "message ≠ celda")


def test_nt_literal_is_the_full_cell_even_with_red_text(tmp_path: Path) -> None:
    # El color de una NT no tiene semántica (RawRow.literal): quitar el tramo «rojo» es un error.
    assert found(make(tmp_path, name="ok"), "literales") == []
    kb = make(
        tmp_path, lambda s: versions(s)[1].update(observation=obs("35.000.000").replace(" (D208≠5)", ""))
    )
    assert has(found(kb, "literales"), "NT_021#1", "observation ≠ celda")


def test_mt_literal_drops_struck_text(tmp_path: Path) -> None:
    def struck(s: dict[str, Any], keep_struck: bool) -> None:
        r = raw_row(s, "MT_V150", "D208c")
        base = r["cells"]["observation"]
        r["cells"]["observation"] = base + " TACHADO"
        r["marks"] = [
            {
                "attr": "observation",
                "change": "deleted",
                "start": len(base),
                "end": len(base) + 8,
                "text": " TACHADO",
            }
        ]
        if keep_struck:
            versions(s)[0]["observation"] = base + " TACHADO"

    assert found(make(tmp_path, lambda s: struck(s, False), name="a"), "literales") == []
    assert has(
        found(make(tmp_path, lambda s: struck(s, True), name="b"), "literales"),
        "baseline",
        "observation ≠ celda",
    )


def test_row_of_another_entity_is_rejected(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        versions(s)[0]["evidence"] = [ref("MT_V150", 167, "D208b")]
        s["fields"]["D208"]["versions"][0]["evidence"] = [ref("MT_V150", 167, "D208")]  # misma ID, otra tabla

    errs = found(make(tmp_path, mutate), "literales")
    assert has(errs, "val:DE:D208c baseline", "fila D208b", "no es de D208c")
    assert has(errs, "field:DE:D208", "tabla «validations»")


def test_uncopied_column_is_inherited_from_based_on(tmp_path: Path) -> None:
    def no_severity(s: dict[str, Any]) -> None:
        del raw_row(s, "NT_024", "D208c")["cells"]["severity"]

    assert found(make(tmp_path, no_severity, name="a"), "literales") == []

    def wrong(s: dict[str, Any]) -> None:
        no_severity(s)
        versions(s)[2]["severity"] = "A"

    assert has(
        found(make(tmp_path, wrong, name="b"), "literales"), "no reproduce severity", "heredarse de based_on"
    )


def test_baseline_literal_without_cell(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: raw_row(s, "MT_V150", "D208c")["cells"].pop("severity"))
    assert has(found(kb, "literales"), "baseline", "severity", "sin celda")


def test_effect_target_matches_row_id(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["raw"]["NT_024"]["rows"].append(row(2, "D208b", "validations", val_cells("D208b", "1319", "otra")))
        effect(s, "NT_024#1")["evidence"] = [ref("NT_024", 2, "D208b")]

    kb = make(tmp_path, mutate)
    assert has(found(kb, "destino_efecto"), "NT_024#1", "destino val:DE:D208c", "fila D208b")
    # not_modeled exento: NT_024#2 apunta a field:DE:D208 y cita la fila de D208c (en el fixture limpio)
    assert found(make(tmp_path, name="ok"), "destino_efecto") == []


# === citas y fechas =================================================================================
def test_invented_quote(tmp_path: Path) -> None:
    kb = make(
        tmp_path, lambda s: versions(s)[2]["legal_basis"][0]["stated_in"].update(quote="Decreto 999/2099")
    )
    assert has(found(kb, "citas"), "legal_basis", "no está en raw/NT_024")


def test_quote_page_printed_and_missing_page(tmp_path: Path) -> None:
    def pref(printed: str, page: str = "167") -> dict[str, Any]:
        return {
            "doc": "MT_V150",
            "rev": S12["MT_V150"],
            "page_pdf": page,
            "page_printed": printed,
            "quote": "D208c",
        }

    assert (
        found(
            make(tmp_path, lambda s: s["issues"]["ISS-0001"].update(evidence=[pref("166")]), name="a"),
            "citas",
        )
        == []
    )
    errs = found(
        make(
            tmp_path,
            lambda s: s["issues"]["ISS-0001"].update(evidence=[pref("999"), pref("1", "5")]),
            name="b",
        ),
        "citas",
    )
    assert has(errs, "page_printed 999")
    assert has(errs, "no existe raw/MT_V150", "p005.txt")


def test_date_slot_must_cite_its_column(tmp_path: Path) -> None:
    kb = make(
        tmp_path,
        lambda s: s["documents"]["NT_024"]["schedule"]["test"].update(
            stated_in=ref("NT_024", 1, "fechas", "prod")
        ),
    )
    assert has(found(kb, "fechas_celdas"), "schedule.test", "exige la celda #test")


def test_date_literal_must_equal_cell(tmp_path: Path) -> None:
    kb = make(
        tmp_path,
        lambda s: s["documents"]["NT_021"]["document_date"].update(value="2023-12-28", literal="28/12/2023"),
    )
    assert has(found(kb, "fechas_celdas"), "document_date", "≠ celda")


def test_date_column_header(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: raw_row(s, "NT_024", "fechas")["header"].__setitem__(1, "Otra columna"))
    assert has(found(kb, "fechas_celdas"), "schedule.test", "encabezado")


def test_date_from_prose_pageref(tmp_path: Path) -> None:
    def prose(literal: str) -> Callable[[dict[str, Any]], None]:
        def mutate(s: dict[str, Any]) -> None:
            s["documents"]["NT_021"]["document_date"]["stated_in"] = {
                "doc": "NT_021",
                "rev": S12["NT_021"],
                "page_pdf": "1",
                "quote": "Fecha: 29/12/2023",
            }
            s["documents"]["NT_021"]["document_date"]["literal"] = literal

        return mutate

    assert found(make(tmp_path, prose("29/12/2023"), name="a"), "fechas_celdas") == []
    s_bad = prose("29-12-2023")
    assert has(found(make(tmp_path, s_bad, name="b"), "fechas_celdas"), "no está en la cita")


# === DSL y enumeraciones ============================================================================
def test_condition_constant_must_be_in_literal(tmp_path: Path) -> None:
    # 70.000.000 en vez de 7.000.000 (§J, controles mecánicos)
    kb = make(tmp_path, lambda s: versions(s)[2].update(condition=cond(70000000)))
    assert has(found(kb, "dsl"), "NT_024#1", "'70000000'")


def test_condition_names_and_syntax(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        versions(s)[1]["condition"] = cond(35000000) | {
            "expr": "exists(D011) and D011 != 13 and F014 >= 35000000"
        }
        versions(s)[0]["condition"] = cond(60000000) | {"expr": "D208 = 5"}

    errs = found(make(tmp_path, mutate), "dsl")
    assert has(errs, "NT_021#1", "lee D011")
    assert has(errs, "baseline", "fuera del DSL")


def test_enum_labels_in_observations(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["fields"]["D208"]["versions"][0]["enumeration"] = [
            {"code": "1", "label": "Carnet de identidad"},
            {"code": "1", "label": "Pasaporte"},
        ]

    errs = found(make(tmp_path, mutate), "enumeracion")
    assert has(errs, "Carnet de identidad", "no está en observations")
    assert has(errs, "repetidos: 1")


# === guardián de cobertura =========================================================================
def prose_mention(s: dict[str, Any], doc: str, text: str) -> None:
    """Agrega a la página 2 de la NT una frase en prosa, fuera de toda fila."""
    s["raw"][doc]["pages"][2] += "\n" + text


def test_unrecognized_mention(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        drop_effect(s, "NT_024#3")
        prose_mention(s, "NT_024", "Para el total de la operación ver el campo F014.")

    kb = make(tmp_path, mutate)
    assert has(found(kb, "cobertura"), "NT_024 menciona F014", "field:DE:F014")


def test_mention_inside_cited_row_is_recognized(tmp_path: Path) -> None:
    """Regla laxa acotada: D208 y F014 solo aparecen en la observación de D208c, fila que cita NT_0xx#1."""

    def mutate(s: dict[str, Any]) -> None:
        for doc in ("NT_021", "NT_024"):
            drop_effect(s, f"{doc}#2")
            drop_effect(s, f"{doc}#3")

    assert found(make(tmp_path, mutate), "cobertura") == []


def test_mention_inside_row_cited_only_by_not_modeled_is_not_exempt(tmp_path: Path) -> None:
    """Una fila citada solo por un `not_modeled` no exime: si NT_024#1 deja de citar la fila, F014 aparece."""

    def mutate(s: dict[str, Any]) -> None:
        drop_effect(s, "NT_024#3")
        effect(s, "NT_024#1").update(disposition="not_modeled", note="[fixture]")

    assert has(found(make(tmp_path, mutate), "cobertura"), "NT_024 menciona F014")


def test_untargeted_pending_recognizes_mentions(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        e = effect(s, "NT_024#3")
        e.update(disposition="pending", note=None)
        del e["target"]
        del e["note"]

    assert found(make(tmp_path, mutate), "cobertura") == []


def test_registered_nt_without_ficha_mentions_vocabulary(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["sources"].append("NT_023")
        s["raw"]["NT_023"] = {"rows": [], "pages": {1: "Se agrega el valor 6 al campo D208 (iTipIDRec)"}}

    kb = make(tmp_path, mutate)
    errs = found(kb, "cobertura")
    assert has(errs, "NT_023 menciona D208", "iTipIDRec", "no tiene ficha")


def test_ledger_is_an_oracle_of_changed_rows(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        drop_effect(s, "NT_024#3")
        set_nt_obs(s, "NT_024", obs("7.000.000").replace("(F014 >= 7.000.000)", "(total >= 7.000.000)"))
        versions(s)[2]["observation"] = raw_row(s, "NT_024", "D208c")["cells"]["observation"]
        versions(s)[2]["condition"] = cond(7000000)
        s["ledger"].append(
            {
                "nt": "NT_024",
                "table": "fields",
                "id": "F014",
                "action": "modified",
                "nt_ref": ref("NT_024", 2, "F014"),
            }
        )

    errs = found(make(tmp_path, mutate), "cobertura")
    assert not has(errs, "NT_024 menciona F014")  # el texto ya no lo nombra…
    assert has(errs, "libro de cambios", "field:DE:F014")  # …pero el libro de cambios sí registra la fila


# === biyección, acciones, inicios y predecesora ======================================================
def test_applied_effect_without_version(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["documents"]["NT_024"]["effects"].append(dict(effect(s, "NT_024#1"), id="NT_024#4"))

    assert has(found(make(tmp_path, mutate), "biyeccion"), "NT_024#4", "sin versión")


def test_pending_effect_cannot_introduce_a_version(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: effect(s, "NT_024#1").update(disposition="pending"))
    assert has(found(kb, "biyeccion"), "NT_024#1", "pending no introduce versiones")


def test_effects_of_one_version_share_start(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["documents"]["NT_021"]["effects"].append(dict(effect(s, "NT_021#1"), id="NT_021#4"))
        versions(s)[2]["introduced_by"] = ["NT_024#1", "NT_021#4"]

    assert has(found(make(tmp_path, mutate), "biyeccion"), "inicios distintos")


def test_tombstone_needs_remove(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: versions(s)[2].update(kind="tombstone"))
    assert has(found(kb, "acciones"), "NT_024#1", "lápida", "remove")
    kb2 = make(tmp_path, lambda s: effect(s, "NT_024#1").update(action="remove"), name="b")
    assert has(found(kb2, "acciones"), "produce una lápida")


def test_two_versions_same_start(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        for slot in ("test", "prod"):
            s["documents"]["NT_024"]["schedule"][slot].update(value="2024-01-01", literal="01/01/2024")

    assert has(
        found(make(tmp_path, mutate), "inicio_unico"), "dos versiones distintas empiezan en 2024-01-01"
    )


def test_based_on_is_temporal_predecessor(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: versions(s)[2].update(based_on="baseline"))
    assert has(found(kb, "predecesora"), "NT_024#1", "predecesora temporal", "NT_021#1")


def test_out_of_order_curation_detected(tmp_path: Path) -> None:
    # NT_024 curada antes que NT_021 (orden del archivo ≠ orden temporal): NT_021 debe basarse en baseline
    # y NT_024 en NT_021; aquí NT_021 dice basarse en NT_024.
    def mutate(s: dict[str, Any]) -> None:
        versions(s)[1]["based_on"] = ["NT_024#1"]
        versions(s)[2]["based_on"] = "baseline"

    errs = found(make(tmp_path, mutate), "predecesora")
    assert has(errs, "NT_021#1", "(baseline)") and has(errs, "NT_024#1", "(NT_021#1)")


# === alcance e interpretación ========================================================================
def _change_message(s: dict[str, Any], doc: str, idx: int, text: str) -> None:
    raw_row(s, doc, "D208c")["cells"]["message"] = text
    versions(s)[idx]["message"] = text


def test_change_outside_declared_scope(tmp_path: Path) -> None:
    def ok(s: dict[str, Any]) -> None:
        effect(s, "NT_024#1")["declared_scope"] = ["observation", "legal_basis"]

    assert found(make(tmp_path, ok, name="a"), "alcance") == []

    def bad(s: dict[str, Any]) -> None:
        ok(s)
        _change_message(s, "NT_024", 2, "Mensaje nuevo [fixture]")

    assert has(
        found(make(tmp_path, bad, name="b"), "alcance"), "NT_024#1", "cambia message fuera del alcance"
    )


def test_row_scope_unacknowledged_severity(tmp_path: Path) -> None:
    def bad(s: dict[str, Any]) -> None:
        raw_row(s, "NT_024", "D208c")["cells"]["severity"] = "AO"
        versions(s)[2]["severity"] = "AO"

    errs = found(make(tmp_path, bad, name="a"), "alcance")
    assert has(errs, "NT_024#1", "severity", "acknowledged_changes")

    def acknowledged(s: dict[str, Any]) -> None:
        bad(s)
        effect(s, "NT_024#1")["acknowledged_changes"] = ["severity"]

    assert found(make(tmp_path, acknowledged, name="b"), "alcance") == []


def test_scope_with_unknown_attribute(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: effect(s, "NT_024#1").update(declared_scope=["Observación"]))
    assert has(found(kb, "alcance"), "atributos desconocidos: Observación")


def test_tombstone_copies_predecessor(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        effect(s, "NT_024#1")["action"] = "remove"
        versions(s)[2].update(kind="tombstone", legal_basis=[])

    errs = found(make(tmp_path, mutate), "alcance")
    assert has(errs, "lápida copia la predecesora", "observation")


def test_interpreted_change_requires_literal_change(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        set_nt_obs(s, "NT_024", obs("35.000.000"))
        versions(s)[2]["observation"] = obs("35.000.000")
        versions(s)[2]["condition"] = cond(35000000) | {
            "level": "partial",
            "gaps": "re-interpretada [fixture]",
        }

    errs = found(make(tmp_path, mutate), "interpretado")
    assert has(errs, "NT_024#1", "cambia condition sin que cambie su literal observation")


# === ambientes, cobertura A1, integridad temporal, colisiones, fechas ================================
def _invert(s: dict[str, Any]) -> None:
    s["documents"]["NT_024"]["schedule"]["test"].update(value="2023-12-01", literal="01/12/2023")


def test_env_inversion_needs_issue(tmp_path: Path) -> None:
    assert has(found(make(tmp_path, _invert, name="a"), "inversion_ambientes"), "en test al revés")

    def with_issue(s: dict[str, Any]) -> None:
        _invert(s)
        s["issues"]["ISS-0002"] = {
            "id": "ISS-0002",
            "kind": "temporal",
            "affects": [{"subject": "NT_024", "env": "test"}],
            "statement": "[fixture] orden invertido en test",
            "blocking": True,
            "status": "open",
        }

    assert found(make(tmp_path, with_issue, name="b"), "inversion_ambientes") == []


def test_approx_start_before_coverage(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: s["documents"]["NT_021"].pop("schedule"))
    assert has(found(kb, "inicio_aproximado"), "NT_021", "supuesto A1")


def test_temporal_referential_integrity(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["documents"]["NT_021"]["effects"].append(
            dict(effect(s, "NT_021#1"), id="NT_021#4", action="remove", target="field:DE:F014")
        )
        f014 = s["fields"]["F014"]["versions"]
        f014.append(dict(f014[0], introduced_by=["NT_021#4"], based_on="baseline", kind="tombstone"))

    errs = found(make(tmp_path, mutate), "integridad_temporal")
    assert has(errs, "val:DE:D208c NT_021#1", "field:DE:F014", "está eliminado")


def test_code_collision_needs_issue(tmp_path: Path) -> None:
    def collide(s: dict[str, Any]) -> None:
        s["validations"]["D208b"] = {
            "key": "val:DE:D208b",
            "context": "DE",
            "id": "D208b",
            "versions": [
                {"introduced_by": "baseline", "code": "1321", "evidence": [ref("MT_V150", 167, "D208b")]}
            ],
        }

    assert has(found(make(tmp_path, collide, name="a"), "colisiones"), "1321", "val:DE:D208b", "val:DE:D208c")

    def declared(s: dict[str, Any]) -> None:
        collide(s)
        s["issues"]["ISS-0003"] = {
            "id": "ISS-0003",
            "kind": "code_collision",
            "affects": [{"subject": "val:DE:D208b"}, {"subject": "val:DE:D208c"}],
            "statement": "[fixture] colisión",
            "blocking": False,
            "status": "open",
        }

    assert found(make(tmp_path, declared, name="b"), "colisiones") == []


def test_dates_sane(tmp_path: Path) -> None:
    def bad(s: dict[str, Any]) -> None:
        s["documents"]["NT_024"]["schedule"]["test"].update(value="2025-02-01", literal="01/02/2025")
        s["documents"]["NT_021"]["document_date"].update(value="2023-06-01", literal="01/06/2023")
        s["issues"]["ISS-0001"]["affects"] = [
            {"subject": "val:DE:D208c", "since": "2025-01-01", "until": "2024-01-01"}
        ]

    errs = found(make(tmp_path, bad, name="a"), "fechas_sanas")
    assert has(errs, "NT_024", "posterior a producción")
    assert has(errs, "NT_021", "214 días", "erratum")
    assert has(errs, "ISS-0001", "ventana vacía o invertida")

    def erratum(s: dict[str, Any]) -> None:
        s["documents"]["NT_021"]["document_date"].update(value="2023-06-01", literal="01/06/2023")
        s["issues"]["ISS-0004"] = {
            "id": "ISS-0004",
            "kind": "erratum",
            "affects": [{"subject": "NT_021"}],
            "statement": "[fixture] errata de fecha",
            "blocking": False,
            "status": "open",
        }

    assert found(make(tmp_path, erratum, name="b"), "fechas_sanas") == []


# === referencias, reemplazo, corridas =================================================================
def test_references_exist(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["validations"]["D208c"]["subject_field"] = "field:DE:D999"
        versions(s)[2]["based_on"] = ["NT_099#1"]
        s["issues"]["ISS-0001"]["affects"].append({"subject": "NT_099"})
        s["issues"]["ISS-0001"]["corrects"] = ["D208c.obs", "val:DE:D208c@NT_099#1.observation"]
        effect(s, "NT_024#2")["target"] = "field:DE:D777"

    errs = found(make(tmp_path, mutate), "referencias")
    assert has(errs, "subject_field field:DE:D999")
    assert has(errs, "based_on NT_099#1 no existe")
    assert has(errs, "el sujeto NT_099 no existe")
    assert has(errs, "'D208c.obs'", "formato desconocido")
    assert has(errs, "no tiene la versión NT_099#1")
    assert has(errs, "NT_024#2", "field:DE:D777")


def test_valid_corrects_entry(tmp_path: Path) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["issues"]["ISS-0001"].update(kind="curation_error", corrects=["val:DE:D208c@NT_021#1.observation"])

    assert found(make(tmp_path, mutate), "referencias") == []


def test_supersession_oracle(tmp_path: Path) -> None:
    kb = make(tmp_path, lambda s: s["documents"]["NT_021"]["superseded_by"].update(since="2025-02-01"))
    assert has(found(kb, "reemplazo"), "superseded_by.since = 2025-02-01", "termina en producción 2025-01-01")


def _llm(s: dict[str, Any], run: str = "s1") -> None:
    effect(s, "NT_024#1")["interpretation"] = {"by": "llm", "run": run}


def _run(outputs: list[str]) -> dict[str, Any]:
    return {
        "session_id": "s1",
        "started_at": "2026-10-17T10:00:00Z",
        "tool": "claude-code",
        "outputs": [{"path": p, "sha256": "0" * 64} for p in outputs],
    }


def test_llm_interpretation_needs_its_run(tmp_path: Path) -> None:
    assert has(found(make(tmp_path, _llm, name="a"), "corridas_llm"), "curation/runs/s1.yaml no existe")

    def listed(s: dict[str, Any]) -> None:
        _llm(s)
        s["runs"]["s1"] = _run(["kb/documents/NT_024.yaml"])

    assert found(make(tmp_path, listed, name="b"), "corridas_llm") == []

    def unlisted(s: dict[str, Any]) -> None:
        _llm(s)
        s["runs"]["s1"] = _run(["kb/documents/NT_021.yaml"])

    assert has(found(make(tmp_path, unlisted, name="c"), "corridas_llm"), "no lista kb/documents/NT_024.yaml")


def test_new_human_interpretation_in_claude_edited_file(tmp_path: Path) -> None:
    base = BaseSnapshot(ref="main", commit="0" * 40, kb=make(tmp_path, name="base"))

    def mutate(s: dict[str, Any]) -> None:
        s["runs"]["s1"] = _run(["kb/documents/NT_024.yaml"])
        effect(s, "NT_024#1")["interpretation"] = {"by": "human", "note": "la escribió «una persona»"}

    errs = errors_of(check_llm_runs(make(tmp_path, mutate), base=base))
    assert has(errs, "NT_024#1", "nueva by: human")
    # sin cambios respecto de la base: la interpretación humana ya existía
    same = make(tmp_path, lambda s: s["runs"].update(s1=_run(["kb/documents/NT_024.yaml"])), name="same")
    assert errors_of(check_llm_runs(same, base=base)) == []
    infos = check_llm_runs(same, base="sin repositorio git")
    assert has(infos, "no comprobado")


def test_new_llm_interpretation_needs_a_run_of_this_change(tmp_path: Path) -> None:
    def old_run(s: dict[str, Any]) -> None:
        s["runs"]["s1"] = _run(["kb/documents/NT_024.yaml"])

    base_kb = make(tmp_path, old_run, name="base")
    run_text = (base_kb.root / "curation" / "runs" / "s1.yaml").read_text(encoding="utf-8")
    base = BaseSnapshot(ref="main", commit="0" * 40, kb=base_kb, runs={"curation/runs/s1.yaml": run_text})

    def reuse_old_run(s: dict[str, Any]) -> None:
        old_run(s)
        _llm(s, "s1")

    errs = errors_of(check_llm_runs(make(tmp_path, reuse_old_run), base=base))
    assert has(errs, "NT_024#1", "no es de este cambio")

    # una corrida nueva de este cambio sí cubre la interpretación
    def new_run(s: dict[str, Any]) -> None:
        old_run(s)
        s["runs"]["s2"] = _run(["kb/documents/NT_024.yaml"]) | {"session_id": "s2"}
        _llm(s, "s2")

    assert errors_of(check_llm_runs(make(tmp_path, new_run, name="b"), base=base)) == []

    # un archivo editado SOLO por una corrida antigua puede recibir una interpretación humana nueva
    def human_after_old_run(s: dict[str, Any]) -> None:
        old_run(s)
        effect(s, "NT_024#1")["interpretation"] = {"by": "human", "note": "revisión humana posterior"}

    assert errors_of(check_llm_runs(make(tmp_path, human_after_old_run, name="c"), base=base)) == []


# === pasado justificado =============================================================================
@pytest.fixture
def base(tmp_path: Path) -> BaseSnapshot:
    return BaseSnapshot(ref="main", commit="f" * 40, kb=make(tmp_path, name="base"))


def past(tmp_path: Path, base: BaseSnapshot, mutate: Callable[[dict[str, Any]], None]) -> list[Finding]:
    return check_past_changes(make(tmp_path, mutate), base=base)


def _curation_issue(s: dict[str, Any], iid: str, corrects: list[str], kind: str = "curation_error") -> None:
    s["issues"][iid] = {
        "id": iid,
        "kind": kind,
        "affects": [{"subject": "val:DE:D208c"}],
        "statement": "[fixture] corrección del pasado",
        "blocking": False,
        "corrects": corrects,
        "status": "open",
    }


def test_past_unchanged(tmp_path: Path, base: BaseSnapshot) -> None:
    fs = past(tmp_path, base, lambda s: None)
    assert errors_of(fs) == [] and has(fs, "sin cambios al pasado")


def test_past_version_deleted_or_reidentified(tmp_path: Path, base: BaseSnapshot) -> None:
    errs = errors_of(past(tmp_path, base, lambda s: versions(s).pop()))
    assert has(errs, "la versión NT_024#1 se eliminó")
    errs = errors_of(
        check_past_changes(
            make(tmp_path, lambda s: versions(s)[2].update(introduced_by=["NT_024#3"]), name="b"), base=base
        )
    )
    assert has(errs, "NT_024#1", "cambió su introduced_by")


def test_past_attribute_change_needs_correcting_issue(tmp_path: Path, base: BaseSnapshot) -> None:
    def edit(s: dict[str, Any]) -> None:
        versions(s)[1]["severity"] = "A"

    assert has(errors_of(past(tmp_path, base, edit)), "val:DE:D208c@NT_021#1.severity")

    def justified(s: dict[str, Any]) -> None:
        edit(s)
        _curation_issue(s, "ISS-0009", ["val:DE:D208c@NT_021#1.severity"])

    fs = check_past_changes(make(tmp_path, justified, name="b"), base=base)
    assert errors_of(fs) == [] and has(fs, "justificado por ISS-0009")


def test_past_corrects_must_be_new_in_this_change(tmp_path: Path) -> None:
    def preexisting(s: dict[str, Any]) -> None:
        _curation_issue(s, "ISS-0009", ["val:DE:D208c@NT_021#1.severity"])

    base = BaseSnapshot(ref="main", commit="f" * 40, kb=make(tmp_path, preexisting, name="base"))

    def edit(s: dict[str, Any]) -> None:
        preexisting(s)
        versions(s)[1]["severity"] = "A"

    assert has(errors_of(past(tmp_path, base, edit)), "NT_021#1.severity")


def test_past_effects_documents_issues(tmp_path: Path, base: BaseSnapshot) -> None:
    def mutate(s: dict[str, Any]) -> None:
        drop_effect(s, "NT_024#3")
        effect(s, "NT_024#1")["declared_scope"] = ["observation"]
        s["documents"]["NT_021"]["schedule"]["prod"].update(value="2024-02-01", literal="01/02/2024")
        del s["issues"]["ISS-0001"]
        del s["fields"]["F014"]

    errs = errors_of(past(tmp_path, base, mutate))
    assert has(errs, "efecto NT_024#3 se eliminó")
    assert has(errs, "NT_024#1.declared_scope")
    assert has(errs, "NT_021: cambia schedule")
    assert has(errs, "Issue ISS-0001 se eliminó")
    assert has(errs, "field:DE:F014 se eliminó")


def test_past_schedule_change_with_temporal_issue(tmp_path: Path, base: BaseSnapshot) -> None:
    def mutate(s: dict[str, Any]) -> None:
        s["documents"]["NT_021"]["schedule"]["prod"].update(value="2024-02-01", literal="01/02/2024")
        s["issues"]["ISS-0005"] = {
            "id": "ISS-0005",
            "kind": "temporal",
            "affects": [{"subject": "NT_021", "env": "prod"}],
            "statement": "[fixture] prórroga",
            "blocking": False,
            "status": "resolved",
            "resolution": "se curó la revisión nueva",
        }

    fs = past(tmp_path, base, mutate)
    assert errors_of(fs) == [] and has(fs, "NT_021.schedule justificado por ISS-0005")


def test_past_adding_superseded_by_is_allowed(tmp_path: Path) -> None:
    base = BaseSnapshot(
        ref="main",
        commit="f" * 40,
        kb=make(tmp_path, lambda s: s["documents"]["NT_021"].pop("superseded_by"), name="base"),
    )
    fs = past(tmp_path, base, lambda s: None)
    assert errors_of(fs) == [] and has(fs, "agrega superseded_by")


def test_past_pending_effect_changes_freely(tmp_path: Path) -> None:
    def pending(s: dict[str, Any]) -> None:
        effect(s, "NT_024#3").update(disposition="pending")

    base = BaseSnapshot(ref="main", commit="f" * 40, kb=make(tmp_path, pending, name="base"))
    assert errors_of(past(tmp_path, base, lambda s: None)) == []


def test_past_manifest_append_only(tmp_path: Path, base: BaseSnapshot) -> None:
    kb = make(tmp_path)
    kb.manifest = kb.manifest.model_copy(update={"revisions": kb.manifest.revisions[:-1]})
    assert has(errors_of(check_past_changes(kb, base=base)), "append-only", "se eliminaron 1")


def test_past_golden_row_deleted_or_changed(tmp_path: Path) -> None:
    golden = [
        {
            "id": "g1",
            "key": "val:DE:D208c",
            "at": "2025-01-01",
            "env": "prod",
            "expect": {"state": "in_force"},
        }
    ]
    base = BaseSnapshot(ref="main", commit="f" * 40, kb=make(tmp_path, name="base"), golden=golden)
    errs = errors_of(past(tmp_path, base, lambda s: None))
    assert has(errs, "fila golden eliminada")
    changed = [dict(golden[0], expect={"state": "removed"})]
    errs = errors_of(
        past(tmp_path, base, lambda s: s["files"].update({integrity.GOLDEN_PATH: dump_kb(changed)}))
    )
    assert has(errs, "expectativa golden", "modificada sin un Issue")


def test_past_without_git_is_not_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))  # aunque tmp esté dentro de otro repo
    kb = make(tmp_path)
    assert load_base(kb.root) == "sin repositorio git"
    fs = check_past_changes(kb)
    assert errors_of(fs) == [] and has(fs, "no comprobado (sin repositorio git)")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        check=True,
        capture_output=True,
    )


def test_past_against_git_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(integrity.BASE_REF_ENV, raising=False)
    kb = make(tmp_path)
    root = kb.root
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "pr")
    snap = load_base(root)
    assert isinstance(snap, BaseSnapshot) and snap.ref == "main" and "val:DE:D208c" in snap.kb.validations
    p = root / "kb" / "validations" / "DE" / "D208c.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("severity: R", "severity: A", 2), encoding="utf-8")
    errs = errors_of(check_past_changes(load_kb(root)))
    assert has(errs, "val:DE:D208c@baseline.severity") or has(errs, "NT_021#1.severity")
    # sin la rama main: no comprobado
    _git(root, "branch", "-q", "-m", "main", "trunk")
    assert "no existe la rama" in str(load_base(root))


# === casos ==========================================================================================
def _case(origin: str = "observed", entity: str = "val:DE:D208c", body: str = "Sin datos personales.") -> str:
    front = {
        "id": "2025-01-03-innominado",
        "origin": origin,
        "env": "prod",
        "document_type": "1",
        "kb_snapshot": "kb-2025.01.01",
        "codes_received": ["1321"],
        "entities": [entity],
        "status": "solved",
        "sanitized": True,
    }
    return "---\n" + dump_kb(front) + "---\n" + body + "\n"


def test_cases(tmp_path: Path) -> None:
    ok = make(
        tmp_path, lambda s: s["files"].update({"cases/2025/2025-01-03-innominado.md": _case()}), name="a"
    )
    assert found(ok, "casos") == []

    def bad(s: dict[str, Any]) -> None:
        s["files"]["cases/2025/2025-01-03-innominado.md"] = _case(
            origin="synthetic",
            entity="val:DE:D999",
            body="<dNumIDRec>4567890</dNumIDRec> masked <dRucRec>****567</dRucRec>",
        )
        s["issues"]["ISS-0001"]["evidence"].append("case:2025-02-02-otro")

    errs = found(make(tmp_path, bad, name="b"), "casos")
    assert has(errs, "sintético")
    assert has(errs, "val:DE:D999 no existe")
    assert has(errs, "dNumIDRec sin sanitizar")
    assert not has(errs, "dRucRec")
    assert has(errs, "case:2025-02-02-otro no es un caso")


# === sifen fmt ======================================================================================
def _fmt(root: Path, check: bool) -> int:
    return cmd_fmt(argparse.Namespace(root=str(root), check=check))


def test_fmt_check_and_rewrite(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kb = make(tmp_path)
    root = kb.root
    assert _fmt(root, True) == 0
    p = root / "kb" / "issues" / "ISS-0001.yaml"
    canonical = p.read_text(encoding="utf-8")
    p.write_text(canonical.replace("id: ISS-0001", 'id: "ISS-0001"'), encoding="utf-8")
    assert _fmt(root, True) == 1
    assert "no canónico: kb/issues/ISS-0001.yaml" in capsys.readouterr().out
    assert p.read_text(encoding="utf-8") != canonical  # --check no escribe
    assert _fmt(root, False) == 0
    assert p.read_text(encoding="utf-8") == canonical
    assert "reformateado: kb/issues/ISS-0001.yaml" in capsys.readouterr().out


def test_fmt_never_rewrites_protected_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kb = make(tmp_path)
    for rel in ("kb/_meta.yaml", "sources.manifest.yaml"):
        p = kb.root / rel
        text = p.read_text(encoding="utf-8")
        p.write_text(
            text.replace("baseline_doc: MT_V150", "baseline_doc: 'MT_V150'").replace(
                "origin: portal", "origin: 'portal'"
            ),
            encoding="utf-8",
        )
    before = {
        rel: (kb.root / rel).read_text(encoding="utf-8") for rel in ("kb/_meta.yaml", "sources.manifest.yaml")
    }
    assert _fmt(kb.root, False) == 1
    out = capsys.readouterr().out
    assert "kb/_meta.yaml (protegido" in out and "sources.manifest.yaml (protegido" in out
    assert {rel: (kb.root / rel).read_text(encoding="utf-8") for rel in before} == before


def test_fmt_refuses_to_drop_comments(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kb = make(tmp_path)
    p = kb.root / "kb" / "validations" / "DE" / "D208c.yaml"
    text = p.read_text(encoding="utf-8").replace(
        "subject_field: field:DE:D208", "subject_field: field:DE:D208 # campo"
    )
    p.write_text(text, encoding="utf-8")
    assert _fmt(kb.root, False) == 1
    assert "corrígelo a mano" in capsys.readouterr().out
    assert p.read_text(encoding="utf-8") == text


def test_fmt_without_kb(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "repo"
    build(root, spec(), with_kb=False)
    assert _fmt(root, True) == 0
    assert "kb/ no existe" in capsys.readouterr().out


# === §K.7: cinco errores sembrados ===================================================================
def test_seeded_errors_detected(tmp_path: Path) -> None:
    """Los cinco errores de §K.7, sembrados juntos en una misma KB, se detectan los cinco."""

    def seed(s: dict[str, Any]) -> None:
        # 1. cita inventada
        versions(s)[2]["legal_basis"][0]["stated_in"]["quote"] = "Decreto 999/2099, art. 1"
        # 2. cambio fuera del alcance declarado (NT 24 declara [observation, legal_basis] y cambia el mensaje)
        effect(s, "NT_024#1")["declared_scope"] = ["observation", "legal_basis"]
        _change_message(s, "NT_024", 2, "Mensaje nuevo [fixture]")
        # 3. mención no reconocida (NT 24 nombra F014 en prosa y nada lo reconoce)
        drop_effect(s, "NT_024#3")
        prose_mention(s, "NT_024", "Para el total de la operación ver el campo F014.")
        # 4. cambio de severidad sin reconocer con alcance row (NT 21: R → AO)
        raw_row(s, "NT_021", "D208c")["cells"]["severity"] = "AO"
        versions(s)[1]["severity"] = "AO"
        versions(s)[2]["severity"] = "AO"  # NT 24 hereda la severidad de NT 21 (no reproduce otra)
        raw_row(s, "NT_024", "D208c")["cells"]["severity"] = "AO"
        effect(s, "NT_024#1")["declared_scope"] = ["observation", "legal_basis"]
        # 5. la fila de una entidad asignada a otra (la regla de D208b como línea base de D208c)
        versions(s)[0]["evidence"] = [ref("MT_V150", 167, "D208b")]

    kb = make(tmp_path, seed)
    fs = errors_of(run_checks(kb, base=NOBASE))
    by = {name: [f for f in fs if f.check == name] for name, _ in integrity.CHECKS}
    assert has(by["citas"], "legal_basis", "Decreto 999/2099"), "1. cita inventada"
    assert has(by["alcance"], "NT_024#1", "message", "fuera del alcance"), "2. fuera del alcance declarado"
    assert has(by["cobertura"], "NT_024 menciona F014"), "3. mención no reconocida"
    assert has(by["alcance"], "NT_021#1", "severity", "acknowledged_changes"), (
        "4. severidad no reconocida (row)"
    )
    assert has(by["literales"], "val:DE:D208c baseline", "fila D208b"), "5. fila de otra entidad"


# === informe de revisión (§D.3 paso 7) ==============================================================
def test_report_lists_versions_calendars_issues_past_and_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def without_nt024(s: dict[str, Any]) -> None:
        del s["documents"]["NT_024"]
        versions(s).pop()
        s["documents"]["NT_021"].pop("superseded_by")

    base = BaseSnapshot(ref="main", commit="a" * 40, kb=make(tmp_path, without_nt024, name="base"))

    def head(s: dict[str, Any]) -> None:
        versions(s)[1]["open_questions"] = ["¿umbral inclusivo? [fixture]"]
        _curation_issue(s, "ISS-0009", ["val:DE:D208c@NT_021#1.open_questions"])
        e = dict(effect(s, "NT_024#1"), id="NT_024#4", disposition="pending")
        del e["target"]
        s["documents"]["NT_024"]["effects"].append(e)

    kb = make(tmp_path, head)
    fs = run_checks(kb, base=base)
    text = integrity.render_report(kb, base, fs)
    assert "base main (aaaaaaaaaaaa)" in text
    assert "Versión NT_024#1 · content · nueva · based_on NT_021#1" in text
    assert "diff contra based_on NT_021#1: condition, legal_basis, observation" in text
    assert "Versión NT_021#1 · content · modificada (cambio al pasado)" in text
    assert "NT_024 (nuevo): document_date '17/12/2024'" in text
    assert "ISS-0009 (curation_error, open)" in text
    assert "justificado por ISS-0009" in text
    assert "NT_024#4 → sin destino" in text
    # cmd_check lo agrega con args.report (la CLI aún no expone --report)
    monkeypatch.setattr(integrity, "load_base", lambda root, refs=None: base)
    rc = cmd_check(argparse.Namespace(root=str(kb.root), json=False, report=True))
    out = capsys.readouterr().out
    assert "# Informe de revisión de la KB" in out
    assert rc == (1 if errors_of(fs) else 0)

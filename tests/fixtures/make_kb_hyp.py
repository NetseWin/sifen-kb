"""Genera las KB de fixture del escenario [HIP] de docs/arquitectura.md §G.5.

    uv run python tests/fixtures/make_kb_hyp.py

- `tests/fixtures/kb_hyp/`: D208c con línea base (≥ 60 M), NT_021#1 (≥ 35 M), NT_024#1 (≥ 7 M),
  NT_901 [HIP] (≥ 5 M; test 2027-02-01, producción 2027-04-01 tras la prórroga de la revisión 2,
  con el Issue `temporal` resuelto) y NT_902 [HIP] (lápida; test 2027-09-01, producción
  2027-10-01). Horizonte: chequeo limpio el 2027-12-31.
- `tests/fixtures/kb_hyp_rev2/` (golden `hyp_rev2_pendiente`): el mismo manifiesto (revisión 2 de
  NT_901 registrada) pero la ficha de NT_901 todavía curada contra la revisión 1 (producción
  2027-03-01) y sin el Issue de la prórroga: lo que hay entre `source add` y el PR que la cura.

NADA de esto es evidencia real: hashes, páginas, claves de fila y URL son marcadores sintéticos;
NT_901/NT_902 no existen; los literales de 60 M, 35 M y 5 M están ADAPTADOS del literal real de
NT 24 (7 M). Todo YAML se escribe con `write_kb_file` (canónico) y se valida con `load_kb`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from sifen_kb.load import load_kb
from sifen_kb.yamlio import write_kb_file

HERE = Path(__file__).resolve().parent
TARGETS = {"kb_hyp": True, "kb_hyp_rev2": False}
"""Directorio -> ¿NT_901 curada en la revisión 2 (prórroga aplicada)?"""

INTERP = {"by": "human", "note": "[HIP] fixture"}
MESSAGE = "Tipo de documento de identidad del receptor incorrecto para el total general de la operación en guaraníes"
LEGAL = "Decreto 872/2023, art. 6, numeral 2, inciso ii)"


def sha(label: str) -> str:
    return hashlib.sha256(f"kb_hyp:{label}".encode()).hexdigest()


def md5(label: str) -> str:
    return hashlib.md5(f"kb_hyp:{label}".encode()).hexdigest()  # noqa: S324 - marcador sintético


REV = {
    "MT_V150": sha("MT_V150"),
    "NT_021": sha("NT_021"),
    "NT_024": sha("NT_024"),
    "NT_901:rev1": sha("NT_901:rev1"),
    "NT_901:rev2": sha("NT_901:rev2"),
    "NT_902": sha("NT_902"),
}


def s12(label: str) -> str:
    return REV[label][:12]


def observation(amount: str) -> str:
    """Literal real de NT 24 (7.000.000); con otro monto es una ADAPTACIÓN de fixture."""
    return (
        "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), El Tipo de documento de "
        "identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la "
        "operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación "
        f"(cuando la moneda es PYG) es mayor o igual a {amount} (F023 >= {amount} o F014 >= {amount})"
    )


def condition(amount: int) -> dict[str, Any]:
    return {
        "expr": (
            f"(not exists(D011) or D011 != 13) and exists(D208) and D208 == 5 and "
            f"((exists(F023) and F023 >= {amount}) or (exists(F014) and F014 >= {amount}))"
        ),
        "level": "partial",
        "gaps": (
            "Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015) "
            "(ISS-0002). Que D011 ausente equivalga a ≠ 13 y que D208 ausente no viole son interpretaciones."
        ),
        "interpretation": INTERP,
    }


def date_stmt(value: str, literal: str, doc: str, rev: str, attr: str) -> dict[str, Any]:
    return {"value": value, "literal": literal, "stated_in": f"raw:{doc}@{s12(rev)}:p1:fechas#{attr}"}


def effect(eid: str, verb: str, action: str, scope: Any, ref: str) -> dict[str, Any]:
    return {
        "id": eid,
        "verb_literal": verb,
        "action": action,
        "target": "val:DE:D208c",
        "declared_scope": scope,
        "evidence": [ref],
        "interpretation": INTERP,
    }


# --- Documentos ------------------------------------------------------------------------------------
def documents(nt901_rev: str) -> dict[str, dict[str, Any]]:
    prorroga = nt901_rev == "NT_901:rev2"
    return {
        "MT_V150": {
            "id": "MT_V150",
            "kind": "manual",
            "title": "Manual Técnico SIFEN versión 150 [fixture]",
            "current_revision": REV["MT_V150"],
            "curation_scope": "pilot",
        },
        "NT_021": {
            "id": "NT_021",
            "kind": "technical_note",
            "number": 21,
            "title": "Nota Técnica N° 21 [fixture]",
            "current_revision": REV["NT_021"],
            "document_date": date_stmt("2023-12-29", "29/12/2023", "NT_021", "NT_021", "fecha"),
            "schedule": {
                "test": date_stmt("2024-01-01", "01/01/2024", "NT_021", "NT_021", "test"),
                "prod": date_stmt("2024-01-01", "01/01/2024", "NT_021", "NT_021", "prod"),
            },
            "superseded_by": {
                "doc": "NT_024",
                "since": "2025-01-01",
                "stated_in": {
                    "doc": "NT_021",
                    "rev": s12("NT_021"),
                    "page_pdf": 1,
                    "quote": "VER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025",
                },
            },
            "effects": [
                effect(
                    "NT_021#1",
                    "Se modifica la siguiente validación",
                    "modify",
                    "row",
                    f"raw:NT_021@{s12('NT_021')}:p2:D208c",
                )
            ],
            "curation_scope": "pilot",
        },
        "NT_024": {
            "id": "NT_024",
            "kind": "technical_note",
            "number": 24,
            "title": "Nota Técnica N° 24 [fixture]",
            "current_revision": REV["NT_024"],
            "document_date": date_stmt("2024-12-17", "17/12/2024", "NT_024", "NT_024", "fecha"),
            "schedule": {
                "test": date_stmt("2025-01-01", "01/01/2025", "NT_024", "NT_024", "test"),
                "prod": date_stmt("2025-01-01", "01/01/2025", "NT_024", "NT_024", "prod"),
            },
            "effects": [
                effect(
                    "NT_024#1",
                    "Se modifica la siguiente validación",
                    "modify",
                    "row",
                    f"raw:NT_024@{s12('NT_024')}:p2:D208c",
                )
            ],
            "curation_scope": "pilot",
        },
        "NT_901": {
            "id": "NT_901",
            "kind": "technical_note",
            "number": 901,
            "title": "Nota Técnica N° 901 [HIP]",
            "current_revision": REV[nt901_rev],
            "document_date": date_stmt("2027-01-15", "15/01/2027", "NT_901", nt901_rev, "fecha"),
            "schedule": {
                "test": date_stmt("2027-02-01", "01/02/2027", "NT_901", nt901_rev, "test"),
                "prod": (
                    date_stmt("2027-04-01", "01/04/2027", "NT_901", nt901_rev, "prod")
                    if prorroga
                    else date_stmt("2027-03-01", "01/03/2027", "NT_901", nt901_rev, "prod")
                ),
            },
            "effects": [
                effect(
                    "NT_901#1",
                    "Se modifica la Observación de la siguiente validación",
                    "modify",
                    ["observation"],
                    f"raw:NT_901@{s12(nt901_rev)}:p2:D208c",
                )
            ],
            "curation_scope": "pilot",
        },
        "NT_902": {
            "id": "NT_902",
            "kind": "technical_note",
            "number": 902,
            "title": "Nota Técnica N° 902 [HIP]",
            "current_revision": REV["NT_902"],
            "document_date": date_stmt("2027-08-02", "02/08/2027", "NT_902", "NT_902", "fecha"),
            "schedule": {
                "test": date_stmt("2027-09-01", "01/09/2027", "NT_902", "NT_902", "test"),
                "prod": date_stmt("2027-10-01", "01/10/2027", "NT_902", "NT_902", "prod"),
            },
            "effects": [
                effect(
                    "NT_902#1",
                    "Se elimina la siguiente validación",
                    "remove",
                    "row",
                    f"raw:NT_902@{s12('NT_902')}:p1:D208c",
                )
            ],
            "curation_scope": "pilot",
        },
    }


# --- Entidades -------------------------------------------------------------------------------------
def d208c(nt901_rev: str) -> dict[str, Any]:
    legal = [
        {
            "citation": LEGAL,
            "stated_in": {"doc": "NT_024", "rev": s12("NT_024"), "page_pdf": 2, "quote": "Decreto 872/2023"},
        }
    ]

    def content(amount_txt: str, amount: int) -> dict[str, Any]:
        return {
            "code": "1321",
            "severity": "R",
            "message": MESSAGE,
            "observation": observation(amount_txt),
            "condition": condition(amount),
        }

    v3 = content("5.000.000", 5000000) | {"legal_basis": legal}
    return {
        "key": "val:DE:D208c",
        "context": "DE",
        "id": "D208c",
        "subject_field": "field:DE:D208",
        "versions": [
            {"introduced_by": "baseline"}
            | content("60.000.000", 60000000)
            | {"evidence": [f"raw:MT_V150@{s12('MT_V150')}:p167:D208c"]},
            {"introduced_by": ["NT_021#1"], "based_on": "baseline"}
            | content("35.000.000", 35000000)
            | {"evidence": [f"raw:NT_021@{s12('NT_021')}:p2:D208c"]},
            {"introduced_by": ["NT_024#1"], "based_on": ["NT_021#1"]}
            | content("7.000.000", 7000000)
            | {"legal_basis": legal, "evidence": [f"raw:NT_024@{s12('NT_024')}:p2:D208c"]},
            {"introduced_by": ["NT_901#1"], "based_on": ["NT_024#1"]}
            | v3
            | {"evidence": [f"raw:NT_901@{s12(nt901_rev)}:p2:D208c"]},
            {"introduced_by": ["NT_902#1"], "based_on": ["NT_901#1"], "kind": "tombstone"}
            | v3
            | {"evidence": [f"raw:NT_902@{s12('NT_902')}:p1:D208c"]},
        ],
    }


def d208() -> dict[str, Any]:
    return {
        "key": "field:DE:D208",
        "context": "DE",
        "id": "D208",
        "versions": [
            {
                "introduced_by": "baseline",
                "evidence": [f"raw:MT_V150@{s12('MT_V150')}:p166:D208"],
                "group": "D3",
                "parent": "D200",
                "xml_name": "iTipIDRec",
                "description": "Tipo de documento de identidad del receptor",
                "data_type": "N",
                "length": "1",
                "occurrence": "0-1",
                "observations": "[fixture] Obligatorio si D201 = 2 y D202 ≠ 4",
            }
        ],
    }


def issues(prorroga: bool) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {
        "ISS-0002": {
            "id": "ISS-0002",
            "kind": "ambiguity",
            "affects": [{"subject": "val:DE:D208c"}],
            "statement": (
                "[fixture] La prosa asocia F023 a moneda extranjera y F014 a PYG; la condición formaliza "
                "el paréntesis (F023 >= X o F014 >= X)."
            ),
            "evidence": [f"raw:NT_024@{s12('NT_024')}:p2:D208c#observation"],
            "blocking": False,
            "status": "open",
        }
    }
    if prorroga:
        out["ISS-0001"] = {
            "id": "ISS-0001",
            "kind": "temporal",
            "affects": [{"subject": "NT_901", "env": "prod"}],
            "statement": (
                "[HIP] Prórroga de NT_901 en producción: la revisión 1 (subida 2027-01-18) declaraba "
                "01/03/2027; la revisión 2 (re-subida 2027-02-20) declara 01/04/2027. Test sin cambios "
                "(01/02/2027)."
            ),
            "evidence": [
                f"raw:NT_901@{s12('NT_901:rev1')}:p1:fechas#prod",
                f"raw:NT_901@{s12('NT_901:rev2')}:p1:fechas#prod",
            ],
            "blocking": False,
            "status": "resolved",
            "resolution": (
                "Se curó la revisión 2: schedule.prod = 2027-04-01 y current_revision actualizada. No se "
                "crea una versión nueva: cambió cuándo empieza, no la regla."
            ),
        }
    return out


def meta() -> dict[str, Any]:
    return {
        "baseline_doc": "MT_V150",
        "baseline_sha256": REV["MT_V150"],
        "coverage_from": "2023-06-17",
        "horizon_grace_days": 7,
        "date_axis_default": "processing",
        "assumptions": [
            {
                "id": "A1",
                "text": "NT 001–012 rigieron antes de coverage_from.",
                "status": "unverified",
            },
            {
                "id": "A2",
                "text": "--at es la fecha de procesamiento (dFecProc).",
                "status": "unverified",
            },
            {
                "id": "FIX",
                "text": (
                    "[HIP] KB de fixture: hashes, páginas y URL son marcadores; NT_901 y NT_902 no existen; "
                    "los literales de 60 M, 35 M y 5 M están adaptados del de NT 24."
                ),
                "status": "unverified",
            },
        ],
    }


def manifest() -> dict[str, Any]:
    def rev(
        label: str, filename: str, portal_t: str, retrieved_at: str, note: str | None = None
    ) -> dict[str, Any]:
        doc = label.split(":")[0]
        r: dict[str, Any] = {
            "doc": doc,
            "sha256": REV[label],
            "md5": md5(label),
            "size": 100000 + int(REV[label][:4], 16),
            "url": f"https://fixture.invalid/kb_hyp/{filename}",
            "filename": filename,
            "portal_t": portal_t,
            "retrieved_at": retrieved_at,
            "origin": "portal",
            "path": f"sources/{doc}/{REV[label][:12]}.pdf",
        }
        if note:
            r["note"] = note
        return r

    return {
        "revisions": [
            rev("MT_V150", "Manual_Tecnico_Version_150.pdf", "2019-09-30T00:00:00", "2026-10-17T10:00:00"),
            rev(
                "NT_021",
                "NT_E_KUATIA_021_MT_V150.pdf",
                "2024-12-30T00:00:00",
                "2026-10-17T10:01:00",
                "Revisión inicial: la de 2024 con marca de agua (fixture).",
            ),
            rev("NT_024", "NT_E_KUATIA_024_MT_V150.pdf", "2024-12-19T00:00:00", "2026-10-17T10:02:00"),
            rev("NT_901:rev1", "NT_E_KUATIA_901.pdf", "2027-01-18T00:00:00", "2027-01-18T12:00:00", "[HIP]"),
            rev(
                "NT_901:rev2",
                "NT_E_KUATIA_901.pdf",
                "2027-02-20T00:00:00",
                "2027-02-20T12:00:00",
                "[HIP] Re-subida: prórroga de producción.",
            ),
            rev("NT_902", "NT_E_KUATIA_902.pdf", "2027-08-02T00:00:00", "2027-08-03T12:00:00", "[HIP]"),
        ],
        "checks": [
            {"at": "2027-12-31T00:00:00", "scope": ["nt", "xsd", "tablas", "manual"], "unregistered": []}
        ],
    }


def _write(path: Path, data: Any) -> None:
    # Copia sin referencias compartidas: el volcador de PyYAML emitiría anchors/alias (prohibidos).
    write_kb_file(path, json.loads(json.dumps(data, ensure_ascii=False)))


def write_fixture(root: Path, *, prorroga: bool) -> None:
    """Escribe una KB de fixture completa en `root` (borra antes su `kb/`)."""
    nt901_rev = "NT_901:rev2" if prorroga else "NT_901:rev1"
    if (root / "kb").exists():
        shutil.rmtree(root / "kb")
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("", encoding="utf-8", newline="\n")
    _write(root / "sources.manifest.yaml", manifest())
    _write(root / "kb" / "_meta.yaml", meta())
    for doc_id, data in documents(nt901_rev).items():
        _write(root / "kb" / "documents" / f"{doc_id}.yaml", data)
    _write(root / "kb" / "validations" / "DE" / "D208c.yaml", d208c(nt901_rev))
    _write(root / "kb" / "fields" / "DE" / "D208.yaml", d208())
    for iss_id, data in issues(prorroga).items():
        _write(root / "kb" / "issues" / f"{iss_id}.yaml", data)


def main(base: Path = HERE) -> int:
    for name, prorroga in TARGETS.items():
        root = base / name
        write_fixture(root, prorroga=prorroga)
        kb = load_kb(root)
        if kb.root != root.resolve() or kb.errors:
            print(f"{name}: errores de carga", *kb.errors, sep="\n  ", file=sys.stderr)
            return 1
        print(
            f"{name}: {len(kb.documents)} documentos, {len(kb.validations)} validaciones, {len(kb.issues)} issues"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Semántica del marcado en `rawio`: `rendered_literal`, `effective_literal`, `color_signal`,
`verb_actions` y `marking_conflicts`.

Regla vigente (decisiones 2 y 3 del usuario, 2026-10-17): en el MT y en las NT el rojo es contenido
eliminado, el verde agregado y el amarillo modificado, junto con el verbo del encabezado. Antes, en
una NT se copiaba la celda completa (`RawRow.literal`); estos tests cambiaron porque cambió la regla.
Contradicciones: regla «mixta» (decisión del usuario, 2026-10-17).
"""

from pathlib import Path
from typing import Any

import pytest

from sifen_kb.rawio import RawRow, iter_rows, marking_conflicts, verb_actions

ROOT = Path(__file__).resolve().parents[2]


def row(doc: str, marks: list[dict], raw_obs: str) -> RawRow:
    return RawRow(
        doc=doc,
        sha12="0" * 12,
        page=1,
        key="D208c",
        occ=1,
        table="validations",
        header=[],
        cells={"observation": raw_obs},
        raw_cells={"observation": raw_obs},
        marks=marks,
    )


RED = [{"attr": "observation", "change": "deleted", "start": 9, "end": 17, "text": "o igual "}]


@pytest.mark.parametrize("doc", ["MT_V150", "NT_021", "NT_024", "NT_099"])
def test_effective_literal_drops_red_text_in_every_document(doc):
    r = row(doc, RED, "es mayor o igual a 7")
    assert r.effective_literal("observation") == r.current("observation") == "es mayor a 7"
    assert r.rendered_literal("observation") == "es mayor o igual a 7"
    assert r.removed_spans("observation") == ["o igual "]


def test_effective_literal_keeps_added_and_modified_text():
    marks = [
        {"attr": "observation", "change": "added", "start": 0, "end": 5, "text": "Nuevo"},
        {"attr": "observation", "change": "modified", "start": 6, "end": 11, "text": "monto"},
    ]
    r = row("NT_099", marks, "Nuevo monto")
    assert r.effective_literal("observation") == r.rendered_literal("observation") == "Nuevo monto"
    assert r.removed_spans("observation") == []


@pytest.mark.parametrize(
    ("doc", "sha12", "amount"),
    [("NT_021", "1e716577d874", "35.000.000"), ("NT_024", "ccc2d1550e92", "7.000.000")],
)
def test_real_nt_d208c_effective_literal_without_d011_exception(doc, sha12, amount):
    """Decisión 3: en NT 21/24 el rojo también elimina: sin «(D011≠13)», sin «o igual» y «>» por «>=»."""
    if not (ROOT / "raw" / doc / sha12).is_dir():
        pytest.skip(f"raw/{doc}/{sha12} no disponible")
    (d208c,) = [r for r in iter_rows(ROOT, doc, sha12) if r.key == "D208c"]
    shown, effective = d208c.rendered_literal("observation"), d208c.effective_literal("observation")
    assert "(D011≠13)" in shown and "mayor o igual" in shown and ">=" in shown
    assert "(D011≠13)" not in effective and "o igual" not in effective and ">=" not in effective
    assert effective.startswith("El Tipo de documento de identidad del receptor")
    assert f"mayor a {amount}" in effective


def vrow(cells: dict[str, str], changes: dict[str, str], *, row_change: str | None = None) -> RawRow:
    marks: list[dict[str, Any]] = [
        {"attr": a, "change": c, "start": 0, "end": len(cells[a]), "text": cells[a]}
        for a, c in changes.items()
    ]
    return RawRow(
        doc="NT_099",
        sha12="0" * 12,
        page=2,
        key=cells["id"],
        occ=1,
        table="validations",
        header=[],
        cells=cells,
        raw_cells=dict(cells),
        changes=changes,
        row_change=row_change,
        marks=marks,
    )


CELLS = {"id": "V001", "message": "Mensaje", "code": "1001", "observation": "Si A = 1", "severity": "R"}
ATTRS = ["code", "severity", "message", "observation"]
WHOLE_RED = {a: "deleted" for a in ("id", "message", "code", "observation")}  # «R» sin color (NT 2)
WHOLE_GREEN = dict.fromkeys(CELLS, "added")


def test_color_signal():
    assert vrow(CELLS, {}).color_signal(ATTRS) is None
    assert vrow(CELLS, WHOLE_RED).color_signal(ATTRS) == "deleted"
    assert vrow(CELLS, WHOLE_GREEN, row_change="added").color_signal(ATTRS) == "added"
    assert vrow(CELLS, {"observation": "modified"}).color_signal(ATTRS) == "modified"
    assert vrow(CELLS, {"id": "deleted", "observation": "added"}).color_signal(ATTRS) == "mixed"


def test_verb_actions():
    assert verb_actions("se modifica la siguiente validación") == {"modify"}
    assert verb_actions("Se eliminan las siguientes validaciones") == {"remove"}
    assert verb_actions(
        "se modifican y elimina las siguientes validaciones y se agrega nueva validación"
    ) == {
        "add",
        "modify",
        "remove",
    }
    assert verb_actions("se excluye") == {"modify", "remove"}
    assert verb_actions("se realizó una verificación de las fórmulas utilizadas") == frozenset()


def kinds(
    r: RawRow, action: str, verb: str, pred: dict[str, str | None] | None = None
) -> list[tuple[str, bool]]:
    found = marking_conflicts(r, action=action, verb_literal=verb, attrs=ATTRS, predecessor=pred)
    return [(c.kind, c.blocking) for c in found]


def test_marking_conflicts_consistent_signals():
    green = vrow(CELLS, WHOLE_GREEN, row_change="added")
    assert kinds(green, "add", "se agrega la siguiente validación") == []
    assert kinds(vrow(CELLS, WHOLE_RED), "remove", "Se eliminan las siguientes validaciones") == []
    assert kinds(vrow(CELLS, {}), "modify", "se realizó una verificación") == []


def test_color_against_curated_action_is_blocking():
    green = vrow(CELLS, WHOLE_GREEN, row_change="added")
    assert kinds(green, "modify", "se modifica la siguiente validación") == [("color_accion", True)]
    assert kinds(vrow(CELLS, WHOLE_RED), "modify", "se modifica") == [("color_accion", True)]


def test_color_against_verb_only_is_traceability():
    """NT 23 #5–#7: filas en verde (altas, `add`) bajo «se modifica la siguiente validación»."""
    green = vrow(CELLS, WHOLE_GREEN, row_change="added")
    assert kinds(green, "add", "se modifica la siguiente validación") == [("color_verbo", False)]


def test_ambiguous_marking_is_blocking():
    mixed = vrow(CELLS, {"id": "deleted", "observation": "added"})
    assert kinds(mixed, "modify", "se modifica") == [("mixto", True)]
    emptied = vrow(CELLS, {"observation": "deleted"})
    assert kinds(emptied, "modify", "se modifica") == [("vacio", True)]


def test_modify_without_effective_change_is_blocking():
    cells = CELLS | {"observation": "Si A = 1 y B=2"}
    red = [{"attr": "observation", "change": "deleted", "start": 8, "end": 14, "text": " y B=2"}]
    r = RawRow(
        "NT_099", "0" * 12, 2, "V001", 1, "validations", [], cells, dict(cells),
        changes={"observation": "modified"}, marks=red,
    )  # fmt: skip
    assert r.effective_literal("observation") == "Si A = 1"
    assert kinds(r, "modify", "se modifica", dict(CELLS)) == [("sin_cambio", True)]
    assert kinds(r, "modify", "se modifica", dict(cells)) == []
    assert kinds(r, "modify", "se modifica") == []  # sin predecesora no se evalúa

# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_geometry.py), integrado en sifen-kb bajo MIT.
"""T-301: IR por geometría para las 5 NT sin etiquetas (001, 007, 011, 012, 013).

Las 22 NT etiquetadas salen por `tagged.extract_tagged`; estas no tienen árbol de estructura.
La rejilla de bordes (rectángulos finos, no los rellenos de resaltado) da filas y columnas, y el
encabezado conocido del dominio confirma que la tabla es de campos o de validaciones.
"""

from pathlib import Path

import corpus_pdf
import pytest

from sifen_kb.pdf.colors import color_conservation
from sifen_kb.pdf.geometry import (
    FIELD_HEADER,
    VALIDATION_HEADER,
    Grid,
    GridRow,
    anchor_gaps,
    extract_geometric,
    grids,
    header_labels,
    normalized,
    runs_of,
)
from sifen_kb.pdf.ir import Cell, Change, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.sifen.artifacts import NT_HEADER, nt_text_conservation

NOTES = corpus_pdf.NOTAS
UNTAGGED = {"001": 3, "007": 2, "011": 3, "012": 1, "013": 3}
FIELD_TEXT = [
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


def note(number: str) -> Path:
    return NOTES / f"NT_E_KUATIA_{number}_MT_V150.pdf"


# --------------------------------------------------------------------------- sintéticos

BLACK = (0.0, 0.0, 0.0)
YELLOW = (1.0, 1.0, 0.0)


def rect(x0: float, top: float, x1: float, bottom: float, color: tuple = BLACK) -> dict:
    return {
        "x0": x0,
        "x1": x1,
        "top": top,
        "bottom": bottom,
        "non_stroking_color": color,
        "fill": True,
        "stroke": False,
    }


def borders(xs: list[float], ys: list[float]) -> list[dict]:
    """Rejilla como la dibuja Word: un rectángulo fino por borde, uno por celda."""
    drawn = [rect(xs[0], y, xs[-1], y + 0.5) for y in ys]
    for top, bottom in zip(ys, ys[1:], strict=False):
        drawn += [rect(x, top, x + 0.5, bottom) for x in xs]
    return drawn


def chars(text: str, x0: float, top: float, size: float = 10.0) -> list[dict]:
    out = []
    for letter in text:
        width = size * 0.5
        out.append(
            {
                "text": letter,
                "x0": x0,
                "x1": x0 + width,
                "top": top,
                "bottom": top + size,
                "size": size,
            }
        )
        x0 += width
    return out


def test_thin_borders_become_a_grid_of_rows_and_columns() -> None:
    found = grids(borders([10.0, 50.0, 90.0], [100.0, 120.0, 140.0]))

    assert found == [
        Grid(
            columns=(10.25, 50.25, 90.25),
            rows=(
                GridRow(top=100.25, bottom=120.25, cols=(0, 1, 2)),
                GridRow(top=120.25, bottom=140.25, cols=(0, 1, 2)),
            ),
        )
    ]


def test_highlight_rects_are_not_borders() -> None:
    # Por esto `find_tables()` no sirve en las NT: toma cada resaltado como una celda.
    marks = [rect(451.2, 265.3, 517.2, 275.6, YELLOW), rect(451.2, 275.6, 510.0, 286.1, YELLOW)]

    assert grids(marks) == []


def test_a_frame_with_a_single_cell_is_not_a_grid() -> None:
    assert grids(borders([10.0, 90.0], [100.0, 140.0])) == []


def test_an_underlined_title_between_two_tables_is_not_a_row() -> None:
    # Las NT subrayan sus títulos, y el subrayado es un rectángulo igual de fino que un borde.
    drawn = borders([10.0, 50.0, 90.0], [100.0, 120.0])
    drawn += [rect(12.0, 160.0, 60.0, 160.5)]
    drawn += borders([10.0, 50.0, 90.0], [200.0, 220.0])

    assert [(g.top, len(g.rows)) for g in grids(drawn)] == [(100.25, 1), (200.25, 1)]


def test_a_cell_with_only_spaces_has_no_runs() -> None:
    assert runs_of([]) == []
    assert runs_of(chars("  ", 10, 100)) == []


def test_lines_join_by_the_explicit_space_at_the_end_of_the_line() -> None:
    # Word cierra el renglón con un espacio cuando el corte cae entre palabras (D-009).
    assert runs_of(chars("Nodo ", 10, 100) + chars("Padre ", 10, 112)) == [Run("Nodo Padre")]
    assert runs_of(chars("Grup", 10, 100) + chars("o ", 10, 112)) == [Run("Grupo")]


def test_a_wider_gap_between_lines_starts_a_new_paragraph() -> None:
    lines = chars("uno ", 10, 100) + chars("dos ", 10, 112) + chars("tres ", 10, 140)

    assert runs_of(lines) == [Run("uno dos\ntres")]


def test_a_highlight_marks_only_the_chars_it_covers() -> None:
    mark = rect(10.0, 100.0, 20.0, 110.0, YELLOW)

    def change_of(char: dict) -> Change | None:
        cx, cy = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
        inside = mark["x0"] <= cx <= mark["x1"] and mark["top"] <= cy <= mark["bottom"]
        return Change.MODIFIED if inside else None

    assert runs_of(chars("abcd", 10, 100), change_of) == [
        Run("ab", Change.MODIFIED),
        Run("cd"),
    ]


def test_normalized_ignores_case_accents_and_the_break_inside_a_label() -> None:
    assert normalized("Nodo Padre") == normalized("NodoPadre") == "nodopadre"
    assert normalized("Descripción") == "descripcion"


def test_header_labels_recognizes_the_domain_header() -> None:
    fields = Table(page=1, rows=[Row([Cell([Run(t)], header=True) for t in FIELD_TEXT])])

    assert header_labels(fields) == FIELD_HEADER
    assert header_labels(Table(page=1, rows=[Row([Cell([Run("otra cosa")])])])) is None


def test_anchor_gaps_reports_a_row_without_its_id() -> None:
    values = ("E8.2", "E735", "d", "d", "E730", "N", "1-1", "1-1", "obs")
    rows = [
        Row([Cell([Run(t)], header=True) for t in FIELD_TEXT]),
        Row([Cell([Run(t)]) for t in values]),
        Row([Cell([Run(t)]) for t in ("E8.2", "", *values[2:])]),
    ]

    assert anchor_gaps(Table(page=1, rows=rows)) == [2]


# ------------------------------------------------------------------- sobre los PDF reales

pytestmark = pytest.mark.skipif(not NOTES.exists(), reason="fuentes de las NT no copiadas")


@pytest.fixture(scope="module")
def nt013() -> Document:
    return extract_geometric(note("013"))


def tables(doc: Document) -> list[Table]:
    return [b for b in doc.blocks if isinstance(b, Table)]


def row_with(doc: Document, value: str) -> list[Cell]:
    """Primera fila cuya primera o segunda celda (grupo/ID, N° Val/ID) es `value`."""
    for table in tables(doc):
        for row in table.rows:
            if any(cell.text == value for cell in row.cells[:2]):
                return row.cells
    raise AssertionError(f"fila {value!r} no encontrada")


def test_field_row_e735_is_reconstructed_cell_by_cell(nt013: Document) -> None:
    cells = row_with(nt013, "E735")

    assert [c.text for c in cells] == [
        "E8.2",
        "E735",
        "dBasGravIVA",
        "Base gravada del IVA por ítem",
        "E730",
        "N",
        "1-15p(0-8)",
        "1-1",
        "Si E731 = 1 o 4 este campo es igual al resultado del cálculo:\n"
        "[100 * EA008 * E733] / [10000 + (E734 * E733)]\n"
        "Si E731 = 2 o 3 este campo es igual 0",
    ]
    assert [c.col for c in cells] == list(range(9))


def test_the_modified_observation_is_the_only_change_of_the_e735_row(nt013: Document) -> None:
    cells = row_with(nt013, "E735")

    assert [{run.change for run in c.runs} for c in cells[:8]] == [{None}] * 8
    assert {run.change for run in cells[8].runs} == {Change.MODIFIED}


def test_the_added_field_row_e737_is_marked_in_every_cell(nt013: Document) -> None:
    cells = row_with(nt013, "E737")

    assert [c.text for c in cells[:8]] == [
        "E8.2",
        "E737",
        "dBasExe",
        "Base Exenta por ítem",
        "E730",
        "N",
        "1-15p(0-8)",
        "1-1",
    ]
    for cell in cells:
        assert {run.change for run in cell.runs} == {Change.ADDED}, cell.text


def test_the_light_green_header_fill_is_not_a_change(nt013: Document) -> None:
    """(0.658824, 0.815686, 0.552941) es el fondo del encabezado de tabla, no un resaltado."""
    headers = [row for table in tables(nt013) for row in table.rows if row.cells[0].header]

    assert headers, "no se reconoció ningún encabezado"
    for row in headers:
        for cell in row.cells:
            assert {run.change for run in cell.runs} <= {None}, cell.text


def test_field_tables_are_recognized_by_their_header(nt013: Document) -> None:
    fields = [t for t in tables(nt013) if header_labels(t) == FIELD_HEADER]

    assert [t.page for t in fields] == [1, 1, 1]
    for table in fields:
        assert [c.text for c in table.rows[0].cells] == FIELD_TEXT
        assert all(c.header for c in table.rows[0].cells)
        assert not any(c.header for row in table.rows[1:] for c in row.cells)


def test_validation_row_283_is_reconstructed(nt013: Document) -> None:
    cells = row_with(nt013, "283")

    assert [c.text for c in cells[:4]] == [
        "283",
        "E737",
        "Error en el cálculo de la base exenta por ítem",
        "1921",
    ]
    assert cells[4].text == (
        "Cálculo de la base exenta por ítem incorrecto. "
        "Si E731 = 4 este campo es igual al resultado del cálculo: "
        "[100 * EA008 * (100 – E733)] / [10000 + (E734 * E733)] "
        "Si E731 = 1 , 2 o 3 este campo es igual 0"
    )
    assert cells[5].text == "R"


def test_validation_tables_of_nt013_keep_their_six_columns(nt013: Document) -> None:
    validations = [t for t in tables(nt013) if header_labels(t) == VALIDATION_HEADER]

    assert [t.page for t in validations] == [2, 2]
    for table in validations:
        assert [c.text for c in table.rows[0].cells] == [
            "N° Val",
            "ID",
            "Mensaje de la Validación",
            "Código",
            "Observación",
            "E",
        ]
    assert [c.text for c in row_with(nt013, "158")[:2]] == ["158", "E735a"]
    assert [c.text for c in row_with(nt013, "159")[:2]] == ["159", "E735b"]
    assert [c.text for c in row_with(nt013, "213")[:2]] == ["213", "F002a"]


def test_a_table_continued_from_the_previous_page_keeps_its_columns(nt013: Document) -> None:
    """F004 y F005 siguen la tabla de F002: la página 2 no repite el encabezado."""
    continued = [t for t in tables(nt013) if t.page == 2 and len(t.rows[0].cells) == 9]

    assert len(continued) == 1
    assert header_labels(continued[0]) is None
    assert [row.cells[1].text for row in continued[0].rows] == ["F004", "F005"]
    assert not any(c.header for row in continued[0].rows for c in row.cells)


def test_split_words_inside_a_narrow_cell_are_joined() -> None:
    """`EA004`+`a` y `dDescGloIt`+`em` se cortan sin espacio: son una sola palabra (D-009)."""
    doc = extract_geometric(note("001"))

    assert row_with(doc, "EA004a")[0].text == "EA004a"
    assert row_with(doc, "EA004")[2].text == "dDescGloItem"


def test_prose_between_tables_is_one_text_block(nt013: Document) -> None:
    texts = [b.text for b in nt013.blocks if isinstance(b, TextBlock)]

    assert (
        "1.1 En Campos que describen el IVA de la operación por ítem (E730-E739) se modifica el "
        "siguiente campo de Observaciones. (Página 90)"
    ) in texts


def test_the_repeated_nt_header_and_the_page_footer_are_artifacts() -> None:
    texts = [b.text for b in extract_geometric(note("012")).blocks if isinstance(b, TextBlock)]

    assert NT_HEADER not in texts
    assert "1" not in texts


@pytest.mark.parametrize("number", sorted(UNTAGGED))
@corpus_pdf.NEEDS_PDFTOTEXT
def test_v1_the_ir_loses_and_duplicates_nothing(number: str) -> None:
    pdf, pages = note(number), range(1, UNTAGGED[number] + 1)

    report = nt_text_conservation(extract_geometric(pdf), pdf, pages)

    assert set(report) == set(pages)
    for page, result in report.items():
        assert result.ok, (page, result.missing.most_common(10), result.extra.most_common(10))


@pytest.mark.parametrize("number", sorted(UNTAGGED))
def test_v6_the_highlights_of_the_ir_match_the_page(number: str) -> None:
    pdf, pages = note(number), range(1, UNTAGGED[number] + 1)

    report = color_conservation(extract_geometric(pdf), pdf, pages)

    for page, by_change in report.items():
        for change, result in by_change.items():
            assert result.ok, (page, change, result.missing, result.extra)


@pytest.mark.parametrize("number", sorted(UNTAGGED))
def test_every_recognized_row_has_its_own_id(number: str) -> None:
    recognized = [t for t in tables(extract_geometric(note(number))) if header_labels(t)]

    assert [anchor_gaps(t) for t in recognized] == [[] for _ in recognized]

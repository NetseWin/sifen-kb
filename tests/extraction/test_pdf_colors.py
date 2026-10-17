# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_colors.py), integrado en sifen-kb bajo MIT.
"""V6: los caracteres resaltados de la IR coinciden con los medidos sobre la página."""

import copy

import corpus_pdf
import pytest

from sifen_kb.pdf.colors import color_conservation, ir_marked_text, runs_by_page
from sifen_kb.pdf.ir import Cell, Change, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.tagged import extract_tagged
from sifen_kb.pdf.verify import compare_chars

MANUAL = corpus_pdf.MANUAL


def test_runs_are_split_between_the_pages_of_the_block() -> None:
    runs = [Run("ab", Change.ADDED), Run("cd"), Run("ef", Change.DELETED)]

    # "abcdef": el texto pasa a la pagina 8 tras "abc" y a la 9 tras "abcde".
    result = runs_by_page(runs, 7, [(3, 8), (5, 9)])

    assert result == {
        7: [Run("ab", Change.ADDED), Run("c")],
        8: [Run("d"), Run("e", Change.DELETED)],
        9: [Run("f", Change.DELETED)],
    }


def test_a_break_at_a_run_boundary_starts_the_next_page() -> None:
    result = runs_by_page([Run("ab", Change.MODIFIED), Run("cd")], 5, [(2, 6)])

    assert result == {5: [Run("ab", Change.MODIFIED)], 6: [Run("cd")]}


def test_ir_marked_text_groups_runs_by_page_and_change() -> None:
    doc = Document(
        "x.pdf",
        "0",
        "test",
        [
            TextBlock(
                page=1,
                role="P",
                runs=[Run("ab", Change.ADDED), Run("cd", Change.MODIFIED)],
                page_breaks=[(3, 2)],
            ),
            Table(page=2, rows=[Row([Cell([Run("E", Change.ADDED)]), Cell([Run("f")])])]),
        ],
    )

    assert ir_marked_text(doc) == {
        1: {Change.ADDED: "ab", Change.MODIFIED: "c", Change.DELETED: ""},
        2: {Change.ADDED: "E", Change.MODIFIED: "d", Change.DELETED: ""},
    }


def test_rows_of_a_merged_table_are_marked_on_their_own_page() -> None:
    # Tabla unida entre dos paginas (T-104): cada fila lleva su resaltado a su pagina.
    table = Table(
        page=1,
        rows=[
            Row([Cell([Run("A001", Change.ADDED)])], page=1),
            Row([Cell([Run("A002", Change.DELETED)])], page=2),
        ],
    )

    assert ir_marked_text(Document("x.pdf", "0", "test", [table])) == {
        1: {Change.ADDED: "A001", Change.MODIFIED: "", Change.DELETED: ""},
        2: {Change.ADDED: "", Change.MODIFIED: "", Change.DELETED: "A002"},
    }


def test_a_cell_split_between_pages_marks_each_half_on_its_page() -> None:
    # Fila partida y fusionada (T-104): `Cell.page_breaks` reparte los tramos de la celda.
    table = Table(
        page=1,
        rows=[
            Row(
                [
                    Cell(
                        [Run("uno\n", Change.DELETED), Run("dos", Change.DELETED)],
                        page_breaks=[(4, 2)],
                    ),
                    Cell([Run("solo en la 2", Change.MODIFIED)], page_breaks=[(0, 2)]),
                ],
                page=1,
            )
        ],
    )

    assert ir_marked_text(Document("x.pdf", "0", "test", [table])) == {
        1: {Change.ADDED: "", Change.MODIFIED: "", Change.DELETED: "uno\n"},
        2: {Change.ADDED: "", Change.MODIFIED: "solo en la 2", Change.DELETED: "dos"},
    }


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
@pytest.mark.parametrize(
    "pages, highlighted",
    [
        # La leyenda es texto negro ("Amarillo = modificaciones"): no lleva ningun rectangulo
        # de resaltado, asi que estas paginas controlan que la IR no invente marcas.
        (range(14, 16), False),
        (range(62, 67), True),  # tablas de campos: filas agregadas, eliminadas, resaltado parcial
        (range(151, 155), True),
        (range(163, 164), True),
    ],
)
def test_sample_pages_mark_exactly_the_highlighted_characters(pages: range, highlighted: bool) -> None:
    doc = extract_tagged(MANUAL, pages=pages)

    report = color_conservation(doc, MANUAL, pages)

    assert set(report) == set(pages)
    for page, by_change in report.items():
        for change, result in by_change.items():
            assert result.ok, (
                page,
                change,
                result.missing.most_common(10),
                result.extra.most_common(10),
            )
    # Sin diferencias, lo marcado en la IR es lo medido: comprobar que la muestra no es vacua.
    marked = ir_marked_text(doc)
    assert highlighted == any(text for by in marked.values() for text in by.values())


def _drop_first_change(doc: Document, change: Change) -> tuple[int, str]:
    """Quita la marca del primer tramo con `change`: simula un resaltado perdido."""
    for block in doc.blocks:
        if isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    for i, run in enumerate(cell.runs):
                        if run.change is change:
                            cell.runs[i] = Run(run.text, None)
                            return block.page, run.text
    raise AssertionError(f"la muestra no tiene tramos {change}")


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
def test_a_lost_highlight_in_the_ir_is_detected() -> None:
    doc = extract_tagged(MANUAL, pages=range(62, 67))
    altered = copy.deepcopy(doc)
    page, text = _drop_first_change(altered, Change.DELETED)

    report = color_conservation(altered, MANUAL, [page])

    diff = report[page][Change.DELETED]
    assert not diff.ok
    assert diff.missing == compare_chars(reference=text, candidate="").missing
    assert not diff.extra
    assert color_conservation(doc, MANUAL, [page])[page][Change.DELETED].ok

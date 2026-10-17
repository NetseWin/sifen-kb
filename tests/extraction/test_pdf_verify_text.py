# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_verify_text.py), integrado en sifen-kb bajo MIT.
"""V1: la IR conserva el texto de la página según un motor independiente (poppler)."""

from collections import Counter

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Block, Cell, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.tagged import extract_tagged
from sifen_kb.pdf.verify import SIFEN_FOOTER, compare_chars, ir_page_text, text_conservation

MANUAL = corpus_pdf.MANUAL


def test_ir_page_text_collects_text_blocks_and_cells() -> None:
    doc = Document(
        "x.pdf",
        "0",
        "test",
        [
            TextBlock(page=1, role="P", runs=[Run("Hola "), Run("mundo")]),
            Table(page=1, rows=[Row([Cell([Run("A1")]), Cell([Run("B")])])]),
            TextBlock(page=2, role="P", runs=[Run("otra")]),
        ],
    )

    assert ir_page_text(doc) == {1: "Hola mundo\nA1\nB", 2: "otra"}


def test_compare_ignores_whitespace_and_reports_both_directions() -> None:
    result = compare_chars(reference="ab c\nd", candidate="a b cc")

    assert result.missing == Counter({"d": 1})
    assert result.extra == Counter({"c": 1})
    assert not result.ok


def test_footer_pattern_matches_the_manual_footer() -> None:
    assert SIFEN_FOOTER.fullmatch("septiembre de 2019                     63")


def test_block_spanning_pages_is_attributed_to_its_page_range() -> None:
    blocks: list[Block] = [
        TextBlock(page=1, role="P", runs=[Run("ab"), Run("c")], page_breaks=[(2, 2)]),
        TextBlock(page=3, role="P", runs=[Run("d")]),
    ]

    assert ir_page_text(Document("x.pdf", "0", "test", blocks)) == {1: "ab", 2: "c", 3: "d"}


def test_rows_of_a_merged_table_are_attributed_to_their_own_page() -> None:
    # Tabla unida entre dos paginas (T-104): el encabezado y el cuerpo se reparten por fila.
    table = Table(
        page=1,
        rows=[
            Row([Cell([Run("ID")], header=True)], page=1),
            Row([Cell([Run("A001")])], page=1),
            Row([Cell([Run("A002")])], page=2),
        ],
    )

    assert ir_page_text(Document("x.pdf", "0", "test", [table])) == {1: "ID\nA001", 2: "A002"}


def test_a_cell_split_between_pages_is_attributed_to_both() -> None:
    # Fila partida por el borde de pagina y fusionada (T-104): la celda lleva `page_breaks`.
    table = Table(
        page=1,
        rows=[
            Row(
                [
                    Cell([Run("AC05")]),
                    Cell([Run("uno\ndos")], page_breaks=[(4, 2)]),
                    Cell([Run("solo en la 2")], page_breaks=[(0, 2)]),
                ],
                page=1,
            )
        ],
    )

    assert ir_page_text(Document("x.pdf", "0", "test", [table])) == {
        1: "AC05\nuno\n",
        2: "dos\nsolo en la 2",
    }


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
@pytest.mark.parametrize(
    "pages",
    [
        range(62, 67),  # tablas de campos
        range(21, 22),  # texto dentro de Figure (diagramas)
        range(29, 31),
        range(58, 59),
        range(197, 198),  # bloques que cruzan de pagina, verificados pagina a pagina
        range(198, 199),
        range(207, 211),
    ],
)
@corpus_pdf.NEEDS_PDFTOTEXT
def test_sample_pages_lose_and_duplicate_nothing(pages: range) -> None:
    doc = extract_tagged(MANUAL, pages=pages)

    report = text_conservation(doc, MANUAL, pages, artifacts=[SIFEN_FOOTER])

    assert set(report) == set(pages)
    for page, result in report.items():
        assert result.ok, (page, result.missing.most_common(10), result.extra.most_common(10))

# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_pipeline.py), integrado en sifen-kb bajo MIT.
"""Pipeline único: todos los productos salen del mismo documento procesado."""

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Table, TextBlock
from sifen_kb.pdf.pipeline import load

MANUAL = corpus_pdf.MANUAL

pytestmark = pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")


def test_a_row_split_across_pages_is_one_row() -> None:
    doc = load(MANUAL, range(153, 155))

    rows = [row for b in doc.blocks if isinstance(b, Table) for row in b.rows]
    ac05 = [row for row in rows if row.cells and row.cells[0].text == "AC05"]
    assert len(ac05) == 1
    assert "Problema en la LCR del certificado de firma" in [c.text for c in ac05[0].cells]
    assert not any(row.cells[0].text.startswith("Problema en la LCR") for row in rows)


def test_tables_continued_on_the_next_page_are_joined() -> None:
    tables = [b for b in load(MANUAL, range(62, 67)).blocks if isinstance(b, Table)]

    assert len(tables) < 9  # 9 tablas por pagina en el arbol


def test_sifen_rules_are_applied_only_when_asked() -> None:
    def headings(sifen: bool) -> list[str]:
        doc = load(MANUAL, range(62, 63), sifen=sifen)
        return [b.text for b in doc.blocks if isinstance(b, TextBlock) and b.level]

    assert "A. Campos firmados del Documento Electrónico (A001-A099)" in headings(True)
    assert headings(False) == []


def test_the_joined_row_covers_the_rows_its_second_half_spanned() -> None:
    # En la pagina 154 la mitad de AC05 abarca 2 filas ('• LCR inexistente' esta debajo): unida,
    # toda la fila AC05 debe abarcar esas 2 filas, no solo su celda 'Resultado'.
    doc = load(MANUAL, range(153, 155))

    rows = [row for b in doc.blocks if isinstance(b, Table) for row in b.rows]
    index = next(i for i, row in enumerate(rows) if row.cells and row.cells[0].text == "AC05")
    spans = {c.col: c.row_span for c in rows[index].cells}
    assert spans == {0: 2, 1: 2, 2: 2, 3: 1, 4: 2}
    assert [c.text for c in rows[index + 1].cells] == ["• LCR inexistente"]


NT013 = MANUAL.parent / "Notas_Tecnicas" / "NT_E_KUATIA_013_MT_V150.pdf"


@pytest.mark.skipif(not NT013.exists(), reason="fuente NT-013 no copiada")
def test_a_pdf_without_structure_tree_goes_through_the_geometric_route() -> None:
    doc = load(NT013)

    assert doc.extractor.startswith("geometry")
    ids = [row.cells[1].text for b in doc.blocks if isinstance(b, Table) for row in b.rows[1:]]
    assert "E735" in ids and "E737" in ids

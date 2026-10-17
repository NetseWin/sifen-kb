# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_sifen_sections.py), integrado en sifen-kb bajo MIT.
"""Títulos de grupo de la tabla de campos del MT V150 (LI/P) → encabezados."""

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Cell, Change, Document, Figure, Row, Run, Table, TextBlock
from sifen_kb.pdf.sifen.sections import promote_sections

MANUAL = corpus_pdf.MANUAL


def doc_of(*blocks: Table | TextBlock | Figure) -> Document:
    return Document("m.pdf", "abc123", "tagged/test", list(blocks))


def promoted(doc: Document) -> list[tuple[str, int | None]]:
    """(texto, nivel) de los bloques de texto que quedaron con encabezado."""
    return [(b.text, b.level) for b in doc.blocks if isinstance(b, TextBlock) and b.level]


def test_group_without_a_digit_becomes_level_2() -> None:
    doc = doc_of(
        TextBlock(page=62, role="LI", runs=[Run("AA. Campos del formato XML (AA001-AA009)")]),
        TextBlock(page=62, role="LI", runs=[Run("A. Campos firmados del DE (A001-A099)")]),
        TextBlock(page=66, role="P", runs=[Run("D. Campos Generales del DE (D001-D299)")]),
    )

    assert promoted(promote_sections(doc)) == [
        ("AA. Campos del formato XML (AA001-AA009)", 2),
        ("A. Campos firmados del DE (A001-A099)", 2),
        ("D. Campos Generales del DE (D001-D299)", 2),
    ]


def test_group_with_a_digit_becomes_level_3() -> None:
    doc = doc_of(
        TextBlock(page=66, role="P", runs=[Run("D1. Operación comercial (D010-D099)")]),
        TextBlock(page=97, role="P", runs=[Run("E10. Campos del transporte (E900-E999)")]),
    )

    assert promoted(promote_sections(doc)) == [
        ("D1. Operación comercial (D010-D099)", 3),
        ("E10. Campos del transporte (E900-E999)", 3),
    ]


def test_spacing_and_dash_variants_inside_the_range_are_accepted() -> None:
    # El PDF escribe el mismo rango de varias formas; los espacios y el guion largo son
    # tipografía del documento, no otra clase de título.
    doc = doc_of(
        TextBlock(page=161, role="P", runs=[Run("C. Campos del Timbrado (C001 - C099)")]),
        TextBlock(page=163, role="P", runs=[Run("D. Datos generales del DE (D001 – D299)")]),
        TextBlock(page=172, role="P", runs=[Run("E7. Condición de la operación (E600–E699)")]),
    )

    assert [level for _, level in promoted(promote_sections(doc))] == [2, 2, 3]


def test_deeper_subgroups_get_one_level_per_number() -> None:
    doc = doc_of(
        TextBlock(page=70, role="P", runs=[Run("D2.1 Actividad económica del emisor (D130-D139)")]),
        TextBlock(page=95, role="P", runs=[Run("E9.3.1. Póliza de seguros (EA790-EA799)")]),
        TextBlock(page=88, role="P", runs=[Run("E8.1.1 Campos del sector (EA001-EA050)")]),
    )

    assert promoted(promote_sections(doc)) == [
        ("D2.1 Actividad económica del emisor (D130-D139)", 4),
        ("E9.3.1. Póliza de seguros (EA790-EA799)", 5),
        ("E8.1.1 Campos del sector (EA001-EA050)", 5),
    ]


def test_blocks_that_do_not_match_the_whole_pattern_are_left_alone() -> None:
    doc = doc_of(
        TextBlock(page=62, role="LI", runs=[Run("• Campo obligatorio para todos los DE")]),
        TextBlock(page=62, role="LI", runs=[Run("A. algo sin rango")]),
        TextBlock(page=62, role="P", runs=[Run("TABLA DE FORMATO DE CAMPOS DEL DE")]),
        # El rango tiene que empezar con la letra del grupo.
        TextBlock(page=62, role="LI", runs=[Run("A. Campos firmados del DE (B001-B099)")]),
        # El rango de un subnivel tampoco puede cambiar de letra inicial.
        TextBlock(page=70, role="P", runs=[Run("D2.1 Actividad del emisor (F130-F139)")]),
        # Texto antes del prefijo de grupo, o rango que no cierra el bloque.
        TextBlock(page=62, role="P", runs=[Run("Ver A. Campos firmados del DE (A001-A099)")]),
        TextBlock(page=62, role="P", runs=[Run("A. Campos firmados (A001-A099) del DE")]),
        # Un título sin cuerpo no es un título.
        TextBlock(page=62, role="P", runs=[Run("A. (A001-A099)")]),
    )

    assert promoted(promote_sections(doc)) == []


def test_a_block_that_the_tree_already_declares_a_heading_keeps_its_level() -> None:
    # Si el árbol del PDF ya dijo el nivel, manda el árbol.
    runs = [Run("D. Campos del DE (D001-D299)")]
    doc = doc_of(TextBlock(page=62, role="H4", runs=runs, level=4))

    assert promoted(promote_sections(doc)) == [("D. Campos del DE (D001-D299)", 4)]


def test_promoted_block_keeps_its_runs_page_and_page_breaks() -> None:
    runs = [Run("A. Campos firmados del "), Run("DE (A001-A099)", Change.MODIFIED)]
    block = TextBlock(page=62, role="LI", runs=runs, page_breaks=[(10, 63)])

    result = promote_sections(doc_of(block)).blocks[0]

    assert isinstance(result, TextBlock)
    assert result.level == 2
    assert result.runs == runs
    assert (result.page, result.role, result.page_breaks) == (62, "LI", [(10, 63)])


def test_the_source_document_is_not_mutated() -> None:
    block = TextBlock(page=62, role="LI", runs=[Run("A. Campos firmados del DE (A001-A099)")])
    table = Table(page=62, rows=[Row([Cell([Run("ID")], header=True)])])
    figure = Figure(page=62, alt_text="diagrama")
    doc = doc_of(block, table, figure)

    result = promote_sections(doc)

    assert result is not doc
    assert result.blocks[0] is not block
    assert block.level is None
    assert [b.kind for b in result.blocks] == ["text", "table", "figure"]
    assert result.blocks[1] is table and result.blocks[2] is figure
    assert result.source == doc.source
    assert (result.sha256, result.extractor) == (doc.sha256, doc.extractor)


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
def test_the_six_group_titles_of_pages_62_to_66_become_headings() -> None:
    from sifen_kb.pdf.tagged import extract_tagged

    doc = extract_tagged(MANUAL, pages=range(62, 67))

    result = promote_sections(doc)

    headings = [(b.page, b.text, b.level) for b in result.blocks if isinstance(b, TextBlock) and b.level]
    assert headings == [
        (62, "AA. Campos que identifican el formato electrónico XML (AA001-AA009)", 2),
        (62, "A. Campos firmados del Documento Electrónico (A001-A099)", 2),
        (63, "B. Campos inherentes a la operación de Documentos Electrónicos (B001-B099)", 2),
        (64, "C. Campos de datos del Timbrado (C001-C099)", 2),
        (66, "D. Campos Generales del Documento Electrónico DE (D001-D299)", 2),
        (66, "D1. Campos inherentes a la operación comercial (D010-D099)", 3),
    ]
    assert all(b.level is None for b in doc.blocks if isinstance(b, TextBlock))

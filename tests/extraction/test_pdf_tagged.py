# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_tagged.py), integrado en sifen-kb bajo MIT.
"""T-102: IR desde el árbol de etiquetas del MT V150 (muestra páginas 62-66).

T-103 (columnas, combinaciones verticales y palabras partidas): páginas 75/85/88 y 151-154.

Orden de lectura y listas anidadas (H-1 de la auditoría): NT-023 páginas 1-3 y MT 29/121/207-210.
"""

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Change, Document, Figure, Table, TextBlock
from sifen_kb.pdf.tagged import extract_tagged

MANUAL = corpus_pdf.MANUAL
NT023 = corpus_pdf.NOTAS / "NT_E_KUATIA_023_MT_V150.pdf"
ISC_TITLE = "Tasas del ISC según Decretos N° 4344/04, N° 5158/10, N° 4693/15, N° 4693/15, N° 4694/15"
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
VALIDATION_HEADER = ["ID", "Resultado de validación", "Código", "Observación", "E"]
RANGE_HEADER = [
    "Inicio ID",
    "Inicio código de respuesta",
    "Fin ID",
    "Fin código de respuesta",
    "Tipo de Regla de Validación",
    "Apartado",
]

pytestmark = pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")


@pytest.fixture(scope="module")
def sample() -> Document:
    return extract_tagged(MANUAL, pages=range(62, 67))


@pytest.fixture(scope="module")
def validations() -> Document:
    """Validaciones AA01-AE04: filas de continuacion y una fila partida entre paginas."""
    return extract_tagged(MANUAL, pages=range(151, 155))


@pytest.fixture(scope="module")
def narrow() -> Document:
    """Celdas angostas que parten palabras: 'Longit ud' (p. 75), '1-15p(0- 8)' (p. 85 y 88)."""
    return extract_tagged(MANUAL, pages=[75, 85, 88])


# Orden de lectura de la muestra del MT (62-66): el arbol ya coincide con la pagina, asi que la
# regla de orden no debe moverla ni un bloque.
MANUAL_OUTLINE = [
    (62, "P", "TABLA DE FORMATO DE CAMPOS DE "),
    (62, "P", "Schema XML 18: DE_v150.xsd (Do"),
    (62, "LI", "AA. Campos que identifican el "),
    (62, "Table", "Grupo"),
    (62, "LI", "A. Campos firmados del Documen"),
    (62, "Table", "Grupo"),
    (63, "Table", "Grupo"),
    (63, "LI", "B. Campos inherentes a la oper"),
    (63, "Table", "Grupo"),
    (64, "Table", "Grupo"),
    (64, "LI", "C. Campos de datos del Timbrad"),
    (64, "Table", "Grupo"),
    (65, "Table", "Grupo"),
    (66, "LI", "D. Campos Generales del Docume"),
    (66, "Table", "Grupo"),
    (66, "P", "D1. Campos inherentes a la ope"),
    (66, "Table", "Grupo"),
]

# Orden impreso de la NT-023, cotejado con `pdftotext -layout -f 1 -l 3`: cada apartado introduce
# la tabla que le sigue, y el arbol los agrupa antes de las cuatro tablas (auditoria H-1).
NT023_OUTLINE = [
    (1, "P", "NOTA TÉCNICA N° 23"),
    (1, "P", "Fecha: 27/08/2024"),
    (1, "Table", "Fecha puesta a disposición par"),
    (1, "P", "Referencia: Correcciones y aju"),
    (1, "LI", "1. FORMATO DE CAMPOS XML"),
    (1, "LI", "1.1. En campos que identifican"),
    (1, "Table", "Grupo"),
    (1, "P", "Observación: Inclusión en cump"),
    (1, "LI", "1.2. En campos que describen l"),
    (1, "Table", "Grupo"),
    (2, "LI", "1.3. En el de Sector Energía E"),
    (2, "Table", "Grupo"),
    (2, "LI", "1.4. H. Campos que identifican"),
    (2, "Table", "Grupo"),
    (2, "P", "Observación: Inclusión opciona"),
    (2, "LI", "2. VALIDACIONES"),
    (2, "LI", "2.1. En datos que identifican "),
    (2, "Table", "ID"),
    (3, "LI", "2.2. H. Campos que identifican"),
    (3, "Table", "ID"),
    (3, "LI", "3. CODIFICACIONES"),
    (3, "P", "3. 1. Se amplía el listado de "),
    (3, "P", "TABLA 5 – CODIFICACIÓN DE UNID"),
    (3, "Table", "CODIFICACIÓN DE UNIDADES DE ME"),
]


def tables(doc: Document) -> list[Table]:
    return [b for b in doc.blocks if isinstance(b, Table)]


def outline(doc: Document) -> list[tuple[int, str, str]]:
    """Orden de lectura resumido: (pagina, etiqueta, inicio del texto) por bloque."""
    summary: list[tuple[int, str, str]] = []
    for block in doc.blocks:
        if isinstance(block, Table):
            summary.append((block.page, "Table", block.rows[0].cells[0].text[:30]))
        elif isinstance(block, Figure):
            summary.append((block.page, "Figure", (block.alt_text or "")[:30]))
        else:
            summary.append((block.page, block.role, block.text[:30]))
    return summary


def list_items(doc: Document) -> list[tuple[int, str]]:
    return [(b.page, b.text) for b in doc.blocks if isinstance(b, TextBlock) and b.role == "LI"]


def table_on(doc: Document, page: int, header: list[str]) -> Table:
    """Primera tabla de la pagina cuyo encabezado es `header`."""
    for table in tables(doc):
        if table.page == page and [c.text for c in table.rows[0].cells] == header:
            return table
    raise AssertionError(f"tabla {header[0]!r} de la pagina {page} no encontrada")


def row_by_id(doc: Document, field_id: str) -> list:
    for table in tables(doc):
        for row in table.rows:
            if len(row.cells) == 9 and row.cells[1].text == field_id:
                return row.cells
    raise AssertionError(f"fila {field_id} no encontrada")


def test_field_tables_keep_the_nine_column_header(sample: Document) -> None:
    field_tables = [t for t in tables(sample) if t.rows and len(t.rows[0].cells) == 9]

    assert field_tables, "no se extrajo ninguna tabla de campos"
    for table in field_tables:
        assert [c.text for c in table.rows[0].cells] == FIELD_HEADER
        assert all(c.header for c in table.rows[0].cells)


def test_deleted_row_is_marked_deleted_in_every_cell(sample: Document) -> None:
    cells = row_by_id(sample, "C009")

    assert [c.text for c in cells[:8]] == [
        "C",
        "C009",
        "dFeFinT",
        "Fecha fin de vigencia del timbrado",
        "C001",
        "F",
        "10",
        "1-1",
    ]
    assert cells[8].text.startswith("Formato AAAA-MM-DD")
    for cell in cells:
        assert {run.change for run in cell.runs} == {Change.DELETED}, cell.text


def test_added_row_is_marked_added(sample: Document) -> None:
    cells = row_by_id(sample, "C010")

    assert cells[2].text == "dSerieNum"
    assert all({r.change for r in c.runs} == {Change.ADDED} for c in cells)


def test_partial_highlight_is_kept_per_run(sample: Document) -> None:
    # B006 (pagina 64): texto previo sin marca + oracion agregada en verde.
    observation = row_by_id(sample, "B006")[8]

    assert [run.change for run in observation.runs] == [None, Change.ADDED]
    assert observation.runs[0].text.startswith("Esta información debe ser impresa en el")
    assert observation.runs[1].text.startswith("Cuando el tipo de documento es Nota de remisión")
    assert observation.runs[1].text.endswith("general Nro. 41/2014")


def test_fully_highlighted_cell_has_a_single_run(sample: Document) -> None:
    observation = row_by_id(sample, "A004")[8]

    assert [run.change for run in observation.runs] == [Change.MODIFIED]


def test_every_block_knows_its_page(sample: Document) -> None:
    assert sample.blocks
    assert {b.page for b in sample.blocks} <= set(range(62, 67))
    assert sample.sha256 and sample.source.endswith("Manual_Tecnico_SIFEN_V150.pdf")


def test_figure_keeps_the_text_drawn_inside_it() -> None:
    doc = extract_tagged(MANUAL, pages=[21])

    figures = [b for b in doc.blocks if isinstance(b, Figure)]
    assert any(f.text for f in figures), "los diagramas de la pagina 21 contienen texto"


def test_extraction_is_deterministic(sample: Document) -> None:
    again = extract_tagged(MANUAL, pages=range(62, 67))

    assert again.to_json() == sample.to_json()


def test_paragraphs_inside_a_cell_are_kept_as_line_breaks(sample: Document) -> None:
    # Cada parrafo de la celda es un P en el arbol: salto real, no ajuste de linea.
    assert row_by_id(sample, "B002")[8].text == "1= Normal\n2= Contingencia"
    assert row_by_id(sample, "B003")[8].text == "Referente al campo B002\n1= “Normal”\n2= “Contingencia”"


def test_list_label_and_body_stay_on_one_line(sample: Document) -> None:
    items = [b.text for b in sample.blocks if isinstance(b, TextBlock) and b.role == "LI"]

    assert "A. Campos firmados del Documento Electrónico (A001-A099)" in items
    assert all("\n" not in text for text in items)


def test_cell_bbox_covers_its_characters_and_empty_cells_have_none(validations: Document) -> None:
    table = table_on(validations, 151, VALIDATION_HEADER)
    aa01, aa02 = table.rows[1], table.rows[5]

    assert aa01.cells[0].text == "AA01"
    assert aa01.cells[0].bbox == pytest.approx((91.82, 634.99, 113.86, 643.99), abs=0.01)
    assert aa02.cells[3].text == ""
    assert aa02.cells[3].bbox is None


def test_full_rows_get_columns_by_index_without_geometry(sample: Document) -> None:
    field_tables = [t for t in tables(sample) if t.rows and len(t.rows[0].cells) == 9]

    assert field_tables
    for table in field_tables:
        for row in table.rows:
            assert [c.col for c in row.cells] == list(range(9))
            assert [c.row_span for c in row.cells] == [1] * 9


def test_continuation_rows_land_in_the_observation_column(validations: Document) -> None:
    # D-008: las combinaciones son verticales; la fila de continuacion trae solo *Observacion*.
    table = table_on(validations, 151, VALIDATION_HEADER)

    assert [c.col for c in table.rows[0].cells] == [0, 1, 2, 3, 4]
    assert [c.col for c in table.rows[1].cells] == [0, 1, 2, 3, 4]
    assert [[c.col for c in row.cells] for row in table.rows[2:5]] == [[3], [3], [3]]
    assert [c.text for row in table.rows[2:5] for c in row.cells] == [
        "Versión incorrecta",
        "No se aceptan certificados de la AC",
        "ExtendKeyUsage no define “ClientAuth“",
    ]


def test_absent_columns_extend_the_row_span_of_the_cell_above(validations: Document) -> None:
    table = table_on(validations, 151, VALIDATION_HEADER)

    assert [c.row_span for c in table.rows[0].cells] == [1, 1, 1, 1, 1]
    # AA01 cubre sus tres filas de continuacion; su propia *Observacion* no.
    assert [c.row_span for c in table.rows[1].cells] == [4, 4, 4, 1, 4]
    assert [c.row_span for row in table.rows[2:5] for c in row.cells] == [1, 1, 1]


def test_empty_cells_of_a_full_row_keep_their_column(validations: Document) -> None:
    # Tabla de rangos: la columna *Apartado* esta vacia en todas las filas.
    table = table_on(validations, 151, RANGE_HEADER)

    for row in table.rows[1:]:
        assert [c.col for c in row.cells] == [0, 1, 2, 3, 4, 5]
        assert row.cells[5].text == ""
        assert row.cells[5].bbox is None


def test_row_split_between_pages_keeps_its_geometric_columns(validations: Document) -> None:
    # La pagina 154 abre con la continuacion de AC05 (pagina 153): Resultado y Observacion.
    table = table_on(validations, 154, VALIDATION_HEADER)
    split = table.rows[1]

    assert [c.col for c in split.cells] == [1, 3]
    assert split.cells[0].text == "Problema en la LCR del certificado de firma"
    assert split.cells[1].text == "• Error en el acceso a la LCR"
    # Dentro de esta pagina, el Resultado cubre los dos renglones de Observacion.
    assert [c.row_span for c in split.cells] == [2, 1]


def test_a_row_with_its_own_id_never_extends_the_row_above(validations: Document) -> None:
    # AC05 (pagina 153) no trae Resultado: quedo en la pagina 154. La celda de AC04 no lo cubre.
    table = table_on(validations, 153, VALIDATION_HEADER)
    ac04, ac05 = table.rows[6], table.rows[9]

    assert ac04.cells[0].text == "AC04" and ac05.cells[0].text == "AC05"
    assert [c.row_span for c in ac04.cells] == [3, 3, 3, 1, 3]
    assert [c.col for c in ac05.cells] == [0, 2, 3, 4]
    assert [c.row_span for c in ac05.cells] == [1, 1, 1, 1]


def test_a_word_split_at_the_end_of_a_line_is_not_separated(validations: Document) -> None:
    # Word escribe un espacio explicito cuando el corte cae entre palabras; si no lo hay, la
    # palabra quedo partida (278 cortes sin espacio en el manual, todos dentro de una palabra).
    table = table_on(validations, 151, RANGE_HEADER)

    assert table.rows[1].cells[0].text == "GEC002\nGDE004"
    assert table.rows[1].cells[2].text == "GEC002c\nGDE008a"
    assert table.rows[2].cells[0].text == "GEI002"
    assert table.rows[7].cells[2].text == "GET030"


def test_narrow_cells_keep_their_ids_and_lengths_whole(narrow: Document) -> None:
    assert row_by_id(narrow, "E645")[6].text == "1-15p(0-4)"
    assert row_by_id(narrow, "E721")[6].text == "1-15p(0-8)"
    assert row_by_id(narrow, "E727")[6].text == "1-15p(0-8)"
    assert row_by_id(narrow, "E725")[6].text == "1-5p(0-4)"


def test_a_header_split_across_lines_is_one_word(narrow: Document) -> None:
    field_tables = [t for t in tables(narrow) if t.rows and len(t.rows[0].cells) == 9]

    assert len(field_tables) >= 2
    for table in field_tables:
        assert [c.text for c in table.rows[0].cells] == FIELD_HEADER


def test_wrapped_words_of_a_paragraph_stay_separated(validations: Document) -> None:
    paragraphs = [b.text for b in validations.blocks if isinstance(b, TextBlock)]

    assert (
        "Campo ID en las tablas de reglas de validación identifica a un código de validación de "
        "dos letras, conforme la secuencia AA, AB, AC,...las cuales a su vez corresponden a un "
        "tipo de validación específico." in paragraphs
    )
    table = table_on(validations, 151, VALIDATION_HEADER)
    assert table.rows[1].cells[1].text == "Certificado de Transmisor Inválido"


def test_a_title_row_is_not_the_header_of_its_table() -> None:
    # Pagina 213: la primera fila es el titulo de la tabla (una celda que abarca todo el ancho);
    # el encabezado real es 'Codigo | Porcentaje'.
    doc = extract_tagged(MANUAL, pages=[213])
    table = table_on(doc, 213, [ISC_TITLE])

    assert [c.text for c in table.rows[1].cells] == ["Código", "Porcentaje"]
    assert all(c.header for c in table.rows[1].cells)
    # El titulo conserva su celda en la primera columna y no combina nada hacia abajo.
    assert [c.col for c in table.rows[0].cells] == [0]
    assert [c.row_span for c in table.rows[0].cells] == [1]
    assert [c.col_span for c in table.rows[0].cells] == [2]
    assert [[c.col for c in row.cells] for row in table.rows[1:]] == [[0, 1]] * 13
    assert [c.text for c in table.rows[13].cells] == ["12", "38%"]


def test_a_title_row_hands_the_header_to_the_next_row_even_without_th() -> None:
    # Pagina 121: matriz de eventos sin ninguna celda TH; el titulo 'DTE' abarca las 5 columnas.
    doc = extract_tagged(MANUAL, pages=[121])
    table = table_on(doc, 121, ["DTE"])

    assert [c.col for c in table.rows[0].cells] == [0]
    assert [c.text for c in table.rows[1].cells][:2] == [
        "Notificación - Recepción",
        "Conformidad parcial",
    ]
    assert [[c.col for c in row.cells] for row in table.rows[1:]] == [[0, 1, 2, 3, 4]] * 7


def test_a_title_row_keeps_the_vertical_combinations_of_the_body() -> None:
    # Pagina 35, Tabla D: titulo, encabezado de 3 celdas y filas de continuacion sin *Formato*.
    doc = extract_tagged(MANUAL, pages=[35])
    table = table_on(doc, 35, ["Tabla D: Formatos numéricos"])

    assert [c.text for c in table.rows[1].cells] == ["Formato", "Para Informar", "Llenar campo con"]
    assert [[c.col for c in row.cells] for row in table.rows[:7]] == [
        [0],
        [0, 1, 2],
        [0, 1, 2],
        [1, 2],
        [1, 2],
        [1, 2],
        [1, 2],
    ]
    assert table.rows[2].cells[0].text == "0-11p0-6"
    assert [c.row_span for c in table.rows[2].cells] == [5, 1, 1]
    assert table.rows[7].cells[0].text == "0-11"
    assert [c.row_span for c in table.rows[7].cells] == [3, 1, 1]


def test_an_inner_title_row_does_not_steal_the_header() -> None:
    # Pagina 147: la fila 8 ('REFERENCIA ESTADO DE VALIDACION') tambien es un titulo de una sola
    # celda y es la unica fila con todas sus celdas TH; el encabezado sigue a la fila-titulo.
    doc = extract_tagged(MANUAL, pages=[147])
    table = table_on(doc, 147, ["GUIA DE REGLAS DE VALIDACIÓN"])

    assert table.rows[8].cells[0].text == "REFERENCIA ESTADO DE VALIDACIÓN"
    assert [c.text for c in table.rows[1].cells][0] == "N° VAL"
    assert [c.col for c in table.rows[1].cells] == [0, 1]
    assert [c.col for c in table.rows[12].cells] == [0, 1]


@pytest.mark.skipif(not NT023.exists(), reason="fuente NT-023 no copiada")
def test_the_unit_table_of_nt_023_gets_its_three_columns() -> None:
    # Tabla 5 de la NT-023: titulo 'CODIFICACION DE UNIDADES DE MEDIDA' sobre el encabezado real.
    doc = extract_tagged(NT023, pages=[3])
    table = table_on(doc, 3, ["CODIFICACIÓN DE UNIDADES DE MEDIDA"])

    assert [c.text for c in table.rows[1].cells] == ["Código", "Representación", "Descripción"]
    assert [c.col for c in table.rows[0].cells] == [0]
    assert [c.col_span for c in table.rows[0].cells] == [3]
    assert [[c.col for c in row.cells] for row in table.rows[1:]] == [[0, 1, 2]] * 27
    assert [c.text for c in table.rows[2].cells] == ["111", "4A", "Bovinas"]


def test_text_drawn_in_separate_boxes_of_a_figure_stays_separated() -> None:
    # En una Figure el texto viene de cuadros independientes: ahi el cambio de renglon si separa.
    doc = extract_tagged(MANUAL, pages=[21])

    figures = [b for b in doc.blocks if isinstance(b, Figure)]
    assert any("MARANGATU 2.0 Acceso y Autenticación" in f.text for f in figures)


@pytest.mark.skipif(not NT023.exists(), reason="fuente NT-023 no copiada")
def test_a_list_item_with_a_nested_list_is_not_a_single_block() -> None:
    # El arbol de la NT-023 mete `1.` y sus cuatro subapartados en un unico LI que cruza de
    # pagina: cada subitem tiene que ser su propio bloque, con la pagina donde se imprime.
    doc = extract_tagged(NT023, pages=[1, 2])

    assert list_items(doc) == [
        (1, "1. FORMATO DE CAMPOS XML"),
        (
            1,
            "1.1. En campos que identifican al receptor del Documento Electrónico DE "
            "(D200-D299) se modifican los siguientes campos: (Página 86)",
        ),
        (
            1,
            "1.2. En campos que describen los ítems de la operación (E700-E899) se modifica "
            "el siguiente campo en la Longitud. (Página 86)",
        ),
        (
            2,
            "1.3. En el de Sector Energía Eléctrica (E791-E799) se modifica el siguiente "
            "campo en la ocurrencia. (Página 93)",
        ),
        (
            2,
            "1.4. H. Campos que identifican al documento asociado (H001-H049) se incorpora "
            "el siguiente campo. (Página 110)",
        ),
        (2, "2. VALIDACIONES"),
        (
            2,
            "2.1. En datos que identifican al receptor del Documento Electrónico DE "
            "(D200 - D299) se modifica la siguiente validación. (Página 167)",
        ),
    ]
    # Ninguno cruza de pagina: el que cruzaba era el LI que los agrupaba.
    assert all(not b.page_breaks for b in doc.blocks if isinstance(b, TextBlock))


@pytest.mark.skipif(not NT023.exists(), reason="fuente NT-023 no copiada")
def test_reading_order_follows_the_page_when_the_tree_disagrees() -> None:
    doc = extract_tagged(NT023, pages=[1, 2, 3])

    assert outline(doc) == NT023_OUTLINE


def test_the_manual_sample_keeps_the_order_of_its_tree(sample: Document) -> None:
    assert outline(sample) == MANUAL_OUTLINE


def test_blocks_side_by_side_keep_the_order_of_the_tree() -> None:
    # Pagina 121: dos matrices de eventos una al lado de la otra (x 263-680 y x 72-233) con sus
    # tops a 0,2 pt. La geometria no dice cual se lee primero: manda el arbol.
    doc = extract_tagged(MANUAL, pages=[121])

    assert [t.rows[0].cells[0].text for t in tables(doc)] == ["DTE", "DE", "Grupo"]


def test_a_footnote_is_read_where_it_is_printed() -> None:
    # Pagina 29: el arbol pone la nota al pie como primer bloque de la pagina; se imprime en
    # y=761, debajo de todo lo demas.
    doc = extract_tagged(MANUAL, pages=[29])

    notes = [b for b in doc.blocks if isinstance(b, TextBlock) and b.role == "Note"]
    assert len(notes) == 1
    assert doc.blocks[-1] is notes[0]
    assert notes[0].text.startswith("1 https://es.wikipedia.org/wiki/Extensible_Markup_Language")


def test_the_steps_of_a_nested_list_get_their_own_page_and_place() -> None:
    # Paginas 207-210: el mismo defecto que la NT-023 dentro del MT. Los cinco pasos de 13.8.4
    # venian en un solo LI atribuido a la pagina 207.
    doc = extract_tagged(MANUAL, pages=range(207, 211))

    steps = [(p, t) for p, t in list_items(doc) if t.startswith("13.8.4.")]
    assert steps == [
        (208, "13.8.4.1. Paso 1 - Concatenar los datos:"),
        (
            208,
            "13.8.4.2. Paso 2 – Concatenar al final de los datos, del paso 1, el Código "
            "Secreto del Contribuyente:",
        ),
        (209, "13.8.4.3. Paso 3 – Generar el Hash con los datos del paso 2:"),
        (209, "13.8.4.4. Paso 4 – Generar la URL para la imagen QR:"),
        (210, "13.8.4.5. Paso 5 – Insertar la URL del paso 4 en el XML:"),
    ]
    # Cada paso queda antes de la tabla que lo ilustra, no todos antes del cuadro de la 207.
    kinds = [(b.page, b.kind) for b in doc.blocks]
    assert kinds.index((208, "text")) < kinds.index((208, "table"))

# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_continuity.py), integrado en sifen-kb bajo MIT.
"""T-104: unir las tablas que Word corta en cada página repitiendo el encabezado."""

import copy

import corpus_pdf
import pytest

from sifen_kb.pdf.colors import color_conservation
from sifen_kb.pdf.continuity import continuation_stats, merge_continued_tables
from sifen_kb.pdf.ir import Cell, Change, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.tagged import extract_tagged
from sifen_kb.pdf.verify import SIFEN_FOOTER, ir_page_text, text_conservation

MANUAL = corpus_pdf.MANUAL


def _header(*texts: str) -> Row:
    return Row([Cell([Run(t)], header=True) for t in texts])


def _body(*texts: str, page: int | None = None) -> Row:
    return Row([Cell([Run(t)]) for t in texts], page=page)


def _doc(*blocks: Table | TextBlock) -> Document:
    return Document("x.pdf", "0", "test", list(blocks))


def _texts(table: Table) -> list[list[str]]:
    return [[cell.text for cell in row.cells] for row in table.rows]


def _id_of(row: Row) -> str:
    return row.cells[0].text if row.cells else ""


def test_the_repeated_header_is_dropped_and_every_row_keeps_its_page() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("ID", "Campo"), _body("A001", "rDE")]),
        Table(page=8, rows=[_header("ID", "Campo"), _body("A002", "dVerFor")]),
    )

    merged = merge_continued_tables(doc)

    assert len(merged.blocks) == 1
    table = merged.blocks[0]
    assert isinstance(table, Table)
    assert table.page == 7
    assert _texts(table) == [["ID", "Campo"], ["A001", "rDE"], ["A002", "dVerFor"]]
    assert [row.page for row in table.rows] == [7, 7, 8]


def test_the_original_document_is_not_mutated() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        Table(page=8, rows=[_header("ID"), _body("A002")]),
    )
    before = copy.deepcopy(doc)

    merge_continued_tables(doc)

    assert doc == before


def test_a_block_between_the_tables_prevents_the_merge() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        TextBlock(page=8, role="P", runs=[Run("Un párrafo")]),
        Table(page=8, rows=[_header("ID"), _body("A002")]),
    )

    merged = merge_continued_tables(doc)

    assert [block.kind for block in merged.blocks] == ["table", "text", "table"]
    assert continuation_stats(doc).separated_candidates == [(7, 8)]


def test_a_different_header_prevents_the_merge() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("ID", "Campo"), _body("A001", "rDE")]),
        Table(page=8, rows=[_header("ID", "Obs."), _body("A002", "dVerFor")]),
    )

    assert len(merge_continued_tables(doc).blocks) == 2


def test_a_table_without_a_header_row_is_never_merged() -> None:
    doc = _doc(
        Table(page=7, rows=[_body("A001")]),
        Table(page=8, rows=[_body("A002")]),
    )

    assert len(merge_continued_tables(doc).blocks) == 2


def test_a_continuation_with_only_the_repeated_header_is_not_merged() -> None:
    """Hay tablas cuyas filas son todas `TH` (páginas 208-214): sin cuerpo que aportar, unirlas
    sería descartar la tabla entera como "encabezado repetido"."""
    doc = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        Table(page=8, rows=[_header("ID")]),
    )

    assert len(merge_continued_tables(doc).blocks) == 2


def test_only_the_next_page_continues_a_table() -> None:
    same = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        Table(page=7, rows=[_header("ID"), _body("A002")]),
    )
    skipped = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        Table(page=9, rows=[_header("ID"), _body("A002")]),
    )

    assert len(merge_continued_tables(same).blocks) == 2
    assert len(merge_continued_tables(skipped).blocks) == 2


def test_a_chain_of_three_pages_becomes_one_table() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        Table(page=8, rows=[_header("ID"), _body("A002")]),
        Table(page=9, rows=[_header("ID"), _body("A003")]),
    )

    merged = merge_continued_tables(doc)

    assert len(merged.blocks) == 1
    table = merged.blocks[0]
    assert isinstance(table, Table)
    assert _texts(table) == [["ID"], ["A001"], ["A002"], ["A003"]]
    assert [row.page for row in table.rows] == [7, 7, 8, 9]


def test_a_title_row_above_the_header_is_part_of_the_header() -> None:
    """La NT trae tablas con un título de una sola celda sobre el encabezado real."""
    title = Row([Cell([Run("CODIFICACIÓN DE UNIDADES DE MEDIDA")], header=True)])
    doc = _doc(
        Table(page=7, rows=[title, _header("ID", "Campo"), _body("A001", "rDE")]),
        Table(page=8, rows=[copy.deepcopy(title), _header("ID", "Campo"), _body("A002", "dVer")]),
    )

    merged = merge_continued_tables(doc)

    table = merged.blocks[0]
    assert isinstance(table, Table)
    assert _texts(table) == [
        ["CODIFICACIÓN DE UNIDADES DE MEDIDA"],
        ["ID", "Campo"],
        ["A001", "rDE"],
        ["A002", "dVer"],
    ]


def test_a_different_title_row_prevents_the_merge() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("TABLA 4"), _header("ID"), _body("A001")]),
        Table(page=8, rows=[_header("TABLA 5"), _header("ID"), _body("A002")]),
    )

    assert len(merge_continued_tables(doc).blocks) == 2


def _with_cols(cells: list[tuple[int, str]], page: int | None = None) -> Row:
    return Row([Cell([Run(text)], col=col) for col, text in cells], page=page)


def test_a_row_split_between_pages_is_joined_cell_by_cell() -> None:
    """Forma real de AC05 (página 153): la fila sigue en la 154 sin la celda de la columna 0."""
    header = Row([Cell([Run(t)], header=True, col=i) for i, t in enumerate("IRCOE")])
    doc = _doc(
        Table(
            page=153,
            rows=[header, _with_cols([(0, "AC05"), (2, "0124"), (3, "• Dirección"), (4, "R")])],
        ),
        Table(
            page=154,
            rows=[copy.deepcopy(header), _with_cols([(1, "Problema en la LCR"), (3, "• Error")])],
        ),
    )

    merged = merge_continued_tables(doc)

    table = merged.blocks[0]
    assert isinstance(table, Table)
    assert _texts(table) == [
        ["I", "R", "C", "O", "E"],
        ["AC05", "Problema en la LCR", "0124", "• Dirección\n• Error", "R"],
    ]
    assert [cell.col for cell in table.rows[1].cells] == [0, 1, 2, 3, 4]
    assert [row.page for row in table.rows] == [153, 153]
    assert continuation_stats(doc).split_rows == 1


def test_the_joined_cell_keeps_the_runs_of_both_parts() -> None:
    header = Row([Cell([Run("ID")], header=True, col=0), Cell([Run("Obs")], header=True, col=1)])
    first = Row([Cell([Run("AC05")], col=0), Cell([Run("uno", Change.ADDED)], col=1)])
    second = Row([Cell([Run("dos", Change.DELETED)], col=1)])
    doc = _doc(
        Table(page=1, rows=[header, first]),
        Table(page=2, rows=[copy.deepcopy(header), second]),
    )

    table = merge_continued_tables(doc).blocks[0]

    assert isinstance(table, Table)
    assert table.rows[1].cells[1].runs == [
        Run("uno", Change.ADDED),
        Run("\n"),
        Run("dos", Change.DELETED),
    ]


def test_a_continuation_starting_at_column_zero_is_a_new_row() -> None:
    header = Row([Cell([Run("ID")], header=True, col=0), Cell([Run("Obs")], header=True, col=1)])
    doc = _doc(
        Table(page=1, rows=[header, _with_cols([(0, "AC05"), (1, "uno")])]),
        Table(page=2, rows=[copy.deepcopy(header), _with_cols([(0, "AC06"), (1, "dos")])]),
    )

    table = merge_continued_tables(doc).blocks[0]

    assert isinstance(table, Table)
    assert _texts(table) == [["ID", "Obs"], ["AC05", "uno"], ["AC06", "dos"]]
    assert continuation_stats(doc).split_rows == 0


def test_without_inferred_columns_a_split_row_is_left_alone() -> None:
    """`col=None` = no hay información de columna: se une la tabla, no se inventa la fila."""
    doc = _doc(
        Table(page=1, rows=[_header("ID", "Obs"), _body("AC05", "uno")]),
        Table(page=2, rows=[_header("ID", "Obs"), _body("dos")]),
    )

    merged = merge_continued_tables(doc)
    table = merged.blocks[0]

    assert isinstance(table, Table)
    assert _texts(table) == [["ID", "Obs"], ["AC05", "uno"], ["dos"]]
    stats = continuation_stats(doc)
    assert stats.split_rows == 0
    assert stats.unknown_columns == [(1, 2)]


def test_a_joined_split_row_keeps_each_half_on_its_own_page() -> None:
    """`Cell.page_breaks` (como en `TextBlock`) reparte la celda fusionada entre sus dos páginas.

    El `\\n` que separa las dos mitades cierra la primera: queda en su página.
    """
    header = Row([Cell([Run("ID")], header=True, col=0), Cell([Run("Obs")], header=True, col=1)])
    doc = _doc(
        Table(page=1, rows=[header, _with_cols([(0, "AC05"), (1, "uno")])]),
        Table(page=2, rows=[copy.deepcopy(header), _with_cols([(1, "dos")])]),
    )

    merged = merge_continued_tables(doc)

    assert ir_page_text(merged) == {1: "ID\nObs\nAC05\nuno\n", 2: "dos"}


def test_the_joined_cell_records_the_offset_where_its_second_half_starts() -> None:
    """El salto va donde empieza la mitad de la página siguiente, tras el `\\n` que las separa."""
    header = Row([Cell([Run("ID")], header=True, col=0), Cell([Run("Obs")], header=True, col=1)])
    doc = _doc(
        Table(page=1, rows=[header, _with_cols([(0, "AC05"), (1, "uno")])]),
        Table(page=2, rows=[copy.deepcopy(header), _with_cols([(1, "dos")])]),
    )

    table = merge_continued_tables(doc).blocks[0]

    assert isinstance(table, Table)
    cells = table.rows[1].cells
    assert cells[1].text == "uno\ndos"
    assert cells[1].page_breaks == [(4, 2)]  # "uno\n" son 4 caracteres
    assert cells[0].page_breaks == []  # la celda de ID no cruza de página
    assert [row.page for row in table.rows] == [1, 1]


def test_a_cell_that_only_exists_in_the_second_half_belongs_to_the_next_page() -> None:
    """Como `Problema en la LCR...` de AC05: la columna se imprime solo en la página 154."""
    header = Row([Cell([Run(t)], header=True, col=i) for i, t in enumerate("IRO")])
    doc = _doc(
        Table(page=153, rows=[header, _with_cols([(0, "AC05"), (2, "• Dirección")])]),
        Table(
            page=154,
            rows=[copy.deepcopy(header), _with_cols([(1, "Problema"), (2, "• Error")])],
        ),
    )

    table = merge_continued_tables(doc).blocks[0]

    assert isinstance(table, Table)
    cells = {cell.col: cell for cell in table.rows[1].cells}
    assert cells[1].page_breaks == [(0, 154)]  # entera en la página siguiente
    assert ir_page_text(merge_continued_tables(doc)) == {
        153: "I\nR\nO\nAC05\n• Dirección\n",
        154: "Problema\n• Error",
    }


def test_a_chain_of_three_pages_shifts_the_offsets_of_each_join() -> None:
    header = Row([Cell([Run("ID")], header=True, col=0), Cell([Run("Obs")], header=True, col=1)])
    doc = _doc(
        Table(page=1, rows=[header, _with_cols([(0, "AC05"), (1, "uno")])]),
        Table(page=2, rows=[copy.deepcopy(header), _with_cols([(1, "dos")])]),
        Table(page=3, rows=[copy.deepcopy(header), _with_cols([(1, "tres")])]),
    )

    table = merge_continued_tables(doc).blocks[0]

    assert isinstance(table, Table)
    cell = table.rows[1].cells[1]
    assert cell.text == "uno\ndos\ntres"
    assert cell.page_breaks == [(4, 2), (8, 3)]
    assert ir_page_text(merge_continued_tables(doc)) == {
        1: "ID\nObs\nAC05\nuno\n",
        2: "dos\n",
        3: "tres",
    }


def test_a_repeated_column_in_a_row_is_too_ambiguous_to_join() -> None:
    header = Row([Cell([Run("ID")], header=True, col=0), Cell([Run("Obs")], header=True, col=1)])
    doc = _doc(
        Table(page=1, rows=[header, _with_cols([(0, "AC05"), (1, "uno")])]),
        Table(page=2, rows=[copy.deepcopy(header), _with_cols([(1, "dos"), (1, "tres")])]),
    )

    table = merge_continued_tables(doc).blocks[0]

    assert isinstance(table, Table)
    assert _texts(table) == [["ID", "Obs"], ["AC05", "uno"], ["dos", "tres"]]


def test_stats_count_the_tables_before_and_after() -> None:
    doc = _doc(
        Table(page=7, rows=[_header("ID"), _body("A001")]),
        Table(page=8, rows=[_header("ID"), _body("A002")]),
        TextBlock(page=8, role="P", runs=[Run("x")]),
        Table(page=9, rows=[_header("Otro"), _body("B001")]),
    )

    stats = continuation_stats(doc)

    assert (stats.tables_before, stats.tables_after, stats.merges) == (3, 2, 1)
    assert stats.dropped_header_rows == 1
    assert stats.dropped_text == {8: "ID"}
    assert stats.separated_candidates == []


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
def test_the_sample_pages_lose_three_repeated_headers() -> None:
    doc = extract_tagged(MANUAL, pages=range(62, 67))

    stats = continuation_stats(doc)

    assert (stats.tables_before, stats.tables_after) == (9, 6)
    assert (stats.merges, stats.dropped_header_rows) == (3, 3)
    assert sorted(stats.dropped_text) == [63, 64, 65]


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
def test_the_row_ac05_split_between_pages_153_and_154_is_joined() -> None:
    """Única fila partida del manual: AC05 sigue en la 154 sin su celda de ID."""
    original = extract_tagged(MANUAL, pages=range(153, 155))
    doc = merge_continued_tables(original)

    rows = [r for b in doc.blocks if isinstance(b, Table) for r in b.rows if _id_of(r) == "AC05"]

    assert continuation_stats(original).split_rows == 1
    assert len(rows) == 1
    assert [cell.text for cell in rows[0].cells] == [
        "AC05",
        "Problema en la LCR del certificado de firma",
        "0124",
        "• Dirección de la LCR no informada\n(CRLDistributionPoint)\n• Error en el acceso a la LCR",
        "R",
    ]


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
@corpus_pdf.NEEDS_PDFTOTEXT
def test_joining_the_split_row_conserves_text_and_colors_page_by_page() -> None:
    """Al fusionar AC05, lo que imprime la 154 sigue atribuido a la 154: `Cell.page_breaks`."""
    pages = range(153, 155)
    original = extract_tagged(MANUAL, pages=pages)
    stats = continuation_stats(original)
    doc = merge_continued_tables(original)

    text = text_conservation(doc, MANUAL, pages, artifacts=[SIFEN_FOOTER], dropped_text=stats.dropped_text)
    colors = color_conservation(doc, MANUAL, pages)

    for page, result in text.items():
        assert result.ok, (page, result.missing.most_common(10), result.extra.most_common(10))
    for page, by_change in colors.items():
        for change, result in by_change.items():
            assert result.ok, (page, change, result.missing.most_common(10))


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
def test_the_part_of_ac05_printed_on_page_154_is_attributed_to_it() -> None:
    doc = merge_continued_tables(extract_tagged(MANUAL, pages=range(153, 155)))

    page_text = ir_page_text(doc)

    assert "• Error en el acceso a la LCR" in page_text[154]
    assert "• Error en el acceso a la LCR" not in page_text[153]
    assert "Problema en la LCR del certificado de firma" in page_text[154]
    assert "• Dirección de la LCR no informada" in page_text[153]


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
@corpus_pdf.NEEDS_PDFTOTEXT
def test_declaring_the_dropped_headers_does_not_blind_v1_to_a_lost_row() -> None:
    pages = range(62, 64)
    original = extract_tagged(MANUAL, pages=pages)
    stats = continuation_stats(original)
    doc = merge_continued_tables(original)
    table = next(b for b in doc.blocks if isinstance(b, Table) and b.rows[-1].page == 63)
    del table.rows[-1]  # una fila de cuerpo de la 63, ademas del encabezado declarado

    report = text_conservation(doc, MANUAL, pages, artifacts=[SIFEN_FOOTER], dropped_text=stats.dropped_text)

    assert report[62].ok
    assert not report[63].ok


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
@corpus_pdf.NEEDS_PDFTOTEXT
def test_the_merged_sample_still_conserves_text_and_colors() -> None:
    pages = range(62, 67)
    original = extract_tagged(MANUAL, pages=pages)
    stats = continuation_stats(original)
    doc = merge_continued_tables(original)

    # Lo unico que la union quita de la IR son los encabezados repetidos, y se declaran: si se
    # perdiera una fila de cuerpo (tomada por encabezado), V1 lo marcaria igual.
    text = text_conservation(doc, MANUAL, pages, artifacts=[SIFEN_FOOTER], dropped_text=stats.dropped_text)
    colors = color_conservation(doc, MANUAL, pages)

    for page, result in text.items():
        assert result.ok, (page, result.missing.most_common(10), result.extra.most_common(10))
    for page, by_change in colors.items():
        for change, result in by_change.items():
            assert result.ok, (page, change, result.missing.most_common(10))


# --- T-206 / D-014: continuaciones sin encabezado repetido etiquetado ----------------------------

NOTES = corpus_pdf.NOTAS


def _placed(*texts: str, page: int | None = None, header: bool = False) -> Row:
    return Row([Cell([Run(t)] if t else [], header=header, col=i) for i, t in enumerate(texts)], page=page)


def _boxed(texts: list[str], bottoms: list[float], lefts: list[float], rights: list[float]) -> Row:
    return Row(
        [
            Cell([Run(t)], col=i, bbox=(lefts[i], bottoms[i] - 10, rights[i], bottoms[i]))
            for i, t in enumerate(texts)
        ]
    )


def test_a_continuation_without_repeated_header_joins_the_table_of_the_previous_page() -> None:
    # MT págs. 158-159: BO02 al pie, BO03 arriba de la página siguiente, sin encabezado.
    doc = _doc(
        Table(page=158, rows=[_placed("ID", "Código", header=True), _placed("BO02", "0501")]),
        Table(page=159, rows=[_placed("BO03", "0502")]),
    )

    [table] = merge_continued_tables(doc).blocks

    assert isinstance(table, Table)
    assert _texts(table) == [["ID", "Código"], ["BO02", "0501"], ["BO03", "0502"]]
    assert [row.page for row in table.rows] == [158, 158, 159]


def test_nt_tables_whose_header_is_tagged_as_body_are_joined_too() -> None:
    # NT-001 págs. 1-2: el autor etiquetó "Grupo | ID…" como TD.
    doc = _doc(
        Table(page=1, rows=[_placed("ID", "Campo"), _placed("F033", "dTotDescGlotem")]),
        Table(page=2, rows=[_placed("F034", "dTotAntItem")]),
    )

    assert len(merge_continued_tables(doc).blocks) == 1


def test_an_untagged_repeated_header_is_dropped_and_declared() -> None:
    # MT págs. 55-56: "ID | Campo | …" se repite en la página siguiente como fila común.
    doc = _doc(
        Table(page=55, rows=[_placed("ID", "Campo"), _placed("RRSch03", "dMsgRes")]),
        Table(page=56, rows=[_placed("ID", "Campo"), _placed("RRSch04", "xContRUC")]),
    )

    [table] = merge_continued_tables(doc).blocks
    stats = continuation_stats(doc)

    assert _texts(table) == [["ID", "Campo"], ["RRSch03", "dMsgRes"], ["RRSch04", "xContRUC"]]
    assert stats.dropped_text == {56: "ID\nCampo"}


def test_a_table_of_different_width_on_the_next_page_is_not_joined() -> None:
    doc = _doc(
        Table(page=59, rows=[_placed("A", "B"), _placed("1", "2")]),
        Table(page=60, rows=[_placed("x", "y", "z")]),
    )

    assert len(merge_continued_tables(doc).blocks) == 2


def test_a_lone_fragment_continues_the_cell_that_overflowed_the_page() -> None:
    # NT-016 págs. 1-2: la observación de XS06 sigue arriba de la página 2 en una celda suelta.
    last = _boxed(
        ["XS06", "A", "Atributos válidos: rsa-sha256"],
        [732, 732, 760],
        [75, 191, 328],
        [93, 234, 528],
    )
    fragment = Row([Cell([Run("rsa-sha384 rsa-sha512")], col=0, col_span=3, bbox=(328, 159, 506, 212))])
    doc = _doc(
        Table(page=1, rows=[_placed("ID", "Tipo", "Observaciones", header=True), last]),
        Table(page=2, rows=[fragment, _placed("XS07", "G", "Grupo de referencia")]),
    )

    [table] = merge_continued_tables(doc).blocks

    assert _texts(table)[1] == ["XS06", "A", "Atributos válidos: rsa-sha256\nrsa-sha384 rsa-sha512"]
    assert _texts(table)[2] == ["XS07", "G", "Grupo de referencia"]


def test_a_title_row_is_not_glued_to_a_cell_that_did_not_overflow() -> None:
    # MT págs. 118-119: "Evento conclusivo" cae en la columna 1, pero en la fila 12 la celda que
    # llega más abajo es otra: es un título de grupo, no la continuación de una celda.
    last = _boxed(["12", "Registro", "WS Sincrónico"], [492, 500, 509], [46, 176, 221], [57, 216, 284])
    title = Row([Cell([Run("Evento conclusivo")], col=0, col_span=3, bbox=(176, 124, 214, 142))])
    doc = _doc(
        Table(page=118, rows=[_placed("N°", "Tipo", "Transmisión", header=True), last]),
        Table(page=119, rows=[title, _placed("13", "Registro", "WS")]),
    )

    [table] = merge_continued_tables(doc).blocks

    assert _texts(table)[2] == ["Evento conclusivo"]


@pytest.mark.skipif(not NOTES.exists(), reason="NT no copiadas")
@pytest.mark.parametrize(
    ("nt", "key", "fragment"),
    [("016", "XS06", "rsa-sha512"), ("019", "GDI002c", "15 días")],
)
def test_real_nt_rows_split_between_pages_keep_their_whole_observation(
    nt: str, key: str, fragment: str
) -> None:
    from sifen_kb.pdf.pipeline import load

    doc = load(next(NOTES.glob(f"*_{nt}_*.pdf")))
    rows = [r for b in doc.blocks if isinstance(b, Table) for r in b.rows]
    [row] = [r for r in rows if r.cells and r.cells[0].text.strip() == key]

    assert fragment in " ".join(c.text for c in row.cells).replace("\n", " ")

# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""T-104 — continuidad de tablas entre páginas.

Word corta cada tabla en el borde de página y repite el encabezado: en el árbol de etiquetas hay
una tabla por página y ninguna cruza de página. Una IA que lee el Markdown ve la misma tabla de
campos empezando de cero en cada página.

`merge_continued_tables` devuelve un documento nuevo con esas tablas unidas. Es deliberadamente
conservador: solo une tablas **contiguas** en `Document.blocks` (si hay un bloque en medio no une,
aunque el encabezado coincida) y solo si la segunda empieza en la página siguiente. Los casos que
descarta se cuentan en `continuation_stats` para poder revisarlos.

Encabezado = las **filas iniciales cuyas celdas son todas `header=True`**. Así entran los títulos
de tabla de una sola celda (p. ej. "CODIFICACIÓN DE UNIDADES DE MEDIDA" en las NT) y los
encabezados de dos filas; y quedan fuera las filas de cuerpo de las tablas de campos, cuya primera
celda ("Grupo") es un `TH` pero las demás no. Se comparan **todas** esas filas, celda a celda.

Al fusionar una fila partida (`_join_rows`), la mitad que venía de la página siguiente se declara
en `Cell.page_breaks` (igual que en `TextBlock`): V1 y V6 reparten la celda entre sus páginas y el
render pone la marca `<!-- pdf_page: N -->` dentro de la celda, en el salto. Así la observación que
el PDF imprime en la página siguiente se cita con su página. En el manual completo ocurre una sola
vez (AC05, páginas 153-154).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from sifen_kb.pdf.ir import Block, Cell, Document, Row, Run, Table


@dataclass(frozen=True)
class MergeStats:
    """Qué unió y qué dejó pasar el algoritmo, para medirlo sobre el documento completo."""

    tables_before: int = 0
    tables_after: int = 0
    merges: int = 0
    dropped_header_rows: int = 0
    split_rows: int = 0
    # Texto de los encabezados repetidos que se descartaron, por pagina: es lo unico que la union
    # quita de la IR, y V1 lo necesita para seguir siendo exacta (`verify.text_conservation`).
    dropped_text: dict[int, str] = field(default_factory=dict)
    # Tablas con el mismo encabezado en páginas consecutivas separadas por otros bloques: no se
    # unen (puede haber texto propio en medio), pero son los casos dudosos a revisar a mano.
    separated_candidates: list[tuple[int, int]] = field(default_factory=list)
    # Uniones donde no se pudo decidir si la primera fila del cuerpo continúa la anterior porque
    # las columnas todavía no están inferidas (`Cell.col is None`, T-103).
    unknown_columns: list[tuple[int, int]] = field(default_factory=list)


def merge_continued_tables(doc: Document) -> Document:
    """Documento nuevo con las tablas partidas por página unidas; no muta el original."""
    blocks, _ = _merge(doc)
    return Document(source=doc.source, sha256=doc.sha256, extractor=doc.extractor, blocks=blocks)


def continuation_stats(doc: Document) -> MergeStats:
    """Métricas de la unión sin quedarse con el documento resultante."""
    return _merge(doc)[1]


def header_rows(table: Table) -> list[Row]:
    """Filas iniciales cuyas celdas son todas de encabezado (ver el módulo)."""
    rows: list[Row] = []
    for row in table.rows:
        if not row.cells or not all(cell.header for cell in row.cells):
            break
        rows.append(row)
    return rows


def _same_header(first: list[Row], second: list[Row]) -> bool:
    """Mismo encabezado = misma cantidad de filas y celdas, con los mismos textos."""
    if not first or len(first) != len(second):
        return False
    return all(
        len(a.cells) == len(b.cells) and all(x.text == y.text for x, y in zip(a.cells, b.cells, strict=True))
        for a, b in zip(first, second, strict=True)
    )


def _last_page(table: Table) -> int:
    """Última página que ocupa la tabla (una ya unida ocupa varias).

    Cuenta también lo que declaran sus celdas: si de la página siguiente solo vino la mitad de una
    fila partida, la tabla llega hasta ahí y la página de después puede continuarla.
    """
    pages = [
        page
        for row in table.rows
        for page in (
            row.page or table.page,
            *(number for cell in row.cells for _, number in cell.page_breaks),
        )
    ]
    return max(pages, default=table.page)


def _with_page(row: Row, page: int) -> Row:
    """Copia de la fila con su página explícita: una tabla unida ya no puede heredarla."""
    return Row(cells=copy.deepcopy(row.cells), page=row.page or page)


def _paged(table: Table) -> Table:
    return Table(page=table.page, rows=[_with_page(row, table.page) for row in table.rows], kind=table.kind)


def _merge(doc: Document) -> tuple[list[Block], MergeStats]:
    blocks: list[Block] = []
    merges = dropped = split = 0
    dropped_text: dict[int, list[str]] = {}
    separated: list[tuple[int, int]] = []
    unknown: list[tuple[int, int]] = []
    before = sum(isinstance(block, Table) for block in doc.blocks)
    last_table: Table | None = None

    for block in doc.blocks:
        if not isinstance(block, Table):
            blocks.append(copy.deepcopy(block))
            continue
        previous = blocks[-1] if blocks else None
        adjacent = isinstance(previous, Table)
        if adjacent and isinstance(previous, Table) and _continues(previous, block):
            joined, joined_split, joined_unknown = _join(previous, block)
            blocks[-1] = joined
            last_table = joined
            merges += 1
            for row in _dropped_rows(previous, block):
                page = row.page or block.page
                dropped_text.setdefault(page, []).extend(cell.text for cell in row.cells)
                dropped += 1
            split += joined_split
            unknown.extend(joined_unknown)
            continue
        if not adjacent and last_table is not None and _continues(last_table, block):
            separated.append((_last_page(last_table), block.page))
        last_table = _paged(block)
        blocks.append(last_table)

    stats = MergeStats(
        tables_before=before,
        tables_after=sum(isinstance(block, Table) for block in blocks),
        merges=merges,
        dropped_header_rows=dropped,
        split_rows=split,
        dropped_text={page: "\n".join(parts) for page, parts in dropped_text.items()},
        separated_candidates=separated,
        unknown_columns=unknown,
    )
    return blocks, stats


def _continues(table: Table, other: Table) -> bool:
    """`other` es la misma tabla en la página siguiente: mismo encabezado, página +1 y algo que
    aportar. Sin cuerpo no se une: hay tablas cuyas filas son todas `TH` (páginas 208-214) y
    unirlas sería descartarlas enteras como encabezado repetido.

    D-014 (T-206): también continúa la tabla de la página siguiente que **no** trae encabezado
    etiquetado, si ambas tienen las columnas inferidas y el mismo ancho. Cubre las tablas que Word
    no repite (MT págs. 157, 159, 193…) y las NT, cuyo encabezado está etiquetado como `TD`.
    """
    header = header_rows(other)
    if other.page != _last_page(table) + 1:
        return False
    if header:
        return len(header) < len(other.rows) and _same_header(header_rows(table), header)
    width = _width(table)
    return width is not None and width == _width(other) and len(_dropped_rows(table, other)) < len(other.rows)


def _width(table: Table) -> int | None:
    """Columnas de la tabla según las celdas ubicadas; None si alguna no tiene columna."""
    cells = [cell for row in table.rows for cell in row.cells]
    if not cells or any(cell.col is None for cell in cells):
        return None
    return max(cell.col + cell.col_span for cell in cells if cell.col is not None)


def _row_texts(row: Row) -> list[str]:
    return [cell.text for cell in row.cells]


def _dropped_rows(table: Table, other: Table) -> list[Row]:
    """Filas de `other` que se descartan al unir: su encabezado etiquetado o, si no lo tiene, la
    primera fila cuando repite textualmente la primera de `table` (encabezado sin etiquetar)."""
    header = header_rows(other)
    if header:
        return header
    if table.rows and other.rows and _row_texts(other.rows[0]) == _row_texts(table.rows[0]):
        return other.rows[:1]
    return []


def _join(table: Table, other: Table) -> tuple[Table, int, list[tuple[int, int]]]:
    """Une `other` a `table` descartando su encabezado repetido."""
    rows = list(table.rows)
    body = [_with_page(row, other.page) for row in other.rows[len(_dropped_rows(table, other)) :]]
    split = 0
    unknown: list[tuple[int, int]] = []
    if rows and body:
        body[0] = _place_fragment(table, rows[-1], body[0])
        state = _split_state(rows[-1], body[0])
        if state == "split":
            rows[-1] = _join_rows(rows[-1], body[0])
            body = body[1:]
            split = 1
        elif state == "unknown":
            unknown.append((rows[-1].page or table.page, other.page))
    return Table(page=table.page, rows=rows + body, kind=table.kind), split, unknown


def _place_fragment(table: Table, last: Row, first: Row) -> Row:
    """D-014: una celda suelta que abarca todo el ancho arriba de la página siguiente es la
    continuación de la celda de `last` que desbordó la página si (1) sus caracteres caen dentro de
    esa columna y (2) esa celda es, en `last`, la que llega más abajo. Si no, queda igual (p. ej. el
    título de grupo "Evento conclusivo", MT pág. 119). Se ubica en su columna para que
    `_split_state` la reconozca como la mitad de una fila partida."""
    width = _width(table)
    if width is None or len(first.cells) != 1:
        return first
    lone = first.cells[0]
    if lone.bbox is None or lone.col != 0 or lone.col_span != width:
        return first
    ranges: dict[int, tuple[float, float]] = {}
    for row in table.rows:
        for cell in row.cells:
            if cell.bbox is not None and cell.col is not None and cell.col_span == 1:
                x0, x1 = ranges.get(cell.col, (cell.bbox[0], cell.bbox[2]))
                ranges[cell.col] = (min(x0, cell.bbox[0]), max(x1, cell.bbox[2]))
    tol = 3.0
    inside = [
        col
        for col, (x0, x1) in ranges.items()
        if lone.bbox[0] >= x0 - tol and lone.bbox[2] <= x1 + tol and lone.bbox[0] <= x0 + tol
    ]
    bottoms = {c.col: c.bbox[3] for c in last.cells if c.bbox is not None and c.col is not None}
    if len(inside) != 1 or inside[0] not in bottoms:
        return first
    col = inside[0]
    if any(b >= bottoms[col] for other_col, b in bottoms.items() if other_col != col):
        return first
    placed = copy.deepcopy(lone)
    placed.col, placed.col_span = col, 1
    return Row(cells=[placed], page=first.page)


def _split_state(last: Row, first: Row) -> str:
    """¿`first` continúa la fila `last` cortada por el borde de página?

    Sí cuando `last` abre la columna 0 y `first` no: sin celda en la primera columna, la fila no
    empieza ahí. Si las columnas no están inferidas (`col is None`) no hay información y no se
    fusiona nada ("unknown"); tampoco si una fila repite una columna, que sería ambiguo.
    """
    if not last.cells or not first.cells or all(cell.header for cell in last.cells):
        return "no"
    columns = [[cell.col for cell in row.cells] for row in (last, first)]
    if any(col is None for cols in columns for col in cols):
        return "unknown"
    if any(len(set(cols)) != len(cols) for cols in columns):
        return "no"
    return "split" if 0 in columns[0] and 0 not in columns[1] else "no"


def _join_rows(last: Row, first: Row) -> Row:
    """Fusiona las dos mitades de una fila partida emparejando las celdas por columna.

    Si la segunda mitad abarca filas hacia abajo (continuaciones en su página), la fila unida las
    abarca entera: una celda que solo vino de la primera mitad se extiende lo mismo.

    La fila resultante queda en la página de la primera mitad; lo que se imprimió en la siguiente
    se declara en `Cell.page_breaks`, celda por celda.
    """
    page = first.page
    below = max((cell.row_span for cell in first.cells), default=1) - 1
    cells: dict[int, Cell] = {}
    for cell in last.cells:
        assert cell.col is not None  # garantizado por `_split_state`
        cells[cell.col] = copy.deepcopy(cell)
        cells[cell.col].row_span += below
    for cell in first.cells:
        assert cell.col is not None
        found = cells.get(cell.col)
        if found is None:
            cells[cell.col] = _moved_cell(cell, page)
        else:
            joined = _join_cells(found, cell, page)
            joined.row_span = found.row_span - below + cell.row_span - 1
            cells[cell.col] = joined
    return Row(cells=[cells[col] for col in sorted(cells)], page=last.page)


def _moved_cell(cell: Cell, page: int | None) -> Cell:
    """Celda que solo existe en la mitad de la página siguiente: entera en esa página."""
    moved = copy.deepcopy(cell)
    if page is not None and moved.runs:
        moved.page_breaks = [(0, page), *moved.page_breaks]
    return moved


def _join_cells(first: Cell, second: Cell, page: int | None = None) -> Cell:
    """Concatena las dos partes de la celda con un salto entre ellas; conserva los tramos.

    `page` es la página de la segunda parte: se declara en `page_breaks` el offset donde empieza,
    y los saltos que ya traía la segunda parte (cadena de tres páginas) se corren ese mismo offset.
    """
    runs = copy.deepcopy(first.runs)
    if runs and second.runs:
        runs.append(Run("\n"))
    offset = sum(len(run.text) for run in runs)
    runs.extend(copy.deepcopy(second.runs))
    breaks = list(first.page_breaks)
    if page is not None and second.runs:
        breaks.append((offset, page))
        breaks.extend((at + offset, number) for at, number in second.page_breaks)
    # `bbox` y `row_span` quedan los de la primera parte: describen su página, no la fusión.
    return Cell(
        runs=runs,
        header=first.header,
        bbox=first.bbox,
        col=first.col,
        row_span=first.row_span,
        page_breaks=breaks,
    )

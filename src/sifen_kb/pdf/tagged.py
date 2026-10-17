# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Extracción desde el árbol de estructura de un Tagged PDF.

El árbol declara tablas, filas, celdas, encabezados y listas; el texto se obtiene de los
caracteres enlazados por MCID. Nada se infiere con modelos: si el árbol no lo dice, no está.

El orden del árbol no siempre es el orden impreso: se corrige por geometría, y solo cuando la
geometría es inequívoca (`_in_reading_order`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page
from pdfplumber.structure import PDFStructElement, PDFStructTree

from sifen_kb.pdf.hashing import sha256_of
from sifen_kb.pdf.ir import (
    BBox,
    Block,
    Cell,
    Change,
    Document,
    Figure,
    Row,
    Run,
    Table,
    TextBlock,
)

EXTRACTOR = f"tagged/pdfplumber-{pdfplumber.__version__}"

# Rellenos de resaltado de Word → cambio. La leyenda (página PDF 15) es texto negro que nombra los
# colores; los valores RGB se midieron sobre el contenido resaltado (V6 cierra en las 217 páginas).
HIGHLIGHTS: dict[tuple[float, ...], Change] = {
    (1.0, 1.0, 0.0): Change.MODIFIED,
    (0.0, 1.0, 0.0): Change.ADDED,
    (1.0, 0.0, 0.0): Change.DELETED,
}
# Contenedores: no aportan texto propio, se recorre su contenido.
CONTAINERS = {"Document", "Part", "Art", "Sect", "Div", "NonStruct", "L", "TOC", "BlockQuote"}
HEADINGS = {"H": 1, "H1": 1, "H2": 2, "H3": 3, "H4": 4, "H5": 5, "H6": 6}

Char = dict
Rect = dict


class PageIndex:
    """Caracteres por MCID y rectángulos de resaltado, calculados una vez por página."""

    def __init__(self, pdf: pdfplumber.pdf.PDF) -> None:
        self._pdf = pdf
        self._chars: dict[int, dict[int, list[Char]]] = {}
        self._marks: dict[int, list[tuple[Rect, Change]]] = {}

    def _load(self, number: int) -> None:
        page: Page = self._pdf.pages[number - 1]
        by_mcid: dict[int, list[Char]] = defaultdict(list)
        for char in page.chars:
            if char.get("mcid") is not None:
                by_mcid[char["mcid"]].append(char)
        self._chars[number] = by_mcid
        marks = []
        for rect in page.rects:
            change = HIGHLIGHTS.get(_rgb(rect.get("non_stroking_color")))
            if rect.get("fill") and change is not None:
                marks.append((rect, change))
        self._marks[number] = marks

    def chars(self, number: int, mcid: int) -> list[Char]:
        if number not in self._chars:
            self._load(number)
        return self._chars[number].get(mcid, [])

    def change_of(self, number: int, char: Char) -> Change | None:
        cx = (char["x0"] + char["x1"]) / 2
        cy = (char["top"] + char["bottom"]) / 2
        for rect, change in self._marks[number]:
            if rect["x0"] <= cx <= rect["x1"] and rect["top"] <= cy <= rect["bottom"]:
                return change
        return None


def _rgb(color: object) -> tuple[float, ...]:
    if isinstance(color, (list, tuple)) and all(isinstance(x, (int, float)) for x in color):
        return tuple(round(x, 2) for x in color)
    return ()


# Un `prune` corta el recorrido: el subárbol del nodo que cumple el predicado no se visita.
Prune = Callable[[PDFStructElement], bool]


def _nested_list(node: PDFStructElement) -> bool:
    return node.type == "L"


def _walk(element: PDFStructElement, prune: Prune | None = None) -> Iterator[PDFStructElement]:
    yield element
    for child in element.children:
        if prune is not None and prune(child):
            continue
        yield from _walk(child, prune)


def _pages_of(element: PDFStructElement, prune: Prune | None = None) -> list[int]:
    return sorted({n.page_number for n in _walk(element, prune) if n.mcids and n.page_number is not None})


def _needs_space(prev: Char, char: Char, drawn: bool) -> bool:
    """Hueco horizontal sin carácter de espacio explícito.

    Un cambio de renglón no separa: Word escribe un espacio explícito al final del renglón
    cuando el corte cae entre palabras, así que si no hay ninguno la palabra quedó partida
    (medido en el manual completo: 4184 cortes con espacio y 278 sin él, y los 278 caen dentro
    de una palabra, p. ej. `GEC0|02`, `Longit|ud`, `1-15p(0-|8)`).
    Excepción `drawn`: en una `Figure` el texto viene de cuadros independientes dibujados uno
    tras otro, no de renglones de un párrafo; ahí el cambio de renglón sí separa.
    """
    if prev["text"].isspace() or char["text"].isspace():
        return False
    height = min(prev["bottom"] - prev["top"], char["bottom"] - char["top"])
    if abs(char["top"] - prev["top"]) > height * 0.5:
        return drawn
    return char["x0"] - prev["x1"] > prev["size"] * 0.15


Piece = tuple[str, Change | None, int]  # texto, cambio, pagina


def _runs(
    element: PDFStructElement, index: PageIndex, prune: Prune | None = None
) -> tuple[list[Run], list[tuple[int, int]]]:
    """Tramos de texto del elemento y los puntos donde el texto pasa a otra pagina."""
    pieces: list[Piece] = []
    prev: Char | None = None
    prev_para: PDFStructElement | None = None
    start = element if element.type == "P" else None
    drawn = element.type == "Figure"
    for node, para in _walk_paragraphs(element, start, prune):
        if node.page_number is None:
            continue
        for mcid in node.mcids or []:
            for char in index.chars(node.page_number, mcid):
                change = index.change_of(node.page_number, char)
                if prev is not None and prev_para is not None and para not in (None, prev_para):
                    # Otro parrafo del arbol: salto real (en una celda, un valor por linea).
                    pieces.append(("\n", None, node.page_number))
                elif prev is not None and _needs_space(prev, char, drawn):
                    pieces.append((" ", None, node.page_number))
                pieces.append((char["text"], change, node.page_number))
                prev, prev_para = char, para
    return _normalize(pieces)


def _walk_paragraphs(
    element: PDFStructElement, para: PDFStructElement | None, prune: Prune | None = None
) -> Iterator[tuple[PDFStructElement, PDFStructElement | None]]:
    """Como `_walk`, junto con el `P` mas cercano que contiene a cada nodo."""
    yield element, para
    for child in element.children:
        if prune is not None and prune(child):
            continue
        yield from _walk_paragraphs(child, child if child.type == "P" else para, prune)


def _normalize(pieces: list[Piece]) -> tuple[list[Run], list[tuple[int, int]]]:
    """Colapsa espacios (un salto de parrafo prevalece), recorta extremos, agrupa por cambio y
    ubica saltos de pagina."""
    compact: list[Piece] = []
    for text, change, page in pieces:
        if text.isspace():
            text = "\n" if "\n" in text else " "
            if not compact:
                continue
            if compact[-1][0].isspace():
                if text == "\n":
                    compact[-1] = ("\n", compact[-1][1], compact[-1][2])
                continue
        compact.append((text, change, page))
    while compact and compact[-1][0].isspace():
        compact.pop()
    # Los espacios de fin de linea quedan fuera del rectangulo de resaltado; un espacio no es
    # contenido, asi que hereda el cambio si sus dos vecinos coinciden.
    for i in range(1, len(compact) - 1):
        if compact[i][0].isspace() and compact[i - 1][1] == compact[i + 1][1]:
            compact[i] = (compact[i][0], compact[i - 1][1], compact[i][2])
    runs: list[Run] = []
    breaks: list[tuple[int, int]] = []
    offset = 0
    for i, (text, change, page) in enumerate(compact):
        if i and page != compact[i - 1][2]:
            breaks.append((offset, page))
        if runs and runs[-1].change == change:
            runs[-1] = Run(runs[-1].text + text, change)
        else:
            runs.append(Run(text, change))
        offset += len(text)
    return runs, breaks


def _bbox(element: PDFStructElement, index: PageIndex, page: int, prune: Prune | None = None) -> BBox | None:
    """Rectangulo de los caracteres con contenido del elemento en `page`; None si no tiene.

    Los espacios quedan fuera: el que Word escribe al final de un renglon esta donde termina
    el papel, no donde esta el contenido, y correria el borde. Una celda vacia no tiene
    rectangulo (su unico caracter es un espacio).
    """
    chars = [
        char
        for node in _walk(element, prune)
        if node.page_number == page
        for mcid in node.mcids or []
        for char in index.chars(page, mcid)
        if not char["text"].isspace()
    ]
    if not chars:
        return None
    return (
        min(c["x0"] for c in chars),
        min(c["top"] for c in chars),
        max(c["x1"] for c in chars),
        max(c["bottom"] for c in chars),
    )


def _title_row(rows: list[Row]) -> Row | None:
    """Fila-titulo: la primera fila es una sola celda y la siguiente trae mas celdas.

    Word arma el titulo de la tabla como una celda combinada que abarca todo el ancho (p. ej.
    'CODIFICACION DE UNIDADES DE MEDIDA' en la NT-023 o 'Tabla D: Formatos numericos' en la
    pagina 35). El arbol no trae `ColSpan`, asi que la fila llega con una celda sola: tomarla
    como encabezado dejaba la tabla en una columna y sin columnas que inferir.

    No se mide el ancho del rectangulo: el titulo va centrado y cubre solo sus caracteres (en la
    pagina 147 titula en x 230-381 y la tabla ocupa 135-477), asi que "abarca todo el ancho" no
    se puede leer de la geometria. La forma si es inequivoca: una celda sola arriba de filas con
    mas celdas.
    """
    if len(rows) < 2 or len(rows[0].cells) != 1 or len(rows[1].cells) < 2:
        return None
    return rows[0]


def _header_row(rows: list[Row], title: Row | None = None) -> Row:
    """Encabezado (D-008): la primera fila con todas sus celdas TH, o la primera fila.

    En las validaciones la celda del ID tambien es TH, asi que no alcanza con "tiene un TH".
    Una fila de una sola celda no puede ser el encabezado de una tabla con mas columnas: es otro
    titulo (en la pagina 147, 'REFERENCIA ESTADO DE VALIDACION' parte la tabla en dos y es la
    unica fila con todas sus celdas TH).
    """
    body = [row for row in rows if row is not title]
    wide = body if title is None else [row for row in body if len(row.cells) > 1]
    return next((row for row in wide if row.cells and all(c.header for c in row.cells)), body[0])


Span = tuple[float, float]  # x0, x1


def _span(box: BBox) -> Span:
    return (box[0], box[2])


def _overlap(one: Span, other: Span) -> float:
    return min(one[1], other[1]) - max(one[0], other[0])


def _spans(header: Row, placed: list[Row], ncols: int) -> list[Span | None]:
    """Rango horizontal de cada columna, medido sobre el encabezado y las filas ya ubicadas.

    El rango del texto del encabezado no alcanza: va centrado y es mas angosto que la columna
    (en la pagina 151 *Observacion* titula 371-426 y su contenido ocupa 296-467, asi que una
    celda corta de continuacion no solapa el titulo). Las filas con tantas celdas como el
    encabezado se ubican por indice, sin geometria: son la medida confiable de la columna.
    """
    spans: list[Span | None] = []
    for col in range(ncols):
        boxes = [row.cells[col].bbox for row in [header, *placed] if row.cells[col].bbox is not None]
        found = [_span(box) for box in boxes if box is not None]
        spans.append((min(s[0] for s in found), max(s[1] for s in found)) if found else None)
    return spans


def _increasing(cols: list[int | None]) -> list[int | None]:
    """Descarta las columnas que rompen el orden: dos celdas de una fila no comparten columna."""
    kept: list[int | None] = []
    last = -1
    for col in cols:
        if col is None or col <= last:
            kept.append(None)
        else:
            kept.append(col)
            last = col
    return kept


def _by_order(cols: list[int | None], ncols: int) -> list[int | None]:
    """Ubica las celdas sin columna por orden entre sus vecinas ubicadas.

    Solo cuando queda una unica asignacion posible: los huecos entre las vecinas son tantos
    como las celdas por ubicar. Si sigue habiendo ambiguedad, quedan en None (no se inventa).
    """
    placed = list(cols)
    start = 0
    while start < len(placed):
        if placed[start] is not None:
            start += 1
            continue
        end = start
        while end < len(placed) and placed[end] is None:
            end += 1
        before = placed[start - 1]
        low = 0 if start == 0 else (before + 1 if before is not None else 0)
        after = placed[end] if end < len(placed) else None
        high = ncols if after is None else after
        if high - low == end - start:
            for i in range(start, end):
                placed[i] = low + (i - start)
        start = end
    return placed


def _columns(row: Row, spans: list[Span | None], ncols: int) -> list[int | None]:
    """Columna de cada celda: la de mayor solape horizontal con su rango (D-008)."""
    cols: list[int | None] = []
    for cell in row.cells:
        best: int | None = None
        widest = 0.0
        for col, span in enumerate(spans):
            if cell.bbox is None or span is None:
                continue
            over = _overlap(_span(cell.bbox), span)
            if over > widest:
                best, widest = col, over
        cols.append(best)
    return _by_order(_increasing(cols), ncols)


def _row_spans(rows: list[Row], header: Row, title: Row | None, ncols: int) -> None:
    """Anota las combinaciones verticales: una columna ausente continua la celda de arriba.

    Una fila de continuacion (sin celda en la primera columna) hereda de arriba las columnas
    que le faltan: la celda que las cubre suma un `row_span`. Una fila que trae su propia
    primera columna es otro registro: si le falta una columna, el valor esta en otra pagina o
    no existe (p. ej. AC05 en la pagina 153) y no se le inventa ninguna combinacion. El
    encabezado no cubre nada: la primera fila de la pagina puede continuar la pagina anterior.
    """
    covering: dict[int, Cell] = {}
    for row in rows:
        # La fila-titulo tampoco cubre nada: abarca todas las columnas, no una.
        if row is header or row is title:
            continue
        cols = [cell.col for cell in row.cells]
        present = {col for col in cols if col is not None}
        if None not in cols and 0 not in present:
            for col in range(ncols):
                if col not in present and col in covering:
                    covering[col].row_span += 1
        for cell in row.cells:
            if cell.col is not None:
                covering[cell.col] = cell


def _assign_columns(rows: list[Row]) -> None:
    """Ubica cada celda en su columna y anota las combinaciones verticales (D-008).

    Una fila con tantas celdas como el encabezado se ubica por indice, sin geometria; las demas,
    por solape con el rango que esas filas miden para cada columna. Si la tabla empieza con una
    fila-titulo, el encabezado es la fila que sigue y el titulo queda aparte.
    """
    if not rows:
        return
    title = _title_row(rows)
    header = _header_row(rows, title)
    ncols = len(header.cells)
    placed = [row for row in rows if row is not header and row is not title and len(row.cells) == ncols]
    for row in [header, *placed]:
        for col, cell in enumerate(row.cells):
            cell.col = col
    if title is not None:
        # El titulo abarca la tabla entera y queda fuera de la medida de las columnas: su texto
        # va centrado y cruza los limites de varias.
        title.cells[0].col = 0
        title.cells[0].col_span = ncols
    spans = _spans(header, placed, ncols)
    for row in rows:
        if row is header or row is title or len(row.cells) == ncols:
            continue
        for cell, col in zip(row.cells, _columns(row, spans, ncols), strict=True):
            cell.col = col
    _row_spans(rows, header, title, ncols)


def _table(element: PDFStructElement, page: int, index: PageIndex) -> Table:
    rows = []
    for node in _walk(element):
        if node.type == "TR":
            cells = []
            for cell in node.children:
                if cell.type not in ("TD", "TH"):
                    continue
                pages = _pages_of(cell)
                cells.append(
                    Cell(
                        _runs(cell, index)[0],
                        header=cell.type == "TH",
                        bbox=_bbox(cell, index, pages[0] if pages else page),
                    )
                )
            rows.append(Row(cells))
    _assign_columns(rows)
    return Table(page=page, rows=rows)


# Bloque con la caja que cubren sus caracteres en su propia pagina; None si no tiene ninguno
# (p. ej. una `Figure` sin texto): sin caja no hay posicion y el bloque no se mueve.
Placed = tuple[BBox | None, Block]


def _sublists(element: PDFStructElement) -> list[PDFStructElement]:
    """Listas anidadas del item, las mas superficiales (sin entrar en las de sus subitems)."""
    return [
        child for node in _walk(element, prune=_nested_list) for child in node.children if _nested_list(child)
    ]


def _list_item(element: PDFStructElement, index: PageIndex, wanted: set[int] | None) -> Iterator[Placed]:
    """Un `LI` con listas anidadas no es un bloque solo: su texto propio y luego sus subitems.

    Word anida los subapartados dentro del `LBody` del apartado que los encabeza. Tomado como un
    bloque unico, el rotulo y los cuatro subapartados salen como una sola viñeta atribuida a la
    pagina del primero (auditoria H-1: `1.`-`1.4.` de la NT-023, y los cinco pasos de 13.8.4 del
    manual, que abarcan las paginas 207-210). Se emite el texto propio del item -- rotulo y cuerpo
    sin la sublista -- y despues se recurre en cada sublista, asi cada subitem es su propio bloque
    con su propia pagina.
    """
    runs, breaks = _runs(element, index, prune=_nested_list)
    pages = _pages_of(element, prune=_nested_list)
    if runs and pages and (wanted is None or not wanted.isdisjoint(pages)):
        yield (
            _bbox(element, index, pages[0], prune=_nested_list),
            TextBlock(page=pages[0], role=element.type, runs=runs, page_breaks=breaks),
        )
    for sublist in _sublists(element):
        yield from _blocks(sublist, index, wanted)


def _blocks(element: PDFStructElement, index: PageIndex, wanted: set[int] | None) -> Iterator[Placed]:
    kind = element.type
    if kind in CONTAINERS:
        for child in element.children:
            yield from _blocks(child, index, wanted)
        return
    if kind == "LI" and _sublists(element):
        yield from _list_item(element, index, wanted)
        return
    pages = _pages_of(element) or ([element.page_number] if element.page_number else [])
    # Filtrar antes de leer caracteres: evita cargar paginas fuera del rango pedido.
    if not pages or (wanted is not None and wanted.isdisjoint(pages)):
        return
    if kind == "Table":
        yield _bbox(element, index, pages[0]), _table(element, pages[0], index)
        return
    runs, breaks = _runs(element, index)
    if kind == "Figure":
        yield (
            _bbox(element, index, pages[0]),
            Figure(page=pages[0], alt_text=element.alt_text, runs=runs, page_breaks=breaks),
        )
    elif runs:
        yield (
            _bbox(element, index, pages[0]),
            TextBlock(page=pages[0], role=kind, runs=runs, level=HEADINGS.get(kind), page_breaks=breaks),
        )


def _precedes(one: BBox, other: BBox) -> bool:
    """`one` se lee antes que `other` segun la pagina: termina por encima de donde `other`
    empieza y los dos comparten columna (sus rangos horizontales se solapan)."""
    return one[3] <= other[1] and _overlap(_span(one), _span(other)) > 0


def _page_order(placed: list[Placed]) -> list[Block]:
    """Bloques de una pagina en orden de lectura: el del arbol, corregido solo donde la geometria
    es inequivoca (`_precedes`). Es un orden topologico y el arbol decide los empates, asi que un
    bloque se mueve unicamente si otro esta entero por encima de el en su misma columna.

    No puede haber ciclos: `_precedes` exige `one.bottom <= other.top`, luego `one.top <
    other.top`, y un ciclo necesitaria que un bloque empezara por encima de si mismo.
    """
    rest = list(placed)
    ordered: list[Block] = []
    while rest:
        ready = next(
            index
            for index, (box, _) in enumerate(rest)
            if box is None
            or not any(
                other is not None and _precedes(other, box)
                for position, (other, _) in enumerate(rest)
                if position != index
            )
        )
        ordered.append(rest.pop(ready)[1])
    return ordered


def _in_reading_order(placed: list[Placed]) -> list[Block]:
    """Orden de lectura del documento: por pagina y, dentro de cada pagina, `_page_order`.

    El orden del arbol y el de la pagina no siempre coinciden: Word deja la nota al pie como
    primer bloque de su pagina y mete apartados enteros (con sus subapartados de la pagina
    siguiente) antes de las tablas que introducen. La pagina de cada bloque es la que ya declara
    la IR --el primer caracter manda--, asi que un bloque que empieza en la pagina N+1 nunca queda
    antes de uno de la pagina N.

    Medido sobre las fuentes: en el manual completo (217 paginas, 1502 bloques) se reubican 15
    bloques -- 5 notas al pie, 1 rotulo de cuadro de la pagina 197 y los 9 de 13.8.4 (paginas
    207-210) --; en las 22 NT etiquetadas, 19 bloques en cuatro notas (008, 010, 023 y 026) y las
    otras 18 quedan igual. Ordenar por `top` a secas movia 26 bloques del manual: ademas de esos
    15, intercalaba las columnas de la maqueta del KuDE (paginas 196-197) y daba vuelta las dos
    matrices de eventos de la pagina 121, que estan una al lado de la otra con 0,2 pt de
    diferencia. De ahi la condicion de compartir columna.
    """
    by_page: dict[int, list[Placed]] = defaultdict(list)
    for item in placed:
        by_page[item[1].page].append(item)
    return [block for page in sorted(by_page) for block in _page_order(by_page[page])]


def extract_tagged(path: Path, pages: Iterable[int] | None = None) -> Document:
    """Extrae la IR de un Tagged PDF, opcionalmente limitada a `pages` (numeración PDF, base 1)."""
    wanted = set(pages) if pages is not None else None
    with pdfplumber.open(path) as pdf:
        index = PageIndex(pdf)
        placed = [item for root in PDFStructTree(pdf) for item in _blocks(root, index, wanted)]
        blocks = _in_reading_order(placed)
    return Document(source=Path(path).name, sha256=sha256_of(Path(path)), extractor=EXTRACTOR, blocks=blocks)

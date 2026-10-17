# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Extracción por geometría, para los PDF que no traen árbol de estructura.

Ruta alternativa a `tagged.extract_tagged` para las 5 Notas Técnicas sin etiquetar
(001, 007, 011, 012, 013; 12 páginas). La salida es la misma IR.

Dos observaciones del sondeo sostienen el método:

1. Las tablas **sí** están dibujadas: cada borde de celda es un rectángulo relleno de menos de
   1,2 pt de grosor. `find_tables()` no sirve porque mezcla esos bordes con los rectángulos de
   resaltado (10 pt de alto), y sale una tabla espuria por resaltado; filtrando por grosor la
   rejilla queda limpia, y con ella las filas y las columnas son las que dibujó el autor.
2. Cada renglón termina con un espacio explícito cuando el corte cae entre palabras, igual que en
   el manual etiquetado (D-009). Por eso un corte **sin** espacio une la palabra (`EA004`+`a` →
   `EA004a`, `Grup`+`o` → `Grupo`) y no hace falta adivinar.

Lo que la rejilla no dice es *qué* tabla es: eso lo aporta el encabezado conocido del dominio
(`HEADERS`). Solo cuando coincide se marca la primera fila como encabezado; una tabla que
continúa en la página siguiente no repite el encabezado y se deja sin marcar (la une T-104).
El texto fuera de la rejilla es prosa, y el encabezado y el pie repetidos de las NT son
artefactos que no entran en la IR.
"""

from __future__ import annotations

import math
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page

from sifen_kb.pdf.hashing import sha256_of
from sifen_kb.pdf.ir import BBox, Block, Cell, Change, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.sifen.artifacts import NT_HEADER
from sifen_kb.pdf.tagged import HIGHLIGHTS

EXTRACTOR = f"geometry/pdfplumber-{pdfplumber.__version__}"

Char = dict
Rect = dict

THIN = 1.2  # grosor máximo de un borde de celda (los medidos son 0,36-0,60)
SHORT = 3.0  # largo mínimo de un borde: menos que eso es la esquina, no un lado
NEAR = 1.5  # tolerancia al unir bordes del mismo eje (Word dibuja cada celda por separado)
PARAGRAPH = 1.5  # salto de párrafo dentro de una celda, en alturas de renglón
PROSE = 2.2  # el mismo salto en la prosa, que va a interlineado 1,5
RAGGED = 0.15  # un renglón que termina a esta fracción del margen cierra el párrafo


def normalized(text: str) -> str:
    """Etiqueta comparable: sin mayúsculas, acentos ni espacios.

    Los espacios se van porque la columna angosta parte la palabra (`Ocur|renci|a`) y porque el
    título ocupa dos renglones (`Nodo|Padre`): lo que se compara es el encabezado, no su maqueta.
    """
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in plain if not unicodedata.combining(c) and not c.isspace())


def _labels(*texts: str) -> tuple[str, ...]:
    return tuple(normalized(text) for text in texts)


FIELD_HEADER = _labels(
    "Grupo",
    "ID",
    "Campo",
    "Descripción",
    "Nodo Padre",
    "Tipo Dato",
    "Longitud",
    "Ocurrencia",
    "Observaciones",
)
# Los schema XML de la NT-011 describen campos sin grupo: el resto del encabezado es el mismo.
SCHEMA_HEADER = FIELD_HEADER[1:]
VALIDATION_HEADER = _labels("N° Val", "ID", "Mensaje de la Validación", "Código", "Observación", "E")
# Cada NT titula la validación a su manera; las demás columnas son siempre las mismas.
VALIDATION_VARIANTS = tuple(
    _labels("ID", message, "Código", observation, "E")
    for message in (
        "Mensaje de la Validación",
        "Mensaje de validación",
        "Resultado de la Validación",
        "Resultado de validación",
    )
    for observation in ("Observación", "Obs")
)
HEADERS: frozenset[tuple[str, ...]] = frozenset(
    {FIELD_HEADER, SCHEMA_HEADER, VALIDATION_HEADER, *VALIDATION_VARIANTS}
)
ANCHOR = normalized("ID")  # columna que abre cada registro, en campos y en validaciones


@dataclass(frozen=True)
class GridRow:
    top: float
    bottom: float
    # Columnas de `Grid.columns` que la fila trae dibujadas: de `cols[i]` a `cols[i+1]`, una celda.
    cols: tuple[int, ...]


@dataclass(frozen=True)
class Grid:
    """Rejilla de una tabla: los bordes horizontales dan las filas y los verticales las columnas."""

    columns: tuple[float, ...]
    rows: tuple[GridRow, ...]

    @property
    def top(self) -> float:
        return self.rows[0].top

    @property
    def bottom(self) -> float:
        return self.rows[-1].bottom

    def cells(self, row: GridRow) -> Iterator[tuple[int, float, float]]:
        """Columna y rango horizontal de cada celda de la fila."""
        for left, right in zip(row.cols, row.cols[1:], strict=False):
            yield left, self.columns[left], self.columns[right]


def _cluster(values: Iterable[float]) -> list[float]:
    """Agrupa coordenadas que son el mismo borde dibujado dos veces, y devuelve su centro."""
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= NEAR:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [sum(group) / len(group) for group in groups]


def _nearest(values: list[float], value: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - value))


def grids(rects: Iterable[Rect]) -> list[Grid]:
    """Rejillas cerradas que dibujan los rectángulos finos, de arriba hacia abajo.

    Un borde horizontal solo delimita una fila si hay verticales que la cruzan de lado a lado y
    los dos horizontales llegan hasta ellos: así el subrayado de un título no forma una tabla.
    Un recuadro de una sola celda tampoco es una tabla: es un cuadro de texto.
    """
    rails: list[tuple[float, float, float]] = []  # y, x0, x1
    stiles: list[tuple[float, float, float]] = []  # x, arriba, abajo
    for rect in rects:
        width, height = rect["x1"] - rect["x0"], rect["bottom"] - rect["top"]
        if height <= THIN and width >= SHORT:
            rails.append(((rect["top"] + rect["bottom"]) / 2, rect["x0"], rect["x1"]))
        elif width <= THIN and height >= SHORT:
            stiles.append(((rect["x0"] + rect["x1"]) / 2, rect["top"], rect["bottom"]))
    ys, xs = _cluster(y for y, _, _ in rails), _cluster(x for x, _, _ in stiles)
    found: dict[int, tuple[int, ...]] = {}
    for i, (top, bottom) in enumerate(zip(ys, ys[1:], strict=False)):
        cols = sorted(
            {
                _nearest(xs, x)
                for x, over, under in stiles
                if over <= top + NEAR
                and under >= bottom - NEAR
                and _reaches(rails, top, x)
                and _reaches(rails, bottom, x)
            }
        )
        if len(cols) >= 2:
            found[i] = tuple(cols)
    tables = (_grid(ys, xs, run, found) for run in _consecutive(sorted(found)))
    return [grid for grid in tables if _cells(grid) >= 2]


def _cells(grid: Grid) -> int:
    return sum(len(row.cols) - 1 for row in grid.rows)


def _reaches(rails: list[tuple[float, float, float]], y: float, x: float) -> bool:
    """El borde horizontal de `y` llega hasta el vertical de `x`."""
    return any(abs(rail - y) <= NEAR and x0 - NEAR <= x <= x1 + NEAR for rail, x0, x1 in rails)


def _consecutive(indexes: list[int]) -> Iterator[list[int]]:
    """Tramos de filas pegadas: un hueco entre bordes horizontales separa dos tablas."""
    run: list[int] = []
    for index in indexes:
        if run and index != run[-1] + 1:
            yield run
            run = []
        run.append(index)
    if run:
        yield run


def _grid(ys: list[float], xs: list[float], run: list[int], found: dict[int, tuple[int, ...]]) -> Grid:
    used = sorted({col for i in run for col in found[i]})
    columns = tuple(xs[col] for col in used)
    rows = tuple(GridRow(ys[i], ys[i + 1], tuple(used.index(col) for col in found[i])) for i in run)
    return Grid(columns=columns, rows=rows)


def _rgb(color: object) -> tuple[float, ...]:
    if isinstance(color, (list, tuple)) and all(isinstance(x, (int, float)) for x in color):
        return tuple(round(x, 2) for x in color)
    return ()


def marks_of(page: Page) -> list[tuple[Rect, Change]]:
    """Resaltados de la página, con la misma regla que `tagged` (leyenda de la página PDF 15).

    El verde claro (0.658824, 0.815686, 0.552941) queda fuera a propósito: en las NT 007, 011,
    012 y 013 es el fondo del encabezado de las tablas, no un cambio.
    """
    marks = []
    for rect in page.rects:
        change = HIGHLIGHTS.get(_rgb(rect.get("non_stroking_color")))
        if rect.get("fill") and change is not None:
            marks.append((rect, change))
    return marks


def _center(char: Char) -> tuple[float, float]:
    return (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2


def _change_at(marks: list[tuple[Rect, Change]], char: Char) -> Change | None:
    cx, cy = _center(char)
    for rect, change in marks:
        if rect["x0"] <= cx <= rect["x1"] and rect["top"] <= cy <= rect["bottom"]:
            return change
    return None


def text_lines(chars: Iterable[Char]) -> list[list[Char]]:
    """Renglones: caracteres a la misma altura, de izquierda a derecha."""
    lines: list[list[Char]] = []
    for char in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])):
        height = char["bottom"] - char["top"]
        if lines and abs(char["top"] - lines[-1][0]["top"]) <= height * 0.5:
            lines[-1].append(char)
        else:
            lines.append([char])
    return [sorted(line, key=lambda c: c["x0"]) for line in lines]


def _needs_space(prev: Char, char: Char) -> bool:
    """Hueco horizontal sin carácter de espacio explícito.

    Un cambio de renglón nunca separa: el espacio del final del renglón está escrito cuando el
    corte cae entre palabras, así que si no hay ninguno la palabra quedó partida (D-009).
    """
    if prev["text"].isspace() or char["text"].isspace():
        return False
    height = min(prev["bottom"] - prev["top"], char["bottom"] - char["top"])
    if abs(char["top"] - prev["top"]) > height * 0.5:
        return False
    return char["x0"] - prev["x1"] > prev["size"] * 0.15


Piece = tuple[str, Change | None]


def runs_of(
    chars: Iterable[Char],
    change_of: Callable[[Char], Change | None] | None = None,
    paragraph: float = PARAGRAPH,
) -> list[Run]:
    """Tramos de texto de un grupo de caracteres, con su marca de cambio.

    Un salto mayor que `paragraph` alturas de renglón es un párrafo nuevo dentro del mismo
    bloque o celda (en la observación de un campo hay varios).
    """
    pieces: list[Piece] = []
    prev: Char | None = None
    for line in text_lines(chars):
        height = max(c["bottom"] - c["top"] for c in line)
        if prev is not None and line[0]["top"] - prev["top"] > height * paragraph:
            pieces.append(("\n", None))
        for char in line:
            if prev is not None and _needs_space(prev, char):
                pieces.append((" ", None))
            pieces.append((char["text"], change_of(char) if change_of else None))
            prev = char
    return _runs(pieces)


def _runs(pieces: list[Piece]) -> list[Run]:
    """Colapsa espacios (un salto de párrafo prevalece), recorta extremos y agrupa por cambio."""
    compact: list[Piece] = []
    for text, change in pieces:
        if text.isspace():
            text = "\n" if "\n" in text else " "
            if not compact:
                continue
            if compact[-1][0].isspace():
                if text == "\n":
                    compact[-1] = ("\n", compact[-1][1])
                continue
        compact.append((text, change))
    while compact and compact[-1][0].isspace():
        compact.pop()
    # El espacio del final del renglón queda fuera del rectángulo de resaltado; no es contenido,
    # así que hereda el cambio si sus dos vecinos coinciden (igual que en `tagged`).
    for i in range(1, len(compact) - 1):
        if compact[i][0].isspace() and compact[i - 1][1] == compact[i + 1][1]:
            compact[i] = (compact[i][0], compact[i - 1][1])
    runs: list[Run] = []
    for text, change in compact:
        if runs and runs[-1].change == change:
            runs[-1] = Run(runs[-1].text + text, change)
        else:
            runs.append(Run(text, change))
    return runs


def _bbox(chars: Iterable[Char]) -> BBox | None:
    """Rectángulo de los caracteres con contenido; None si la celda está vacía (como `tagged`)."""
    full = [c for c in chars if not c["text"].isspace()]
    if not full:
        return None
    return (
        min(c["x0"] for c in full),
        min(c["top"] for c in full),
        max(c["x1"] for c in full),
        max(c["bottom"] for c in full),
    )


def header_labels(table: Table) -> tuple[str, ...] | None:
    """Encabezado conocido del dominio que trae la primera fila, o None si no es ninguno."""
    if not table.rows:
        return None
    labels = tuple(normalized(cell.text) for cell in table.rows[0].cells)
    return labels if labels in HEADERS else None


def _cell_at(row: Row, col: int, ncols: int) -> Cell | None:
    if len(row.cells) == ncols:
        return row.cells[col]
    return next((cell for cell in row.cells if cell.col == col), None)


def anchor_gaps(table: Table, labels: tuple[str, ...] | None = None) -> list[int]:
    """Filas cuya celda de ID está vacía.

    Cada registro de una tabla de campos o de validaciones empieza con su ID; una fila sin ID no
    está explicada por la rejilla (sería una combinación vertical) y se reporta en lugar de
    inventarla (D-009). `labels` sirve para revisar una tabla que continúa de la página anterior
    y por eso no repite el encabezado.
    """
    labels = labels or header_labels(table)
    if labels is None or ANCHOR not in labels:
        return []
    col = labels.index(ANCHOR)
    gaps = []
    for i, row in enumerate(table.rows):
        cell = _cell_at(row, col, len(labels))
        if cell is None or not cell.text.strip():
            gaps.append(i)
    return gaps


def _locate(found: list[Grid], char: Char) -> tuple[int, int, int] | None:
    """Celda (rejilla, fila, columna) donde cae el centro del carácter; None si está en la prosa."""
    cx, cy = _center(char)
    for g, grid in enumerate(found):
        if not grid.top <= cy <= grid.bottom:
            continue
        for r, row in enumerate(grid.rows):
            if not row.top <= cy <= row.bottom:
                continue
            for col, left, right in grid.cells(row):
                if left <= cx <= right:
                    return g, r, col
    return None


def _table(
    grid: Grid,
    page: int,
    chars: dict[tuple[int, int], list[Char]],
    change_of: Callable[[Char], Change | None],
) -> Table:
    rows = []
    for r, row in enumerate(grid.rows):
        cells = [
            Cell(
                runs_of(chars.get((r, col), []), change_of),
                bbox=_bbox(chars.get((r, col), [])),
                col=col,
            )
            for col, _, _ in grid.cells(row)
        ]
        rows.append(Row(cells))
    table = Table(page=page, rows=rows)
    if header_labels(table) is not None:
        for cell in rows[0].cells:
            cell.header = True
    return table


def _prose_lines(lines: list[list[Char]], page: int) -> list[list[Char]]:
    """Renglones de prosa sin los artefactos de página de las NT.

    Se descartan el encabezado repetido y el pie, que es solo el número de página y solo si es el
    último renglón con contenido: un número suelto en otra parte es contenido (`sifen/artifacts`).
    """
    kept = [
        line
        for line in lines
        if any(not c["text"].isspace() for c in line)
        and "".join(c["text"] for c in line).strip() != NT_HEADER
    ]
    if kept and "".join(c["text"] for c in kept[-1]).strip() == str(page):
        kept.pop()
    return kept


def _paragraphs(lines: list[list[Char]]) -> Iterator[list[Char]]:
    """Párrafos de prosa: corta por interlineado y por renglón corto.

    El interlineado solo no alcanza: un título y el párrafo que le sigue están a la misma
    distancia que dos renglones del mismo párrafo. Un renglón que termina lejos del margen
    derecho cierra el párrafo, que es lo que distingue al título del texto que envuelve.
    """
    if not lines:
        return
    margin = max(c["x1"] for line in lines for c in line)
    width = margin - min(c["x0"] for line in lines for c in line)
    current = list(lines[0])
    for prev, line in zip(lines, lines[1:], strict=False):
        height = max(c["bottom"] - c["top"] for c in line)
        ragged = margin - max(c["x1"] for c in prev) > width * RAGGED
        if ragged or line[0]["top"] - prev[0]["top"] > height * PROSE:
            yield current
            current = []
        current += line
    yield current


def _page_blocks(page: Page) -> list[Block]:
    number = page.page_number
    marks = marks_of(page)

    def change_of(char: Char) -> Change | None:
        return _change_at(marks, char)

    found = grids(page.rects)
    inside: dict[int, dict[tuple[int, int], list[Char]]] = {g: {} for g in range(len(found))}
    loose: list[Char] = []
    for char in page.chars:
        where = _locate(found, char)
        if where is None:
            loose.append(char)
        else:
            g, r, col = where
            inside[g].setdefault((r, col), []).append(char)
    blocks: list[tuple[float, Block]] = [
        (grid.top, _table(grid, number, inside[g], change_of)) for g, grid in enumerate(found)
    ]
    for chars in _paragraphs(_prose_lines(text_lines(loose), number)):
        runs = runs_of(chars, change_of, paragraph=math.inf)
        if runs:
            blocks.append((chars[0]["top"], TextBlock(page=number, role="P", runs=runs)))
    return [block for _, block in sorted(blocks, key=lambda pair: pair[0])]


def extract_geometric(path: Path, pages: Iterable[int] | None = None) -> Document:
    """Extrae la IR por geometría, opcionalmente limitada a `pages` (numeración PDF, base 1)."""
    wanted = set(pages) if pages is not None else None
    blocks: list[Block] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            if wanted is None or page.page_number in wanted:
                blocks.extend(_page_blocks(page))
    return Document(source=Path(path).name, sha256=sha256_of(Path(path)), extractor=EXTRACTOR, blocks=blocks)

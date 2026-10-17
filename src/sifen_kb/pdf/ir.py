# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Representación intermedia (IR) canónica: fuente única de todos los derivados.

Cada bloque sabe de qué página viene. El texto se guarda en tramos (`Run`) con su
marca de cambio, porque un mismo párrafo o celda puede estar resaltado solo en parte.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum


class Change(Enum):
    """Semántica de los resaltados de Word según la leyenda del documento."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass(frozen=True)
class Run:
    text: str
    change: Change | None = None


def runs_text(runs: list[Run]) -> str:
    return "".join(run.text for run in runs)


def split_by_page(text: str, page: int, breaks: list[tuple[int, int]]) -> dict[int, str]:
    """Reparte el texto de un bloque entre sus paginas segun `page_breaks`."""
    parts: dict[int, str] = {}
    start, current = 0, page
    for offset, next_page in breaks:
        parts[current] = parts.get(current, "") + text[start:offset]
        start, current = offset, next_page
    parts[current] = parts.get(current, "") + text[start:]
    return parts


def _page_at(offset: int, page: int, breaks: list[tuple[int, int]]) -> int:
    """Pagina vigente en `offset` dentro del texto concatenado de los tramos."""
    current = page
    for at, next_page in breaks:
        if at <= offset:
            current = next_page
    return current


def split_runs(runs: list[Run], page: int, breaks: list[tuple[int, int]]) -> list[tuple[int, list[Run]]]:
    """Tramos en orden de lectura, cortados en cada salto de pagina.

    Misma logica que `split_by_page` —los saltos son offsets sobre el texto concatenado—, pero a
    nivel de tramos y conservando el orden: un tramo cortado por un salto aporta a las dos paginas.
    Un salto en el offset 0 significa que todo el contenido esta en la pagina siguiente.
    """
    segments: list[tuple[int, list[Run]]] = []

    def add(number: int, run: Run) -> None:
        if segments and segments[-1][0] == number:
            segments[-1][1].append(run)
        else:
            segments.append((number, [run]))

    offset = 0
    for run in runs:
        end = offset + len(run.text)
        inner = [(at - offset, next_page) for at, next_page in breaks if offset < at < end]
        for number, text in split_by_page(run.text, _page_at(offset, page, breaks), inner).items():
            if text:
                add(number, Run(text, run.change))
        offset = end
    return segments


BBox = tuple[float, float, float, float]  # x0, top, x1, bottom (coordenadas de pdfplumber)


@dataclass
class Cell:
    runs: list[Run]
    header: bool = False
    # Rectangulo que cubren sus caracteres en su pagina; None si la celda esta vacia.
    bbox: BBox | None = None
    # Columna (base 0) segun el encabezado de la tabla; None mientras no se infiere (T-103).
    col: int | None = None
    # Filas que ocupa hacia abajo (combinacion vertical).
    row_span: int = 1
    # Columnas que ocupa hacia la derecha desde `col` (p. ej. el titulo de una tabla).
    col_span: int = 1
    # (offset, pagina) donde el texto de la celda pasa a otra pagina, como en `TextBlock`: lo llena
    # `continuity._join_cells` al fusionar una fila partida por el borde de pagina (T-104).
    page_breaks: list[tuple[int, int]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return runs_text(self.runs)


@dataclass
class Row:
    cells: list[Cell]
    # Pagina de la fila; None = la de su tabla. Una tabla unida entre paginas la necesita (T-104).
    page: int | None = None


@dataclass
class Table:
    page: int
    rows: list[Row]
    kind: str = "table"


@dataclass
class TextBlock:
    """Párrafo, encabezado, ítem de lista, entrada de índice, etc. (`role` = etiqueta PDF)."""

    page: int
    role: str
    runs: list[Run]
    level: int | None = None
    # (offset, pagina) donde el texto pasa a otra pagina: el bloque continua en las siguientes.
    page_breaks: list[tuple[int, int]] = field(default_factory=list)
    kind: str = "text"

    @property
    def text(self) -> str:
        return runs_text(self.runs)


@dataclass
class Figure:
    """Imagen o diagrama. `runs` guarda el texto dibujado dentro (etiquetas de cuadros de texto);
    su orden de lectura no es confiable y no debe presentarse como prosa."""

    page: int
    alt_text: str | None
    runs: list[Run] = field(default_factory=list)
    page_breaks: list[tuple[int, int]] = field(default_factory=list)
    kind: str = "figure"

    @property
    def text(self) -> str:
        return runs_text(self.runs)


Block = Table | TextBlock | Figure


@dataclass
class Document:
    source: str
    sha256: str
    extractor: str
    blocks: list[Block] = field(default_factory=list)

    def to_json(self) -> str:
        """Serialización determinista: mismas entradas → mismos bytes."""
        data = asdict(self)
        return json.dumps(data, default=_encode, ensure_ascii=False, indent=1, sort_keys=True)


def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"no serializable: {type(value).__name__}")

# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""V6 — conservación de colores: los resaltados de la IR frente a los medidos en la página.

Ruta independiente de `tagged.PageIndex`: recorre *todos* los caracteres de la página y les asigna
un cambio según el rectángulo relleno que contiene su centro, sin pasar por el árbol de estructura
ni por los MCID. Al comparar los multiconjuntos de caracteres por página y por tipo de cambio,
detecta resaltados perdidos, duplicados o mal atribuidos por la normalización de tramos.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pdfplumber
from pdfplumber.page import Page

from sifen_kb.pdf.ir import Change, Document, Run, Table, split_runs
from sifen_kb.pdf.tagged import HIGHLIGHTS
from sifen_kb.pdf.verify import CharDiff, compare_chars

Rect = dict


def _rgb(color: object) -> tuple[float, ...]:
    """Color de relleno redondeado; `()` si no es una tupla de numeros."""
    if isinstance(color, (list, tuple)) and all(isinstance(x, (int, float)) for x in color):
        return tuple(round(x, 2) for x in color)
    return ()


def highlight_rects(page: Page) -> list[tuple[Rect, Change]]:
    """Rectángulos rellenos con uno de los colores de la leyenda."""
    marks: list[tuple[Rect, Change]] = []
    for rect in page.rects:
        change = HIGHLIGHTS.get(_rgb(rect.get("non_stroking_color")))
        if rect.get("fill") and change is not None:
            marks.append((rect, change))
    return marks


def page_marked_text(page: Page) -> dict[Change, str]:
    """Caracteres de la página cuyo centro cae dentro de un resaltado, por tipo de cambio."""
    marks = highlight_rects(page)
    found: dict[Change, list[str]] = {change: [] for change in Change}
    for char in page.chars:
        cx = (char["x0"] + char["x1"]) / 2
        cy = (char["top"] + char["bottom"]) / 2
        for rect, change in marks:
            if rect["x0"] <= cx <= rect["x1"] and rect["top"] <= cy <= rect["bottom"]:
                found[change].append(char["text"])
                break
    return {change: "".join(text) for change, text in found.items()}


def runs_by_page(runs: list[Run], page: int, breaks: list[tuple[int, int]]) -> dict[int, list[Run]]:
    """Reparte los tramos entre sus paginas conservando la marca de cambio (`ir.split_runs`)."""
    parts: dict[int, list[Run]] = {}
    for number, segment in split_runs(runs, page, breaks):
        parts.setdefault(number, []).extend(segment)
    return parts


def ir_marked_text(doc: Document) -> dict[int, dict[Change, str]]:
    """Texto marcado en la IR por pagina y tipo de cambio.

    Cada fila de tabla va a `row.page or table.page`: una tabla unida entre paginas (T-104)
    reparte sus filas entre las paginas que ocupa, y una celda fusionada de una fila partida se
    reparte con sus propios `Cell.page_breaks`.
    """
    pages: dict[int, dict[Change, list[str]]] = {}

    def add(page: int, run: Run) -> None:
        found = pages.setdefault(page, {change: [] for change in Change})
        if run.change is not None:
            found[run.change].append(run.text)

    for block in doc.blocks:
        if isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    page = row.page or block.page
                    for number, runs in runs_by_page(cell.runs, page, cell.page_breaks).items():
                        for run in runs:
                            add(number, run)
        else:
            for page, runs in runs_by_page(block.runs, block.page, block.page_breaks).items():
                for run in runs:
                    add(page, run)
    return {page: {c: "".join(t) for c, t in found.items()} for page, found in pages.items()}


def color_conservation(doc: Document, pdf: Path, pages: Iterable[int]) -> dict[int, dict[Change, CharDiff]]:
    """Compara, por pagina y tipo de cambio, los caracteres marcados en la IR con los medidos."""
    marked = ir_marked_text(doc)
    report: dict[int, dict[Change, CharDiff]] = {}
    with pdfplumber.open(pdf) as opened:
        for number in pages:
            measured = page_marked_text(opened.pages[number - 1])
            found = marked.get(number, {})
            report[number] = {
                change: compare_chars(reference=measured[change], candidate=found.get(change, ""))
                for change in Change
            }
    return report

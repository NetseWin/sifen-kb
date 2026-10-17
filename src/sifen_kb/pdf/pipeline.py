# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Pipeline único: extracción del árbol, unión de tablas continuadas y, a pedido, reglas SIFEN.

Un PDF sin árbol de estructura (sin etiquetas) va por la ruta geométrica: misma IR.

Markdown, campos.json y validaciones.json salen de este mismo documento, así no difieren entre sí.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pdfplumber.structure import StructTreeMissing

from sifen_kb.pdf.continuity import merge_continued_tables
from sifen_kb.pdf.geometry import extract_geometric
from sifen_kb.pdf.ir import Document
from sifen_kb.pdf.tagged import extract_tagged


def load(pdf: Path, pages: Iterable[int] | None = None, sifen: bool = False) -> Document:
    wanted = list(pages) if pages is not None else None
    try:
        extracted = extract_tagged(pdf, pages=wanted)
    except StructTreeMissing:
        extracted = extract_geometric(pdf, pages=wanted)
    doc = merge_continued_tables(extracted)
    if sifen:
        from sifen_kb.pdf.sifen.sections import promote_sections

        doc = promote_sections(doc)
    return doc

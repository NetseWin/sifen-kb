# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Artefactos de página de las Notas Técnicas: lo que queda fuera del árbol y V1 debe descontar.

El pie de las NT es solo el número de página. Se descarta únicamente la última línea no vacía y
solo si es exactamente ese número: un número suelto en otra línea es contenido y V1 debe verlo.
El encabezado repetido (`NT_HEADER`) queda fuera del árbol en las NT más antiguas y dentro en
otras: se descarta de los dos lados, solo como línea o bloque completo.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from sifen_kb.pdf.ir import Document, TextBlock
from sifen_kb.pdf.verify import CharDiff, compare_chars, ir_page_text, poppler_page_text

NT_HEADER = "Sistema Integrado de Facturación Electrónica Nacional"


def strip_nt_header(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line.strip() != NT_HEADER).strip("\n")


def _without_header(doc: Document) -> Document:
    blocks = [b for b in doc.blocks if not (isinstance(b, TextBlock) and b.text == NT_HEADER)]
    return replace(doc, blocks=blocks)


def strip_nt_footer(text: str, page: int) -> str:
    lines = text.rstrip().splitlines()
    if lines and lines[-1].strip() == str(page):
        lines.pop()
    return "\n".join(lines).rstrip()


def nt_text_conservation(doc: Document, pdf: Path, pages: Iterable[int]) -> dict[int, CharDiff]:
    """V1 para una NT: como `verify.text_conservation`, descontando encabezado y pie."""
    ir_text = ir_page_text(_without_header(doc))
    return {
        page: compare_chars(
            reference=strip_nt_header(strip_nt_footer(poppler_page_text(pdf, page), page)),
            candidate=ir_text.get(page, ""),
        )
        for page in pages
    }

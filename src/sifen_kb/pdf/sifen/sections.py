# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Títulos de los grupos y subgrupos de campos del MT V150: de ítem de lista o párrafo a encabezado.

Word etiquetó los títulos de la tabla de formato de campos como `LI` o `P`, así que el árbol
del PDF no los declara como encabezados. Se reconocen por su forma completa: prefijo del grupo,
punto, título y, cerrando el bloque, el rango de IDs del grupo con ese mismo prefijo
(`AA. ... (AA001-AA009)`, `D1. ... (D010-D099)`). Nada más se promueve: un ítem de lista normal
sigue siendo un ítem.
"""

from __future__ import annotations

import re
from dataclasses import replace

from sifen_kb.pdf.ir import Block, Document, TextBlock

# Guion del rango: el documento usa el ASCII y también rayas Unicode (D001 – D299).
_GUION = r"[-\u2010-\u2015]"
# El rango arranca con las letras del grupo, sin los números del subgrupo (D1 → D010-D099); un
# subgrupo puede usar una letra más (E8.1.1 → EA001-EA050). Admite los espacios sueltos que deja
# el PDF (C001 - C099, E605- E619).
_ID = r"(?P=grupo)[A-Z]?\d{3}"
_RANGO = rf"\(\s*{_ID}\s*{_GUION}\s*{_ID}\s*\)"
# Grupo con punto (`A.`) o subgrupo numerado con punto final opcional (`D2.1`, `E9.3.1.`).
SECTION = re.compile(
    rf"(?P<grupo>[A-Z]{{1,2}})(?:(?P<subgrupo>\d+(?:\.\d+)*)\.?|\.) (?P<titulo>.*\S)\s*{_RANGO}"
)


def level_of(text: str) -> int | None:
    """Nivel del título: 2 para el grupo y uno más por cada número del subgrupo (D2.1 → 4),
    hasta 6; None si no es un título."""
    match = SECTION.fullmatch(text.strip())
    if match is None:
        return None
    depth = len(match["subgrupo"].split(".")) if match["subgrupo"] else 0
    return min(2 + depth, 6)


def promote_sections(doc: Document) -> Document:
    """Devuelve un Document nuevo con los títulos de grupo convertidos en encabezados."""
    blocks: list[Block] = [
        _promoted(block) if isinstance(block, TextBlock) else block for block in doc.blocks
    ]
    return replace(doc, blocks=blocks)


def _promoted(block: TextBlock) -> TextBlock:
    """Copia del bloque con su nivel de encabezado; el original queda intacto."""
    if block.level is not None:  # el árbol ya dijo el nivel: manda el árbol.
        return block
    level = level_of(block.text)
    return block if level is None else replace(block, level=level)

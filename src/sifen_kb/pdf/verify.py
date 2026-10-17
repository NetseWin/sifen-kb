# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Verificaciones independientes de la IR.

V1 — conservación de texto: el multiconjunto de caracteres (sin espacios) de cada página en la IR
debe coincidir con el que produce `pdftotext` (poppler), otro motor de extracción. Detecta texto
perdido o duplicado; no mide orden. Solo se descuentan artefactos declarados (p. ej. pie de página).

V7 — reproducibilidad: dos corridas en procesos separados, con distinta semilla de hash, dan la
misma IR byte a byte.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from sifen_kb.pdf.ir import Document, Table, split_by_page

# Pie de página del MT V150: queda fuera del árbol de etiquetas (auditoría §3).
SIFEN_FOOTER = re.compile(r"septiembre de 2019\s+\d+")


@dataclass(frozen=True)
class CharDiff:
    missing: Counter[str]  # en la referencia, ausentes de la IR
    extra: Counter[str]  # en la IR, ausentes de la referencia

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra


def _chars(text: str) -> Counter[str]:
    # NFKC iguala ligaduras y formas de compatibilidad que cada motor puede expandir distinto.
    return Counter(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def compare_chars(reference: str, candidate: str) -> CharDiff:
    ref, cand = _chars(reference), _chars(candidate)
    return CharDiff(missing=ref - cand, extra=cand - ref)


def ir_page_text(doc: Document) -> dict[int, str]:
    """Texto de la IR por pagina; los bloques que cruzan paginas se reparten con `page_breaks`.

    En una tabla unida entre paginas (T-104) cada fila lleva la suya en `Row.page`, y una celda
    fusionada de una fila partida se reparte con sus propios `Cell.page_breaks`.
    """
    pages: dict[int, list[str]] = defaultdict(list)

    def add(page: int, text: str, breaks: list[tuple[int, int]]) -> None:
        for number, part in split_by_page(text, page, breaks).items():
            if part:
                pages[number].append(part)

    for block in doc.blocks:
        if isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    add(row.page or block.page, cell.text, cell.page_breaks)
        else:
            add(block.page, block.text, block.page_breaks)
    return {page: "\n".join(parts) for page, parts in pages.items()}


def poppler_page_text(pdf: Path, page: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def strip_artifacts(text: str, artifacts: Iterable[re.Pattern[str]]) -> str:
    patterns = list(artifacts)
    return "\n".join(
        line for line in text.splitlines() if not any(p.fullmatch(line.strip()) for p in patterns)
    )


_DIGEST_SCRIPT = """
import hashlib, sys
from pathlib import Path
from sifen_kb.pdf.tagged import extract_tagged
pages = [int(p) for p in sys.argv[2:]]
doc = extract_tagged(Path(sys.argv[1]), pages=pages)
print(hashlib.sha256(doc.to_json().encode()).hexdigest())
"""


def extraction_digest(pdf: Path, pages: Iterable[int], hash_seed: int) -> str:
    """SHA-256 de la IR extraída en un proceso nuevo con `PYTHONHASHSEED=hash_seed`."""
    env = {**os.environ, "PYTHONHASHSEED": str(hash_seed)}
    result = subprocess.run(
        [sys.executable, "-c", _DIGEST_SCRIPT, str(pdf), *map(str, pages)],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout.strip()


def text_conservation(
    doc: Document,
    pdf: Path,
    pages: Iterable[int],
    artifacts: Iterable[re.Pattern[str]] = (),
    dropped_text: Mapping[int, str] | None = None,
) -> dict[int, CharDiff]:
    """V1 sobre `doc`. `dropped_text` es texto que la pagina imprime y la IR ya no guarda por una
    transformacion declarada (los encabezados repetidos que descarta `merge_continued_tables`):
    se suma al candidato, asi que cualquier *otra* perdida sigue apareciendo."""
    ir_text = ir_page_text(doc)
    patterns = list(artifacts)
    dropped = dropped_text or {}
    return {
        page: compare_chars(
            reference=strip_artifacts(poppler_page_text(pdf, page), patterns),
            candidate=ir_text.get(page, "") + "\n" + dropped.get(page, ""),
        )
        for page in pages
    }

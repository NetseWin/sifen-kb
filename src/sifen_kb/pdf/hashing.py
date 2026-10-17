# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""SHA-256 de un archivo (de `pdf_to_md/sources.py`, solo `sha256_of`).

El resto de aquel módulo (manifiesto CSV del script de descarga) no aplica: en sifen-kb las fuentes
y sus hashes los gobierna `sources.manifest.yaml` (`sifen_kb.sources`).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()

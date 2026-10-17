# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_reproducible.py), integrado en sifen-kb bajo MIT.
"""V7: dos corridas independientes producen una IR idéntica byte a byte."""

import corpus_pdf
import pytest

from sifen_kb.pdf.verify import extraction_digest

MANUAL = corpus_pdf.MANUAL


@pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")
def test_separate_processes_with_different_hash_seeds_give_the_same_ir() -> None:
    # Procesos distintos con otra semilla de hash: detecta orden dependiente de sets o dicts.
    first = extraction_digest(MANUAL, range(62, 67), hash_seed=1)
    second = extraction_digest(MANUAL, range(62, 67), hash_seed=2)

    assert len(first) == 64
    assert first == second

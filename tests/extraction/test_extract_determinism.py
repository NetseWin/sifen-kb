"""`sifen extract` es determinista: la semilla de hash y el reparto en tramos no cambian ni un byte de `raw/`.

Complementa a `test_pdf_reproducible.py` (V7 sobre la IR de cinco páginas del MT): aquí se prueba la
cadena COMPLETA de `sifen_kb.extract` (IR → unión de tablas → filas → `pages/`, `index.json`,
`tables.jsonl` y el libro `_ledger`), sobre un subconjunto pequeño del corpus para que sea rápido:

- NT 016, 019, 023 y 024 (tablas de validaciones con celdas combinadas, una fila que cruza páginas y fechas
  en palabras o con rótulo partido) y las páginas 151 a 155 del MT (validaciones con combinación vertical y
  la fila AC05, que cruza de la 153 a la 154);
- dos subprocesos con `PYTHONHASHSEED` distintos deben escribir los mismos bytes;
- partir una fuente en tramos de páginas (y extraerlos en paralelo, como hace `extract_ir`) debe dar los
  mismos bytes que una sola corrida de un solo tramo, aun cuando el corte cae dentro de una tabla.

Orden de magnitud (12 CPU, con otras cargas en la máquina): ~15 s la prueba de semillas (dos procesos en
paralelo), ~15 s la del corte dentro de una tabla del MT y 2-5 s cada NT; ~40 s en total. Sin PDF en
`sources/` se saltan, igual que las demás pruebas de extracción.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import corpus_pdf
import pytest

from sifen_kb.extract import (
    CHUNK_PAGES,
    IR,
    Source,
    _chunks,
    build_doc,
    extract_chunk,
    extract_ir,
    load_fixes,
)
from sifen_kb.pdf.ir import Document

ROOT = corpus_pdf.ROOT
SOURCES = corpus_pdf.sources()
MT = "MT_V150"


def needs(*docs: str) -> pytest.MarkDecorator:
    missing = [d for d in docs if d not in SOURCES]
    return pytest.mark.skipif(bool(missing), reason=f"fuente(s) {', '.join(missing)} no disponible(s)")


def assert_same_files(a: dict[str, str], b: dict[str, str], what: str) -> None:
    """Mismos archivos con los mismos bytes; si no, nombra cuáles difieren (sin volcar el contenido)."""
    differing = sorted({k for k in a.keys() | b.keys() if a.get(k) != b.get(k)})
    assert not differing, f"{what}: {len(differing)} archivos difieren, p. ej. {differing[:5]}"


# --- el reparto en tramos (`_chunks`) ----------------------------------------------------------------


def test_chunks_partition_every_document_without_gaps_or_overlaps() -> None:
    assert _chunks(0) == []
    for size in (1, 2, 5, 36, CHUNK_PAGES):
        for npages in range(1, 400):
            chunks = _chunks(npages, size)
            covered = [p for first, last in chunks for p in range(first, last + 1)]
            assert covered == list(range(1, npages + 1)), (npages, size, chunks)
            lengths = [last - first + 1 for first, last in chunks]
            assert min(lengths) >= 1
            assert max(lengths) - min(lengths) <= 1, f"reparto desparejo: {(npages, size, chunks)}"
            assert max(lengths) <= max(size * 3 // 2 + 1, 1), (
                f"tramo demasiado largo: {(npages, size, chunks)}"
            )


def test_chunks_known_splits() -> None:
    assert len(_chunks(217)) == 6  # el MT, como dice la documentación de extract
    assert _chunks(217)[0] == (1, 36) and _chunks(217)[-1][1] == 217
    assert _chunks(5, 1) == [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]
    assert _chunks(5, 99) == [(1, 5)]
    assert _chunks(1) == [(1, 1)]


# --- la semilla de hash no cambia ningún byte --------------------------------------------------------

SEED_DOCS = ("NT_016", "NT_019", "NT_023", "NT_024")
MT_FIRST, MT_LAST = 151, 155

# Corre en un proceso nuevo con otra PYTHONHASHSEED: extrae las NT con `generate` (todo el camino de
# `sifen extract` salvo el reparto en procesos), las páginas del MT con `extract_chunk` + `build_doc`, y
# arma el libro de cambios con ese MT parcial. Imprime el sha256 de cada archivo que escribiría.
_SEED_SCRIPT = """
import hashlib, json, sys
from pathlib import Path
from sifen_kb.extract import IR, build_doc, extract_chunk, extractor_info, generate, load_fixes, pdf_sources
from sifen_kb.extract_ledger import build_ledger
from sifen_kb.load import load_manifest

root, first, last, *docs = sys.argv[1:]
root, first, last = Path(root), int(first), int(last)
fixes = load_fixes(root)
sources = {s.doc: s for s in pdf_sources(root, load_manifest(root))}
files, outputs = generate(root, [sources[d] for d in docs], fixes, ledger=False, jobs=1)
chunk = extract_chunk(str(sources["MT_V150"].path), first, last)
mt = build_doc(sources["MT_V150"], IR(chunk.extractor, chunk.blocks, chunk.printed, last), fixes)
files.update(mt.files)
ledger = build_ledger(mt.ledger, [o.ledger for o in outputs], extractor_info())
files.update({f"raw/_ledger/{name}": text for name, text in ledger.items()})
print(json.dumps({
    "hash_probe": hash("sifen-kb"),
    "rows": mt.rows + sum(o.rows for o in outputs),
    "ledger_lines": len(ledger["changes.jsonl"].splitlines()),
    "sha256": {path: hashlib.sha256(text.encode("utf-8")).hexdigest() for path, text in sorted(files.items())},
}))
"""


def _spawn_extraction(hash_seed: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", _SEED_SCRIPT, str(ROOT), str(MT_FIRST), str(MT_LAST), *SEED_DOCS],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=ROOT,
        env={**os.environ, "PYTHONHASHSEED": str(hash_seed)},
    )


def _finish(proc: subprocess.Popen[str], hash_seed: int) -> dict[str, Any]:
    out, err = proc.communicate()
    assert proc.returncode == 0, f"la extracción con PYTHONHASHSEED={hash_seed} falló:\n{err}"
    return json.loads(out)


@needs(MT, *SEED_DOCS)
def test_extraction_writes_the_same_bytes_with_different_hash_seeds() -> None:
    first, second = _spawn_extraction(1), _spawn_extraction(2)  # en paralelo: son independientes
    a, b = _finish(first, 1), _finish(second, 2)

    # Control: las semillas se aplicaron de verdad (si no, la comparación no probaría nada) y se extrajo algo.
    assert a["hash_probe"] != b["hash_probe"]
    assert a["rows"] > 20 and a["ledger_lines"] > 0
    assert {"raw/_ledger/changes.jsonl", "raw/_ledger/index.json"} <= a["sha256"].keys()
    assert len(a["sha256"]) == len(b["sha256"])

    assert_same_files(a["sha256"], b["sha256"], "PYTHONHASHSEED=1 vs 2")


# --- por tramos == una sola corrida ------------------------------------------------------------------


def _same_ir(single: IR, chunked: IR, source: Source) -> None:
    def as_json(ir: IR) -> str:
        return Document(
            source=source.path.name, sha256=source.sha256, extractor=ir.extractor, blocks=ir.blocks
        ).to_json()

    assert chunked.extractor == single.extractor
    assert chunked.npages == single.npages
    assert chunked.printed == single.printed
    assert len(chunked.blocks) == len(single.blocks)
    assert as_json(chunked) == as_json(single), "la IR por tramos no es la de la corrida única"


@pytest.mark.parametrize("doc", ["NT_010", "NT_016", "NT_019"])
def test_note_chunked_parallel_extraction_equals_a_single_chunk(doc: str) -> None:
    if doc not in SOURCES:
        pytest.skip(f"fuente {doc} no disponible")
    source = SOURCES[doc]
    fixes = load_fixes(ROOT)

    single = extract_ir([source], jobs=1, chunk_pages=1000)[doc]
    chunked = extract_ir([source], jobs=3, chunk_pages=1)[doc]  # un tramo por página y en procesos aparte
    assert len(_chunks(single.npages, 1000)) == 1
    assert len(_chunks(chunked.npages, 1)) == chunked.npages >= 4

    _same_ir(single, chunked, source)
    assert_same_files(
        build_doc(source, single, fixes).files, build_doc(source, chunked, fixes).files, f"{doc}: tramos"
    )


@needs(MT)
def test_manual_cut_inside_a_continued_table_loses_nothing() -> None:
    mt = SOURCES[MT]
    fixes = load_fixes(ROOT)
    path = str(mt.path)
    # Un corte entre las páginas 153 y 154, donde la fila AC05 continúa: se parte la fila al medio.
    with ProcessPoolExecutor(max_workers=3) as pool:
        whole, left, right = pool.map(
            extract_chunk, [path] * 3, [MT_FIRST, MT_FIRST, 154], [MT_LAST, 153, MT_LAST]
        )
    assert whole.extractor == left.extractor == right.extractor

    single = IR(whole.extractor, whole.blocks, whole.printed, MT_LAST)
    chunked = IR(left.extractor, left.blocks + right.blocks, {**left.printed, **right.printed}, MT_LAST)
    _same_ir(single, chunked, mt)

    expected = build_doc(mt, single, fixes)
    got = build_doc(mt, chunked, fixes)
    assert_same_files(expected.files, got.files, "MT 151-155: tramos 151-153 + 154-155")

    # Control: el corte cayó donde decía, o sea que la prueba no es vacua.
    rows = [json.loads(line) for line in expected.files[f"raw/{MT}/{mt.sha12}/tables.jsonl"].splitlines()]
    assert any(r["key"] == "AC05" and r["pages"] == [153, 154] for r in rows)

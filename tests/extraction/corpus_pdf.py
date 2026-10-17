"""Corpus oficial para las pruebas de extracción: los PDF registrados en `sources.manifest.yaml`.

Las pruebas vendorizadas de pdf_to_md esperan su layout (`sifen-v150/Manual_Tecnico_SIFEN_V150.pdf`,
`sifen-v150/Notas_Tecnicas/NT_E_KUATIA_0NN_MT_V150.pdf`). Este módulo lo arma con enlaces
simbólicos (o copias, si el sistema no permite enlaces) en `build/test-corpus/` a partir de la
revisión más reciente de cada DocId del manifiesto de sifen-kb. El nombre del archivo importa:
`Document.source` lo toma y algunas pruebas lo comparan.

Sin manifiesto o sin el archivo, las rutas no existen y las pruebas se saltan (skip limpio).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from sifen_kb.extract import Source, pdf_sources
from sifen_kb.load import load_manifest

ROOT = Path(__file__).resolve().parents[2]
FUENTES = ROOT / "build" / "test-corpus" / "sifen-v150"
MANUAL = FUENTES / "Manual_Tecnico_SIFEN_V150.pdf"
NOTAS = FUENTES / "Notas_Tecnicas"


def sources() -> dict[str, Source]:
    """Revisiones PDF vigentes del manifiesto cuyo archivo existe, por DocId."""
    try:
        found = pdf_sources(ROOT, load_manifest(ROOT))
    except OSError, ValueError:  # manifiesto ausente o inválido: no hay corpus
        return {}
    return {s.doc: s for s in found if s.path.is_file()}


def _mirror_name(doc: str) -> Path | None:
    if doc == "MT_V150":
        return MANUAL
    if doc.startswith("NT_"):
        return NOTAS / f"NT_E_KUATIA_{doc[3:]}_MT_V150.pdf"
    return None


def _link(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    try:
        os.symlink(target, link)
    except OSError:
        shutil.copyfile(target, link)


def build_mirror() -> None:
    for doc, src in sources().items():
        name = _mirror_name(doc)
        if name is not None:
            _link(src.path, name)


build_mirror()

# Testigo independiente (V1): poppler `pdftotext`. No es dependencia de sifen-kb: sin él, se salta.
NEEDS_PDFTOTEXT = pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="poppler pdftotext no instalado (testigo opcional de V1)"
)

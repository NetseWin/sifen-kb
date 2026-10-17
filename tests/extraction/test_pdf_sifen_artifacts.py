# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_sifen_artifacts.py), integrado en sifen-kb bajo MIT.
"""Pie de página de las NT: solo el número de página, en la última línea."""

import corpus_pdf
import pytest

from sifen_kb.pdf.sifen.artifacts import nt_text_conservation, strip_nt_footer, strip_nt_header
from sifen_kb.pdf.tagged import extract_tagged

NT023 = corpus_pdf.NOTAS / "NT_E_KUATIA_023_MT_V150.pdf"


def test_only_the_last_line_with_the_exact_page_number_is_dropped() -> None:
    text = "Longitud\n   1\ncuerpo\n\n        3\n\n"

    assert strip_nt_footer(text, page=3) == "Longitud\n   1\ncuerpo"


def test_a_last_line_with_another_number_is_kept() -> None:
    # Un "1" suelto que no es el número de la página es contenido: V1 debe seguir viéndolo.
    assert strip_nt_footer("cuerpo\n  1\n", page=3) == "cuerpo\n  1"


@pytest.mark.skipif(not NT023.exists(), reason="fuente NT-023 no copiada")
@corpus_pdf.NEEDS_PDFTOTEXT
def test_nt023_loses_and_duplicates_nothing() -> None:
    pages = range(1, 5)
    doc = extract_tagged(NT023, pages=pages)

    report = nt_text_conservation(doc, NT023, pages)

    for page, result in report.items():
        assert result.ok, (page, result.missing.most_common(10), result.extra.most_common(10))


def test_the_running_header_is_dropped_only_as_a_whole_line() -> None:
    text = "   Sistema Integrado de Facturación Electrónica Nacional\nNOTA TÉCNICA N° 2\n"

    assert strip_nt_header(text) == "NOTA TÉCNICA N° 2"
    assert strip_nt_header("Ver Sistema Integrado de Facturación Electrónica Nacional") == (
        "Ver Sistema Integrado de Facturación Electrónica Nacional"
    )


NOTES = NT023.parent


@pytest.mark.skipif(not NT023.exists(), reason="fuentes NT no copiadas")
@pytest.mark.parametrize("number", ["002", "010", "016"])
@corpus_pdf.NEEDS_PDFTOTEXT
def test_older_notes_with_the_header_outside_the_tree_close_v1(number: str) -> None:
    pdf = NOTES / f"NT_E_KUATIA_{number}_MT_V150.pdf"
    doc = extract_tagged(pdf)
    pages = sorted({b.page for b in doc.blocks})

    report = nt_text_conservation(doc, pdf, pages)

    for page, result in report.items():
        assert result.ok, (page, result.missing.most_common(10), result.extra.most_common(10))

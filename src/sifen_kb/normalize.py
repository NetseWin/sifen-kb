"""Única normalización de texto del proyecto (docs/arquitectura.md §H, condición 2).

La aplica `extract` al escribir `tables.jsonl` (que conserva además `raw_text`) y la usan
TODAS las comparaciones (celdas, citas, fechas). Si se cambia, cambia la evidencia: hay que
regenerar `raw/` y volver a verificar `kb/`.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

_SOFT_HYPHEN = "­"
_SPACES = re.compile(r"[ \t  -   　]+")
_DATE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


def normalize_text(s: str) -> str:
    """NFC; sin guion blando; saltos de línea dentro de una celda unidos con un espacio
    (sin espacio si la línea anterior termina en "-"); espacios colapsados; strip.

    Idempotente: normalize_text(normalize_text(x)) == normalize_text(x).
    """
    s = unicodedata.normalize("NFC", s).replace(_SOFT_HYPHEN, "")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACES.sub(" ", ln).strip() for ln in s.split("\n")]
    out = ""
    for ln in lines:
        if not ln:
            continue
        if not out:
            out = ln
        elif out.endswith("-"):
            out += ln
        else:
            out += " " + ln
    return _SPACES.sub(" ", out).strip()


def parse_date_literal(literal: str) -> date | None:
    """'01/01/2025' -> date(2025, 1, 1). Devuelve None si el literal no es dd/mm/aaaa."""
    m = _DATE.match(normalize_text(literal))
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    return date(y, mo, d)


def sha12(sha256_hex: str) -> str:
    return sha256_hex[:12]

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
_DATE = re.compile(r"^(\d{1,2})([/-])(\d{1,2})\2(\d{4})$")
_DATE_WORDS = re.compile(r"^(\d{1,2}) de ([a-záéíóú]+) del? (\d{4})$", re.IGNORECASE)
_MONTHS: dict[str, int] = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


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
    """Fecha tal como la escriben las NT -> `date`; None si el literal no es una fecha.

    Formas reales del corpus: '01/01/2025' (NT 019, 021, 024…), '14-10-2019' (NT 001) y en palabras,
    '30 de agosto de 2024' (NT 023), '17 de Junio del 2023' (NT 013), con «setiembre» o
    «septiembre». Una fecha imposible (31/02/2024) también da None.
    """
    s = normalize_text(literal)
    if m := _DATE.match(s):
        d, mo, y = int(m[1]), int(m[3]), int(m[4])
    elif (m := _DATE_WORDS.match(s)) and m[2].lower() in _MONTHS:
        d, mo, y = int(m[1]), _MONTHS[m[2].lower()], int(m[3])
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def sha12(sha256_hex: str) -> str:
    return sha256_hex[:12]

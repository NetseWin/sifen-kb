from datetime import date

import pytest

from sifen_kb.normalize import normalize_text, parse_date_literal
from sifen_kb.yamlio import KBYamlError, dump_kb, is_canonical, load_kb_text


def test_kbloader_codes_stay_strings():
    data = load_kb_text("a: 0160\nb: 0260\nc: NO\nd: on\ne: 1.50\nf: 2024-04-01\ng: 1321\nh: 1:30\n")
    assert data == {
        "a": "0160",
        "b": "0260",
        "c": "NO",
        "d": "on",
        "e": "1.50",
        "f": "2024-04-01",
        "g": "1321",
        "h": "1:30",
    }


def test_kbloader_bool_and_null_only():
    assert load_kb_text("a: true\nb: false\nc: null\nd:\ne: ~\n") == {
        "a": True,
        "b": False,
        "c": None,
        "d": None,
        "e": None,
    }
    assert load_kb_text("a: True\n") == {"a": "True"}


@pytest.mark.parametrize(
    "text",
    [
        "a: 1\na: 2\n",
        "a: &x 1\nb: *x\n",
        "a: !!int 5\n",
        "base: &b {x: 1}\nother:\n  <<: *b\n",
    ],
)
def test_kbloader_rejects_duplicates_anchors_aliases_tags(text):
    with pytest.raises(KBYamlError, match="línea"):
        load_kb_text(text)


def test_fmt_roundtrip_detects_comments_and_truncation():
    canonical = dump_kb({"code": "0160", "message": "Texto con # numeral", "list": ["a", "b"]})
    assert is_canonical(canonical)
    assert not is_canonical(canonical + "# comentario\n")
    # Un " #" en un escalar plano trunca el texto en silencio: el roundtrip lo delata.
    assert load_kb_text("m: Monto # total\n") == {"m": "Monto"}
    assert not is_canonical("m: Monto # total\n")


def test_dump_uses_block_literal_for_long_text_and_keeps_unicode():
    obs = "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), el monto es mayor o igual a 7.000.000"
    out = dump_kb({"observation": obs, "code": "1321", "flag": "true"})
    assert "observation: |-\n" in out
    assert "≠" in out
    assert "code: 1321\n" in out
    assert "flag: 'true'\n" in out
    assert load_kb_text(out)["observation"] == obs
    assert load_kb_text(out)["flag"] == "true"


def test_dump_ints_dates_and_long_urls_as_plain_scalars():
    from datetime import UTC, datetime

    url = "https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_024_MT_V150.pdf/abc?t=1734617000000"
    out = dump_kb(
        {"size": 5204470, "d": date(2025, 1, 1), "at": datetime(2026, 10, 17, 19, 5, tzinfo=UTC), "url": url}
    )
    assert "size: 5204470\n" in out
    assert "d: 2025-01-01\n" in out
    assert "at: 2026-10-17T19:05:00+00:00\n" in out
    assert f"url: {url}\n" in out
    assert "!!" not in out
    assert is_canonical(out)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Tipo de documento\nde identidad", "Tipo de documento de identidad"),
        ("1-15p(0-\n8)", "1-15p(0-8)"),
        ("Recep­tor", "Receptor"),
        ("  a    b \t c  ", "a b c"),
        ("é", "é"),
        ("", ""),
        ("\n\n x \n\n", "x"),
    ],
)
def test_normalize_text_cases(raw, expected):
    assert normalize_text(raw) == expected


@pytest.mark.parametrize("raw", ["a\nb-\nc", "  x  y ", "1-15p(0-\n8)", "Á­B\nC"])
def test_normalize_idempotent(raw):
    once = normalize_text(raw)
    assert normalize_text(once) == once


def test_date_literal_parsing():
    assert parse_date_literal("01/01/2025") == date(2025, 1, 1)
    assert parse_date_literal(" 1/1/2024 ") == date(2024, 1, 1)
    assert parse_date_literal("a definir") is None
    assert parse_date_literal("2025-01-01") is None

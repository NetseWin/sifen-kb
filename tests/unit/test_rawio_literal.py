"""`RawRow.literal`: el color solo elimina texto en el MT V150 (único documento con leyenda)."""

from pathlib import Path

import pytest

from sifen_kb.rawio import RawRow, iter_rows

ROOT = Path(__file__).resolve().parents[2]


def row(doc: str, marks: list[dict], raw_obs: str) -> RawRow:
    return RawRow(
        doc=doc,
        sha12="0" * 12,
        page=1,
        key="D208c",
        occ=1,
        table="validations",
        header=[],
        cells={"observation": raw_obs},
        raw_cells={"observation": raw_obs},
        marks=marks,
    )


RED = [{"attr": "observation", "change": "deleted", "start": 9, "end": 17, "text": "o igual "}]


def test_literal_in_mt_drops_red_text():
    r = row("MT_V150", RED, "es mayor o igual a 7")
    assert r.literal("observation") == r.current("observation") == "es mayor a 7"


@pytest.mark.parametrize("doc", ["NT_021", "NT_024", "NT_099"])
def test_literal_in_nt_keeps_red_text(doc):
    r = row(doc, RED, "es mayor o igual a 7")
    assert r.current("observation") == "es mayor a 7"
    assert r.literal("observation") == "es mayor o igual a 7"


@pytest.mark.parametrize(("doc", "sha12"), [("NT_021", "1e716577d874"), ("NT_024", "ccc2d1550e92")])
def test_literal_real_nt_d208c_keeps_d011_exception(doc, sha12):
    """En NT 21/24 el rojo marca texto VIGENTE (sifen.md §5): el literal conserva D011≠13 y ">=."""
    if not (ROOT / "raw" / doc / sha12).is_dir():
        pytest.skip(f"raw/{doc}/{sha12} no disponible")
    (d208c,) = [r for r in iter_rows(ROOT, doc, sha12) if r.key == "D208c"]
    obs = d208c.literal("observation")
    assert "(D011≠13)" in obs and ">=" in obs and "mayor o igual" in obs
    assert "(D011≠13)" not in d208c.current("observation")

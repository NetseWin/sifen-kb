from pathlib import Path

from sifen_kb.load import load_kb
from sifen_kb.yamlio import write_kb_file

ISSUE = {
    "id": "ISS-0001",
    "kind": "ambiguity",
    "affects": [{"subject": "val:DE:D208c"}],
    "statement": "x",
    "blocking": False,
    "status": "open",
}


def test_duplicate_issue_id_is_a_load_error(tmp_path: Path):
    """Dos archivos con el mismo id de Issue no se pisan en silencio: el segundo es un error de carga."""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    write_kb_file(tmp_path / "kb" / "issues" / "ISS-0001.yaml", ISSUE)
    write_kb_file(
        tmp_path / "kb" / "issues" / "ISS-0001b.yaml", {**ISSUE, "statement": "y"}
    )  # se carga después
    kb = load_kb(tmp_path)
    assert kb.issues["ISS-0001"].statement == "x"
    assert any("ISS-0001 duplicado" in e for e in kb.errors)

"""Pruebas del check `pr-scope` (`sifen_kb.prscope`) con repos git temporales."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from sifen_kb import prscope
from sifen_kb.prscope import Change, classify, evaluate, is_extractor_code, is_secret_file, main

BASE_FILES = {
    "README.md": "# sifen-kb\n",
    "CLAUDE.md": "reglas\n",
    "pyproject.toml": "[project]\nname='x'\n",
    "docs/uso.md": "uso\n",
    "kb/validations/DE/D208c.yaml": "key: val:DE:D208c\n",
    "kb/_meta.yaml": "baseline: x\n",
    "tests/golden/temporal.yaml": "- {}\n",
    "tests/unit/test_algo.py": "def test_a(): pass\n",
    "cases/2026/caso.md": "caso\n",
    "curation/prompts/curar_entidad.md": "prompt\n",
    "src/sifen_kb/__init__.py": "",
    "src/sifen_kb/extract.py": "x = 1\n",
    "src/sifen_kb/temporal.py": "t = 1\n",
    "src/sifen_kb/pdf/tagged.py": "p = 1\n",
    "sources/NT_001/aaaaaaaaaaaa.pdf": "%PDF-1.7 a\n",
    "sources.manifest.yaml": "revisions: []\n",
    "raw/NT_001/aaaaaaaaaaaa/index.json": "{}\n",
    ".github/workflows/ci.yml": "name: ci\n",
}


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return cp.stdout.strip()


def write(repo: Path, rel: str, text: str = "nuevo\n") -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for rel, text in BASE_FILES.items():
        write(root, rel, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "pr")
    return root


def commit(repo: Path, message: str = "cambio") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def run(repo: Path, capsys, title: str | None = None, base: str = "main") -> tuple[int, str]:
    env = {"PR_TITLE": title} if title is not None else {}
    code = main([base, "--repo", str(repo)], env=env)
    return code, capsys.readouterr().out


# --- clasificación ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("kb/validations/DE/D208c.yaml", "knowledge"),
        ("kb/_meta.yaml", "knowledge"),
        ("tests/golden/temporal.yaml", "knowledge"),
        ("tests/golden/pages/p167.json", "knowledge"),
        ("cases/2026/2026-10-02-caso.md", "knowledge"),
        ("curation/prompts/curar_entidad.md", "knowledge"),
        ("curation/runs/abc.yaml", "knowledge"),
        ("src/sifen_kb/temporal.py", "code"),
        ("tests/unit/test_x.py", "code"),
        ("tests/fixtures/xml/a.xml", "code"),
        ("tests/allowlist_pii.yaml", "code"),
        (".github/workflows/ci.yml", "code"),
        (".claude/settings.json", "code"),
        ("CLAUDE.md", "code"),
        ("pyproject.toml", "code"),
        ("uv.lock", "code"),
        (".gitignore", "code"),
        (".gitattributes", "code"),
        ("algo_nuevo.py", "code"),
        ("docs/uso.md", "neutral"),
        ("docs/investigacion/pdf.md", "neutral"),
        ("README.md", "neutral"),
        ("CONTRIBUTING.md", "neutral"),
        ("LICENSE", "neutral"),
        ("NOTICE", "neutral"),
        ("sources/NT_024/0123456789ab.pdf", "neutral"),
        ("sources.manifest.yaml", "neutral"),
        ("raw/MT_V150/976cd88c05c3/index.json", "neutral"),
        ("extraction/fixes.yaml", "neutral"),
    ],
)
def test_classify(path, expected):
    assert classify(path) == expected


def test_root_markdown_is_neutral_but_nested_markdown_follows_its_directory():
    assert classify("README.md") == "neutral"
    assert classify("src/LEEME.md") == "code"
    assert classify("kb/nota.md") == "knowledge"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/sifen_kb/extract.py", True),
        ("src/sifen_kb/pdf/tagged.py", True),
        ("tests/unit/test_extract.py", True),
        ("tests/unit/test_pdf_tagged.py", True),
        ("src/sifen_kb/temporal.py", False),
        ("src/sifen_kb/normalize.py", False),
        ("tests/unit/test_temporal.py", False),
    ],
)
def test_is_extractor_code(path, expected):
    assert is_extractor_code(path) is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.p12", True),
        ("x/y/cert.PFX", True),
        ("clave.key", True),
        ("kb/cert.pem", True),
        ("almacen.jks", True),
        ("docs/pemex.md", False),
        ("keyboard.txt", False),
        ("sources/XSD_DIR/2026-10-17/siRecepDE_v150.xsd", False),
    ],
)
def test_is_secret_file(path, expected):
    assert is_secret_file(path) is expected


# --- evaluate (sin git) ----------------------------------------------------------------------------
def test_evaluate_empty_diff_is_ok():
    assert evaluate([]).ok


def test_evaluate_reports_lists_per_scope():
    report = evaluate([Change("M", "kb/a.yaml"), Change("M", "docs/x.md"), Change("A", "kb/b.yaml")])
    assert report.by_scope["knowledge"] == ["kb/a.yaml", "kb/b.yaml"]
    assert report.by_scope["neutral"] == ["docs/x.md"]
    assert report.by_scope["code"] == []
    assert report.ok


# --- main con repos git ----------------------------------------------------------------------------
def test_knowledge_only_pr_passes(repo, capsys):
    write(repo, "kb/validations/DE/D208c.yaml", "key: val:DE:D208c\nversions: []\n")
    write(repo, "tests/golden/temporal.yaml", "- {a: 1}\n")
    write(repo, "cases/2026/otro.md", "otro\n")
    write(repo, "curation/runs/s1.yaml", "session_id: s1\n")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 0
    assert "conocimiento (4)" in out
    assert "pr-scope: OK" in out


def test_code_only_pr_passes(repo, capsys):
    write(repo, "src/sifen_kb/temporal.py", "t = 2\n")
    write(repo, "tests/unit/test_algo.py", "def test_b(): pass\n")
    write(repo, ".github/workflows/ci.yml", "name: ci2\n")
    write(repo, "pyproject.toml", "[project]\nname='y'\n")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 0
    assert "código/configuración (4)" in out


def test_neutral_files_mix_with_anything(repo, capsys):
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    write(repo, "docs/uso.md", "otro uso\n")
    write(repo, "README.md", "# otro\n")
    write(repo, "sources/NT_002/bbbbbbbbbbbb.pdf", "%PDF-1.7 b\n")
    write(repo, "sources.manifest.yaml", "revisions: []\nchecks: []\n")
    write(repo, "raw/NT_002/bbbbbbbbbbbb/index.json", "{}\n")
    commit(repo)
    code, _ = run(repo, capsys)
    assert code == 0
    git(repo, "reset", "-q", "--hard", "main")
    write(repo, "src/sifen_kb/temporal.py", "t = 3\n")
    write(repo, "docs/uso.md", "otro uso\n")
    write(repo, "extraction/fixes.yaml", "fixes: []\n")
    commit(repo)
    code, _ = run(repo, capsys)
    assert code == 0


@pytest.mark.parametrize(
    ("knowledge_file", "code_file"),
    [
        ("kb/validations/DE/D208c.yaml", "src/sifen_kb/temporal.py"),
        ("tests/golden/temporal.yaml", "tests/unit/test_algo.py"),
        ("cases/2026/caso.md", ".github/workflows/ci.yml"),
        ("curation/prompts/curar_entidad.md", "CLAUDE.md"),
        ("kb/_meta.yaml", "pyproject.toml"),
        ("kb/validations/DE/D208c.yaml", ".claude/settings.json"),
    ],
)
def test_mixing_knowledge_and_code_fails(repo, capsys, knowledge_file, code_file):
    write(repo, knowledge_file, "cambio de conocimiento\n")
    write(repo, code_file, "cambio de código\n")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 1
    assert "mezcla conocimiento" in out
    assert knowledge_file in out
    assert code_file in out
    assert "pr-scope: FALLA" in out


def test_mixing_is_detected_across_commits_of_the_same_pr(repo, capsys):
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    commit(repo, "curación")
    write(repo, "src/sifen_kb/temporal.py", "t = 9\n")
    commit(repo, "código")
    code, _ = run(repo, capsys)
    assert code == 1


def test_only_changes_since_merge_base_count(repo, capsys):
    git(repo, "checkout", "-q", "main")
    write(repo, "src/sifen_kb/temporal.py", "cambio posterior en main\n")
    commit(repo, "main avanza")
    git(repo, "checkout", "-q", "pr")
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 0
    assert "src/sifen_kb/temporal.py" not in out


# --- sources/ solo adiciones -----------------------------------------------------------------------
def test_sources_additions_are_allowed(repo, capsys):
    write(repo, "sources/NT_024/cccccccccccc.pdf", "%PDF-1.7 c\n")
    write(repo, "sources/XSD_DIR/2026-11-01/siRecepDE_v150.xsd", "<xs:schema/>\n")
    commit(repo)
    code, _ = run(repo, capsys)
    assert code == 0


def test_sources_modification_fails(repo, capsys):
    write(repo, "sources/NT_001/aaaaaaaaaaaa.pdf", "%PDF-1.7 ALTERADO\n")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 1
    assert "sources/ solo admite ADICIONES" in out
    assert "M sources/NT_001/aaaaaaaaaaaa.pdf" in out


def test_sources_deletion_fails(repo, capsys):
    (repo / "sources/NT_001/aaaaaaaaaaaa.pdf").unlink()
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 1
    assert "D sources/NT_001/aaaaaaaaaaaa.pdf" in out


def test_sources_rename_fails(repo, capsys):
    git(repo, "mv", "sources/NT_001/aaaaaaaaaaaa.pdf", "sources/NT_001/zzzzzzzzzzzz.pdf")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 1
    assert "D sources/NT_001/aaaaaaaaaaaa.pdf" in out


# --- certificados y claves -------------------------------------------------------------------------
@pytest.mark.parametrize(
    "rel", ["cert.p12", "private/firma.pfx", "kb/clave.key", "docs/ejemplo.pem", "sources/NT_099/almacen.jks"]
)
def test_adding_secret_files_fails(repo, capsys, rel):
    write(repo, rel, "binario\n")
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 1
    assert "certificados ni claves" in out
    assert rel in out


def test_deleting_a_secret_file_is_allowed(repo, capsys):
    git(repo, "checkout", "-q", "main")
    write(repo, "viejo.pem", "no debería estar\n")
    commit(repo, "se coló")
    git(repo, "checkout", "-q", "-B", "pr")
    git(repo, "rm", "-q", "viejo.pem")
    commit(repo, "se borra")
    code, _ = run(repo, capsys)
    assert code == 0


# --- excepción extractor-recopy --------------------------------------------------------------------
def extractor_pr(repo: Path) -> None:
    write(repo, "src/sifen_kb/pdf/tagged.py", "p = 2\n")
    write(repo, "raw/NT_001/aaaaaaaaaaaa/index.json", '{"v": 2}\n')
    write(repo, "kb/validations/DE/D208c.yaml", "key: val:DE:D208c\nversions: [recopiado]\n")
    commit(repo)


def test_extractor_exception_requires_title_tag(repo, capsys):
    extractor_pr(repo)
    for title in (None, "Cambia el extractor", "extractor recopy"):
        code, out = run(repo, capsys, title)
        assert code == 1
        assert "extractor-recopy" in out
        assert "mezcla conocimiento" in out


@pytest.mark.parametrize("title", ["extractor-recopy: columnas partidas", "fix [Extractor-Recopy] literales"])
def test_extractor_exception_applies_with_tag(repo, capsys, title):
    extractor_pr(repo)
    code, out = run(repo, capsys, title)
    assert code == 0
    assert "EXCEPCIÓN extractor-recopy aplicada" in out
    assert "kb/validations/DE/D208c.yaml" in out


def test_extractor_exception_via_title_option(repo, capsys):
    extractor_pr(repo)
    assert main(["main", "--repo", str(repo), "--title", "extractor-recopy"], env={}) == 0
    assert "EXCEPCIÓN" in capsys.readouterr().out


def test_extractor_exception_needs_raw_changes(repo, capsys):
    write(repo, "src/sifen_kb/pdf/tagged.py", "p = 2\n")
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    commit(repo)
    code, out = run(repo, capsys, "extractor-recopy")
    assert code == 1
    assert "mezcla conocimiento" in out


def test_extractor_exception_needs_extractor_changes(repo, capsys):
    write(repo, "src/sifen_kb/temporal.py", "t = 5\n")
    write(repo, "raw/NT_001/aaaaaaaaaaaa/index.json", '{"v": 2}\n')
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    commit(repo)
    code, _ = run(repo, capsys, "extractor-recopy")
    assert code == 1


def test_extractor_exception_rejects_other_code(repo, capsys):
    extractor_pr(repo)
    write(repo, "src/sifen_kb/temporal.py", "t = 6\n")
    commit(repo, "además, el resolvedor")
    code, out = run(repo, capsys, "extractor-recopy")
    assert code == 1
    assert "solo admite código del extractor" in out
    assert "src/sifen_kb/temporal.py" in out


def test_extractor_exception_rejects_golden_and_other_knowledge(repo, capsys):
    extractor_pr(repo)
    write(repo, "tests/golden/temporal.yaml", "- {cambiado: 1}\n")
    commit(repo, "además, el golden")
    code, out = run(repo, capsys, "extractor-recopy")
    assert code == 1
    assert "solo puede cambiar bajo kb/" in out
    assert "tests/golden/temporal.yaml" in out


def test_extractor_pr_without_knowledge_needs_no_tag(repo, capsys):
    write(repo, "src/sifen_kb/pdf/tagged.py", "p = 3\n")
    write(repo, "raw/NT_001/aaaaaaaaaaaa/index.json", '{"v": 3}\n')
    commit(repo)
    code, out = run(repo, capsys)
    assert code == 0
    assert "EXCEPCIÓN" not in out


def test_extractor_exception_does_not_excuse_sources_changes(repo, capsys):
    extractor_pr(repo)
    write(repo, "sources/NT_001/aaaaaaaaaaaa.pdf", "ALTERADO\n")
    commit(repo)
    code, out = run(repo, capsys, "extractor-recopy")
    assert code == 1
    assert "sources/ solo admite ADICIONES" in out


# --- errores de uso y de git -----------------------------------------------------------------------
def test_unknown_base_ref_is_exit_code_2(repo, capsys):
    code = main(["origin/no-existe", "--repo", str(repo)], env={})
    captured = capsys.readouterr()
    assert code == 2
    assert "pr-scope: ERROR" in captured.err
    assert "fetch-depth" in captured.err


def test_option_like_base_ref_is_rejected(repo, capsys):
    code = main(["--repo", str(repo), "--", "--output=x"], env={})
    assert code == 2
    assert "base_ref inválido" in capsys.readouterr().err


def test_missing_argument_is_a_usage_error():
    with pytest.raises(SystemExit) as e:
        main([], env={})
    assert e.value.code == 2


def test_not_a_git_repo_is_exit_code_2(tmp_path, capsys):
    assert main(["main", "--repo", str(tmp_path)], env={}) == 2
    assert "pr-scope: ERROR" in capsys.readouterr().err


def test_step_summary_is_written(repo, tmp_path, capsys):
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    commit(repo)
    summary = tmp_path / "summary.md"
    code = main(["main", "--repo", str(repo)], env={"GITHUB_STEP_SUMMARY": str(summary)})
    capsys.readouterr()
    assert code == 0
    assert "pr-scope: OK" in summary.read_text(encoding="utf-8")


def test_module_entrypoint_exit_codes(repo):
    src = Path(prscope.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(src), "PR_TITLE": ""}
    write(repo, "kb/validations/DE/D208c.yaml", "cambio\n")
    write(repo, "src/sifen_kb/temporal.py", "t = 7\n")
    commit(repo)
    cp = subprocess.run(
        [sys.executable, "-m", "sifen_kb.prscope", "main"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
        check=False,
    )
    assert cp.returncode == 1
    assert "pr-scope: FALLA" in cp.stdout

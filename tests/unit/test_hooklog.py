"""Pruebas de `sifen_kb.hooklog`: bitácora de curación armada desde el JSON de los hooks de Claude Code."""

import hashlib
import io
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sifen_kb import hooklog
from sifen_kb.hooklog import (
    HookLogError,
    instructions_digest,
    main,
    normalize_event,
    process,
    resolve_root,
    run_path,
)
from sifen_kb.model import CurationRun
from sifen_kb.yamlio import is_canonical, load_kb_file

NOW = datetime(2026, 10, 17, 19, 30, 45, 123456, tzinfo=UTC)
CLAUDE_MD = "# SIFEN KB — reglas para Claude\n\n1. Usa `sifen explain`.\n"
PROMPT_MD = "# Curar una entidad\n\nLiterales solo con `sifen draft`.\n"
KB_FILE = "kb/validations/DE/D208c.yaml"


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return cp.stdout.strip()


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root, "CLAUDE.md", CLAUDE_MD)
    write(root, "curation/prompts/curar_entidad.md", PROMPT_MD)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root.resolve()


def start_payload(repo: Path, session_id: str = "sess-1", **extra: object) -> dict:
    return {
        "session_id": session_id,
        "cwd": str(repo),
        "hook_event_name": "SessionStart",
        "source": "startup",
        **extra,
    }


def post_payload(repo: Path, file_path: str, session_id: str = "sess-1", tool: str = "Write") -> dict:
    return {
        "session_id": session_id,
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"file_path": file_path, "content": "x"},
        "tool_response": {"filePath": file_path, "type": "create"},
    }


def load_run(path: Path) -> CurationRun:
    return CurationRun.model_validate(load_kb_file(path))


# --- eventos y utilidades --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("SessionStart", "SessionStart"),
        ("session_start", "SessionStart"),
        ("session-start", "SessionStart"),
        ("PostToolUse", "PostToolUse"),
        ("post-tool-use", "PostToolUse"),
        ("PreToolUse", None),
        ("", None),
    ],
)
def test_normalize_event(name, expected):
    assert normalize_event(name) == expected


def test_instructions_digest_is_sha256_of_concatenated_files(repo):
    digest, inputs = instructions_digest(repo)
    assert digest == hashlib.sha256((CLAUDE_MD + PROMPT_MD).encode("utf-8")).hexdigest()
    assert [(i.path, i.sha256) for i in inputs] == [
        ("CLAUDE.md", hashlib.sha256(CLAUDE_MD.encode("utf-8")).hexdigest()),
        ("curation/prompts/curar_entidad.md", hashlib.sha256(PROMPT_MD.encode("utf-8")).hexdigest()),
    ]


def test_instructions_digest_missing_files(tmp_path):
    assert instructions_digest(tmp_path) == (None, [])
    write(tmp_path, "CLAUDE.md", CLAUDE_MD)
    digest, inputs = instructions_digest(tmp_path)
    assert digest == hashlib.sha256(CLAUDE_MD.encode("utf-8")).hexdigest()
    assert [i.path for i in inputs] == ["CLAUDE.md"]


def test_resolve_root_uses_git_toplevel_from_subdirectory(repo):
    sub = repo / "kb" / "validations"
    sub.mkdir(parents=True)
    assert resolve_root({"cwd": str(sub)}) == repo


def test_resolve_root_without_git_is_cwd(tmp_path):
    assert resolve_root({"cwd": str(tmp_path)}) == tmp_path.resolve()


@pytest.mark.parametrize("session_id", ["../../evil", "a/b\\c", "..", "", None, 42])
def test_run_path_never_escapes_runs_dir(tmp_path, session_id):
    p = run_path(tmp_path, session_id)
    if p is not None:
        assert p.parent == tmp_path / "curation" / "runs"
        assert p.suffix == ".yaml"


# --- SessionStart ---------------------------------------------------------------------------------
def test_session_start_creates_run(repo):
    head = git(repo, "rev-parse", "HEAD")
    path = process("SessionStart", start_payload(repo, model="claude-sonnet-5-5"), now=NOW)
    assert path == repo / "curation" / "runs" / "sess-1.yaml"
    run = load_run(path)
    assert run.session_id == "sess-1"
    assert run.started_at == NOW.replace(microsecond=0)
    assert run.base_commit == head
    assert run.tool == "claude-code"
    assert run.model == "claude-sonnet-5-5"
    assert run.prompt_path == "curation/prompts/curar_entidad.md"
    assert run.instructions_sha256 == hashlib.sha256((CLAUDE_MD + PROMPT_MD).encode("utf-8")).hexdigest()
    assert [i.path for i in run.inputs] == ["CLAUDE.md", "curation/prompts/curar_entidad.md"]
    assert run.outputs == []


def test_session_start_file_is_canonical_yaml(repo):
    path = process("SessionStart", start_payload(repo), now=NOW)
    text = path.read_text(encoding="utf-8")
    assert "\r" not in text
    assert is_canonical(text)
    assert "started_at: 2026-10-17T19:30:45Z" in text


def test_session_start_without_model_and_without_commits(tmp_path):
    root = tmp_path / "nogit"
    root.mkdir()
    write(root, "CLAUDE.md", CLAUDE_MD)
    path = process("SessionStart", start_payload(root), now=NOW)
    run = load_run(path)
    assert run.model is None
    assert run.base_commit is None
    assert "model" not in path.read_text(encoding="utf-8")


def test_session_start_in_repo_without_commits(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    run = load_run(process("SessionStart", start_payload(root.resolve()), now=NOW))
    assert run.base_commit is None


@pytest.mark.parametrize("source", ["resume", "compact", "clear"])
def test_session_start_keeps_existing_run(repo, source):
    process("SessionStart", start_payload(repo), now=NOW)
    write(repo, KB_FILE, "key: val:DE:D208c\n")
    process("PostToolUse", post_payload(repo, str(repo / KB_FILE)), now=NOW)
    later = datetime(2026, 10, 18, 8, 0, 0, tzinfo=UTC)
    path = process("SessionStart", start_payload(repo, source=source), now=later)
    run = load_run(path)
    assert run.started_at == NOW.replace(microsecond=0)
    assert [o.path for o in run.outputs] == [KB_FILE]


def test_session_start_requires_session_id(repo):
    with pytest.raises(HookLogError):
        process("SessionStart", {"cwd": str(repo)}, now=NOW)
    assert not (repo / "curation" / "runs").exists()


# --- PostToolUse ----------------------------------------------------------------------------------
def test_post_tool_use_records_output_with_current_sha256(repo):
    process("SessionStart", start_payload(repo), now=NOW)
    f = write(repo, KB_FILE, "key: val:DE:D208c\nid: D208c\n")
    path = process("PostToolUse", post_payload(repo, str(f)), now=NOW)
    run = load_run(path)
    assert [(o.path, o.sha256) for o in run.outputs] == [
        (KB_FILE, hashlib.sha256(f.read_bytes()).hexdigest())
    ]


def test_post_tool_use_replaces_previous_entry_of_same_path(repo):
    process("SessionStart", start_payload(repo), now=NOW)
    a = write(repo, "kb/documents/NT_024.yaml", "id: NT_024\n")
    b = write(repo, KB_FILE, "v: 1\n")
    process("PostToolUse", post_payload(repo, str(a)), now=NOW)
    path = process("PostToolUse", post_payload(repo, str(b)), now=NOW)
    b.write_text("v: 2\n", encoding="utf-8", newline="\n")
    process("PostToolUse", post_payload(repo, str(a)), now=NOW)  # mismo archivo, sin cambios
    a.write_text("id: NT_024\ntitle: Nota Técnica N° 24\n", encoding="utf-8", newline="\n")
    process("PostToolUse", post_payload(repo, str(a), tool="Edit"), now=NOW)
    outputs = load_run(path).outputs
    assert [o.path for o in outputs] == ["kb/documents/NT_024.yaml", KB_FILE]
    assert outputs[0].sha256 == hashlib.sha256(a.read_bytes()).hexdigest()
    assert outputs[1].sha256 == hashlib.sha256(b"v: 1\n").hexdigest()  # b no se volvió a registrar


def test_post_tool_use_relative_path_resolves_against_cwd(repo):
    write(repo, KB_FILE, "v: 1\n")
    payload = post_payload(repo, KB_FILE)
    path = process("PostToolUse", payload, now=NOW)
    assert [o.path for o in load_run(path).outputs] == [KB_FILE]


def test_post_tool_use_from_subdirectory_cwd(repo):
    f = write(repo, KB_FILE, "v: 1\n")
    payload = post_payload(repo, str(f))
    payload["cwd"] = str(repo / "kb")
    path = process("PostToolUse", payload, now=NOW)
    assert path == repo / "curation" / "runs" / "sess-1.yaml"
    assert [o.path for o in load_run(path).outputs] == [KB_FILE]


def test_post_tool_use_notebook_path(repo):
    write(repo, "docs/n.ipynb", "{}")
    payload = post_payload(repo, "unused", tool="NotebookEdit")
    payload["tool_input"] = {"notebook_path": str(repo / "docs" / "n.ipynb")}
    path = process("PostToolUse", payload, now=NOW)
    assert [o.path for o in load_run(path).outputs] == ["docs/n.ipynb"]


def test_post_tool_use_creates_run_if_session_start_was_missed(repo):
    f = write(repo, KB_FILE, "v: 1\n")
    path = process("PostToolUse", post_payload(repo, str(f), session_id="late"), now=NOW)
    run = load_run(path)
    assert run.session_id == "late"
    assert run.started_at == NOW.replace(microsecond=0)
    assert run.base_commit == git(repo, "rev-parse", "HEAD")
    assert [o.path for o in run.outputs] == [KB_FILE]


@pytest.mark.parametrize(
    "case",
    [
        "outside_repo",
        "runs_dir",
        "git_dir",
        "missing_file",
        "directory",
        "other_tool",
        "no_input",
        "bad_input",
    ],
)
def test_post_tool_use_ignores_what_is_not_an_output(repo, tmp_path, case):
    payload = post_payload(repo, str(repo / KB_FILE))
    if case == "outside_repo":
        outside = write(tmp_path, "otro/archivo.yaml", "x: 1\n")
        payload["tool_input"] = {"file_path": str(outside)}
    elif case == "runs_dir":
        payload["tool_input"] = {"file_path": str(write(repo, "curation/runs/otra.yaml", "x: 1\n"))}
    elif case == "git_dir":
        payload["tool_input"] = {"file_path": str(repo / ".git" / "HEAD")}
    elif case == "missing_file":
        payload["tool_input"] = {"file_path": str(repo / "kb" / "no_existe.yaml")}
    elif case == "directory":
        payload["tool_input"] = {"file_path": str(repo / "curation")}
    elif case == "other_tool":
        write(repo, KB_FILE, "v: 1\n")
        payload["tool_name"] = "Read"
    elif case == "no_input":
        del payload["tool_input"]
    else:
        payload["tool_input"] = ["no", "es", "un", "objeto"]
    assert process("PostToolUse", payload, now=NOW) is None
    assert not (repo / "curation" / "runs" / "sess-1.yaml").exists()


def test_post_tool_use_does_not_overwrite_corrupt_run(repo):
    f = write(repo, KB_FILE, "v: 1\n")
    corrupt = write(repo, "curation/runs/sess-1.yaml", "session_id: [sin cerrar\n")
    before = corrupt.read_bytes()
    with pytest.raises(HookLogError):
        process("PostToolUse", post_payload(repo, str(f)), now=NOW)
    assert corrupt.read_bytes() == before


def test_post_tool_use_requires_session_id(repo):
    payload = post_payload(repo, str(write(repo, KB_FILE, "v: 1\n")))
    del payload["session_id"]
    with pytest.raises(HookLogError):
        process("PostToolUse", payload, now=NOW)


def test_post_tool_use_parallel_hooks_do_not_lose_entries(repo):
    process("SessionStart", start_payload(repo), now=NOW)
    files = [write(repo, f"kb/documents/NT_{n:03d}.yaml", f"n: {n}\n") for n in range(1, 9)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda f: process("PostToolUse", post_payload(repo, str(f)), now=NOW), files))
    outputs = load_run(repo / "curation" / "runs" / "sess-1.yaml").outputs
    assert sorted(o.path for o in outputs) == sorted(f.relative_to(repo).as_posix() for f in files)


def test_unknown_event_is_an_error(repo):
    with pytest.raises(HookLogError):
        process("PreToolUse", start_payload(repo))


# --- main: nunca falla, nunca escribe por stdout --------------------------------------------------
def run_main(argv, stdin_text):
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(stdin_text), stderr=err)
    return code, err.getvalue()


def test_main_end_to_end_via_stdin(repo, capsys):
    code, err = run_main(["SessionStart"], json.dumps(start_payload(repo, model="claude-sonnet-5-5")))
    assert (code, err) == (0, "")
    f = write(repo, KB_FILE, "v: 1\n")
    code, err = run_main(["PostToolUse"], json.dumps(post_payload(repo, str(f))))
    assert (code, err) == (0, "")
    run = load_run(repo / "curation" / "runs" / "sess-1.yaml")
    assert run.model == "claude-sonnet-5-5"
    assert [o.path for o in run.outputs] == [KB_FILE]
    assert capsys.readouterr().out == ""  # lo que sale por stdout en SessionStart se inyecta como contexto


def test_main_takes_event_from_hook_event_name_when_no_argument(repo):
    code, _ = run_main([], json.dumps(start_payload(repo)))
    assert code == 0
    assert (repo / "curation" / "runs" / "sess-1.yaml").is_file()


@pytest.mark.parametrize(
    ("argv", "stdin_text", "message"),
    [
        (["SessionStart"], "esto no es json", "inesperado"),
        (["SessionStart"], "", "session_id"),
        (["SessionStart"], "[1, 2]", "objeto"),
        (["Desconocido"], "{}", "desconocido"),
        ([], "{}", "falta el evento"),
        (["PostToolUse"], '{"cwd": "/no/existe/jamas"}', "session_id"),
    ],
)
def test_main_never_fails_loudly(argv, stdin_text, message, capsys):
    code, err = run_main(argv, stdin_text)
    assert code == 0
    assert err.startswith("hooklog:")
    assert message in err
    assert capsys.readouterr().out == ""


def test_main_swallows_unexpected_exceptions(repo, monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise RuntimeError("fallo interno")

    monkeypatch.setattr(hooklog, "process", boom)
    code, err = run_main(["SessionStart"], json.dumps(start_payload(repo)))
    assert code == 0
    assert "RuntimeError" in err
    assert capsys.readouterr().out == ""


def test_module_entrypoint_exit_code_zero_with_garbage_stdin(tmp_path):
    src = Path(hooklog.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(src)}
    cp = subprocess.run(
        [sys.executable, "-m", "sifen_kb.hooklog", "PostToolUse"],
        input="{{{ no es json",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
    assert cp.returncode == 0
    assert cp.stdout == ""
    assert "hooklog:" in cp.stderr


def test_module_entrypoint_creates_run(repo):
    src = Path(hooklog.__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(src)}
    cp = subprocess.run(
        [sys.executable, "-m", "sifen_kb.hooklog", "SessionStart"],
        input=json.dumps(start_payload(repo, session_id="e2e")),
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
        check=False,
    )
    assert (cp.returncode, cp.stdout, cp.stderr) == (0, "", "")
    assert load_run(repo / "curation" / "runs" / "e2e.yaml").session_id == "e2e"

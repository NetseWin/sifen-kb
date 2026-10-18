"""Bitácora de curación armada por hooks de Claude Code (docs/arquitectura.md §J, §D.4, §F.1).

Los hooks de `.claude/settings.json` ejecutan, con el JSON del evento por stdin:

    uv run python -m sifen_kb.hooklog SessionStart
    uv run python -m sifen_kb.hooklog PostToolUse        # matcher: Edit|Write|MultiEdit
    uv run python -m sifen_kb.hooklog Backfill           # manual: NO es un hook (ver más abajo)

y este módulo arma `curation/runs/<session_id>.yaml` (modelo `CurationRun`). La bitácora NO la
escribe el agente: es evidencia de qué instrucciones y qué archivos tocó una sesión de Claude.

Campos del JSON de entrada que se usan realmente (documentación de hooks de Claude Code,
https://code.claude.com/docs/en/hooks; todos los eventos traen los campos comunes):

- comunes:        `session_id`, `cwd`, `hook_event_name` (el resto —`transcript_path`,
                  `permission_mode`— se ignora)
- `SessionStart`: `source` (startup | resume | clear | compact | fork; no se usa: el archivo existente
                  de una sesión retomada se conserva) y `model` (puede faltar: entonces se omite)
- `PostToolUse`:  `tool_name` (Edit | Write | MultiEdit | NotebookEdit) y `tool_input.file_path`
                  (`tool_input.notebook_path` para NotebookEdit). `tool_response` no se usa.
- `Backfill`:      `session_id`, `cwd`, `paths` (lista de rutas, relativas al `cwd` o absolutas, dentro
                  del repo) y `reason` (motivo del registro retrospectivo; obligatorio). `tool_name` NO
                  se usa ni se acepta como criterio: el backfill es un acto humano explícito, no un
                  evento de herramienta.

Qué escribe cada evento:

- `SessionStart`: crea el archivo con `session_id`, `started_at` (UTC), `base_commit`
  (`git rev-parse HEAD`, si se puede), `tool` ("claude-code": el hook no expone la versión),
  `model` (si el evento lo trae), `prompt_path` (curation/prompts/curar_entidad.md),
  `instructions_sha256` y `inputs` (CLAUDE.md y el prompt, con su sha256). Si el archivo ya
  existe (sesión retomada o compactada) no lo toca.
- `PostToolUse`: agrega a `outputs` la ruta tocada (relativa a la raíz del repo, con `/`) con el
  sha256 actual del archivo; la entrada previa del mismo path se reemplaza en su lugar. Se ignoran
  las rutas fuera del repo, `.git/`, la propia bitácora y los archivos que ya no existen.
- `Backfill`: registro manual y explícito de salidas que los hooks NO capturaron (por ejemplo, ediciones
  hechas en una sesión con herramientas MCP ajenas a los hooks). La corrida debe EXISTIR (nunca crea el
  encabezado a posteriori), el `reason` es obligatorio y cada entrada queda con `source: backfill`, el
  motivo y `recorded_at` (UTC, sin microsegundos): la procedencia es visible en el propio archivo. Un
  path ya registrado por un hook conserva SU entrada (se omite y se informa: la evidencia del hook no se
  reescribe); un path ya registrado con backfill se actualiza (sha256, motivo e instante). Si una ruta no
  es registrable no se registra NINGUNA.

`instructions_sha256` = sha256 de los bytes de CLAUDE.md seguidos de los del prompt de curación
(sin separador; un archivo ausente no aporta bytes). Se reproduce a mano con:

    cat CLAUDE.md curation/prompts/curar_entidad.md | sha256sum

Garantía de no bloqueo: un hook roto no puede frenar la sesión. `main()` devuelve SIEMPRE 0 para
`SessionStart`/`PostToolUse`, no escribe nada por stdout (en `SessionStart` lo que sale por stdout se
inyecta como contexto de Claude) y reporta cualquier problema por stderr. Los hooks de una misma tanda
corren en paralelo, por eso la actualización de un archivo se hace bajo un lock de archivo en el
directorio temporal del sistema y con escritura atómica (`os.replace`).

`Backfill` NO es un hook y no goza de esa garantía: es manual y falla ruidoso — devuelve 1 con el
problema por stderr y sin tocar la bitácora si algo no es registrable; con éxito devuelve 0 e imprime
por stderr un resumen corto de lo registrado y lo omitido.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, TextIO

from sifen_kb.model import CurationRun, FileHash, RunOutput
from sifen_kb.yamlio import load_kb_file, write_kb_file

SESSION_START = "SessionStart"
POST_TOOL_USE = "PostToolUse"
BACKFILL = "Backfill"
_EVENTS = {"sessionstart": SESSION_START, "posttooluse": POST_TOOL_USE, "backfill": BACKFILL}

RUNS_DIR = "curation/runs"
INSTRUCTIONS_PATH = "CLAUDE.md"
PROMPT_PATH = "curation/prompts/curar_entidad.md"
TOOL_NAME = "claude-code"

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_PATH_KEYS = ("file_path", "notebook_path")
_IGNORED_PREFIXES = (RUNS_DIR + "/", ".git/")

_LOCK_TIMEOUT_S = 5.0
_LOCK_STALE_S = 10.0


class HookLogError(Exception):
    """Problema esperable (entrada incompleta, archivo corrupto): se informa por stderr y se sale con 0."""


# --- utilidades ------------------------------------------------------------------------------------
def normalize_event(name: str) -> str | None:
    """`SessionStart`, `session_start` y `session-start` son el mismo evento."""
    return _EVENTS.get(re.sub(r"[^a-z]", "", name.lower()))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(cwd: Path, *args: str) -> str | None:
    try:
        cp = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except OSError, subprocess.SubprocessError:
        return None
    out = cp.stdout.strip()
    return out if cp.returncode == 0 and out else None


def resolve_root(payload: dict[str, Any]) -> Path:
    """Raíz del repo: `git rev-parse --show-toplevel` desde `cwd`; si no hay git, el propio `cwd`."""
    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    top = _git(cwd, "rev-parse", "--show-toplevel") if cwd.is_dir() else None
    return Path(top).resolve() if top else cwd.resolve()


def _safe_session_name(session_id: object) -> str | None:
    """El `session_id` se usa como nombre de archivo: solo [A-Za-z0-9._-], sin rutas."""
    if not isinstance(session_id, str):
        return None
    name = re.sub(r"[^A-Za-z0-9._-]", "_", session_id).strip("._")[:128]
    return name or None


def run_path(root: Path, session_id: object) -> Path | None:
    name = _safe_session_name(session_id)
    return root / RUNS_DIR / f"{name}.yaml" if name else None


def instructions_digest(root: Path) -> tuple[str | None, list[FileHash]]:
    """sha256 de CLAUDE.md + prompt (bytes concatenados) y la lista de esos archivos como `inputs`."""
    h = hashlib.sha256()
    inputs: list[FileHash] = []
    for rel in (INSTRUCTIONS_PATH, PROMPT_PATH):
        p = root / rel
        if p.is_file():
            data = p.read_bytes()
            h.update(data)
            inputs.append(FileHash(path=rel, sha256=hashlib.sha256(data).hexdigest()))
    return (h.hexdigest() if inputs else None), inputs


def _touched_path(payload: dict[str, Any], root: Path) -> str | None:
    """Ruta (relativa al repo, con `/`) que tocó la herramienta, o None si no hay que registrarla."""
    tool = payload.get("tool_name")
    if isinstance(tool, str) and tool not in EDIT_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = next(
        (tool_input[k] for k in _PATH_KEYS if isinstance(tool_input.get(k), str) and tool_input[k]), None
    )
    if raw is None:
        return None
    p = Path(raw)
    if not p.is_absolute():
        cwd = payload.get("cwd")
        p = (Path(cwd) if isinstance(cwd, str) and cwd else root) / p
    try:
        rel = p.resolve().relative_to(root).as_posix()
    except OSError, ValueError:
        return None
    if rel.startswith(_IGNORED_PREFIXES) or not (root / rel).is_file():
        return None
    return rel


# --- lectura y escritura del archivo de la corrida ------------------------------------------------
@contextlib.contextmanager
def _file_lock(target: Path) -> Iterator[None]:
    """Lock de archivo (O_EXCL) en el directorio temporal; si no se logra a tiempo, sigue sin lock."""
    digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()[:16]
    lock = Path(tempfile.gettempdir()) / f"sifen-kb-hooklog-{digest}.lock"
    fd: int | None = None
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > _LOCK_STALE_S:
                    lock.unlink(missing_ok=True)
                    continue
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
        except OSError:
            break
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(OSError):
                lock.unlink(missing_ok=True)


def read_run(path: Path) -> CurationRun:
    try:
        return CurationRun.model_validate(load_kb_file(path))
    except Exception as e:
        raise HookLogError(f"{path}: archivo de bitácora ilegible o inválido ({e}); no se modifica") from None


def write_run(path: Path, run: CurationRun) -> None:
    """Escritura canónica (`write_kb_file`) a un temporal y reemplazo atómico."""
    tmp = path.with_name(path.name + ".tmp")
    write_kb_file(tmp, run.model_dump(mode="json", exclude_none=True))
    os.replace(tmp, path)


def new_run(session_id: str, payload: dict[str, Any], root: Path, now: datetime) -> CurationRun:
    digest, inputs = instructions_digest(root)
    model = payload.get("model")
    return CurationRun(
        session_id=session_id,
        started_at=now,
        base_commit=_git(root, "rev-parse", "HEAD"),
        tool=TOOL_NAME,
        model=model if isinstance(model, str) and model else None,
        prompt_path=PROMPT_PATH,
        instructions_sha256=digest,
        inputs=inputs,
        outputs=[],
    )


# --- eventos ---------------------------------------------------------------------------------------
def on_session_start(payload: dict[str, Any], root: Path, now: datetime) -> Path:
    session_id = payload.get("session_id")
    path = run_path(root, session_id)
    if path is None or not isinstance(session_id, str):
        raise HookLogError("SessionStart sin `session_id` utilizable: no se crea la bitácora")
    with _file_lock(path):
        if path.exists():  # sesión retomada (resume/compact): se conserva lo ya registrado
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        write_run(path, new_run(session_id, payload, root, now))
    return path


def on_post_tool_use(payload: dict[str, Any], root: Path, now: datetime) -> Path | None:
    session_id = payload.get("session_id")
    path = run_path(root, session_id)
    if path is None or not isinstance(session_id, str):
        raise HookLogError("PostToolUse sin `session_id` utilizable: no se registra la salida")
    rel = _touched_path(payload, root)
    if rel is None:
        return None
    entry = RunOutput(path=rel, sha256=sha256_file(root / rel))
    with _file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        run = read_run(path) if path.exists() else new_run(session_id, payload, root, now)
        outputs = list(run.outputs)
        for i, old in enumerate(outputs):
            if old.path == rel:
                outputs[i] = entry
                break
        else:
            outputs.append(entry)
        write_run(path, run.model_copy(update={"outputs": outputs}))
    return path


# --- backfill (registro manual, no es un evento de hook) --------------------------------------------
class BackfillResult(NamedTuple):
    """Resultado de un backfill: la corrida tocada, los paths registrados y los omitidos (ya tenían entrada de hook)."""

    path: Path
    registered: list[str]
    skipped: list[str]


def _backfill_rel(raw: object, root: Path, payload: dict[str, Any]) -> str:
    """Ruta registrable (relativa al repo, con `/`), o `HookLogError` explicando por qué no lo es."""
    if not isinstance(raw, str) or not raw:
        raise HookLogError(f"ruta inválida en `paths`: {raw!r}")
    p = Path(raw)
    if not p.is_absolute():
        cwd = payload.get("cwd")
        p = (Path(cwd) if isinstance(cwd, str) and cwd else root) / p
    try:
        rel = p.resolve().relative_to(root).as_posix()
    except OSError, ValueError:
        raise HookLogError(f"la ruta {raw!r} está fuera del repositorio") from None
    if rel == ".git" or rel.startswith(_IGNORED_PREFIXES):
        raise HookLogError(f"la ruta {rel} no se puede registrar ({RUNS_DIR}/ o .git/)")
    if not (root / rel).is_file():
        raise HookLogError(f"la ruta {rel} no existe o no es un archivo")
    return rel


def on_backfill(payload: dict[str, Any], root: Path, now: datetime) -> BackfillResult:
    """Registro manual y explícito de salidas que los hooks no capturaron (modo `Backfill`).

    Reglas: la corrida debe EXISTIR (un backfill nunca crea la bitácora a posteriori), `reason` es
    obligatorio, `tool_name` no se considera y cada path debe existir dentro del repo (fuera de
    `curation/runs/` y `.git/`). Un path ya registrado por un hook conserva SU entrada (se omite y se
    informa); un path ya registrado con backfill se actualiza. Si un path no es registrable no se
    registra NINGUNO: esto no es un hook, es un acto manual que falla ruidoso.
    """
    session_id = payload.get("session_id")
    path = run_path(root, session_id)
    if path is None or not isinstance(session_id, str):
        raise HookLogError("Backfill sin `session_id` utilizable: no se registra nada")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise HookLogError("Backfill sin `reason`: el registro retrospectivo exige un motivo explícito")
    raw_paths = payload.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        raise HookLogError("Backfill sin `paths`: se espera una lista no vacía de rutas")
    if not path.is_file():
        raise HookLogError(f"{path}: la corrida no existe; el backfill nunca crea la bitácora a posteriori")
    rels: list[str] = []
    problems: list[str] = []
    for raw in raw_paths:
        try:
            rel = _backfill_rel(raw, root, payload)
        except HookLogError as e:
            problems.append(str(e))
            continue
        if rel not in rels:
            rels.append(rel)
    if problems:
        raise HookLogError("Backfill rechazado, no se registró nada: " + "; ".join(problems))
    stamp = now.replace(microsecond=0)  # UTC sin microsegundos: el instante del registro, no del hecho
    registered: list[str] = []
    skipped: list[str] = []
    with _file_lock(path):
        run = read_run(path)
        outputs = list(run.outputs)
        for rel in rels:
            entry = RunOutput(
                path=rel, sha256=sha256_file(root / rel), source="backfill", reason=reason, recorded_at=stamp
            )
            for i, old in enumerate(outputs):
                if old.path != rel:
                    continue
                if old.source == "backfill":
                    outputs[i] = entry
                    registered.append(rel)
                else:  # entrada de hook: la evidencia del hecho no se reescribe
                    skipped.append(rel)
                break
            else:
                outputs.append(entry)
                registered.append(rel)
        if registered:
            write_run(path, run.model_copy(update={"outputs": outputs}))
    return BackfillResult(path, registered, skipped)


def _report_backfill(res: BackfillResult, stderr: TextIO) -> None:
    """Resumen corto del backfill por stderr (el stdout queda limpio, igual que en los hooks)."""
    reg = ", ".join(res.registered) or "ninguno"
    skip = ", ".join(res.skipped) or "ninguno"
    print(
        f"hooklog: backfill {res.path.name}: registrados: {reg}; omitidos (ya registrados por un hook): {skip}",
        file=stderr,
    )


# --- despacho ---------------------------------------------------------------------------------------
def process(event: str, payload: dict[str, Any], now: datetime | None = None) -> Path | None:
    """Despacha un evento. Devuelve el archivo de la bitácora tocado (None si no había nada que registrar)."""
    kind = normalize_event(event)
    if kind is None:
        raise HookLogError(
            f"evento desconocido: {event!r} (se esperaba SessionStart, PostToolUse o Backfill)"
        )
    stamp = (now or datetime.now(UTC)).replace(microsecond=0)
    root = resolve_root(payload)
    if kind == SESSION_START:
        return on_session_start(payload, root, stamp)
    if kind == BACKFILL:
        return on_backfill(payload, root, stamp).path
    return on_post_tool_use(payload, root, stamp)


# --- punto de entrada ------------------------------------------------------------------------------
def _read_payload(stdin: TextIO) -> dict[str, Any]:
    if stdin.isatty():
        return {}
    text = stdin.read().lstrip("﻿")
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise HookLogError("el JSON de stdin no es un objeto")
    return data


def _utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(Exception):
            reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None, stdin: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Los eventos de hook devuelven SIEMPRE 0 (un hook roto no bloquea la sesión) y no escriben por
    stdout. El modo manual `Backfill` falla ruidoso: devuelve 1 y explica el problema por stderr."""
    stdin = stdin if stdin is not None else sys.stdin
    stderr = stderr if stderr is not None else sys.stderr
    if stdin is sys.stdin:
        _utf8(stdin)
    if stderr is sys.stderr:
        _utf8(stderr)
    args = list(sys.argv[1:] if argv is None else argv)
    event = args[0] if args else None
    loud = isinstance(event, str) and normalize_event(event) == BACKFILL  # el modo manual es explícito
    try:
        payload = _read_payload(stdin)
        if not isinstance(event, str) or not event:
            event = payload.get("hook_event_name")
            loud = isinstance(event, str) and normalize_event(event) == BACKFILL
        if not isinstance(event, str) or not event:
            raise HookLogError(
                "falta el evento (argumento SessionStart|PostToolUse|Backfill o `hook_event_name`)"
            )
        if loud:
            _report_backfill(on_backfill(payload, resolve_root(payload), datetime.now(UTC)), stderr)
            return 0
        process(event, payload)
    except HookLogError as e:
        print(f"hooklog: {e}", file=stderr)
        return 1 if loud else 0
    except Exception as e:
        tail = "" if loud else "; la sesión continúa"
        print(f"hooklog: error inesperado ({type(e).__name__}: {e}){tail}", file=stderr)
        return 1 if loud else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

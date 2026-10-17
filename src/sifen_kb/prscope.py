"""Check `pr-scope` del CI (docs/arquitectura.md §J "Controles mecánicos" y §L).

Uso:

    python -m sifen_kb.prscope <base_ref>          # p. ej. origin/main
    PR_TITLE="..." python -m sifen_kb.prscope origin/main

Lista los archivos que cambia el PR (`git diff --name-status base...HEAD`, es decir, contra el
ancestro común) y los clasifica:

- CONOCIMIENTO: `kb/**`, `tests/golden/**`, `cases/**`, `curation/**`.
- CÓDIGO (protegido): `src/**`, el resto de `tests/**`, `.github/**`, `.claude/**`, `CLAUDE.md`,
  `pyproject.toml`, `uv.lock`. Todo archivo que no figure en ninguna lista (`.gitignore`,
  `.gitattributes`, `.python-version`…) también cuenta como código: lo no previsto se trata con el
  criterio más estricto.
- NEUTRO: `docs/**`, los `*.md` de la raíz (salvo `CLAUDE.md`), `LICENSE`, `NOTICE`, `sources/**`,
  `sources.manifest.yaml`, `raw/**` y `extraction/**`.

Falla (código de salida 1) si:

1. el PR mezcla CONOCIMIENTO con CÓDIGO (un PR de curación no puede desactivar el test que lo
   detectaría, y un PR de código no cambia la KB);
2. `sources/` no recibe solo ADICIONES (equivale a que `git diff --diff-filter=DMR base...HEAD --
   sources/` salga vacío; aquí se pide además que no haya cambios de tipo);
3. se agrega o modifica un `*.p12`, `*.pfx`, `*.key`, `*.pem` o `*.jks` (borrarlo sí se permite).

Excepción `extractor-recopy` (§J, cambio del extractor): si el PR cambia el extractor
(`src/sifen_kb/extract.py` o `src/sifen_kb/pdf/**`) y regenera `raw/**`, puede volver a copiar con
`sifen draft` los literales afectados en `kb/`. Para admitir esa mezcla el título del PR (variable
de entorno `PR_TITLE`) debe contener la etiqueta `extractor-recopy`, y entonces:

- el único código que puede cambiar es el del extractor y sus pruebas (`tests/unit/test_extract*.py`,
  `tests/unit/test_pdf*.py`);
- el conocimiento que cambia debe estar solo bajo `kb/` (nada de `tests/golden/`, `cases/` ni
  `curation/`);
- el check lo reporta como excepción aplicada y no verifica que los cambios de `kb/` sean solo
  literales: esa comprobación es de la revisión humana (el informe del PR y `sifen check` ya
  exigen literal = celda de `raw/`).

Códigos de salida: 0 correcto, 1 incumple el alcance, 2 error de uso o de git.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

KNOWLEDGE_PREFIXES = ("kb/", "tests/golden/", "cases/", "curation/")
CODE_PREFIXES = ("src/", "tests/", ".github/", ".claude/")
CODE_FILES = frozenset({"CLAUDE.md", "pyproject.toml", "uv.lock"})
NEUTRAL_PREFIXES = ("docs/", "sources/", "raw/", "extraction/")
NEUTRAL_FILES = frozenset({"sources.manifest.yaml", "LICENSE", "NOTICE"})

SOURCES_PREFIX = "sources/"
SECRET_SUFFIXES = (".p12", ".pfx", ".key", ".pem", ".jks")

EXTRACTOR_TAG = "extractor-recopy"
EXTRACTOR_PREFIXES = ("src/sifen_kb/pdf/",)
EXTRACTOR_FILES = frozenset({"src/sifen_kb/extract.py"})
EXTRACTOR_TEST_PREFIXES = ("tests/unit/test_extract", "tests/unit/test_pdf")

KNOWLEDGE = "knowledge"
CODE = "code"
NEUTRAL = "neutral"
_LABELS = {KNOWLEDGE: "conocimiento", CODE: "código/configuración", NEUTRAL: "neutro"}
_MAX_LISTED = 25


class PrScopeError(Exception):
    """Error de uso o de git (no una violación del alcance): código de salida 2."""


@dataclass(frozen=True)
class Change:
    status: str  # A (agregado), M, D, T… tal como lo informa git con --no-renames
    path: str  # ruta del repo con `/`


@dataclass
class Report:
    changes: list[Change]
    by_scope: dict[str, list[str]] = field(default_factory=lambda: {KNOWLEDGE: [], CODE: [], NEUTRAL: []})
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


# --- clasificación ---------------------------------------------------------------------------------
def classify(path: str) -> str:
    """CONOCIMIENTO / CÓDIGO / NEUTRO de una ruta del repo (separador `/`). Lo no previsto es CÓDIGO."""
    if path.startswith(KNOWLEDGE_PREFIXES):
        return KNOWLEDGE
    if path.startswith(CODE_PREFIXES) or path in CODE_FILES:
        return CODE
    if path.startswith(NEUTRAL_PREFIXES) or path in NEUTRAL_FILES:
        return NEUTRAL
    if "/" not in path and path.endswith(".md"):
        return NEUTRAL
    return CODE


def is_extractor_code(path: str) -> bool:
    return (
        path in EXTRACTOR_FILES
        or path.startswith(EXTRACTOR_PREFIXES)
        or path.startswith(EXTRACTOR_TEST_PREFIXES)
    )


def is_secret_file(path: str) -> bool:
    return PurePosixPath(path).name.lower().endswith(SECRET_SUFFIXES)


# --- git -------------------------------------------------------------------------------------------
def changed_files(base_ref: str, repo: Path) -> list[Change]:
    """`git diff --name-status -z --no-renames <base>...HEAD`: un renombrado cuenta como borrado + alta."""
    if not base_ref or base_ref.startswith("-"):
        raise PrScopeError(f"base_ref inválido: {base_ref!r}")
    try:
        cp = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-status", "-z", "--no-renames", f"{base_ref}...HEAD"],
            capture_output=True,
            check=False,
        )
    except OSError as e:
        raise PrScopeError(f"no se pudo ejecutar git: {e}") from None
    if cp.returncode != 0:
        detail = cp.stderr.decode("utf-8", "replace").strip()
        raise PrScopeError(
            f"git diff {base_ref}...HEAD falló: {detail} (¿el checkout tiene fetch-depth: 0 y existe {base_ref}?)"
        )
    parts = cp.stdout.decode("utf-8", "surrogateescape").split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    if len(parts) % 2:
        raise PrScopeError("salida inesperada de git diff --name-status -z")
    return [Change(status=parts[i][:1], path=parts[i + 1]) for i in range(0, len(parts), 2)]


# --- evaluación ------------------------------------------------------------------------------------
def _listing(paths: Sequence[str]) -> str:
    shown = ", ".join(paths[:_MAX_LISTED])
    return shown + (f" … (+{len(paths) - _MAX_LISTED} más)" if len(paths) > _MAX_LISTED else "")


def evaluate(changes: Sequence[Change], title: str | None = None) -> Report:
    report = Report(changes=list(changes))
    for c in report.changes:
        report.by_scope[classify(c.path)].append(c.path)
    knowledge, code = report.by_scope[KNOWLEDGE], report.by_scope[CODE]

    if knowledge and code:
        _check_mixed(report, knowledge, code, title)

    bad_sources = [
        f"{c.status} {c.path}"
        for c in report.changes
        if c.path.startswith(SOURCES_PREFIX) and c.status != "A"
    ]
    if bad_sources:
        report.errors.append(
            "sources/ solo admite ADICIONES (nunca se modifica, borra ni mueve una fuente oficial; una "
            "re-subida de DNIT es un archivo nuevo): " + _listing(bad_sources)
        )

    secrets = [c.path for c in report.changes if c.status != "D" and is_secret_file(c.path)]
    if secrets:
        report.errors.append(
            "no se agregan certificados ni claves (*.p12 *.pfx *.key *.pem *.jks): " + _listing(secrets)
        )
    return report


def _check_mixed(report: Report, knowledge: list[str], code: list[str], title: str | None) -> None:
    mixed = (
        f"el PR mezcla conocimiento ({_listing(knowledge)}) con código o configuración ({_listing(code)}): "
        "separa en dos PR (docs/arquitectura.md §J)"
    )
    extractor_changed = any(is_extractor_code(p) for p in code)
    raw_changed = any(c.path.startswith("raw/") for c in report.changes)
    if not (extractor_changed and raw_changed):
        report.errors.append(mixed)
        return
    if EXTRACTOR_TAG not in (title or "").lower():
        report.errors.append(
            mixed + f". Cambia el extractor y regenera raw/: si en kb/ solo se vuelven a copiar literales, "
            f"agrega la etiqueta `{EXTRACTOR_TAG}` al título del PR"
        )
        return
    other_code = [p for p in code if not is_extractor_code(p)]
    other_knowledge = [p for p in knowledge if not p.startswith("kb/")]
    if other_code:
        report.errors.append(
            f"excepción {EXTRACTOR_TAG}: solo admite código del extractor (src/sifen_kb/extract.py, "
            f"src/sifen_kb/pdf/**) y sus pruebas; además cambia: {_listing(other_code)}"
        )
    if other_knowledge:
        report.errors.append(
            f"excepción {EXTRACTOR_TAG}: el conocimiento solo puede cambiar bajo kb/; además cambia: "
            f"{_listing(other_knowledge)}"
        )
    if not other_code and not other_knowledge:
        report.notes.append(
            f"EXCEPCIÓN {EXTRACTOR_TAG} aplicada (título del PR + cambio del extractor + raw/ regenerado): "
            "la revisión humana debe confirmar que los cambios de kb/ son solo literales vueltos a copiar "
            f"con `sifen draft`: {_listing([p for p in knowledge if p.startswith('kb/')])}"
        )


# --- salida ----------------------------------------------------------------------------------------
def render(report: Report, base_ref: str) -> str:
    lines = [f"pr-scope: {base_ref}...HEAD, {len(report.changes)} archivo(s) cambiado(s)"]
    for scope in (KNOWLEDGE, CODE, NEUTRAL):
        paths = report.by_scope[scope]
        lines.append(f"  {_LABELS[scope]} ({len(paths)})" + (f": {_listing(paths)}" if paths else ""))
    lines += [f"NOTA: {n}" for n in report.notes]
    lines += [f"ERROR: {e}" for e in report.errors]
    lines.append("pr-scope: OK" if report.ok else "pr-scope: FALLA")
    return "\n".join(lines)


def _write_step_summary(text: str, env: Mapping[str, str]) -> None:
    target = env.get("GITHUB_STEP_SUMMARY")
    if target:
        with contextlib.suppress(OSError), Path(target).open("a", encoding="utf-8", newline="\n") as f:
            f.write("```text\n" + text + "\n```\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m sifen_kb.prscope",
        description="Verifica que un PR no mezcle conocimiento con código y que respete sources/ y los secretos.",
    )
    p.add_argument("base_ref", help="referencia base del PR, p. ej. origin/main")
    p.add_argument("--repo", default=".", help="raíz del repositorio (por defecto, el directorio actual)")
    p.add_argument(
        "--title", default=None, help="título del PR (por defecto, la variable de entorno PR_TITLE)"
    )
    return p


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", newline="\n")
    args = build_parser().parse_args(argv)
    title = args.title if args.title is not None else env.get("PR_TITLE")
    try:
        changes = changed_files(args.base_ref, Path(args.repo))
    except PrScopeError as e:
        print(f"pr-scope: ERROR: {e}", file=sys.stderr)
        return 2
    report = evaluate(changes, title)
    text = render(report, args.base_ref)
    print(text)
    _write_step_summary(text, env)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

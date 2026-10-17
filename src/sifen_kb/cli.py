"""CLI `sifen` (argparse, delgada). Cada subcomando delega en `módulo:función(args) -> int`.

Consulta:       explain, status
Mantenimiento:  source check, source add, extract, draft, check, fmt
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable

from sifen_kb import __version__


def _lazy(target: str) -> Callable[[argparse.Namespace], int]:
    mod_name, func_name = target.split(":")

    def run(args: argparse.Namespace) -> int:
        mod = importlib.import_module(f"sifen_kb.{mod_name}")
        return int(getattr(mod, func_name)(args) or 0)

    return run


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sifen",
        description="Base de conocimiento SIFEN: qué regla rige en cada fecha y ambiente, con evidencia de DNIT.",
    )
    p.add_argument("--version", action="version", version=f"sifen-kb {__version__}")
    p.add_argument("--root", default=None, help="raíz del repositorio (por defecto se busca desde el cwd)")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMANDO")

    # --- consulta -------------------------------------------------------------------------------
    ex = sub.add_parser("explain", help="explica un código, ID, xml_name o documento a una fecha y ambiente")
    ex.add_argument("term", help="código (1321), ID (D208c), xml_name (iTipIDRec) o documento (NT_024)")
    ex.add_argument("--at", help="fecha AAAA-MM-DD (por defecto: hoy). Eje: procesamiento (supuesto A2)")
    ex.add_argument("--env", choices=["prod", "test"], default="prod")
    ex.add_argument("--history", action="store_true", help="muestra toda la historia con fuentes")
    ex.add_argument("--xml", help="XML de un DE para evaluar la regla (solo lectura; PII enmascarada)")
    ex.add_argument("--response", help="XML de respuesta de SIFEN (de ahí se toma dFecProc)")
    ex.add_argument("--processed-at", dest="processed_at", help="fecha de procesamiento AAAA-MM-DD")
    ex.add_argument("--show-pii", action="store_true", help="no enmascara datos personales (solo uso local)")
    ex.add_argument("--json", action="store_true", help="salida JSON (contrato estable)")
    ex.set_defaults(func=_lazy("explain:cmd_explain"))

    st = sub.add_parser("status", help="horizonte de fuentes, pendientes, Issues, cobertura y supuestos")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=_lazy("explain:cmd_status"))

    # --- mantenimiento ------------------------------------------------------------------------
    so = sub.add_parser("source", help="fuentes oficiales (manifiesto)")
    sosub = so.add_subparsers(dest="source_cmd", required=True, metavar="ACCIÓN")
    sc = sosub.add_parser("check", help="compara hashes de las URL conocidas y de los listados del portal")
    sc.add_argument("--scope", default="nt,xsd,manual,tablas", help="lista separada por comas")
    sc.add_argument("--offline", action="store_true", help="no consulta la red (solo verifica el repo)")
    sc.set_defaults(func=_lazy("sources:cmd_source_check"))
    sa = sosub.add_parser("add", help="descarga (solo dominios DNIT), hashea y registra una revisión")
    sa.add_argument("--doc", required=True, help="DocId, p. ej. NT_024")
    sa.add_argument("--url", help="URL oficial (dominio DNIT permitido)")
    sa.add_argument("--file", help="copia local que conserva la empresa (origin: offline; exige --note)")
    sa.add_argument("--note")
    sa.set_defaults(func=_lazy("sources:cmd_source_add"))

    xt = sub.add_parser("extract", help="genera raw/ desde sources/ (determinista)")
    xt.add_argument("--doc", action="append", help="limitar a estos DocId")
    xt.add_argument("--check", action="store_true", help="regenera en memoria y compara byte a byte con raw/")
    xt.set_defaults(func=_lazy("extract:cmd_extract"))

    dr = sub.add_parser(
        "draft", help="copia celdas de raw/ a kb/: <DocId> (calendario) o <EffectId> (versión)"
    )
    dr.add_argument("target", help="NT_024 o NT_024#1")
    dr.set_defaults(func=_lazy("draft:cmd_draft"))

    ck = sub.add_parser("check", help="esquema, formato, integridad, evidencia y cobertura")
    ck.add_argument("--json", action="store_true")
    ck.set_defaults(func=_lazy("integrity:cmd_check"))

    fm = sub.add_parser("fmt", help="formato canónico de kb/ (y manifiesto)")
    fm.add_argument("--check", action="store_true", help="no escribe; falla si algún archivo no es canónico")
    fm.set_defaults(func=_lazy("integrity:cmd_fmt"))
    return p


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

"""YAML restringido del canónico (docs/arquitectura.md §H).

- `KBLoader`: todo escalar es `str` salvo `true`/`false`/`null`. Claves duplicadas, anchors,
  alias y tags explícitos son error con número de línea. Los tipos los decide Pydantic.
  Motivo: con `yaml.safe_load`, `0160` se vuelve 112 (octal YAML 1.1), `NO` se vuelve False y
  las claves duplicadas pasan sin aviso.
- `dump_kb`: volcado canónico. `sifen fmt --check` exige `dump_kb(load_kb(texto)) == texto`,
  lo que detecta a la vez comentarios, truncamientos (`" #"`) y formato no canónico.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

_BOOL = re.compile(r"^(?:true|false)$")
_NULL = re.compile(r"^(?:null|~|)$")


class KBYamlError(ValueError):
    pass


def _install_minimal_resolvers(cls: type) -> None:
    cls.yaml_implicit_resolvers = {}
    cls.add_implicit_resolver("tag:yaml.org,2002:bool", _BOOL, list("tf"))
    cls.add_implicit_resolver("tag:yaml.org,2002:null", _NULL, ["n", "~", ""])


class KBLoader(yaml.SafeLoader):
    def compose_node(self, parent: Any, index: Any) -> Any:  # noqa: D102
        if self.check_event(yaml.AliasEvent):
            ev = self.peek_event()
            raise KBYamlError(f"alias no permitido (línea {ev.start_mark.line + 1})")
        ev = self.peek_event()
        if getattr(ev, "anchor", None):
            raise KBYamlError(f"anchor no permitido (línea {ev.start_mark.line + 1})")
        tag = getattr(ev, "tag", None)
        if tag not in (None, "!") and not isinstance(ev, yaml.StreamStartEvent | yaml.DocumentStartEvent):
            raise KBYamlError(f"tag explícito no permitido: {tag} (línea {ev.start_mark.line + 1})")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise KBYamlError(f"clave duplicada {key!r} (línea {key_node.start_mark.line + 1})")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


_install_minimal_resolvers(KBLoader)


class KBDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:  # noqa: D102 - el loader rechaza anchors y alias
        return True


_install_minimal_resolvers(KBDumper)


def _block_worthy(s: str) -> bool:
    # Prosa larga en bloque `|-`; identificadores y URLs largas (sin espacios) quedan en una línea.
    return "\n" in s or (len(s) > 80 and " " in s) or " #" in s or ": " in s


def _repr_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    if _block_worthy(data) and data == data.strip() and "\t" not in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def _repr_as_plain_text(dumper: yaml.SafeDumper, data: object) -> yaml.ScalarNode:
    """Enteros, fechas y fechas-hora se vuelcan como escalar plano (el loader los lee como str)."""
    text = data.isoformat() if isinstance(data, date | datetime) else str(data)
    return dumper.represent_scalar("tag:yaml.org,2002:str", text)


KBDumper.add_representer(str, _repr_str)
for _t in (int, date, datetime):
    KBDumper.add_representer(_t, _repr_as_plain_text)


class _IndentedListDumper(KBDumper):
    """Listas indentadas bajo su clave (estilo habitual en PRs)."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
        return super().increase_indent(flow, False)


def load_kb_text(text: str, *, source: str = "<texto>") -> Any:
    try:
        return yaml.load(text, Loader=KBLoader)  # noqa: S506 - KBLoader es un SafeLoader restringido
    except KBYamlError as e:
        raise KBYamlError(f"{source}: {e}") from None
    except yaml.YAMLError as e:
        raise KBYamlError(f"{source}: YAML inválido: {e}") from None


def load_kb_file(path: str | Path) -> Any:
    p = Path(path)
    return load_kb_text(p.read_text(encoding="utf-8"), source=str(p))


def dump_kb(data: Any) -> str:
    """Volcado canónico: UTF-8 sin escapar, sin plegado de líneas, orden de claves preservado."""
    return yaml.dump(
        data,
        Dumper=_IndentedListDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10**9,
        indent=2,
    )


def write_kb_file(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write(dump_kb(data))


def is_canonical(text: str, *, source: str = "<texto>") -> bool:
    return dump_kb(load_kb_text(text, source=source)) == text

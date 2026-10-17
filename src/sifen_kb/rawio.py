"""Contrato del directorio `raw/` (evidencia textual generada; nadie la edita a mano).

Layout por revisión de documento:

    raw/<DocId>/<sha12>/
        index.json          metadatos de la extracción y de cada página
        pages/pNNN.txt      texto de la página PDF NNN (1-based), tal como sale del motor, LF
        tables.jsonl        una fila de tabla por línea (solo páginas/tablas extraídas)

`tables.jsonl` — cada línea es un objeto JSON con:
    page      int   página PDF donde EMPIEZA la fila
    key       str   clave de la fila: el ID (columna "ID") en tablas de campos/validaciones,
                    "fechas" en la tabla de fechas de una NT, u otra clave declarada
    occ       int   1-based: desambigua un mismo `key` repetido en la misma página
    table     str   "fields" | "validations" | "dates" | "other"
    header    list  encabezados literales de la tabla
    cells     dict  atributo -> texto NORMALIZADO (normalize_text)
    raw_cells dict  atributo -> texto tal como salió del extractor
    pages     list  páginas que ocupa la fila (más de una si se unió una fila partida)
    fix_ids   list  ids de extraction/fixes.yaml aplicados a esta fila

Una referencia `raw:DOC@sha12:pN:KEY[~occ][#attr]` resuelve a la fila con page=N, key=KEY y
occ (1 por defecto); con `#attr`, a la celda `cells[attr]`.

Toda escritura es determinista: UTF-8, LF, JSON con claves ordenadas y sin escapar Unicode.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sifen_kb.model import parse_ref

# Mapeo encabezado literal (normalizado, en minúsculas) -> atributo.  Lo amplía `extract` si
# encuentra variantes reales; un encabezado desconocido es un error de extracción visible.
FIELD_HEADERS: dict[str, str] = {
    "grupo": "group",
    "id": "id",
    "campo": "xml_name",
    "descripción": "description",
    "nodo padre": "parent",
    "tipo dato": "data_type",
    "longitud": "length",
    "ocurrencia": "occurrence",
    "observaciones": "observations",
    "versión": "version",
}
VALIDATION_HEADERS: dict[str, str] = {
    "n° val": "num",
    "id": "id",
    "mensaje": "message",
    "código": "code",
    "observación": "observation",
    "e": "severity",
    "v": "v",
}


@dataclass(frozen=True)
class RawRow:
    doc: str
    sha12: str
    page: int
    key: str
    occ: int
    table: str
    header: list[str]
    cells: dict[str, str]
    raw_cells: dict[str, str]
    pages: list[int] = field(default_factory=list)
    fix_ids: list[str] = field(default_factory=list)

    @property
    def ref(self) -> str:
        occ = f"~{self.occ}" if self.occ != 1 else ""
        return f"raw:{self.doc}@{self.sha12}:p{self.page}:{self.key}{occ}"


def rev_dir(root: Path, doc: str, sha12: str) -> Path:
    return root / "raw" / doc / sha12


def page_path(root: Path, doc: str, sha12: str, page: int) -> Path:
    return rev_dir(root, doc, sha12) / "pages" / f"p{page:03d}.txt"


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_index(root: Path, doc: str, sha12: str, index: dict[str, Any]) -> None:
    write_text(
        rev_dir(root, doc, sha12) / "index.json",
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
    )


def write_rows(root: Path, doc: str, sha12: str, rows: list[dict[str, Any]]) -> None:
    lines = [dumps_json(r) for r in rows]
    write_text(rev_dir(root, doc, sha12) / "tables.jsonl", "".join(line + "\n" for line in lines))


def read_index(root: Path, doc: str, sha12: str) -> dict[str, Any] | None:
    p = rev_dir(root, doc, sha12) / "index.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def read_page(root: Path, doc: str, sha12: str, page: int) -> str | None:
    p = page_path(root, doc, sha12, page)
    return p.read_text(encoding="utf-8") if p.exists() else None


def iter_rows(root: Path, doc: str, sha12: str) -> Iterator[RawRow]:
    p = rev_dir(root, doc, sha12) / "tables.jsonl"
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            yield RawRow(
                doc=doc,
                sha12=sha12,
                page=d["page"],
                key=d["key"],
                occ=d.get("occ", 1),
                table=d.get("table", "other"),
                header=d.get("header", []),
                cells=d.get("cells", {}),
                raw_cells=d.get("raw_cells", {}),
                pages=d.get("pages", [d["page"]]),
                fix_ids=d.get("fix_ids", []),
            )


class RawStore:
    """Acceso con caché a raw/ para resolver referencias."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._rows: dict[tuple[str, str], dict[tuple[int, str, int], RawRow]] = {}

    def rows(self, doc: str, sha12: str) -> dict[tuple[int, str, int], RawRow]:
        k = (doc, sha12)
        if k not in self._rows:
            self._rows[k] = {(r.page, r.key, r.occ): r for r in iter_rows(self.root, doc, sha12)}
        return self._rows[k]

    def row(self, ref: str) -> RawRow | None:
        p = parse_ref(ref)
        return self.rows(str(p["doc"]), str(p["sha12"])).get((int(p["page"]), str(p["key"]), int(p["occ"])))  # type: ignore[arg-type]

    def cell(self, ref: str) -> str | None:
        p = parse_ref(ref)
        r = self.row(ref)
        if r is None or not p["attr"]:
            return None
        return r.cells.get(str(p["attr"]))

    def page_text(self, doc: str, sha12: str, page: int) -> str | None:
        return read_page(self.root, doc, sha12, page)

    def index(self, doc: str, sha12: str) -> dict[str, Any] | None:
        return read_index(self.root, doc, sha12)

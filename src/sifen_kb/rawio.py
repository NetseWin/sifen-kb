"""Contrato del directorio `raw/` (evidencia textual generada; nadie la edita a mano).

Lo genera `sifen extract` (`sifen_kb.extract`) desde las revisiones PDF de `sources.manifest.yaml`.

Layout por revisión de documento:

    raw/<DocId>/<sha12>/
        index.json          metadatos de la extracción y de cada página
        pages/pNNN.txt      texto de la página PDF NNN (1-based), tal como sale del motor, LF
        tables.jsonl        una fila de tabla por línea

`pages/pNNN.txt` — texto de la IR por página (`sifen_kb.pdf.verify.ir_page_text` sobre el documento
SIN unir tablas): los caracteres que el árbol de etiquetas enlaza por MCID (o, en un PDF sin
etiquetas, los que lee la ruta geométrica), en orden de lectura, un bloque o celda por renglón.
Conserva el texto tachado/rojo (eliminado) y el resaltado, sin marcas. No trae el mobiliario de
página que queda fuera del árbol (pie "septiembre de 2019 NNN" del MT, número de página y
encabezado de las NT antiguas). Un archivo por página del PDF, aunque esté vacía; termina en LF.

`index.json`:
    doc, sha256         revisión extraída
    extractor           {name, version (sifen-kb), engine (p. ej. "tagged/pdfplumber-0.11.10"),
                         page_printed_engine, origin {project, commit}}
    tagged              bool: el PDF trae árbol de etiquetas (si no, ruta geométrica)
    pages               [{page_pdf, page_printed, sha256, chars}]; `page_printed` es el número del
                        pie "septiembre de 2019 NNN" del MT (null si la página no lo trae o el
                        documento no es el MT); `sha256` y `chars` son del contenido de pNNN.txt
    tables              {fields, validations, dates}: filas escritas por tipo
    anomalies           filas de tablas reconocidas que NO entraron en tables.jsonl (con motivo)
    nt_info             solo NT: {numero, fecha_literal, test_literal, prod_literal, page} tal como
                        aparecen en el documento (normalize_text); null si no están

`tables.jsonl` — cada línea es un objeto JSON con:
    page      int   página PDF donde EMPIEZA la fila
    key       str   clave de la fila: el ID (columna "ID") en tablas de campos/validaciones,
                    "fechas" en la tabla de fechas de una NT, u otra clave declarada
    occ       int   1-based: desambigua un mismo `key` repetido en la misma página (entre todas
                    las tablas de la página, en orden de lectura)
    table     str   "fields" | "validations" | "dates" | "other"
    header    list  encabezados literales de la tabla (normalize_text), en orden de columna. En
                    "dates": los rótulos literales en el orden fecha, test, prod
    cells     dict  atributo -> texto NORMALIZADO (normalize_text), con las correcciones de
                    extraction/fixes.yaml aplicadas
    raw_cells dict  atributo -> texto tal como salió del extractor (sin correcciones). En una
                    validación que abarca varias filas (combinación vertical) la observación es
                    la unión de sus celdas no vacías con "\\n"
    pages     list  páginas que ocupa la fila (más de una si se unió una fila partida)
    fix_ids   list  ids de extraction/fixes.yaml aplicados a esta fila
    changes   dict  atributo -> "added" | "modified" | "deleted" según el resaltado del PDF
                    (verde, amarillo, rojo; leyenda del MT, pág. PDF 15). Un atributo resaltado
                    entero con un solo color lleva ese color; uno resaltado en parte o con
                    varios colores lleva "modified" (el detalle está en `marks`). Sin resaltado,
                    el atributo no figura
    row_change str|null  el color cuando TODO el texto de la fila está resaltado con uno solo
                    (fila agregada, eliminada o modificada entera). El "N° Val" sin resaltar no
                    cuenta: el MT lo deja sin color al agregar una validación
    marks     list  tramos resaltados: {attr, change, start, end, text}; `start`/`end` son
                    offsets en `raw_cells[attr]` (sin los espacios de los bordes del tramo)

Texto vigente de una celda: `RawRow.current(attr)` quita los tramos "deleted" de `raw_cells` y
normaliza (la misma regla que el libro de cambios de pdf_to_md). `cells` conserva TODO el texto
impreso, también el tachado.

**El literal que copia y verifica la KB es `RawRow.literal(attr)`, no `current`.** El color solo
tiene leyenda en el MT V150 (amarillo = modificación, verde = adición, rojo = eliminación): ahí
`literal == current`. En las NT el resaltado no tiene semántica fiable (docs/arquitectura.md §I.4;
docs/investigacion/sifen.md §5): en NT 21 y NT 24 el rojo marca «Si el Tipo de transacción es
distinto a Muestras médicas (D011≠13)», «o igual» y el «=» de «>=», y ese texto SIGUE VIGENTE. Por
eso en una NT `literal == cells[attr]` (todo el texto impreso) y la acción sale del verbo del
encabezado, nunca del color.

Atributos: campos (FIELD_HEADERS) group, id, xml_name, description, parent, data_type, length,
occurrence, observations, version; validaciones (VALIDATION_HEADERS) num, id, message, code,
observation, severity, v; fechas (DATE_ATTRS) fecha, test, prod.

Una referencia `raw:DOC@sha12:pN:KEY[~occ][#attr]` resuelve a la fila con page=N, key=KEY y
occ (1 por defecto); con `#attr`, a la celda `cells[attr]`.

`raw/_ledger/` — libro de cambios NT↔MT (`changes.jsonl` + `index.json`), DERIVADO determinista de
las filas de raw/ con `sifen_kb.pdf.sifen.changes`: una línea por fila de campo o validación de
una NT emparejada por (tabla, ID) con la fila vigente del MT V150, con la acción DEDUCIDA (color
de la fila; sin color, presencia en el MT), páginas, referencias raw a las dos filas y vigencias
literales de la NT. Es una deducción de herramienta —sugerencia para curar y oráculo de
cobertura—, NO una afirmación normativa: lo normativo vive en kb/ y lo revisa una persona.

Toda escritura es determinista: UTF-8, LF, JSON con claves ordenadas y sin escapar Unicode.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sifen_kb.model import parse_ref
from sifen_kb.normalize import normalize_text

# Mapeo encabezado literal (normalizado, en minúsculas: `header_key`) -> atributo.  Lo amplía
# `extract` con las variantes reales; un encabezado desconocido es un error de extracción visible.
FIELD_HEADERS: dict[str, str] = {
    "grupo": "group",
    "id": "id",
    "campo": "xml_name",
    "descripción": "description",
    "nodo padre": "parent",
    "tipo dato": "data_type",
    "longitud": "length",
    "longit ud": "length",  # título partido en dos renglones (MT págs. 62-112, 4 tablas)
    "long.": "length",  # NT-018
    "ocurrencia": "occurrence",
    "ocu": "occurrence",  # tablas de eventos del MT (págs. 121-123) y varias NT
    "ocu.": "occurrence",  # NT-018
    "observaciones": "observations",
    "versión": "version",
}
VALIDATION_HEADERS: dict[str, str] = {
    "n° val": "num",
    "nº val": "num",  # otra grafía del ordinal
    "nro. val": "num",  # NT-016
    "id": "id",
    "mensaje": "message",
    "mensaje de la validación": "message",
    "mensaje de validación": "message",  # NT-001, NT-016
    "resultado de la validación": "message",
    "resultado de validación": "message",
    "código": "code",
    "c;odigo": "code",  # errata del título impreso en NT-016
    "observación": "observation",
    "obs": "observation",
    "obs.": "observation",
    "e": "severity",
    "v": "v",
}
DATE_ATTRS: tuple[str, ...] = ("fecha", "test", "prod")
DATES_KEY = "fechas"
TABLES: tuple[str, ...] = ("fields", "validations", "dates", "other")
CHANGES: tuple[str, ...] = ("added", "modified", "deleted")
ROW_FIELDS: tuple[str, ...] = (
    "page",
    "key",
    "occ",
    "table",
    "header",
    "cells",
    "raw_cells",
    "pages",
    "fix_ids",
    "changes",
    "row_change",
    "marks",
)
LEDGER_DIR = "_ledger"
COLOR_LEGEND_DOC = "MT_V150"
"""Único documento cuya leyenda da semántica al color (ver `RawRow.literal`)."""


def header_key(literal: str) -> str:
    """Clave de búsqueda de un encabezado en FIELD_HEADERS / VALIDATION_HEADERS."""
    return normalize_text(literal).lower()


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
    changes: dict[str, str] = field(default_factory=dict)
    row_change: str | None = None
    marks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ref(self) -> str:
        occ = f"~{self.occ}" if self.occ != 1 else ""
        return f"raw:{self.doc}@{self.sha12}:p{self.page}:{self.key}{occ}"

    def current(self, attr: str) -> str:
        """Texto vigente de la celda: `raw_cells[attr]` sin los tramos tachados, normalizado.

        No aplica correcciones: `extract` rechaza una corrección sobre un atributo con tramos
        resaltados, así que si el atributo tiene una, no tiene tramos y vale `cells[attr]`.
        """
        if attr in self.cells and not any(m["attr"] == attr for m in self.marks):
            return self.cells[attr]
        text = self.raw_cells[attr]
        for m in sorted(
            (m for m in self.marks if m["attr"] == attr and m["change"] == "deleted"),
            key=lambda m: m["start"],
            reverse=True,
        ):
            text = text[: m["start"]] + text[m["end"] :]
        return normalize_text(text)

    def literal(self, attr: str) -> str:
        """Literal de la celda que copia `sifen draft` y verifica `sifen check`.

        En el MT V150 (único documento con leyenda de colores) es `current(attr)`; en cualquier
        otro documento, `cells[attr]` completo: el color de una NT no elimina texto.
        """
        return self.current(attr) if self.doc == COLOR_LEGEND_DOC else self.cells[attr]


def rev_dir(root: Path, doc: str, sha12: str) -> Path:
    return root / "raw" / doc / sha12


def page_path(root: Path, doc: str, sha12: str, page: int) -> Path:
    return rev_dir(root, doc, sha12) / "pages" / f"p{page:03d}.txt"


def ledger_dir(root: Path) -> Path:
    return root / "raw" / LEDGER_DIR


def dumps_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def index_text(index: dict[str, Any]) -> str:
    """Contenido canónico de un index.json."""
    return json.dumps(index, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def rows_text(rows: list[dict[str, Any]]) -> str:
    """Contenido canónico de un .jsonl: una línea por objeto, LF final."""
    return "".join(dumps_json(r) + "\n" for r in rows)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def write_index(root: Path, doc: str, sha12: str, index: dict[str, Any]) -> None:
    write_text(rev_dir(root, doc, sha12) / "index.json", index_text(index))


def write_rows(root: Path, doc: str, sha12: str, rows: list[dict[str, Any]]) -> None:
    write_text(rev_dir(root, doc, sha12) / "tables.jsonl", rows_text(rows))


def read_index(root: Path, doc: str, sha12: str) -> dict[str, Any] | None:
    p = rev_dir(root, doc, sha12) / "index.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def read_page(root: Path, doc: str, sha12: str, page: int) -> str | None:
    p = page_path(root, doc, sha12, page)
    return p.read_text(encoding="utf-8") if p.exists() else None


def row_from_dict(doc: str, sha12: str, d: dict[str, Any]) -> RawRow:
    return RawRow(
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
        changes=d.get("changes", {}),
        row_change=d.get("row_change"),
        marks=d.get("marks", []),
    )


def iter_rows(root: Path, doc: str, sha12: str) -> Iterator[RawRow]:
    p = rev_dir(root, doc, sha12) / "tables.jsonl"
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            yield row_from_dict(doc, sha12, json.loads(line))


def iter_ledger(root: Path) -> Iterator[dict[str, Any]]:
    """Líneas de raw/_ledger/changes.jsonl (deducción de herramienta, ver el módulo)."""
    p = ledger_dir(root) / "changes.jsonl"
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


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

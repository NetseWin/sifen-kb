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

Semántica del marcado (decisiones 2 y 3 del usuario, 2026-10-17; docs/arquitectura.md §I.4)
-------------------------------------------------------------------------------------------
En el MT V150 **y en las NT** el rojo es contenido eliminado, el verde agregado y el amarillo
modificado (leyenda del MT, pág. PDF 15), leídos siempre junto con el verbo del encabezado. Cada
celda tiene dos literales:

- `RawRow.rendered_literal(attr)` = `cells[attr]`: todo lo visible en el PDF, con su marcado.
- `RawRow.effective_literal(attr)` = `current(attr)`: el contenido efectivo, derivado de forma
  determinista quitando los tramos "deleted" (lo agregado y lo modificado se conservan). **Es el
  literal que copia `sifen draft` y verifica `sifen check`**, en cualquier documento. Excepción: la
  fila que elimina una regla reproduce lo eliminado, y la lápida se contrasta con `rendered`.

El color nunca decide solo. `color_signal` resume el marcado de una fila y `marking_conflicts` lo
contrasta con la acción curada del efecto y con el verbo literal del encabezado (`verb_actions`).
Regla «mixta» (decisión del usuario, 2026-10-17): color ≠ acción curada, marcado que no permite
reconstruir el contenido efectivo de forma unívoca, o `modify` cuyo contenido efectivo es igual al
de la predecesora ⇒ Issue BLOQUEANTE; color ≠ verbo literal del encabezado pero = acción curada ⇒
Issue de trazabilidad (no bloqueante). Lo exige la comprobación `marcado` de `sifen check`; esta
capa solo detecta, no decide.

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
import re
from collections.abc import Iterable, Iterator, Mapping
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
IMPLIED_ACTION: dict[str, str] = {"added": "add", "deleted": "remove", "modified": "modify"}
"""Acción que indica `RawRow.color_signal`; "mixed" no indica ninguna (marcado no unívoco)."""
_VERBS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("add", re.compile(r"\b(?:agreg|incorpor|inclu|adicion|nuev[oa]s?\b)", re.IGNORECASE)),
    ("modify", re.compile(r"\b(?:modific|reemplaz|sustitu|actualiz|corrig|cambi|exclu)", re.IGNORECASE)),
    # «se excluye» restringe el alcance (modify de la condición, §F.3) o quita la regla: ambas.
    ("remove", re.compile(r"\b(?:elimin|suprim|derog|exclu)", re.IGNORECASE)),
)


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

    def rendered_literal(self, attr: str) -> str:
        """Todo lo visible de la celda (`cells[attr]`), también el texto en rojo."""
        return self.cells[attr]

    def effective_literal(self, attr: str) -> str:
        """Contenido efectivo de la celda en cualquier documento: sin los tramos en rojo (eliminados).

        Es el literal que copia `sifen draft` y verifica `sifen check` (ver el módulo). Coincide con
        `current(attr)`: lo agregado (verde) y lo modificado (amarillo) se conservan.
        """
        return self.current(attr)

    def removed_spans(self, attr: str) -> list[str]:
        """Tramos en rojo de la celda, en orden: lo que `effective_literal` quita."""
        deleted = [m for m in self.marks if m["attr"] == attr and m["change"] == "deleted"]
        return [m["text"] for m in sorted(deleted, key=lambda m: m["start"])]

    def color_signal(self, attrs: Iterable[str]) -> str | None:
        """Resumen del marcado de la fila sobre `attrs` (y la celda `id`): qué dice el color.

        - None: ninguna de esas celdas está resaltada (sin señal de color).
        - "added" / "deleted": la fila entera es un alta / una baja: `row_change` lo dice, o la celda
          `id` está entera de ese color y toda otra celda resaltada también (en NT 2 la «R» de la
          severidad de D208d/D210a quedó sin color: no cuenta).
        - "mixed": la celda `id` es un alta o una baja y otra celda tiene otro marcado (no unívoco).
        - "modified": cualquier otro marcado (tramos en una fila que se conserva).
        """
        considered = [a for a in dict.fromkeys(["id", *attrs]) if a in self.cells]
        marked = [self.changes[a] for a in considered if a in self.changes]
        if not marked:
            return None
        whole = self.row_change if self.row_change in ("added", "deleted") else None
        if whole is None and self.changes.get("id") in ("added", "deleted"):
            whole = self.changes["id"]
        if whole is None:
            return "modified"
        return whole if all(c == whole for c in marked) else "mixed"


def verb_actions(verb_literal: str) -> frozenset[str]:
    """Acciones que nombra el verbo literal del encabezado («se modifican y elimina …» → modify, remove).

    Vacío si no nombra ninguna reconocible («se realizó una verificación de las fórmulas»): entonces
    el verbo no contradice ningún color.
    """
    return frozenset(action for action, pattern in _VERBS if pattern.search(verb_literal))


@dataclass(frozen=True)
class MarkingConflict:
    """Contradicción entre el marcado de la fila y la acción o el verbo de su efecto."""

    kind: str
    """`color_accion`, `mixto`, `vacio` o `sin_cambio` (bloqueantes); `color_verbo` (trazabilidad)."""
    blocking: bool
    message: str


def marking_conflicts(
    row: RawRow,
    *,
    action: str,
    verb_literal: str,
    attrs: Iterable[str],
    predecessor: Mapping[str, str | None] | None = None,
) -> list[MarkingConflict]:
    """Contradicciones del marcado de `row` con la acción curada y el verbo literal (regla «mixta»).

    `attrs`: columnas literales que copia la entidad. `predecessor`: literales efectivos de la
    predecesora por columna (solo para `modify`; sin ella no se evalúa `sin_cambio`). Detecta; no
    decide: cada conflicto exige un Issue (bloqueante salvo `color_verbo`), ver el módulo.
    """
    attrs = [a for a in attrs if a in row.cells]
    out: list[MarkingConflict] = []
    signal = row.color_signal(attrs)
    implied = IMPLIED_ACTION.get(signal or "")
    verbs = verb_actions(verb_literal)
    if signal == "mixed":
        out.append(
            MarkingConflict(
                "mixto",
                True,
                f"{row.ref}: la celda id es un alta o una baja y otras celdas tienen otro marcado: el "
                "contenido efectivo no se reconstruye de forma unívoca",
            )
        )
    elif implied is not None and implied != action:
        out.append(
            MarkingConflict(
                "color_accion",
                True,
                f"{row.ref}: el marcado ({signal}) indica `{implied}` y el efecto es `{action}`",
            )
        )
    elif implied is not None and verbs and implied not in verbs:
        out.append(
            MarkingConflict(
                "color_verbo",
                False,
                f"{row.ref}: el marcado ({signal}) indica `{implied}`, como la acción curada, y el verbo "
                f"del encabezado «{verb_literal}» no lo nombra",
            )
        )
    if action in ("add", "modify") and signal != "deleted":
        emptied = [a for a in attrs if row.rendered_literal(a) and not row.effective_literal(a)]
        if emptied:
            out.append(
                MarkingConflict(
                    "vacio",
                    True,
                    f"{row.ref}: el rojo vacía {', '.join(emptied)} en una fila que no se elimina "
                    f"(`{action}`): el contenido efectivo no se reconstruye de forma unívoca",
                )
            )
    if action == "modify" and predecessor is not None and attrs:
        same = all(
            normalize_text(row.effective_literal(a)) == normalize_text(predecessor.get(a) or "")
            for a in attrs
        )
        if same:
            out.append(
                MarkingConflict(
                    "sin_cambio",
                    True,
                    f"{row.ref}: el efecto es `modify` y el contenido efectivo de la fila es igual al de la "
                    "predecesora en todas las columnas que reproduce",
                )
            )
    return out


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

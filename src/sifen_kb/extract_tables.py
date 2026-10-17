"""IR de un documento (`sifen_kb.pdf`) → filas de `raw/<doc>/<sha12>/tables.jsonl` (contrato: `rawio`).

Reconoce las tablas con las reglas vendorizadas de pdf_to_md (`sifen.fields.is_field_table`,
`sifen.validations._tablas`/`_mapa`) para que raw/ y el libro de cambios lean las mismas filas:

- campos: una fila por fila de cuerpo de una tabla de campos (9 columnas);
- validaciones: una fila por ficha; las filas de continuación (sin primera columna, combinación
  vertical) suman su observación a la ficha abierta, igual que `validations._leer`;
- fechas (solo NT): la tabla "Fecha puesta a disposición para el Ambiente de Test/Producción" más
  el literal del párrafo "Fecha:", en una fila `key="fechas"`.

Lo que no se puede leer con certeza no se inventa: va a `anomalies` del index.json con su motivo.
Las correcciones solo entran por `extraction/fixes.yaml` (`apply_fixes`).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from sifen_kb.model import DocId, M, Sha12
from sifen_kb.normalize import normalize_text
from sifen_kb.pdf.ir import Cell, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.sifen import validations as V
from sifen_kb.pdf.sifen.changes import _es_vigencia, note_info
from sifen_kb.pdf.sifen.fields import is_field_table
from sifen_kb.rawio import DATES_KEY, FIELD_HEADERS, VALIDATION_HEADERS, header_key


class ExtractionError(ValueError):
    """Defecto de extracción que exige revisión (encabezado desconocido, corrección rota…)."""


# Columna normalizada de `validations` → atributo de raw/.
VALIDATION_COLUMN_ATTR: dict[str, str] = {
    "numero": "num",
    "id": "id",
    "resultado": "message",
    "codigo": "code",
    "observaciones": "observation",
    "efecto": "severity",
    "version": "v",
}
# Columna de `fields.FieldRecord` → atributo de raw/ (lo usa el libro de cambios).
FIELD_COLUMN_ATTR: dict[str, str] = {
    "grupo": "group",
    "id": "id",
    "campo": "xml_name",
    "descripcion": "description",
    "nodo_padre": "parent",
    "tipo_dato": "data_type",
    "longitud": "length",
    "ocurrencia": "occurrence",
    "observaciones": "observations",
}
_DATE_LABEL = re.compile(r"^Fecha puesta a disposici[óo]n para el Ambiente de (Test|Producci[óo]n)$", re.I)
_FECHA = "Fecha:"
_KEY_OK = re.compile(r"^[^:#~\s][^:#~]*$")


def runs_text(runs: Sequence[Run]) -> str:
    return "".join(run.text for run in runs)


@dataclass
class Fila:
    """Una fila de raw/ en construcción; `order` la ubica en el orden de lectura del documento."""

    table: str
    page: int
    key: str
    header: list[str]
    runs: dict[str, list[Run]]
    pages: list[int]
    order: tuple[int, int]
    cells_override: dict[str, str] = field(default_factory=dict)
    fix_ids: list[str] = field(default_factory=list)
    occ: int = 1

    def raw_cells(self) -> dict[str, str]:
        return {attr: runs_text(runs) for attr, runs in self.runs.items()}

    def cells(self) -> dict[str, str]:
        out = {attr: normalize_text(text) for attr, text in self.raw_cells().items()}
        out.update(self.cells_override)
        return out

    def marks(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for attr in sorted(self.runs):
            offset = 0
            for run in self.runs[attr]:
                end = offset + len(run.text)
                text = run.text
                if run.change is not None and text.strip():
                    lead = len(text) - len(text.lstrip())
                    trail = len(text) - len(text.rstrip())
                    out.append(
                        {
                            "attr": attr,
                            "change": run.change.value,
                            "start": offset + lead,
                            "end": end - trail,
                            "text": text.strip(),
                        }
                    )
                offset = end
        return out

    def changes(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for attr, runs in self.runs.items():
            kinds = {run.change for run in runs if run.text.strip()}
            if not kinds - {None}:
                continue
            only = next(iter(kinds)) if len(kinds) == 1 else None
            out[attr] = only.value if only is not None else "modified"
        return out

    def row_change(self) -> str | None:
        # El N° Val sin resaltar no vota (regla de `validations._estado`).
        kinds = {
            run.change
            for attr, runs in self.runs.items()
            for run in runs
            if run.text.strip() and not (attr == "num" and run.change is None)
        }
        if len(kinds) != 1 or None in kinds:
            return None
        only = next(iter(kinds))
        return only.value if only is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "key": self.key,
            "occ": self.occ,
            "table": self.table,
            "header": self.header,
            "cells": self.cells(),
            "raw_cells": self.raw_cells(),
            "pages": self.pages,
            "fix_ids": self.fix_ids,
            "changes": self.changes(),
            "row_change": self.row_change(),
            "marks": self.marks(),
        }


@dataclass
class Tablas:
    """Filas y anomalías de un documento."""

    filas: list[Fila] = field(default_factory=list)
    anomalies: list[dict[str, Any]] = field(default_factory=list)


def _attrs(header: Row, mapping: dict[str, str], table: str, page: int) -> list[str]:
    attrs = []
    for cell in header.cells:
        key = header_key(cell.text)
        if key not in mapping:
            raise ExtractionError(
                f"encabezado desconocido en una tabla de {table} (página {page}): {cell.text!r}; "
                "agregue la variante a rawio.FIELD_HEADERS/VALIDATION_HEADERS"
            )
        attrs.append(mapping[key])
    if len(set(attrs)) != len(attrs):
        raise ExtractionError(f"encabezado de {table} con atributos repetidos (página {page}): {attrs}")
    return attrs


def _row_pages(page: int, cells: Sequence[Cell]) -> set[int]:
    return {page, *(number for cell in cells for _, number in cell.page_breaks)}


def _anomaly(table: str, page: int, reason: str, texts: Sequence[str]) -> dict[str, Any]:
    return {"table": table, "page": page, "reason": reason, "texts": [normalize_text(t) for t in texts]}


def _field_rows(doc: Document, out: Tablas) -> None:
    for bi, block in enumerate(doc.blocks):
        if not (isinstance(block, Table) and is_field_table(block)):
            continue
        attrs = _attrs(block.rows[0], FIELD_HEADERS, "campos", block.page)
        header = [normalize_text(c.text) for c in block.rows[0].cells]
        for seq, row in enumerate(block.rows[1:]):
            page = row.page if row.page is not None else block.page
            texts = [c.text for c in row.cells]
            if len(row.cells) != len(attrs):
                out.anomalies.append(_anomaly("fields", page, f"{len(row.cells)}-celdas", texts))
                continue
            runs = {attr: list(cell.runs) for attr, cell in zip(attrs, row.cells, strict=True)}
            key = normalize_text(runs_text(runs["id"]))
            if not _KEY_OK.match(key):
                out.anomalies.append(_anomaly("fields", page, "sin-id-valido", texts))
                continue
            out.filas.append(
                Fila("fields", page, key, header, runs, sorted(_row_pages(page, row.cells)), (bi, seq))
            )


@dataclass
class _Ficha:
    principal: dict[str, Cell]
    observaciones: list[Cell]
    pages: set[int]
    page: int
    order: tuple[int, int]


def _validation_rows(doc: Document, out: Tablas) -> None:
    index = {id(block): i for i, block in enumerate(doc.blocks)}
    header_row: Row | None = None
    seq = 0
    for tabla in V._tablas(doc):
        if V.header_columns(tabla.table) is not None:
            header_row = tabla.table.rows[0]
        if header_row is None:  # imposible: `_tablas` solo continúa una tabla reconocida
            raise ExtractionError(f"tabla de validaciones sin encabezado (página {tabla.table.page})")
        attrs = _attrs(header_row, VALIDATION_HEADERS, "validaciones", tabla.table.page)
        esperados = [VALIDATION_COLUMN_ATTR[c] for c in tabla.columnas]
        if attrs != esperados:
            raise ExtractionError(
                f"encabezado de validaciones mal mapeado (página {tabla.table.page}): {attrs} != {esperados}"
            )
        header = [normalize_text(c.text) for c in header_row.cells]
        to_attr = dict(zip(tabla.columnas, attrs, strict=True))
        abierta: _Ficha | None = None

        def cerrar(
            ficha: _Ficha | None, header: list[str] = header, to_attr: dict[str, str] = to_attr
        ) -> None:
            if ficha is None:
                return
            runs: dict[str, list[Run]] = {}
            for columna, attr in to_attr.items():
                if columna == "observaciones":
                    celdas = [c for c in ficha.observaciones if c.text.strip()]
                    if not celdas:
                        continue
                    joined: list[Run] = []
                    for i, cell in enumerate(celdas):
                        if i:
                            joined.append(Run("\n"))
                        joined.extend(cell.runs)
                    runs[attr] = joined
                elif columna in ficha.principal:
                    runs[attr] = list(ficha.principal[columna].runs)
            key = normalize_text(runs_text(runs.get("id", [])))
            if not _KEY_OK.match(key):
                texts = [runs_text(r) for r in runs.values()]
                out.anomalies.append(_anomaly("validations", ficha.page, "sin-id-valido", texts))
                return
            out.filas.append(
                Fila("validations", ficha.page, key, header, runs, sorted(ficha.pages), ficha.order)
            )

        for row in tabla.cuerpo:
            page = row.page if row.page is not None else tabla.table.page
            texts = [c.text for c in row.cells]
            mapa = V._mapa(row, tabla.columnas)
            if isinstance(mapa, str):
                out.anomalies.append(_anomaly("validations", page, mapa, texts))
                continue
            if tabla.columnas[0] in mapa:
                cerrar(abierta)
                obs = [mapa["observaciones"]] if "observaciones" in mapa else []
                abierta = _Ficha(mapa, obs, _row_pages(page, row.cells), page, (index[id(tabla.table)], seq))
                seq += 1
                continue
            if abierta is None:
                out.anomalies.append(_anomaly("validations", page, "continuacion-sin-ficha", texts))
                continue
            de_mas = [c.text for col, c in mapa.items() if col != "observaciones" and c.text.strip()]
            if de_mas:
                out.anomalies.append(
                    _anomaly("validations", page, "continuacion-con-columnas-de-mas", de_mas)
                )
            if "observaciones" in mapa:
                abierta.observaciones.append(mapa["observaciones"])
            abierta.pages |= _row_pages(page, row.cells)
        cerrar(abierta)


def nt_info(doc: Document) -> tuple[dict[str, Any], Fila | None, list[dict[str, Any]]]:
    """Número, fecha y vigencias de una NT tal como están impresas, y su fila de fechas.

    La fecha sale del primer párrafo que empieza con "Fecha:"; las vigencias, de la tabla de dos
    columnas cuyas filas rotulan "Fecha puesta a disposición para el Ambiente de Test" y "…de
    Producción" (NT 013 en adelante). El rótulo se compara normalizado: en NT-021 y NT-024 viene
    partido en dos renglones ("Ambiente de" / "Producción").
    """
    anomalies: list[dict[str, Any]] = []
    fecha: tuple[str, int, int, list[Run]] | None = None  # literal crudo, página, bloque, tramos
    for bi, block in enumerate(doc.blocks):
        if isinstance(block, TextBlock) and block.text.lstrip().startswith(_FECHA):
            first = block.text.lstrip().split("\n", 1)[0]
            raw = first[len(_FECHA) :].strip()
            fecha = (raw, block.page, bi, [Run(raw)])
            break
    tabla: tuple[int, Table] | None = next(
        ((bi, b) for bi, b in enumerate(doc.blocks) if isinstance(b, Table) and _es_vigencia(b)), None
    )
    runs: dict[str, list[Run]] = {}
    labels: dict[str, str] = {}
    if fecha is not None:
        runs["fecha"] = fecha[3]
        labels["fecha"] = _FECHA
    if tabla is not None:
        for row in tabla[1].rows:
            texts = [c.text for c in row.cells]
            label = normalize_text(row.cells[0].text) if row.cells else ""
            m = _DATE_LABEL.match(label)
            if m is None or len(row.cells) != 2:
                anomalies.append(_anomaly("dates", tabla[1].page, "fila-de-fechas-no-reconocida", texts))
                continue
            attr = "test" if m.group(1).lower() == "test" else "prod"
            if attr in runs:
                anomalies.append(_anomaly("dates", tabla[1].page, "fecha-repetida", texts))
                continue
            runs[attr] = list(row.cells[1].runs)
            labels[attr] = label
    attrs = [a for a in ("fecha", "test", "prod") if a in runs]
    fila: Fila | None = None
    if tabla is not None and ("test" in runs or "prod" in runs):
        page = tabla[1].page
        pages = {page} | ({fecha[1]} if fecha is not None else set())
        fila = Fila(
            "dates",
            page,
            DATES_KEY,
            [labels[a] for a in attrs],
            {a: runs[a] for a in attrs},
            sorted(pages),
            (tabla[0], 0),
        )
    info = {
        "numero": note_info(doc).numero,
        "fecha_literal": normalize_text(runs_text(runs["fecha"])) if "fecha" in runs else None,
        "test_literal": normalize_text(runs_text(runs["test"])) if "test" in runs else None,
        "prod_literal": normalize_text(runs_text(runs["prod"])) if "prod" in runs else None,
        "page": tabla[1].page if tabla is not None else (fecha[1] if fecha is not None else None),
    }
    return info, fila, anomalies


def build_rows(doc: Document, *, is_nt: bool) -> tuple[Tablas, dict[str, Any] | None]:
    """Filas de campos, validaciones y (en una NT) fechas, en orden de lectura, con `occ`."""
    out = Tablas()
    _field_rows(doc, out)
    _validation_rows(doc, out)
    info: dict[str, Any] | None = None
    if is_nt:
        info, fila, anomalies = nt_info(doc)
        out.anomalies.extend(anomalies)
        if fila is not None:
            out.filas.append(fila)
    out.filas.sort(key=lambda f: f.order)
    assign_occ(out.filas)
    return out, info


def assign_occ(filas: Sequence[Fila]) -> None:
    seen: Counter[tuple[int, str]] = Counter()
    for fila in filas:
        seen[(fila.page, fila.key)] += 1
        fila.occ = seen[(fila.page, fila.key)]


# --- extraction/fixes.yaml -----------------------------------------------------------------------


class Fix(M):
    """Una corrección de un defecto de extracción, justificada y revisada (docs/arquitectura.md §I)."""

    id: str
    doc: DocId
    sha12: Sha12
    page: int
    key: str
    occ: int = 1
    attr: str
    original: str
    corrected: str
    motivo: str
    evidencia: str


def parse_fixes(data: Any, source: str = "extraction/fixes.yaml") -> list[Fix]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ExtractionError(f"{source}: se esperaba una lista de correcciones")
    fixes = []
    for i, item in enumerate(data, 1):
        try:
            fixes.append(Fix.model_validate(item))
        except ValidationError as e:
            raise ExtractionError(f"{source}: corrección n.º {i} inválida: {e}") from None
    ids = Counter(f.id for f in fixes)
    repetidos = sorted(k for k, n in ids.items() if n > 1)
    if repetidos:
        raise ExtractionError(f"{source}: ids repetidos: {', '.join(repetidos)}")
    return fixes


def apply_fixes(doc: str, sha12: str, filas: Sequence[Fila], fixes: Sequence[Fix]) -> list[str]:
    """Aplica las correcciones de esta revisión; devuelve sus ids. Una corrección que no encuentra
    su fila, cuyo `original` ya no coincide o que cae en un atributo con tramos resaltados es un
    error: no se aplica a ciegas."""
    aplicadas: list[str] = []
    by_ref = {(f.page, f.key, f.occ): f for f in filas}
    for fix in fixes:
        if (fix.doc, fix.sha12) != (doc, sha12):
            continue
        fila = by_ref.get((fix.page, fix.key, fix.occ))
        if fila is None:
            raise ExtractionError(
                f"corrección {fix.id}: no hay fila {fix.key}~{fix.occ} en la página {fix.page} de {doc}@{sha12}"
            )
        cells = fila.cells()
        if fix.attr not in cells:
            raise ExtractionError(f"corrección {fix.id}: la fila no tiene el atributo {fix.attr!r}")
        if normalize_text(fix.original) != cells[fix.attr]:
            raise ExtractionError(
                f"corrección {fix.id}: el original no coincide con lo extraído "
                f"({normalize_text(fix.original)!r} != {cells[fix.attr]!r})"
            )
        if any(m["attr"] == fix.attr for m in fila.marks()):
            raise ExtractionError(
                f"corrección {fix.id}: el atributo {fix.attr!r} tiene tramos resaltados; "
                "el contrato de raw/ no admite corregirlo (ver rawio.RawRow.current)"
            )
        fila.cells_override[fix.attr] = normalize_text(fix.corrected)
        fila.fix_ids.append(fix.id)
        if fix.attr == "id":
            fila.key = normalize_text(fix.corrected)
        aplicadas.append(fix.id)
    assign_occ(filas)
    return aplicadas

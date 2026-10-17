"""`raw/_ledger/`: libro de cambios NT↔MT como artefacto DERIVADO y determinista de `sifen extract`.

Corre el libro vendorizado de pdf_to_md (`sifen_kb.pdf.sifen.changes.libro_de_cambios`, T-302:
211 filas de campos y validaciones emparejadas sobre MT V150 + 27 NT) y lo ancla a raw/: cada
línea de `changes.jsonl` lleva la referencia `raw:` de la fila de la NT y la de la fila vigente del
MT, las páginas y las vigencias literales de la NT (de su fila `fechas`).

Es una DEDUCCIÓN de herramienta: la acción sale del color de la fila o, sin color, de si el ID
está en el MT. Sirve como sugerencia al curar y como oráculo de cobertura (toda fila de una NT
debería quedar reconocida por un efecto en kb/). No es una afirmación normativa.

No entran las filas de esquemas de WS y firma (tipo `esquema` del libro): raw/ no extrae esas
tablas; se cuentan en `index.json` → `excluded`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from sifen_kb.extract_tables import FIELD_COLUMN_ATTR, VALIDATION_COLUMN_ATTR
from sifen_kb.pdf.ir import Document
from sifen_kb.pdf.sifen.changes import Alerta, Cambio, libro_de_cambios
from sifen_kb.rawio import DATES_KEY, index_text, rows_text

NATURE = (
    "Deducción de herramienta (sifen_kb.pdf.sifen.changes, vendorizado de pdf_to_md): sugerencia "
    "para curar y oráculo de cobertura. NO es una afirmación normativa; lo normativo vive en kb/."
)
_ACTION = {"agregado": "added", "modificado": "modified", "eliminado": "deleted", "sin_cambio": "unchanged"}
_TABLE = {"campo": "fields", "validacion": "validations"}


@dataclass(frozen=True)
class LedgerDoc:
    """Un documento ya extraído: su IR (unida, con reglas SIFEN) y sus filas de raw/."""

    doc: str
    sha12: str
    document: Document
    rows: list[dict[str, Any]]
    info: dict[str, Any] | None
    printed: dict[int, int | None]


def make_ref(doc: str, sha12: str, row: dict[str, Any]) -> str:
    occ = f"~{row['occ']}" if row["occ"] != 1 else ""
    return f"raw:{doc}@{sha12}:p{row['page']}:{row['key']}{occ}"


def _action(value: object) -> str | None:
    return _ACTION.get(str(value)) if value is not None else None


def build_ledger(mt: LedgerDoc, notes: list[LedgerDoc], extractor: dict[str, Any]) -> dict[str, str]:
    """Archivos de raw/_ledger/ (nombre → contenido)."""
    libro = libro_de_cambios(mt.document, [n.document for n in notes])
    by_sha = {n.document.sha256: n for n in notes}
    by_number = {n.info["numero"]: n.doc for n in notes if n.info and n.info.get("numero") is not None}

    def nt_doc(number: int | None) -> str | None:
        return by_number.get(number) if number is not None else None

    alerts: dict[tuple[int, str | None, int | None], list[Alerta]] = defaultdict(list)
    for alerta in libro.alertas:
        alerts[(alerta.nt, alerta.id, alerta.nt_pdf_page)].append(alerta)
    attached: set[int] = set()
    used: Counter[tuple[str, str, int, str]] = Counter()
    lines: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for cambio in libro.cambios:
        table = _TABLE.get(cambio.tipo)
        if table is None:
            excluded[cambio.tipo] += 1
            continue
        nt = by_sha[cambio.sha256]
        line = _line(cambio, table, nt, mt, used, nt_doc)
        mine = alerts.get((cambio.nt, cambio.id, cambio.nt_pdf_page), [])
        attached.update(id(a) for a in mine)
        line["alerts"] = [{"type": a.tipo, "detail": a.detalle} for a in mine]
        counts[f"{table}:{line['action']}"] += 1
        lines.append(line)
    sueltas = [
        {"nt": nt_doc(a.nt), "type": a.tipo, "id": a.id, "nt_page": a.nt_pdf_page, "detail": a.detalle}
        for a in libro.alertas
        if id(a) not in attached
    ]
    index = {
        "nature": NATURE,
        "extractor": extractor,
        "mt": {"doc": mt.doc, "sha12": mt.sha12},
        "notes": [{"doc": n.doc, "sha12": n.sha12, "numero": (n.info or {}).get("numero")} for n in notes],
        "counts": dict(sorted(counts.items())),
        "excluded": dict(sorted(excluded.items())),
        "unresolved_refs": sum(1 for ln in lines if ln["nt_ref"] is None)
        + sum(1 for ln in lines if ln["mt_page"] is not None and ln["mt_ref"] is None),
        "alerts": sueltas,
    }
    return {"changes.jsonl": rows_text(lines), "index.json": index_text(index)}


def _line(
    cambio: Cambio,
    table: str,
    nt: LedgerDoc,
    mt: LedgerDoc,
    used: Counter[tuple[str, str, int, str]],
    nt_doc: Any,
) -> dict[str, Any]:
    # Fila de la NT: la k-ésima con esa (tabla, página, clave), en el orden del libro.
    clave = (nt.doc, table, cambio.nt_pdf_page, cambio.id)
    candidatas = [
        r for r in nt.rows if (r["table"], r["page"], r["key"]) == (table, cambio.nt_pdf_page, cambio.id)
    ]
    k = used[clave]
    used[clave] += 1
    nt_ref = make_ref(nt.doc, nt.sha12, candidatas[k]) if k < len(candidatas) else None
    mt_ref = None
    if cambio.mt_pdf_page is not None:
        vigente = next(
            (
                r
                for r in mt.rows
                if (r["table"], r["page"], r["key"]) == (table, cambio.mt_pdf_page, cambio.id)
                and r["row_change"] != "deleted"
            ),
            None,
        )
        mt_ref = make_ref(mt.doc, mt.sha12, vigente) if vigente is not None else None
    fechas = next((r for r in nt.rows if r["table"] == "dates" and r["key"] == DATES_KEY), None)
    to_attr = FIELD_COLUMN_ATTR if table == "fields" else VALIDATION_COLUMN_ATTR
    info = nt.info or {}
    evidencia = cambio.evidencia
    return {
        "nt": nt.doc,
        "nt_number": cambio.nt,
        "table": table,
        "id": cambio.id,
        "action": _ACTION[cambio.cambio],
        "nt_page": cambio.nt_pdf_page,
        "nt_ref": nt_ref,
        "mt_page": cambio.mt_pdf_page,
        "mt_page_printed": mt.printed.get(cambio.mt_pdf_page) if cambio.mt_pdf_page else None,
        "mt_ref": mt_ref,
        "cited_pages": list(cambio.paginas_citadas),
        "differing_attrs": [to_attr.get(c, c) for c in cambio.columnas_distintas],
        "prior_nts": [nt_doc(n) or str(n) for n in cambio.nt_previas],
        "dates_ref": make_ref(nt.doc, nt.sha12, fechas) if fechas is not None else None,
        "test": info.get("test_literal"),
        "prod": info.get("prod_literal"),
        "evidence": {
            "color": _action(evidencia.get("color")),
            "verbs": sorted(_ACTION.get(str(v), str(v)) for v in evidencia.get("verbos", [])),  # type: ignore[union-attr]
            "in_mt": bool(evidencia.get("en_mt")),
            "added_by_nt": nt_doc(evidencia.get("agregado_por_nt")),  # type: ignore[arg-type]
        },
    }

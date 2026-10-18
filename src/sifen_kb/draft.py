"""`sifen draft`: copia literales y fechas de `raw/` a `kb/` (docs/arquitectura.md §D.3 pasos 4–5, §F, §G.3, §J).

Principio: **los literales y las fechas los copia esta herramienta desde `raw/`; nadie los teclea**
(ni una persona ni el LLM). Lo interpretado (`condition`, `enumeration`, `legal_basis`,
`open_questions`, `subject_field`, los efectos) NUNCA lo escribe `draft`: lo hereda tal cual solo
cuando su literal de origen no cambió, y si no, lo deja fuera y avisa.

Modos
-----
- `sifen draft <DocId>` → `draft_document`:
    * sin ficha: crea `kb/documents/<DocId>.yaml` mínima desde el manifiesto (`id`, `kind`
      deducido del DocId, `number`, `title`, `current_revision` = última revisión registrada,
      `curation_scope: dates_only`, sin efectos);
    * con ficha: actualiza SOLO `document_date`, `change_period` y `schedule`. `current_revision`
      no cambia salvo `update_revision=True` (opción de CLI propuesta, no cableada); si hay una
      revisión más nueva, avisa.
    * NT con fila `fechas` (NT 013–027): `document_date` y `schedule.test`/`schedule.prod` con
      `literal` = `cells[attr]`, `value` = `parse_date_literal(literal)` y `stated_in` = CellRef
      `raw:<DocId>@<sha12>:p<N>:fechas#<attr>`. "a definir" ⇒ `value: null`.
    * NT sin fila `fechas` (NT 001–012): `schedule` null; `document_date` desde
      `index.json["nt_info"]["fecha_literal"]` con una PageRef cuya `quote` es la frase «Fecha: …»
      tal como está en la página (verificada por contención en la página normalizada);
      `change_period` desde «Cambios desde la fecha X al Y» (NT 001–011). Si la cita no está en la
      página, el campo queda null y se avisa: no se inventa.
    * MT y documentos que no son NT: solo ficha mínima, sin fechas.
- `sifen draft <EffectId>` → `draft_effect`: versión nueva de la entidad destino del efecto (o
  agrega el efecto a la versión existente con el mismo inicio, §G.3), copiando con
  `RawRow.effective_literal(attr)` todas las columnas literales que la fila citada reproduce y
  heredando de `based_on` (predecesora TEMPORAL en producción, calculada con `temporal`) las que no
  trae. `action: remove` ⇒ lápida. Idempotente: si una versión ya cita el efecto, no hace nada.
- `draft_baseline(kb, key, rowref)` (sin CLI todavía): crea la entidad con su versión `baseline`
  desde la fila del Manual Técnico (línea base de `kb/_meta.yaml`).

Escritura: siempre con `yamlio.write_kb_file` y verificando `yamlio.is_canonical`. Nunca escribe
en `raw/`, `sources/`, `sources.manifest.yaml` ni `kb/_meta.yaml`. Antes de escribir valida el
modelo Pydantic y, para entidades, que la línea de tiempo resultante sea coherente en ambos
ambientes (`temporal.timeline`); si algo falla, no escribe nada.

Decisiones ante ambigüedades (lectura conservadora, documentada aquí y en el informe)
-------------------------------------------------------------------------------------
1. `title` no es un literal con evidencia: es un rótulo determinista. NT → «Nota Técnica N° n»
   (como §G.5); XSD_DIR → «Esquemas XSD (<url>)»; el resto → nombre del archivo del manifiesto
   sin extensión. En una ficha existente no se toca.
2. `kind` por DocId: MT_* → manual; NT_* → technical_note; XSD_DIR/XSD_RAR → xsd_bundle (XSD_RAR
   contiene un XML, pero DNIT lo publica como estructura XSD); CHECKSUM_* → checksum_list;
   TABLA_* → codelist; GUIA_* → guide; COM_* → communication; NORMA_* → legal. `number` solo en NT.
3. `current_revision` de una ficha nueva = la ÚLTIMA revisión registrada en el manifiesto
   (orden de registro, append-only: `sources.latest_revision`).
4. Una NT con número ≥ 13 sin fila `fechas` es un error (no se escribe una ficha "sin calendario"
   que el resolvedor leería como inicio aproximado). Se valida el rótulo de cada columna de la
   fila `fechas` (`Fecha:`, «…Ambiente de Test», «…Producción»); si no corresponde, ese campo no
   se copia y se avisa.
5. PageRef de NT 001–012: `quote` = la frase completa tal como aparece en la página normalizada
   («Fecha: 14-10-2019», «Cambios desde la fecha 10-09-2019 al 14-10-2019»); `literal` = solo la
   fecha (⊂ `quote`). Así la cita es verificable y dice al revisor qué fecha es. «Cambios desde»
   con una sola fecha (NT 006) ⇒ `change_period` null con aviso.
6. En una ficha existente, una fecha cuyo `stated_in` apunta a OTRO documento (p. ej. un
   comunicado de prórroga) se conserva y se avisa: `draft <DocId>` solo reemplaza lo que viene del
   propio documento.
7. Una celda vacía en la fila de la NT se copia como ausente (`None`), no como `""`: la NT
   reproduce la columna y está vacía. Una columna que la tabla de la NT no tiene se hereda.
8. Los literales se copian con `RawRow.effective_literal(attr)`, en el MT y en las NT: el rojo es
   contenido eliminado (decisiones 2 y 3 del usuario, 2026-10-17; §I.4; `rawio`). Si quitó tramos,
   se avisa con su texto para contrastarlos con el PDF (`rendered_literal` es la celda completa).
   La lápida es la excepción: su fila reproduce lo eliminado y se compara con la predecesora por
   `rendered_literal`. Las contradicciones del marcado con la acción o el verbo del efecto
   (`rawio.marking_conflicts`) se avisan: no se deciden aquí; `sifen check` (`marcado`) exige el
   Issue que corresponda.
9. Herencia de lo interpretado: `condition` se hereda de la predecesora solo si `observation` no
   cambió; `enumeration` (+ `enumeration_interpretation`) solo si `observations` no cambió.
   `legal_basis`, `open_questions` y `subject_field` nunca se copian (se avisa si la predecesora
   tenía `legal_basis`). La lápida sigue la misma regla (sus literales no cambian ⇒ hereda
   `condition`).
10. Primera versión de una entidad creada por `action: add` sin predecesora: el modelo exige
    `based_on` ≠ null fuera de la base; se usa `based_on: baseline` (= el estado de la línea base,
    donde la entidad no existía), la misma convención que `tests/unit/test_temporal.py`.
11. `modify`/`remove` sobre una entidad inexistente es un error: primero hace falta su versión
    base (`draft_baseline`); el mensaje lista las filas candidatas del MT. `add` sobre una entidad
    que la línea base ya tiene, o sobre una vigente, es un error (lo decide una persona). `add`
    tras una lápida (reintroducción) se admite con aviso de Issue obligatorio.
12. El efecto debe citar EXACTAMENTE una fila (RowRef, o CellRefs de una misma fila) de su propio
    documento y de la revisión curada (`current_revision`, o `from_revision`); la clave de la fila
    debe ser el ID de la entidad y la tabla, la de su tipo. Una lápida admite como evidencia una
    PageRef (eliminación en prosa).
13. Mismo inicio (§G.3): si ya hay una versión con el mismo inicio en producción, el efecto se
    AGREGA a esa versión (`introduced_by: [e1, e2]`) si también coincide el inicio en test; si
    no, error. La combinación es una fusión a tres vías con base = predecesora: cada fila aporta
    las columnas en que difiere de la predecesora; dos filas que cambian la misma columna de forma
    distinta son un error. Dos versiones prospectivas ("a definir") solo se combinan si son del
    mismo documento.
14. `draft` NO quita `disposition: pending` del efecto ni toca otros efectos: eso es parte de la
    curación (interpretación) y lo recuerda en la salida.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from sifen_kb.load import KB, find_root, load_kb
from sifen_kb.model import (
    DateStatement,
    DocumentSource,
    Effect,
    Field,
    PageRef,
    SourceRevision,
    Validation,
    parse_ref,
)
from sifen_kb.normalize import normalize_text, parse_date_literal, sha12
from sifen_kb.rawio import DATE_ATTRS, DATES_KEY, RawRow, marking_conflicts
from sifen_kb.sources import latest_revision
from sifen_kb.temporal import (
    Start,
    TemporalDataError,
    diff_versions,
    effect_start,
    timeline,
    version_label,
    version_start,
)
from sifen_kb.yamlio import KBYamlError, dump_kb, is_canonical, load_kb_file, load_kb_text, write_kb_file

DOC_ID_RE = re.compile(
    r"^(MT_V150|NT_\d{3}|XSD_DIR|XSD_RAR|CHECKSUM_MT|TABLA_GEO|(GUIA|COM|NORMA)_[A-Z0-9_]+)$"
)
EFFECT_ID_RE = re.compile(r"^(?P<doc>[A-Z][A-Z0-9_]*)#(?P<n>\d+)$")
_KEY_RE = re.compile(r"^(?P<type>field|val):(?P<ctx>[A-Z][A-Z-]*):(?P<id>\w+)$")

# Mapa atributo de celda de raw/ -> atributo del modelo (en el orden de escritura del modelo).
VALIDATION_LITERALS: dict[str, str] = {
    "code": "code",
    "severity": "severity",
    "message": "message",
    "observation": "observation",
}
FIELD_LITERALS: dict[str, str] = {
    "group": "group",
    "parent": "parent",
    "xml_name": "xml_name",
    "description": "description",
    "data_type": "data_type",
    "length": "length",
    "occurrence": "occurrence",
    "observations": "observations",
}
# Atributo interpretado -> literal del que depende (se hereda solo si ese literal no cambió).
VALIDATION_INTERPRETED: dict[str, str] = {"condition": "observation"}
FIELD_INTERPRETED: dict[str, str] = {
    "enumeration": "observations",
    "enumeration_interpretation": "observations",
}
NEVER_COPIED: tuple[str, ...] = ("legal_basis", "open_questions")
INTERPRETED_ATTRS: frozenset[str] = frozenset({*VALIDATION_INTERPRETED, *FIELD_INTERPRETED, *NEVER_COPIED})
OBSERVATION_ATTRS: frozenset[str] = frozenset({"observation", "observations"})
"""Con `declared_scope: row`, el cambio de la observación no necesita `acknowledged_changes`."""

_A_DEFINIR = re.compile(r"(?i)a\s+definir|a\s+comunicar")
_HEADER_OK: dict[str, re.Pattern[str]] = {
    "fecha": re.compile(r"^Fecha:$"),
    "test": re.compile(r"Ambiente de Test$", re.IGNORECASE),
    "prod": re.compile(r"Ambiente de Producci[óo]n$", re.IGNORECASE),
}
_DATE_TXT = r"\d{1,2}[/-]\d{1,2}[/-]\d{4}"
_CHANGE_PERIOD = re.compile(
    rf"Cambios desde la fecha:?\s*(?P<desde>{_DATE_TXT})\s*al\s*(?P<hasta>{_DATE_TXT})(?!\d)", re.IGNORECASE
)
_CHANGE_PERIOD_ANY = re.compile(r"Cambios desde", re.IGNORECASE)
_DOC_ORDER: list[str] = list(DocumentSource.model_fields)
_BASIS_TXT: dict[str, str] = {
    "stated": "declarada",
    "approx": "aproximada",
    "missing_test": "test sin fecha declarada",
    "undated": "a definir o no declarada",
}
_MAX_DOC_TO_TEST_DAYS = 90
"""§K.4 `test_dates_sane`: más de 90 días entre `document_date` y test exige un Issue `erratum`."""

HUMAN_REVIEW_DATES = (
    "REVISIÓN HUMANA OBLIGATORIA: contraste cada fecha con el PDF renderizado (columna y ambiente "
    "correctos, erratas de año). draft copia; no decide."
)
HUMAN_REVIEW_VERSION = (
    "REVISIÓN HUMANA OBLIGATORIA: revise el diff contra la predecesora y los literales contra el PDF; "
    "lo interpretado (condition, enumeration, legal_basis) se completa aparte con interpretation."
)


class DraftError(ValueError):
    """`draft` no puede copiar sin inventar o sin romper la KB: no escribe nada."""


@dataclass
class DraftResult:
    """Qué hizo (o haría, con `write=False`) un `draft`."""

    target: str
    path: Path | None = None
    changed: bool = False
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] | None = None
    review: str = HUMAN_REVIEW_DATES
    dry_run: bool = False
    """`--dry-run`: `changed` dice qué se escribiría; no se escribió nada."""

    def render(self, root: Path | None = None) -> str:
        where = _rel(root, self.path) if self.path is not None else self.target
        if not self.changed:
            state = "sin cambios"
        else:
            state = "se escribiría (--dry-run: no se escribió nada)" if self.dry_run else "escrito"
        head = f"{where}: {state}"
        out = [head, *(f"  {ln}" for ln in self.lines)]
        out += [f"AVISO: {w}" for w in self.warnings]
        out.append(self.review)
        return "\n".join(out)


# --- utilidades ------------------------------------------------------------------------------------
def _rel(root: Path | None, path: Path) -> str:
    if root is None:
        return str(path)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _q(v: Any) -> str:
    """Valor para la salida: «texto» o (vacío)."""
    if v is None or v == "":
        return "(vacío)"
    if isinstance(v, str):
        return f"«{v}»"
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _plain(data: Any) -> Any:
    """Copia JSON pura (sin referencias compartidas, solo dict/list/str/None/bool/int)."""
    return json.loads(json.dumps(data, ensure_ascii=False))


def _as_loaded(data: Any) -> Any:
    """`data` tal como lo leería el KBLoader (todo escalar es str): para comparar con lo ya escrito."""
    return load_kb_text(dump_kb(_plain(data)))


def _set_ordered(data: dict[str, Any], key: str, value: Any, order: list[str]) -> None:
    """Pone `key` en su lugar según el orden del modelo (o la quita si `value` es None)."""
    if value is None:
        data.pop(key, None)
        return
    if key in data:
        data[key] = value
        return
    later = set(order[order.index(key) + 1 :])
    items = list(data.items())
    pos = next((i for i, (k, _) in enumerate(items) if k in later), len(items))
    items.insert(pos, (key, value))
    data.clear()
    data.update(items)


def _write(kb: KB, path: Path, data: dict[str, Any]) -> None:
    data = _plain(data)
    text = dump_kb(data)
    if not is_canonical(text, source=str(path)):  # defensa: el volcador debe ser estable
        raise DraftError(f"{_rel(kb.root, path)}: el volcado no es canónico; no se escribe")
    root = kb.root.resolve()
    for forbidden in ("raw", "sources"):
        if (root / forbidden) in path.resolve().parents:
            raise DraftError(f"draft no escribe en {forbidden}/")
    if path.resolve() in (root / "kb" / "_meta.yaml", root / "sources.manifest.yaml"):
        raise DraftError("draft no escribe kb/_meta.yaml")
    write_kb_file(path, data)


def _check_load_errors(kb: KB, *paths: Path) -> None:
    """Aborta si no cargó el manifiesto o alguno de los archivos que se van a tocar."""
    rels = set()
    for p in paths:
        try:
            rels.add(str(p.relative_to(kb.root)))
        except ValueError:
            continue
    for err in kb.errors:
        if err.startswith("sources.manifest.yaml") or any(err.startswith(f"{r}:") for r in rels):
            raise DraftError(f"kb/ no carga: {err}")


def _doc_number(doc_id: str) -> int | None:
    return int(doc_id[3:]) if doc_id.startswith("NT_") else None


def _doc_kind(doc_id: str) -> str:
    if doc_id.startswith("MT_"):
        return "manual"
    if doc_id.startswith("NT_"):
        return "technical_note"
    if doc_id.startswith("XSD_"):
        return "xsd_bundle"
    if doc_id.startswith("CHECKSUM_"):
        return "checksum_list"
    if doc_id.startswith("TABLA_"):
        return "codelist"
    if doc_id.startswith("GUIA_"):
        return "guide"
    if doc_id.startswith("COM_"):
        return "communication"
    if doc_id.startswith("NORMA_"):
        return "legal"
    raise DraftError(f"{doc_id}: no se puede deducir `kind` del DocId")


def _doc_title(doc_id: str, rev: SourceRevision) -> str:
    n = _doc_number(doc_id)
    if n is not None:
        return f"Nota Técnica N° {n}"
    if doc_id == "XSD_DIR":
        return f"Esquemas XSD ({rev.url})"
    return Path(rev.filename).stem.strip() or doc_id


def _document_path(kb: KB, doc_id: str) -> Path:
    return kb.paths.get(doc_id) or kb.root / "kb" / "documents" / f"{doc_id}.yaml"


def _entity_parts(key: str) -> tuple[str, str, str]:
    m = _KEY_RE.match(key)
    if not m:
        raise DraftError(f"clave de entidad inválida: {key!r} (se espera field:DE:<ID> o val:DE:<ID>)")
    return m["type"], m["ctx"], m["id"]


def _entity_path(kb: KB, key: str) -> Path:
    etype, ctx, ent_id = _entity_parts(key)
    sub = "fields" if etype == "field" else "validations"
    return kb.paths.get(key) or kb.root / "kb" / sub / ctx / f"{ent_id}.yaml"


def _literals_of(etype: str) -> dict[str, str]:
    return FIELD_LITERALS if etype == "field" else VALIDATION_LITERALS


def _interpreted_of(etype: str) -> dict[str, str]:
    return FIELD_INTERPRETED if etype == "field" else VALIDATION_INTERPRETED


def _table_of(etype: str) -> str:
    return "fields" if etype == "field" else "validations"


def _stated_doc(stmt: Any) -> str | None:
    si = stmt.get("stated_in") if isinstance(stmt, dict) else None
    if isinstance(si, str):
        try:
            return str(parse_ref(si)["doc"])
        except ValueError:
            return None
    if isinstance(si, dict):
        return si.get("doc")
    return None


# --- fechas de un documento ------------------------------------------------------------------------
def _statement(literal: str, stated_in: Any, label: str, res: DraftResult) -> dict[str, Any] | None:
    if not literal:
        res.warnings.append(f"{label}: celda vacía; no se copia")
        return None
    value = parse_date_literal(literal)
    if value is None:
        if _A_DEFINIR.search(literal):
            res.lines.append(f"{label}: {_q(literal)} = a definir → value: null (prospectiva, nunca vigente)")
        else:
            res.warnings.append(
                f"{label}: {_q(literal)} no se reconoce como fecha ni como «a definir»: value: null "
                "(la versión quedaría prospectiva); contrastar con el PDF"
            )
    stmt = {"value": value.isoformat() if value else None, "literal": literal, "stated_in": stated_in}
    try:
        DateStatement.model_validate(stmt)
    except ValidationError as e:
        raise DraftError(f"{label}: fecha inválida {literal!r}: {e}") from None
    return stmt


def _page_ref(kb: KB, doc_id: str, s12: str, page: int, index: dict[str, Any] | None, quote: str) -> Any:
    """PageRef verificada: `normalize_text(quote)` contenida en la página normalizada; None si no."""
    text = kb.raw.page_text(doc_id, s12, page)
    if text is None or normalize_text(quote) not in normalize_text(text):
        return None
    printed = next(
        (p.get("page_printed") for p in (index or {}).get("pages", []) if p.get("page_pdf") == page), None
    )
    ref: dict[str, Any] = {"doc": doc_id, "rev": s12, "page_pdf": page}
    if printed is not None:
        ref["page_printed"] = int(printed)
    ref["quote"] = quote
    PageRef.model_validate(ref)
    return ref


def _dates_from_row(row: RawRow, res: DraftResult) -> dict[str, dict[str, Any]]:
    present = [a for a in DATE_ATTRS if a in row.cells]
    if len(row.header) != len(present):
        raise DraftError(
            f"{row.ref}: {len(row.header)} rótulos para {len(present)} celdas de fecha; "
            "no se puede saber qué columna es qué ambiente"
        )
    out: dict[str, dict[str, Any]] = {}
    for attr, label in zip(present, row.header, strict=True):
        if not _HEADER_OK[attr].search(normalize_text(label)):
            res.warnings.append(
                f"{row.ref}#{attr}: rótulo {_q(label)} no corresponde a «{attr}»; no se copia"
            )
            continue
        if any(m["attr"] == attr for m in row.marks):
            res.warnings.append(
                f"{row.ref}#{attr}: la celda tiene tramos resaltados/tachados; contrastar con el PDF"
            )
        stmt = _statement(row.cells[attr], f"{row.ref}#{attr}", f"{row.ref}#{attr}", res)
        if stmt is not None:
            out[attr] = stmt
    return out


def _date_from_page(
    kb: KB, doc_id: str, s12: str, index: dict[str, Any] | None, res: DraftResult
) -> tuple[dict[str, Any] | None, list[int]]:
    info = (index or {}).get("nt_info") or {}
    lit, page = info.get("fecha_literal"), info.get("page")
    if not lit or not page:
        res.warnings.append(f"{doc_id}: index.json no trae nt_info.fecha_literal/page: document_date null")
        return None, []
    text = kb.raw.page_text(doc_id, s12, int(page))
    if text is None:
        res.warnings.append(f"{doc_id}: falta raw/…/pages/p{int(page):03d}.txt: document_date null")
        return None, [int(page)]
    m = re.search(r"Fecha:\s*" + re.escape(lit) + r"(?!\d)", normalize_text(text))
    ref = _page_ref(kb, doc_id, s12, int(page), index, m.group(0)) if m else None
    if ref is None:
        res.warnings.append(
            f"{doc_id}: «Fecha: {lit}» no está en la página {page} de raw/: document_date null (no se inventa)"
        )
        return None, [int(page)]
    return _statement(lit, ref, "document_date", res), [int(page)]


def _change_period(
    kb: KB, doc_id: str, s12: str, index: dict[str, Any] | None, pages: list[int], res: DraftResult
) -> list[dict[str, Any]] | None:
    for page in pages:
        text = kb.raw.page_text(doc_id, s12, page)
        if text is None:
            continue
        norm = normalize_text(text)
        m = _CHANGE_PERIOD.search(norm)
        if m:
            ref = _page_ref(kb, doc_id, s12, page, index, m.group(0))
            if ref is None:  # imposible: la cita sale de la propia página
                res.warnings.append(f"{doc_id}: «{m.group(0)}» no verificable en la página {page}")
                return None
            a = _statement(m["desde"], ref, "change_period[0]", res)
            b = _statement(m["hasta"], ref, "change_period[1]", res)
            return [a, b] if a is not None and b is not None else None
        if _CHANGE_PERIOD_ANY.search(norm):
            res.warnings.append(
                f"{doc_id}: «Cambios desde …» sin dos fechas reconocibles en la página {page}: "
                "change_period null (contrastar con el PDF)"
            )
            return None
    return None


def _dates_sanity(doc_id: str, out: dict[str, Any], res: DraftResult) -> None:
    def val(stmt: Any) -> date | None:
        return date.fromisoformat(stmt["value"]) if stmt and stmt.get("value") else None

    sched = out.get("schedule") or {}
    t, p, d = val(sched.get("test")), val(sched.get("prod")), val(out.get("document_date"))
    if t and p and t > p:
        res.warnings.append(f"{doc_id}: test ({t}) posterior a producción ({p}): contrastar con el PDF")
    if d and t and (t - d).days > _MAX_DOC_TO_TEST_DAYS:
        res.warnings.append(
            f"{doc_id}: {(t - d).days} días entre document_date ({d}) y test ({t}): posible errata de año; "
            "exige un Issue `erratum` (§K.4 test_dates_sane)"
        )
    cp = out.get("change_period")
    if cp and val(cp[0]) and val(cp[1]) and val(cp[0]) > val(cp[1]):
        res.warnings.append(f"{doc_id}: change_period invertido ({cp[0]['literal']} > {cp[1]['literal']})")


def _document_dates(kb: KB, doc_id: str, rev: SourceRevision, res: DraftResult) -> dict[str, Any]:
    """{document_date, change_period, schedule} copiados de raw/ de la revisión `rev` (solo NT)."""
    s12 = sha12(rev.sha256)
    index = kb.raw.index(doc_id, s12)
    rows = list(kb.raw.rows(doc_id, s12).values())
    if index is None and not rows:
        raise DraftError(f"{doc_id}@{s12}: raw/ no extraído para esta revisión (ejecute `sifen extract`)")
    fechas = [r for r in rows if r.key == DATES_KEY]
    if len(fechas) > 1:
        raise DraftError(f"{doc_id}@{s12}: {len(fechas)} filas `fechas`; no se elige una")
    out: dict[str, Any] = {"document_date": None, "change_period": None, "schedule": None}
    number = _doc_number(doc_id)
    if fechas:
        row = fechas[0]
        stmts = _dates_from_row(row, res)
        out["document_date"] = stmts.get("fecha")
        if "fecha" not in stmts:
            res.warnings.append(f"{row.ref}: sin «Fecha:» del documento: document_date null")
        sched = {env: stmts[env] for env in ("test", "prod") if env in stmts}
        out["schedule"] = sched or None
        for env in ("test", "prod"):
            if env not in sched:
                res.warnings.append(
                    f"{doc_id}: sin fecha de {env} en la tabla de fechas (schedule.{env} null)"
                )
        pages = sorted(set(row.pages))
    else:
        if number is not None and number >= 13:
            raise DraftError(
                f"{doc_id}@{s12}: una NT ≥ 013 declara su calendario y raw/ no tiene la fila `fechas`; "
                "no se escribe una ficha sin calendario (revisar la extracción)"
            )
        res.lines.append(f"{doc_id}: sin tabla de fechas (NT 001–012): schedule null (supuesto A1)")
        out["document_date"], pages = _date_from_page(kb, doc_id, s12, index, res)
    out["change_period"] = _change_period(kb, doc_id, s12, index, pages, res)
    _dates_sanity(doc_id, out, res)
    return out


def _describe_stmt(stmt: Any) -> str:
    if stmt is None:
        return "(null)"
    si = stmt["stated_in"]
    if isinstance(si, dict):
        page = (
            f"p. {si['page_printed']} impresa / {si['page_pdf']} PDF"
            if si.get("page_printed")
            else f"p. {si['page_pdf']} PDF"
        )
        where = f"{si['doc']} rev {si['rev']} {page}, cita {_q(si['quote'])}"
    else:
        where = si
    return f"{_q(stmt['literal'])} → {stmt['value'] or 'null'} · {where}"


def _merge_dates(
    doc_id: str, data: dict[str, Any], new: dict[str, Any], res: DraftResult, *, created: bool
) -> None:
    """Escribe los campos de fecha en `data`, conservando los declarados en OTRO documento."""
    for key in ("document_date", "change_period", "schedule"):
        old = data.get(key)
        value = new.get(key)
        if key == "schedule":
            merged: dict[str, Any] = {}
            for env in ("test", "prod"):
                o = (old or {}).get(env) if isinstance(old, dict) else None
                n = (value or {}).get(env)
                if o is not None and _stated_doc(o) not in (None, doc_id):
                    res.warnings.append(
                        f"schedule.{env}: se conserva la fecha declarada en {_stated_doc(o)} (no en {doc_id})"
                    )
                    n = o
                if n is not None:
                    merged[env] = n
            value = merged or None
        elif key == "change_period":
            if isinstance(old, list) and any(_stated_doc(s) not in (None, doc_id) for s in old):
                res.warnings.append("change_period: se conserva el declarado en otro documento")
                value = old
        elif old is not None and _stated_doc(old) not in (None, doc_id):
            res.warnings.append(
                f"{key}: se conserva la fecha declarada en {_stated_doc(old)} (no en {doc_id})"
            )
            value = old
        _set_ordered(data, key, value, _DOC_ORDER)
        if created:
            if key == "schedule":
                for env in ("test", "prod"):
                    if value and env in value:
                        res.lines.append(f"schedule.{env}: {_describe_stmt(value[env])}")
            elif key == "change_period":
                if value:
                    res.lines.append(
                        f"change_period: {_describe_stmt(value[0])} … {_describe_stmt(value[1])}"
                    )
            elif value is not None:
                res.lines.append(f"{key}: {_describe_stmt(value)}")
            continue
        if _as_loaded(old) != _as_loaded(value):
            if key == "schedule":
                for env in ("test", "prod"):
                    o = (old or {}).get(env) if isinstance(old, dict) else None
                    n = (value or {}).get(env)
                    if _as_loaded(o) != _as_loaded(n):
                        res.lines.append(f"schedule.{env}: {_describe_stmt(o)}  ⇒  {_describe_stmt(n)}")
            elif key == "change_period":
                res.lines.append(f"change_period: {_plain(old)}  ⇒  {_plain(value)}")
            else:
                res.lines.append(f"{key}: {_describe_stmt(old)}  ⇒  {_describe_stmt(value)}")


def draft_document(kb: KB, doc_id: str, *, update_revision: bool = False, write: bool = True) -> DraftResult:
    """`sifen draft <DocId>`: ficha mínima o actualización de sus fechas (ver el docstring del módulo).

    `update_revision=True` (opción de CLI propuesta, p. ej. `--update-revision`) mueve
    `current_revision` a la última revisión del manifiesto y copia las fechas de esa revisión.
    """
    if not DOC_ID_RE.match(doc_id):
        raise DraftError(f"DocId inválido: {doc_id!r}")
    path = _document_path(kb, doc_id)
    _check_load_errors(kb, path)
    latest = latest_revision(kb.manifest, doc_id)
    if latest is None:
        raise DraftError(
            f"{doc_id} no tiene revisiones en sources.manifest.yaml: una persona debe registrarla "
            "(`sifen source add`)"
        )
    res = DraftResult(target=doc_id, path=path)
    existing = kb.documents.get(doc_id)
    if existing is None and path.exists():
        raise DraftError(f"{_rel(kb.root, path)} existe pero no carga: corríjalo antes (no se sobrescribe)")
    created = existing is None
    if created:
        rev = latest
        data: dict[str, Any] = {"id": doc_id, "kind": _doc_kind(doc_id)}
        if _doc_number(doc_id) is not None:
            data["number"] = str(_doc_number(doc_id))
        data["title"] = _doc_title(doc_id, rev)
        data["current_revision"] = rev.sha256
        data["curation_scope"] = "dates_only"
        res.lines.append(f"ficha nueva: kind {data['kind']}, curation_scope dates_only, sin efectos")
        res.lines.append(f"current_revision: {sha12(rev.sha256)} (última revisión registrada)")
        old_data = None
    else:
        data = load_kb_file(path)
        old_data = _plain(data)
        cur = existing.current_revision
        cur_rev = next((r for r in kb.manifest.revisions if r.doc == doc_id and r.sha256 == cur), None)
        if cur_rev is None:
            raise DraftError(f"{doc_id}: current_revision {sha12(cur)} no está en el manifiesto")
        rev = cur_rev
        if latest.sha256 != cur:
            if update_revision:
                rev = latest
                data["current_revision"] = latest.sha256
                res.lines.append(
                    f"current_revision: {sha12(cur)} ⇒ {sha12(latest.sha256)} (pedido explícitamente)"
                )
                res.warnings.append(
                    "revisión nueva: si cambió una fecha es una prórroga (§G.3): agregue un Issue `temporal` "
                    "(resuelto) con ambas fechas; si cambiaron filas, efectos con `from_revision`"
                )
            else:
                res.warnings.append(
                    f"{doc_id}: el manifiesto tiene una revisión más nueva ({sha12(latest.sha256)}); "
                    f"current_revision sigue en {sha12(cur)} y las fechas se copiaron de esa revisión "
                    "(para curar la nueva: opción propuesta `--update-revision`)"
                )
    if doc_id.startswith("NT_"):
        dates = _document_dates(kb, doc_id, rev, res)
        _merge_dates(doc_id, data, dates, res, created=created)
    else:
        res.lines.append(f"{doc_id}: no es una NT: sin fechas que copiar (schedule null)")
    try:
        model = DocumentSource.model_validate(data)
    except ValidationError as e:
        raise DraftError(f"{doc_id}: la ficha resultante no valida: {e}") from None
    data = _plain(data)
    res.data = data
    res.changed = old_data is None or _as_loaded(data) != old_data  # contenido, no formato (`sifen fmt`)
    if not created and not res.changed:
        res.lines.append("fechas ya al día con raw/ (nada que escribir)")
    if write and res.changed:
        _write(kb, path, data)
        kb.documents[doc_id] = model
        kb.paths[doc_id] = path
        kb.reindex()
    return res


# --- versiones de entidades ------------------------------------------------------------------------
def _baseline_rev(kb: KB) -> tuple[str | None, str | None]:
    if kb.meta is not None:
        return kb.meta.baseline_doc, sha12(kb.meta.baseline_sha256)
    rev = latest_revision(kb.manifest, "MT_V150")
    return ("MT_V150", sha12(rev.sha256)) if rev else (None, None)


def _baseline_candidates(kb: KB, etype: str, ent_id: str) -> list[str]:
    doc, s12 = _baseline_rev(kb)
    if doc is None or s12 is None:
        return []
    rows = kb.raw.rows(doc, s12).values()
    return sorted(
        (r.ref for r in rows if r.key == ent_id and r.table == _table_of(etype)),
        key=lambda ref: int(parse_ref(ref)["page"]),  # type: ignore[arg-type]
    )


def _check_row(row: RawRow, etype: str, ent_id: str, ref: str) -> None:
    if row.key != ent_id:
        raise DraftError(f"{ref}: la fila es {row.key!r}, no {ent_id!r} (fila citada ≠ ID de la entidad)")
    if row.table != _table_of(etype):
        raise DraftError(f"{ref}: la fila es de la tabla {row.table!r}, no de {_table_of(etype)!r}")


def _copy_row(row: RawRow, etype: str, res: DraftResult) -> tuple[dict[str, str | None], list[str]]:
    """Columnas literales que la fila reproduce: atributo del modelo -> literal efectivo (o None si vacío)."""
    out: dict[str, str | None] = {}
    for raw_attr, attr in _literals_of(etype).items():
        if raw_attr not in row.cells:
            continue
        value = row.effective_literal(raw_attr)
        out[attr] = value or None
        removed = row.removed_spans(raw_attr)
        if removed:
            res.warnings.append(
                f"{attr}: se quitaron de {row.ref} los tramos en rojo (contenido eliminado) "
                f"{', '.join(_q(s) for s in removed)}; contrastar con el PDF"
            )
    return out, list(out)


def _marking_warnings(
    res: DraftResult, row: RawRow | None, eff: Effect, etype: str, pred_raw: dict[str, Any] | None
) -> None:
    """Avisa de las contradicciones del marcado (`rawio.marking_conflicts`); no decide nada."""
    if row is None:
        return
    pred = {raw: (pred_raw or {}).get(attr) for raw, attr in _literals_of(etype).items()}
    conflicts = marking_conflicts(
        row,
        action=eff.action,
        verb_literal=eff.verb_literal,
        attrs=list(_literals_of(etype)),
        predecessor=pred if pred_raw is not None else None,
    )
    for c in conflicts:
        need = "un Issue BLOQUEANTE" if c.blocking else "un Issue de trazabilidad (no bloqueante)"
        res.warnings.append(
            f"marcado ({c.kind}): {c.message}. Exige {need} sobre {eff.target} o {eff.id} que cite la fila "
            "(`sifen check`, comprobación `marcado`); draft no decide"
        )


def _version_dict(
    etype: str,
    introduced_by: Any,
    based_on: Any,
    kind: str,
    literals: dict[str, Any],
    interpreted: dict[str, Any],
    evidence: list[Any],
) -> dict[str, Any]:
    d: dict[str, Any] = {"introduced_by": introduced_by}
    if based_on is not None:
        d["based_on"] = based_on
    if kind == "tombstone":
        d["kind"] = "tombstone"
    for attr in _literals_of(etype).values():
        if literals.get(attr) is not None:
            d[attr] = literals[attr]
    for attr in _interpreted_of(etype):
        if interpreted.get(attr) is not None:
            d[attr] = interpreted[attr]
    d["evidence"] = evidence
    return d


def _validate_entity(etype: str, data: dict[str, Any]) -> Field | Validation:
    try:
        return (Field if etype == "field" else Validation).model_validate(data)
    except ValidationError as e:
        raise DraftError(
            f"{data.get('key')}: la entidad resultante no valida (¿celda mal extraída? proponga una "
            f"corrección en extraction/fixes.yaml; no se teclea): {e}"
        ) from None


def _commit_entity(kb: KB, key: str, etype: str, model: Field | Validation) -> Field | Validation | None:
    """Pone `model` en la KB en memoria y verifica la línea de tiempo; devuelve la anterior."""
    target = kb.fields if etype == "field" else kb.validations
    prev = target.get(key)
    target[key] = model  # type: ignore[assignment]
    try:
        for env in ("test", "prod"):
            timeline(kb, key, env)  # type: ignore[arg-type]
    except TemporalDataError as e:
        if prev is None:
            target.pop(key, None)
        else:
            target[key] = prev  # type: ignore[assignment]
        raise DraftError(f"{key}: la línea de tiempo resultante es incoherente: {e}") from None
    return prev


def _rollback(kb: KB, key: str, etype: str, prev: Field | Validation | None) -> None:
    target = kb.fields if etype == "field" else kb.validations
    if prev is None:
        target.pop(key, None)
    else:
        target[key] = prev  # type: ignore[assignment]


def draft_baseline(kb: KB, key: str, rowref: str, *, write: bool = True) -> DraftResult:
    """Crea la entidad `key` con su versión `baseline` copiada de la fila `rowref` del Manual Técnico.

    La fila debe ser de la línea base (`kb/_meta.yaml`: `baseline_doc` + `baseline_sha256`; sin
    `_meta`, una revisión registrada de MT_V150, con aviso), su clave = el ID y su tabla = el tipo.
    Idempotente si la entidad ya tiene esa misma base; error si tiene otra base o no tiene base
    (una entidad creada por `add` no recibe una base a posteriori sin decisión humana).
    `subject_field` (relación campo↔validación) es interpretación: no se escribe.
    """
    etype, ctx, ent_id = _entity_parts(key)
    path = _entity_path(kb, key)
    _check_load_errors(kb, path)
    try:
        ref = parse_ref(rowref)
    except ValueError as e:
        raise DraftError(str(e)) from None
    if ref["attr"]:
        raise DraftError(f"{rowref}: se espera una RowRef (sin #atributo)")
    res = DraftResult(target=key, path=path, review=HUMAN_REVIEW_VERSION)
    base_doc, base12 = _baseline_rev(kb)
    if kb.meta is None:
        if base_doc is None or (ref["doc"], ref["sha12"]) != (base_doc, base12):
            raise DraftError(f"{rowref}: sin kb/_meta.yaml solo se admite la última revisión de MT_V150")
        res.warnings.append("kb/_meta.yaml ausente: se tomó la última revisión de MT_V150 como línea base")
    elif (ref["doc"], ref["sha12"]) != (base_doc, base12):
        raise DraftError(f"{rowref}: no es la línea base declarada en kb/_meta.yaml ({base_doc}@{base12})")
    row = kb.raw.row(rowref)
    if row is None:
        raise DraftError(f"{rowref}: no resuelve a ninguna fila de raw/")
    _check_row(row, etype, ent_id, rowref)
    ent = kb.entity(key)
    if ent is None and path.exists():
        raise DraftError(f"{_rel(kb.root, path)} existe pero no carga: corríjalo antes (no se sobrescribe)")
    if ent is not None:
        bases = [v for v in ent.versions if v.introduced_by == "baseline"]
        if bases and row.ref in bases[0].evidence:
            res.lines.append(f"{key} ya tiene su versión base desde {row.ref}: no se duplica")
            return res
        if bases:
            raise DraftError(f"{key} ya tiene una versión base con otra evidencia ({bases[0].evidence})")
        raise DraftError(
            f"{key} existe sin versión base (la creó un `add`): agregarle una base del MT contradice ese "
            "efecto; lo decide una persona (Issue)"
        )
    literals, copied = _copy_row(row, etype, res)
    version = _version_dict(etype, "baseline", None, "content", literals, {}, [row.ref])
    data: dict[str, Any] = {"key": key, "context": ctx, "id": ent_id, "versions": [version]}
    model = _validate_entity(etype, data)
    prev = _commit_entity(kb, key, etype, model)
    res.lines.append(f"entidad nueva con versión base (línea base) ← {row.ref}")
    res.lines.append(f"copiado: {', '.join(copied)}")
    for attr in copied:
        res.lines.append(f"  {attr}: {_q(literals.get(attr))}")
    if etype == "val":
        res.lines.append("pendiente (interpretación, no lo escribe draft): subject_field, condition")
    data = _plain(data)
    res.data = data
    res.changed = True
    if write:
        try:
            _write(kb, path, data)
        except DraftError:
            _rollback(kb, key, etype, prev)
            raise
        kb.paths[key] = path
    else:
        _rollback(kb, key, etype, prev)
    return res


def _effect_row(kb: KB, doc: DocumentSource, eff: Effect, etype: str, ent_id: str) -> RawRow | None:
    rows: dict[str, RawRow] = {}
    for ev in eff.evidence:
        if not isinstance(ev, str):
            continue
        p = parse_ref(ev)
        if p["doc"] != doc.id:
            raise DraftError(f"{eff.id}: la evidencia {ev} es de otro documento ({p['doc']})")
        rev12 = eff.from_revision or sha12(doc.current_revision)
        if p["sha12"] != rev12:
            raise DraftError(
                f"{eff.id}: la evidencia {ev} es de la revisión {p['sha12']}; la ficha está curada contra {rev12}"
            )
        row = kb.raw.row(ev)
        if row is None:
            raise DraftError(f"{eff.id}: {ev} no resuelve a ninguna fila de raw/")
        rows[row.ref] = row
    if len(rows) > 1:
        raise DraftError(
            f"{eff.id}: cita {len(rows)} filas ({', '.join(rows)}); draft no elige: un efecto por fila"
        )
    if not rows:
        if eff.action == "remove":
            return None
        raise DraftError(f"{eff.id}: sin RowRef en `evidence`: no hay fila de la que copiar literales")
    row = next(iter(rows.values()))
    _check_row(row, etype, ent_id, row.ref)
    return row


def _predecessor(starts: list[Start], new: Start, exclude: set[int]) -> int | None:
    """Índice de la versión con el mayor inicio estrictamente anterior a `new` (prospectiva: la última)."""
    nd = new[0]
    cands = [
        (s[0], i)
        for i, s in enumerate(starts)
        if s[0] is not None and i not in exclude and (nd is None or s[0] < nd)
    ]
    return max(cands)[1] if cands else None


def _describe_start(s: Start) -> str:
    if s[1] == "baseline":
        return "línea base"
    basis = _BASIS_TXT.get(s[1], s[1])
    return f"{s[0]} ({basis})" if s[0] is not None else f"sin fecha ({basis})"


def _scope_outside(kb: KB, effect_ids: list[str], changed: list[str]) -> list[str]:
    outside = []
    for attr in changed:
        if attr in INTERPRETED_ATTRS:
            continue
        ok = False
        for eid in effect_ids:
            e = kb.effect(eid)
            if e.declared_scope == "row":
                ok = ok or attr in OBSERVATION_ATTRS or attr in e.acknowledged_changes
            else:
                ok = ok or attr in e.declared_scope
        if not ok:
            outside.append(attr)
    return outside


def _inherit_interpreted(
    etype: str, pred_raw: dict[str, Any] | None, literals: dict[str, Any], res: DraftResult
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if pred_raw is None:
        return out
    for attr, source in _interpreted_of(etype).items():
        if pred_raw.get(attr) is None:
            continue
        if literals.get(source) == pred_raw.get(source):
            out[attr] = pred_raw[attr]
        elif attr != "enumeration_interpretation":
            res.warnings.append(
                f"{attr}: la predecesora lo tenía y cambió el literal `{source}`: NO se hereda; "
                "formalizar de nuevo (interpretación con interpretation: {by: llm, run: …})"
            )
    for attr in NEVER_COPIED:
        if pred_raw.get(attr):
            res.warnings.append(
                f"{attr}: la predecesora lo tenía y draft no lo copia (interpretación): si sigue aplicando, "
                "agréguelo con su evidencia; si no, el diff lo mostrará"
            )
    return out


def _three_way(
    etype: str,
    ours: dict[str, Any],
    base: dict[str, Any] | None,
    theirs: dict[str, Any],
    eid: str,
) -> list[str]:
    """Fusiona en `ours` las columnas que `theirs` cambia respecto de `base`; devuelve las tocadas."""
    touched = []
    for attr in theirs:
        t, o, b = theirs[attr], ours.get(attr), (base or {}).get(attr)
        if t == o or t == b:
            continue
        if o != b:
            raise DraftError(
                f"{eid}: la versión con el mismo inicio ya cambió `{attr}` a {_q(o)} y esta fila dice {_q(t)}: "
                "dos efectos del mismo día discrepan; lo decide una persona (Issue)"
            )
        if t is None:
            ours.pop(attr, None)
        else:
            ours[attr] = t
        touched.append(attr)
    order = [*_literals_of(etype).values()]
    lits = {a: ours.pop(a) for a in order if a in ours}
    rest = list(ours.items())
    ours.clear()
    head = [(k, v) for k, v in rest if k in ("introduced_by", "based_on", "kind")]
    tail = [(k, v) for k, v in rest if k not in ("introduced_by", "based_on", "kind")]
    ours.update(head)
    ours.update(lits)
    ours.update(tail)
    return touched


def draft_effect(kb: KB, effect_id: str, *, write: bool = True) -> DraftResult:
    """`sifen draft <EffectId>`: versión nueva (o fusión §G.3) de la entidad destino del efecto."""
    m = EFFECT_ID_RE.match(effect_id)
    if not m:
        raise DraftError(f"EffectId inválido: {effect_id!r} (se espera p. ej. NT_024#1)")
    doc_path = _document_path(kb, m["doc"])
    _check_load_errors(kb, doc_path)
    if not kb.has_effect(effect_id):
        raise DraftError(
            f"el efecto {effect_id} no existe en {_rel(kb.root, doc_path)}: el curador lo escribe primero "
            "(verb_literal, action, target, declared_scope, evidence = RowRef de la fila, interpretation)"
        )
    doc, eff = kb.doc_of(effect_id), kb.effect(effect_id)
    if eff.disposition == "not_modeled":
        raise DraftError(f"{effect_id} es `not_modeled`: no tiene versión")
    if eff.target is None:
        raise DraftError(f"{effect_id} no tiene `target`: no hay entidad que versionar")
    key = eff.target
    etype, ctx, ent_id = _entity_parts(key)
    path = _entity_path(kb, key)
    _check_load_errors(kb, doc_path, path)
    if doc.schedule is None and (_doc_number(doc.id) or 0) >= 13:
        raise DraftError(f"{doc.id} no tiene calendario en kb/: ejecute primero `sifen draft {doc.id}`")
    res = DraftResult(target=effect_id, path=path, review=HUMAN_REVIEW_VERSION)
    if doc.schedule is None and doc.document_date is None:
        res.warnings.append(
            f"{doc.id} no tiene fechas en kb/: su inicio es aproximado (anterior a la cobertura)"
        )

    ent = kb.entity(key)
    if ent is None and path.exists():
        raise DraftError(f"{_rel(kb.root, path)} existe pero no carga: corríjalo antes (no se sobrescribe)")
    versions = list(ent.versions) if ent is not None else []
    for i, v in enumerate(versions):
        if v.introduced_by != "baseline" and effect_id in v.introduced_by:
            res.lines.append(
                f"{effect_id} ya está aplicado: lo cita la versión {i} ({version_label(v)}); no se duplica"
            )
            return res

    row = _effect_row(kb, doc, eff, etype, ent_id)
    try:
        if ent is not None:
            for env in ("test", "prod"):
                timeline(kb, key, env)  # type: ignore[arg-type]
        new_start = {env: effect_start(kb, effect_id, env) for env in ("test", "prod")}  # type: ignore[arg-type]
        starts = {env: [version_start(kb, v, env) for v in versions] for env in ("test", "prod")}  # type: ignore[arg-type]
    except TemporalDataError as e:
        raise DraftError(f"{key}: datos temporales incoherentes: {e}") from None

    # ¿Mismo inicio que una versión existente? (§G.3)
    np_ = new_start["prod"]
    if np_[0] is not None:
        same = [i for i, s in enumerate(starts["prod"]) if s == np_]
        clash = [i for i, s in enumerate(starts["prod"]) if s[0] == np_[0] and s != np_]
        if clash:
            raise DraftError(
                f"{effect_id}: misma fecha de producción que otra versión con distinta base de inicio"
            )
    else:
        pros = [i for i, s in enumerate(starts["prod"]) if s[0] is None]
        same = [
            i
            for i in pros
            if versions[i].introduced_by != "baseline"
            and all(kb.has_effect(e) and kb.doc_of(e).id == doc.id for e in versions[i].introduced_by)
        ]
        if set(pros) - set(same):
            raise DraftError(
                f"{effect_id}: inicio en producción sin fecha y ya hay otra versión prospectiva de otro "
                "documento: no hay orden temporal para elegir la predecesora (lo decide una persona)"
            )
    if len(same) > 1:
        raise DraftError(f"{key}: varias versiones con el mismo inicio que {effect_id}")

    ent_raw: dict[str, Any] | None = load_kb_file(path) if ent is not None else None
    raw_versions: list[dict[str, Any]] = list(ent_raw["versions"]) if ent_raw else []
    pred = _predecessor(starts["prod"], np_, set(same))
    pred_v = versions[pred] if pred is not None else None
    pred_raw = raw_versions[pred] if pred is not None else None

    if same:
        idx = same[0]
        if starts["test"][idx] != new_start["test"]:
            raise DraftError(
                f"{effect_id}: mismo inicio en producción que {version_label(versions[idx])} pero distinto en test "
                f"({_describe_start(new_start['test'])} ≠ {_describe_start(starts['test'][idx])}): "
                "no puede ser una sola versión (§G.3)"
            )
        return _merge_into(
            kb, res, key, etype, eff, row, idx, versions, raw_versions, ent_raw, pred_v, pred_raw, write
        )

    # Reglas por acción.
    if eff.action in ("modify", "remove"):
        if ent is None:
            cands = _baseline_candidates(kb, etype, ent_id)
            hint = (
                f" Filas candidatas en la línea base: {', '.join(cands)}. Cree la versión base con "
                f"draft_baseline (CLI propuesta: `sifen draft {cands[0].split('@')[0][4:]}:{ent_id}`) y repita."
                if cands
                else " La línea base no tiene una fila con ese ID: ¿el efecto es un `add`?"
            )
            raise DraftError(f"{key} no existe en kb/: un `{eff.action}` necesita la versión previa.{hint}")
        if pred_v is None:
            raise DraftError(
                f"{effect_id}: ninguna versión de {key} empieza antes en producción: no hay predecesora"
            )
        if pred_v.kind == "tombstone":
            raise DraftError(
                f"{effect_id}: la predecesora ({version_label(pred_v)}) es una lápida: `{eff.action}` sobre una "
                "regla eliminada (¿reintroducción? → `add` + Issue)"
            )
    else:  # add
        if ent is None:
            cands = _baseline_candidates(kb, etype, ent_id)
            if cands:
                raise DraftError(
                    f"{effect_id}: `add` pero la línea base ya tiene {ent_id} ({', '.join(cands)}): ¿modify? "
                    "Lo decide una persona (Issue)"
                )
        elif pred_v is None:
            raise DraftError(f"{effect_id}: `add` anterior a todas las versiones existentes de {key}")
        elif pred_v.kind != "tombstone":
            raise DraftError(
                f"{effect_id}: `add` sobre {key}, vigente en esa fecha ({version_label(pred_v)}): ¿es un `modify`?"
            )
        else:
            res.warnings.append(
                f"reintroducción tras la lápida {version_label(pred_v)}: exige un Issue que la justifique (§G.3)"
            )

    _marking_warnings(res, row, eff, etype, pred_raw)
    based_on: Any = "baseline" if pred_v is None else _plain(pred_v.introduced_by)
    lit_attrs = list(_literals_of(etype).values())
    pred_lits = {a: (pred_raw or {}).get(a) for a in lit_attrs}
    if eff.action == "remove":
        assert pred_raw is not None
        literals = {a: v for a, v in pred_lits.items() if v is not None}
        copied: list[str] = []
        inherited = [a for a in lit_attrs if a in literals]
        if row is not None:
            # La fila que elimina reproduce lo eliminado (en rojo): se compara lo visible.
            for raw_attr, attr in _literals_of(etype).items():
                shown = row.rendered_literal(raw_attr) if raw_attr in row.cells else None
                if raw_attr in row.cells and (shown or None) != pred_lits.get(attr):
                    res.warnings.append(
                        f"la fila que elimina ({row.ref}) difiere de la predecesora en `{attr}`: "
                        f"{_q(shown)} ≠ {_q(pred_lits.get(attr))}; revisar (¿falta una versión?)"
                    )
            evidence: list[Any] = [row.ref]
        else:
            evidence = [
                ev if isinstance(ev, str) else ev.model_dump(mode="json", exclude_none=True)
                for ev in eff.evidence
            ]
        kind = "tombstone"
    else:
        assert row is not None
        literals, copied = _copy_row(row, etype, res)
        inherited = []
        for attr in lit_attrs:
            if attr not in literals and pred_lits.get(attr) is not None:
                literals[attr] = pred_lits[attr]
                inherited.append(attr)
        literals = {a: v for a, v in literals.items() if v is not None}
        evidence = [row.ref]
        kind = "content"
    interpreted = _inherit_interpreted(etype, pred_raw, literals, res)
    version = _version_dict(etype, [effect_id], based_on, kind, literals, interpreted, evidence)

    if ent_raw is None:
        ent_raw = {"key": key, "context": ctx, "id": ent_id, "versions": []}
    ent_raw = dict(ent_raw)
    ent_raw["versions"] = [*raw_versions, version]
    model = _validate_entity(etype, ent_raw)
    prev = _commit_entity(kb, key, etype, model)
    new_v = model.versions[-1]

    verb = {
        "add": "versión inicial" if ent is None else "reintroducción",
        "modify": "versión nueva",
        "remove": "lápida",
    }[eff.action]
    res.lines.append(f"{verb} {effect_id} ({eff.action} {key}) — {doc.id} rev {sha12(doc.current_revision)}")
    res.lines.append(
        f"inicio: prod {_describe_start(new_start['prod'])} · test {_describe_start(new_start['test'])}"
    )
    res.lines.append(
        f"based_on: {based_on if isinstance(based_on, str) else '+'.join(based_on)} "
        + (
            "(sin predecesora: convención para la primera versión de un `add`)"
            if pred_v is None
            else "(predecesora temporal en producción)"
        )
    )
    if copied:
        res.lines.append(f"copiado de {row.ref if row else '-'}: {', '.join(copied)}")
    if inherited:
        res.lines.append(f"heredado de {version_label(pred_v) if pred_v else '-'}: {', '.join(inherited)}")
    for attr in interpreted:
        res.lines.append(f"heredado (interpretado, su literal no cambió): {attr}")
    _report_diff(kb, res, [effect_id], pred_v, new_v, etype)
    _warn_order(kb, res, key, versions, starts, new_start, pred, effect_id)
    _reminders(res, eff, etype, new_v)

    data = _plain(ent_raw)
    res.data = data
    res.changed = True
    if write:
        try:
            _write(kb, path, data)
        except DraftError:
            _rollback(kb, key, etype, prev)
            raise
        kb.paths[key] = path
    else:
        _rollback(kb, key, etype, prev)
    return res


def _merge_into(
    kb: KB,
    res: DraftResult,
    key: str,
    etype: str,
    eff: Effect,
    row: RawRow | None,
    idx: int,
    versions: list[Any],
    raw_versions: list[dict[str, Any]],
    ent_raw: dict[str, Any] | None,
    pred_v: Any,
    pred_raw: dict[str, Any] | None,
    write: bool,
) -> DraftResult:
    """§G.3: agrega `eff` a la versión `idx` que ya tiene el mismo inicio (fusión a tres vías)."""
    assert ent_raw is not None
    _marking_warnings(res, row, eff, etype, pred_raw)
    target = versions[idx]
    ours = dict(raw_versions[idx])
    is_tomb = target.kind == "tombstone"
    if (eff.action == "remove") != is_tomb:
        raise DraftError(
            f"{eff.id}: la versión con el mismo inicio ({version_label(target)}) es "
            f"{'una lápida' if is_tomb else 'de contenido'} y este efecto es `{eff.action}`: contradicción (Issue)"
        )
    lit_attrs = list(_literals_of(etype).values())
    touched: list[str] = []
    if not is_tomb:
        assert row is not None
        theirs, _ = _copy_row(row, etype, res)
        base = {a: (pred_raw or {}).get(a) for a in lit_attrs} if pred_raw is not None else None
        before_obs = {a: ours.get(a) for a in OBSERVATION_ATTRS}
        touched = _three_way(etype, ours, base, theirs, eff.id)
        for attr, source in _interpreted_of(etype).items():
            if ours.get(attr) is not None and ours.get(source) != before_obs.get(source):
                ours.pop(attr)
                if attr != "enumeration_interpretation":
                    res.warnings.append(
                        f"{attr}: cambió `{source}` con {eff.id}: se quitó; formalizar de nuevo"
                    )
    ours["introduced_by"] = [*ours["introduced_by"], eff.id]
    ev = row.ref if row is not None else None
    if ev is not None and ev not in ours["evidence"]:
        ours["evidence"] = [*ours["evidence"], ev]
    elif row is None:
        for e in eff.evidence:
            d = e if isinstance(e, str) else e.model_dump(mode="json", exclude_none=True)
            if d not in ours["evidence"]:
                ours["evidence"] = [*ours["evidence"], d]
    new_raw = list(raw_versions)
    new_raw[idx] = ours
    data = dict(ent_raw)
    data["versions"] = new_raw
    model = _validate_entity(etype, data)
    prev = _commit_entity(kb, key, etype, model)
    new_v = model.versions[idx]
    res.lines.append(
        f"{eff.id} se agrega a la versión {idx} ({version_label(target)}): mismo inicio en ambos ambientes "
        f"(§G.3) → introduced_by: {', '.join(new_v.introduced_by)}"  # type: ignore[arg-type]
    )
    if row is not None:
        res.lines.append(f"columnas que aporta {row.ref}: {', '.join(touched) or '(ninguna distinta)'}")
    if ours.get("based_on") != (_plain(pred_v.introduced_by) if pred_v is not None else ours.get("based_on")):
        res.warnings.append(
            f"based_on de la versión {idx} no es la predecesora temporal ({version_label(pred_v)})"
        )
    _report_diff(kb, res, list(new_v.introduced_by), pred_v, new_v, etype)  # type: ignore[arg-type]
    _reminders(res, eff, etype, new_v)
    data = _plain(data)
    res.data = data
    res.changed = True
    if write:
        try:
            _write(kb, res.path, data)  # type: ignore[arg-type]
        except DraftError:
            _rollback(kb, key, etype, prev)
            raise
        kb.paths[key] = res.path  # type: ignore[assignment]
    else:
        _rollback(kb, key, etype, prev)
    return res


def _report_diff(
    kb: KB, res: DraftResult, effect_ids: list[str], pred_v: Any, new_v: Any, etype: str
) -> None:
    if pred_v is None:
        res.lines.append("diff: versión inicial (sin predecesora)")
        for attr in _literals_of(etype).values():
            if getattr(new_v, attr) is not None:
                res.lines.append(f"  + {attr}: {_q(getattr(new_v, attr))}")
        return
    changed = diff_versions(pred_v, new_v)
    res.lines.append(
        f"diff contra {version_label(pred_v)}: {', '.join(changed) or '(sin cambios de contenido)'}"
    )
    a = pred_v.model_dump(mode="json")
    b = new_v.model_dump(mode="json")
    for attr in changed:
        res.lines.append(f"  - {attr}: {_q(a.get(attr))}")
        res.lines.append(f"  + {attr}: {_q(b.get(attr))}")
    outside = _scope_outside(kb, effect_ids, changed)
    if outside:
        scopes = "; ".join(f"{e}: {kb.effect(e).declared_scope}" for e in effect_ids)
        res.warnings.append(
            f"el diff cae FUERA de declared_scope ({scopes}): {', '.join(outside)}. Con `row`, reconózcalo en "
            "acknowledged_changes si la NT lo cambia de verdad; si no, revise la fila (§G.3, anti-R3)"
        )
    if new_v.kind == "content" and not changed:
        res.warnings.append(
            "la versión nueva no cambia ningún literal respecto de la predecesora: revisar el efecto"
        )


def _warn_order(
    kb: KB,
    res: DraftResult,
    key: str,
    versions: list[Any],
    starts: dict[str, list[Start]],
    new_start: dict[str, Start],
    pred: int | None,
    effect_id: str,
) -> None:
    nd = new_start["prod"][0]
    pred_label = _plain(versions[pred].introduced_by) if pred is not None else None
    for j, v in enumerate(versions):
        sj = starts["prod"][j][0]
        if nd is not None and sj is not None and sj > nd and _plain(v.based_on) == pred_label:
            res.warnings.append(
                f"curación fuera de orden: {version_label(v)} (desde {sj}) tiene based_on {pred_label} y ahora su "
                f"predecesora temporal es {effect_id}: re-materializar lo heredado (§F.2)"
            )
    pred_test = _predecessor(starts["test"], new_start["test"], set())
    if new_start["test"][0] is not None and pred_test != pred and pred_test is not None:
        res.warnings.append(
            f"orden invertido entre ambientes: en test la predecesora sería {version_label(versions[pred_test])}; "
            "exige un Issue `temporal` bloqueante en test durante la ventana invertida (§G.3)"
        )


def _reminders(res: DraftResult, eff: Effect, etype: str, new_v: Any) -> None:
    todo = []
    if etype == "val" and new_v.kind == "content" and getattr(new_v, "condition", None) is None:
        todo.append("condition (expr/level/gaps)")
    if (
        etype == "field"
        and getattr(new_v, "observations", None)
        and getattr(new_v, "enumeration", None) is None
    ):
        todo.append("enumeration si la observación enumera valores")
    if eff.disposition == "pending":
        todo.append(f"quitar `disposition: pending` de {eff.id} cuando esté curado")
    if todo:
        res.lines.append("pendiente (interpretación, no lo hace draft): " + "; ".join(todo))


# --- CLI -------------------------------------------------------------------------------------------
def cmd_draft(args: argparse.Namespace) -> int:
    """`sifen draft <DocId>|<EffectId>`. Salida: 0 = hecho (o ya al día); 1 = error; 2 = objetivo inválido."""
    target = str(args.target).strip()
    root_arg = getattr(args, "root", None)
    root = find_root(Path(root_arg) if root_arg else None)
    baseline = getattr(args, "baseline", None)
    write = not getattr(args, "dry_run", False)
    if baseline is not None:
        if not _KEY_RE.match(target):
            print(
                f"error: con --baseline, TARGET es una clave de entidad (val:DE:D208c), no {target!r}",
                file=sys.stderr,
            )
            return 2
    elif not (EFFECT_ID_RE.match(target) or DOC_ID_RE.match(target)):
        print(
            f"error: objetivo inválido {target!r}: se espera un DocId (NT_024), un EffectId (NT_024#1) "
            "o una clave de entidad con --baseline",
            file=sys.stderr,
        )
        return 2
    try:
        kb = load_kb(root)
        if baseline is not None:
            res = draft_baseline(kb, target, baseline, write=write)
        elif EFFECT_ID_RE.match(target):
            res = draft_effect(kb, target, write=write)
        else:
            update = bool(getattr(args, "update_revision", False))
            res = draft_document(kb, target, update_revision=update, write=write)
    except (DraftError, KBYamlError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for err in kb.errors:
        print(f"AVISO: kb/ tiene errores de carga ajenos a este draft: {err}", file=sys.stderr)
    res.dry_run = not write
    print(res.render(kb.root))
    return 0

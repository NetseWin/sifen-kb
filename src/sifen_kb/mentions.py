"""Índice de menciones en `raw/` (modo índice de `explain`: estado `not_curated`; G.2 y O).

Recuperación SIN resolución: dice dónde aparece un término (ID, código, `xml_name`), nunca qué
regla rige. Por eso la salida va siempre con el aviso "vigencia no resuelta" y ordenada por
fecha de producción del documento (la más reciente primero), nunca por número de NT.

Contrato de lectura (ver `rawio`): `raw/<DocId>/<sha12>/pages/pNNN.txt` de la revisión MÁS
RECIENTE de cada documento del manifiesto, e `index.json` (opcional) para la página impresa.
Solo se recorren documentos del manifiesto: directorios auxiliares como `raw/_ledger/` nunca se
leen como documentos.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from sifen_kb.load import KB
from sifen_kb.model import Mention
from sifen_kb.normalize import normalize_text, parse_date_literal, sha12
from sifen_kb.rawio import read_index, rev_dir

EXCERPT_RADIUS = 70
"""Caracteres de contexto a cada lado de la coincidencia en el extracto."""

_PAGE_FILE = re.compile(r"^p(\d+)\.txt$")
_ENTITY_KEY = re.compile(r"^(?:field|val):[A-Z][A-Z-]*:(\w+)$")


def term_pattern(term: str) -> re.Pattern[str]:
    """Coincidencia de palabra completa: `D208` no coincide dentro de `D2080` ni de `D208c`."""
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")


def key_terms(kb: KB, key: str) -> list[str]:
    """Vocabulario de una clave (G.2): ID, códigos y `xml_name` de todas sus versiones.

    Para una clave no curada (`val:DE:D208x`) es su ID; para un término suelto, el término.
    """
    ent = kb.entity(key)
    if ent is None:
        m = _ENTITY_KEY.match(key)
        return [m.group(1)] if m else [key]
    terms: list[str] = [ent.id]
    for v in ent.versions:
        for t in (getattr(v, "code", None), getattr(v, "xml_name", None)):
            if t and t not in terms:
                terms.append(t)
    return terms


def latest_pages_dir(kb: KB, doc_id: str) -> Path | None:
    """`raw/<doc>/<sha12>/pages` de la revisión más reciente del manifiesto (exista o no)."""
    rev = kb.latest_revision(doc_id)
    if rev is None:
        return None
    return rev_dir(kb.root, doc_id, sha12(rev.sha256)) / "pages"


def has_raw_text(kb: KB, doc_id: str) -> bool:
    """¿Tiene `raw/` (texto por página) la revisión más reciente de `doc_id`?"""
    d = latest_pages_dir(kb, doc_id)
    return d is not None and d.is_dir()


@lru_cache(maxsize=4096)
def _normalized_page(path: str, mtime_ns: int, size: int) -> str:
    # La clave incluye mtime y tamaño: una regeneración de raw/ invalida la caché.
    return normalize_text(Path(path).read_text(encoding="utf-8"))


def _page_text(p: Path) -> str:
    st = p.stat()
    return _normalized_page(str(p), st.st_mtime_ns, st.st_size)


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def printed_page(index: dict[str, Any] | None, page: int) -> int | None:
    """Página impresa de la página PDF `page` según `index.json`, tolerando sus variantes.

    Admite `pages` como lista de objetos (`page`/`page_pdf`/`pdf_page` + `page_printed`/
    `printed_page`/`printed`) o como diccionario `{"<n>": {...} | n}`. Sin dato: None.
    """
    if not index:
        return None
    pages = index.get("pages")
    entry: Any = None
    if isinstance(pages, dict):
        entry = pages.get(str(page), pages.get(f"p{page:03d}"))
    elif isinstance(pages, list):
        for e in pages:
            if isinstance(e, dict) and _as_int(e.get("page", e.get("page_pdf", e.get("pdf_page")))) == page:
                entry = e
                break
    if isinstance(entry, dict):
        for k in ("page_printed", "printed_page", "printed"):
            if k in entry:
                return _as_int(entry[k])
        return None
    return _as_int(entry)


def _excerpt(text: str, start: int, end: int) -> str:
    a = max(0, start - EXCERPT_RADIUS)
    b = min(len(text), end + EXCERPT_RADIUS)
    return ("…" if a > 0 else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def doc_dates(kb: KB, doc_id: str, index: dict[str, Any] | None = None) -> tuple[date | None, date | None]:
    """(fecha de producción, fecha del documento) para ORDENAR menciones.

    Fuente: la ficha de `kb/documents/`. Sin ficha (entregable 0 o NT recién registrada), los
    literales `nt_info` que `extract` copió en `index.json`, si son dd/mm/aaaa; nunca el número.
    """
    doc = kb.documents.get(doc_id)
    if doc is not None:
        prod = doc.schedule.prod.value if doc.schedule and doc.schedule.prod else None
        ddate = doc.document_date.value if doc.document_date else None
        return prod, ddate
    info = (index or {}).get("nt_info")
    if not isinstance(info, dict):
        return None, None

    def lit(k: str) -> date | None:
        v = info.get(k)
        return parse_date_literal(v) if isinstance(v, str) else None

    return lit("prod_literal"), lit("fecha_literal")


def _sort_key(dates: dict[str, tuple[date | None, date | None]], m: Mention) -> tuple[Any, ...]:
    """Producción desc.; sin producción al final, por fecha de documento desc.; nunca por número.

    El DocId solo desempata fechas iguales (determinismo), nunca ordena por sí mismo.
    """
    prod, ddate = dates.get(m.doc, (None, None))
    return (
        prod is None,
        -prod.toordinal() if prod else 0,
        ddate is None,
        -ddate.toordinal() if ddate else 0,
        m.doc,
        m.page_pdf,
    )


def find_mentions(kb: KB, terms: list[str]) -> list[Mention]:
    """Menciones de `terms` (palabra completa) en el texto por página de `raw/`.

    Una mención por (documento, página), con el extracto de la primera coincidencia. Solo la
    revisión más reciente del manifiesto de cada documento. Si `raw/` no existe, `[]`.
    """
    uniq = [t for t in dict.fromkeys(terms) if t]
    if not uniq or not (kb.root / "raw").is_dir():
        return []
    patterns = [term_pattern(t) for t in uniq]
    out: list[Mention] = []
    dates: dict[str, tuple[date | None, date | None]] = {}
    for doc_id in sorted({r.doc for r in kb.manifest.revisions}):
        if doc_id.startswith("_"):  # raw/_ledger y similares: no son documentos
            continue
        pages_dir = latest_pages_dir(kb, doc_id)
        if pages_dir is None or not pages_dir.is_dir():
            continue
        rev12 = pages_dir.parent.name
        try:
            index = read_index(kb.root, doc_id, rev12)
        except ValueError:  # index.json ilegible: la página impresa queda sin dato
            index = None
        dates[doc_id] = doc_dates(kb, doc_id, index)
        for p in sorted(pages_dir.iterdir()):
            pm = _PAGE_FILE.match(p.name)
            if pm is None:
                continue
            text = _page_text(p)
            hits = [m for pat in patterns if (m := pat.search(text))]
            if not hits:
                continue
            first = min(hits, key=lambda m: m.start())
            page = int(pm.group(1))
            out.append(
                Mention(
                    doc=doc_id,
                    rev=rev12,
                    page_pdf=page,
                    page_printed=printed_page(index, page),
                    excerpt=_excerpt(text, first.start(), first.end()),
                    prod_date=dates[doc_id][0],
                )
            )
    out.sort(key=lambda m: _sort_key(dates, m))
    return out


def mentioning_docs(kb: KB, terms: list[str]) -> set[str]:
    """Documentos cuyo `raw/` (revisión más reciente) menciona alguno de `terms`."""
    return {m.doc for m in find_mentions(kb, terms)}

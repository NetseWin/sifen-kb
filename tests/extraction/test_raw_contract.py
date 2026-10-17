"""Contrato de `raw/` versionado (`sifen_kb.rawio`): lee lo que hay en el repositorio, sin PDF ni extracción.

Cubre, para cada revisión (`raw/<DocId>/<sha12>/`):

- cada línea de `tables.jsonl` trae exactamente `rawio.ROW_FIELDS` con los tipos del contrato;
- `cells[attr] == normalize_text(raw_cells[attr])`, salvo donde una corrección de `extraction/fixes.yaml`
  (`fix_ids`) lo justifique;
- cada fila tiene una `RowRef` válida y resuelve a UNA sola fila (`(page, key, occ)` únicos; `occ` consecutivo
  desde 1 por `(page, key)`); cada celda, a una `CellRef` que devuelve `cells[attr]`;
- `index.json` (`pages[].sha256` y `chars`) coincide con los `pages/pNNN.txt`;
- el texto normalizado de cada celda está en el texto normalizado de su(s) página(s), con UNA excepción
  estructural y enumerada (`MULTICELL_OBSERVATIONS`);
- `RawRow.current` sigue el contrato (quita lo tachado y normaliza);
- `raw/_ledger/changes.jsonl`: toda referencia `raw:` que cita resuelve a una fila existente.

La extracción en sí (que `raw/` se regenere idéntico a partir de los PDF) NO se prueba aquí: eso es
`sifen extract --check` y `test_extract_determinism.py`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from sifen_kb import rawio
from sifen_kb.extract import load_fixes, pdf_sources
from sifen_kb.extract_tables import Fix
from sifen_kb.load import load_manifest
from sifen_kb.model import CellRef, RowRef, parse_ref
from sifen_kb.normalize import normalize_text
from sifen_kb.rawio import RawRow

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw"
MT = "MT_V150"

ROW_REF = TypeAdapter(RowRef)
CELL_REF = TypeAdapter(CellRef)
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Atributos admitidos por tabla (rawio: FIELD_HEADERS, VALIDATION_HEADERS, DATE_ATTRS).
ATTRS: dict[str, frozenset[str]] = {
    "fields": frozenset(rawio.FIELD_HEADERS.values()),
    "validations": frozenset(rawio.VALIDATION_HEADERS.values()),
    "dates": frozenset(rawio.DATE_ATTRS),
}

# Excepción ENUMERADA a "el texto de la celda está en el texto de su página".
#
# Son `observation` de validaciones con combinación vertical (una ficha con varias filas de la tabla): el
# contrato de `rawio` define la observación como la unión de sus celdas no vacías con "\n". El árbol de
# etiquetas lee esas celdas en orden de fila, así que la celda de otra columna que cae entre ellas (aquí la
# `E` de severidad: "R") queda ENTRE la primera y las demás celdas de observación en el texto de la página
# y la unión no es contigua (p. ej. MT p. 151, AA01: "…en el mensaje" / "R" / "Versión incorrecta"). Para
# estas filas se exige, en cambio, que CADA celda componente (cada renglón de `raw_cells`) esté en la
# página. No hay fix ni texto fuera del árbol detrás de ninguna: lo comprueba el propio test.
#
# La lista es exacta, no un permiso general: una fila que falle y no figure aquí rompe el test, y una que
# figure y ya cumpla la regla estricta también (para no dejar excepciones muertas). Al regenerar `raw/`
# con otra revisión, hay que revisar la lista a propósito.
MULTICELL_OBSERVATIONS: frozenset[tuple[str, int, str]] = frozenset(
    {
        (MT, 151, "AA01"),
        (MT, 152, "AA03"),
        (MT, 152, "AA04"),
        (MT, 153, "AC01"),
        (MT, 153, "AC04"),
        (MT, 154, "AD01"),
        (MT, 154, "AD02"),
        ("NT_016", 3, "AC01"),
        ("NT_016", 3, "AD01"),
        ("NT_016", 3, "AD02"),
        ("NT_016", 4, "I002"),
        ("NT_019", 2, "GDI002c"),
    }
)


def _revisions() -> list[tuple[str, str]]:
    if not RAW.is_dir():
        return []
    return sorted(
        (doc.name, rev.name)
        for doc in RAW.iterdir()
        if doc.is_dir() and doc.name != rawio.LEDGER_DIR
        for rev in doc.iterdir()
        if rev.is_dir()
    )


REVISIONS = _revisions()
BY_REVISION = pytest.mark.parametrize(("doc", "sha12"), REVISIONS, ids=[f"{d}@{s}" for d, s in REVISIONS])


@cache
def rows_of(doc: str, sha12: str) -> tuple[RawRow, ...]:
    return tuple(rawio.iter_rows(ROOT, doc, sha12))


@cache
def lines_of(doc: str, sha12: str) -> tuple[dict[str, Any], ...]:
    path = rawio.rev_dir(ROOT, doc, sha12) / "tables.jsonl"
    return tuple(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())


@cache
def index_of(doc: str, sha12: str) -> dict[str, Any]:
    index = rawio.read_index(ROOT, doc, sha12)
    assert index is not None, f"falta {doc}@{sha12}/index.json"
    return index


@cache
def fixes_by_id() -> dict[str, Fix]:
    return {f.id: f for f in load_fixes(ROOT)}


def _report(problems: list[str], limit: int = 25) -> str:
    shown = "\n  ".join(problems[:limit])
    more = f"\n  … y {len(problems) - limit} más" if len(problems) > limit else ""
    return f"{len(problems)} problemas:\n  {shown}{more}"


# --- la revisión de raw/ corresponde al manifiesto -------------------------------------------------


def test_raw_covers_the_manifest_pdf_revisions() -> None:
    manifest = load_manifest(ROOT)
    latest = {s.doc: s.sha12 for s in pdf_sources(ROOT, manifest)}
    known = {(r.doc, r.sha256[:12]) for r in manifest.revisions}
    have = set(REVISIONS)
    assert have, "raw/ vacío: ningún test del contrato se ejecutaría"
    assert set(latest.items()) <= have, "revisión PDF vigente sin su raw/"
    assert have <= known, f"raw/ de revisiones que el manifiesto no registra: {sorted(have - known)}"


# --- campos obligatorios y tipos de cada fila ------------------------------------------------------


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_str_dict(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    )


def _row_problems(d: dict[str, Any], npages: int) -> list[str]:
    """Incumplimientos del contrato de una línea de tables.jsonl (vacío si cumple)."""
    missing = set(rawio.ROW_FIELDS) - set(d)
    extra = set(d) - set(rawio.ROW_FIELDS)
    out = []
    if missing:
        out.append(f"faltan campos {sorted(missing)}")
    if extra:
        out.append(f"campos fuera del contrato {sorted(extra)}")
    if missing:
        return out  # sin los campos no se pueden comprobar los tipos

    bad = out.append

    if not (_is_int(d["page"]) and 1 <= d["page"] <= npages):
        bad(f"page={d['page']!r} no es una página 1..{npages}")
    if not (isinstance(d["key"], str) and d["key"]):
        bad(f"key={d['key']!r} no es un texto no vacío")
    if not (_is_int(d["occ"]) and d["occ"] >= 1):
        bad(f"occ={d['occ']!r} no es un entero >= 1")
    if d["table"] not in rawio.TABLES:
        bad(f"table={d['table']!r} fuera de {rawio.TABLES}")
    if not (isinstance(d["header"], list) and all(isinstance(h, str) for h in d["header"])):
        bad("header no es una lista de textos")
    for name in ("cells", "raw_cells"):
        if not _is_str_dict(d[name]):
            bad(f"{name} no es un objeto de textos")
    pages = d["pages"]
    if not (isinstance(pages, list) and pages and all(_is_int(p) for p in pages)):
        bad(f"pages={pages!r} no es una lista no vacía de enteros")
    elif not (pages == sorted(set(pages)) and pages[0] == d["page"] and 1 <= pages[-1] <= npages):
        bad(f"pages={pages!r} debe ser creciente, empezar en page={d['page']} y estar en 1..{npages}")
    if not (isinstance(d["fix_ids"], list) and all(isinstance(i, str) for i in d["fix_ids"])):
        bad("fix_ids no es una lista de textos")
    if not (_is_str_dict(d["changes"]) and set(d["changes"].values()) <= set(rawio.CHANGES)):
        bad(f"changes={d['changes']!r} fuera de {rawio.CHANGES}")
    if d["row_change"] is not None and d["row_change"] not in rawio.CHANGES:
        bad(f"row_change={d['row_change']!r} fuera de {rawio.CHANGES}")
    if not isinstance(d["marks"], list):
        bad("marks no es una lista")
    if out:
        return out  # lo que sigue supone la estructura básica

    cells, raw_cells = d["cells"], d["raw_cells"]
    if set(cells) != set(raw_cells):
        bad(f"cells y raw_cells difieren en atributos: {sorted(set(cells) ^ set(raw_cells))}")
    if d["table"] in ATTRS and not set(cells) <= ATTRS[d["table"]]:
        bad(f"atributos {sorted(set(cells) - ATTRS[d['table']])} no son de la tabla {d['table']}")
    if d["table"] == "dates":
        if d["key"] != rawio.DATES_KEY:
            bad(f"una fila de fechas lleva key={rawio.DATES_KEY!r}, no {d['key']!r}")
        if len(d["header"]) != len(cells):
            bad("en fechas, un rótulo de encabezado por atributo")
    elif d["table"] in ("fields", "validations") and d["key"] != cells.get("id"):
        bad(f"key={d['key']!r} debe ser la celda ID ({cells.get('id')!r})")
    if not set(d["changes"]) <= set(raw_cells):
        bad("changes cita atributos que la fila no tiene")

    marked: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in d["marks"]:
        if not (isinstance(m, dict) and set(m) == {"attr", "change", "start", "end", "text"}):
            bad(f"marca mal formada: {m!r}")
            continue
        raw = raw_cells.get(m["attr"])
        if raw is None or m["change"] not in rawio.CHANGES:
            bad(f"marca sobre un atributo ausente o con cambio inválido: {m!r}")
        elif not (_is_int(m["start"]) and _is_int(m["end"]) and 0 <= m["start"] < m["end"] <= len(raw)):
            bad(f"offsets fuera de raw_cells[{m['attr']!r}]: {m!r}")
        elif raw[m["start"] : m["end"]] != m["text"]:
            bad(f"el texto de la marca no es raw_cells[{m['attr']!r}][{m['start']}:{m['end']}]: {m!r}")
        else:
            marked[m["attr"]].append(m)
    # `changes` y `marks` cuentan lo mismo: un atributo figura en changes si y solo si tiene tramos.
    if set(d["changes"]) != set(marked):
        bad(f"changes {sorted(d['changes'])} != atributos con marcas {sorted(marked)}")
    for attr, change in d["changes"].items():
        if change != "modified" and {m["change"] for m in marked.get(attr, [])} != {change}:
            bad(f"changes[{attr!r}]={change!r} no coincide con sus marcas")
    if d["row_change"] is not None:
        for attr, text in cells.items():
            if (
                text
                and not (attr == "num" and attr not in d["changes"])
                and d["changes"].get(attr) != d["row_change"]
            ):
                bad(f"row_change={d['row_change']!r} pero {attr!r} no está resaltado igual")
    return out


@BY_REVISION
def test_every_row_has_the_contract_fields_and_types(doc: str, sha12: str) -> None:
    npages = len(index_of(doc, sha12)["pages"])
    problems = [
        f"línea {n} ({d.get('table')}:{d.get('key')}@p{d.get('page')}): {p}"
        for n, d in enumerate(lines_of(doc, sha12), 1)
        for p in _row_problems(d, npages)
    ]
    assert not problems, _report(problems)


def _valid_line(**over: Any) -> dict[str, Any]:
    line: dict[str, Any] = {
        "page": 1,
        "key": "D208",
        "occ": 1,
        "table": "fields",
        "header": ["ID", "Campo"],
        "cells": {"id": "D208", "xml_name": "iTipIDRec"},
        "raw_cells": {"id": "D208", "xml_name": "iTipIDRec"},
        "pages": [1],
        "fix_ids": [],
        "changes": {},
        "row_change": None,
        "marks": [],
    }
    line.update(over)
    return line


@pytest.mark.parametrize(
    "over",
    [
        {"page": True},
        {"page": 0},
        {"page": 3},
        {"occ": 0},
        {"key": ""},
        {"table": "campos"},
        {"cells": {"id": "D208", "xml_name": 7}},
        {"cells": {"id": "D208"}},  # cells y raw_cells difieren
        {"pages": [2]},  # no empieza en page
        {"pages": [1, 1]},
        {"fix_ids": "FIX-0001"},
        {"changes": {"id": "cambiado"}},
        {"changes": {"id": "added"}},  # figura en changes pero no tiene marcas
        {"row_change": "rojo"},
        {"marks": [{"attr": "id", "change": "added", "start": 0, "end": 99, "text": "D208"}]},
        {"marks": [{"attr": "id", "change": "added", "start": 0, "end": 2, "text": "XX"}]},
        {"key": "D209"},  # key distinta de la celda ID
    ],
    ids=lambda o: next(iter(o)) + "=" + str(next(iter(o.values()))),
)
def test_row_problems_detects_a_broken_row(over: dict[str, Any]) -> None:
    # Control del verificador: una fila válida no da problemas y cada rotura da al menos uno.
    assert _row_problems(_valid_line(), npages=2) == []
    assert _row_problems(_valid_line(**over), npages=2)


def test_row_problems_detects_missing_and_unknown_fields() -> None:
    line = _valid_line()
    del line["marks"]
    assert _row_problems(line, npages=1) == ["faltan campos ['marks']"]
    assert any("fuera del contrato" in p for p in _row_problems(_valid_line(extra=1), npages=1))


# --- cells == normalize_text(raw_cells), salvo una corrección --------------------------------------


def _cell_problems(row: RawRow, fixes: dict[str, Fix]) -> list[str]:
    """`cells` es `normalize_text(raw_cells)` salvo en los atributos que corrige una entrada de fixes.yaml."""
    out = []
    applied: dict[str, list[Fix]] = defaultdict(list)
    for fix_id in row.fix_ids:
        fix = fixes.get(fix_id)
        if fix is None:
            out.append(f"fix_ids cita {fix_id}, que no está en extraction/fixes.yaml")
        elif (fix.doc, fix.sha12) != (row.doc, row.sha12):
            out.append(f"{fix_id} es de {fix.doc}@{fix.sha12}, no de esta revisión")
        elif fix.attr not in row.raw_cells:
            out.append(f"{fix_id} corrige {fix.attr!r}, que la fila no tiene")
        else:
            applied[fix.attr].append(fix)
    for attr, raw in row.raw_cells.items():
        if attr not in applied:
            if row.cells.get(attr) != normalize_text(raw):
                out.append(f"{attr}: cells={row.cells.get(attr)!r} != normalize_text(raw_cells)")
            continue
        chain = applied[attr]
        if normalize_text(chain[0].original) != normalize_text(raw):
            out.append(f"{attr}: el original de {chain[0].id} no es lo extraído")
        if row.cells.get(attr) != normalize_text(chain[-1].corrected):
            out.append(f"{attr}: cells={row.cells.get(attr)!r} != corrección de {chain[-1].id}")
        if any(m["attr"] == attr for m in row.marks):
            out.append(f"{attr}: corregido pese a tener tramos resaltados (lo prohíbe el contrato)")
    return out


@BY_REVISION
def test_cells_are_the_normalized_raw_cells_unless_a_fix_says_otherwise(doc: str, sha12: str) -> None:
    fixes = fixes_by_id()
    problems = [f"{row.ref}: {p}" for row in rows_of(doc, sha12) for p in _cell_problems(row, fixes)]
    assert not problems, _report(problems)

    # Y las correcciones vigentes de esta revisión están todas aplicadas, cada una en alguna fila.
    expected = [f.id for f in fixes.values() if (f.doc, f.sha12) == (doc, sha12)]
    in_rows = sorted(i for row in rows_of(doc, sha12) for i in row.fix_ids)
    assert in_rows == sorted(expected)
    assert index_of(doc, sha12)["fixes"] == expected


def _row(cells: dict[str, str], raw_cells: dict[str, str], fix_ids: list[str] | None = None) -> RawRow:
    return RawRow(
        "NT_020", "0d877d1fb16a", 1, "E827", 1, "fields", [], cells, raw_cells, fix_ids=fix_ids or []
    )


def _fix(**over: str) -> Fix:
    data = {
        "id": "FIX-0001",
        "doc": "NT_020",
        "sha12": "0d877d1fb16a",
        "page": "1",
        "key": "E82",
        "attr": "id",
        "original": "E82",
        "corrected": "E827",
        "motivo": "m",
        "evidencia": "e",
    }
    return Fix.model_validate({**data, **over})


def test_cell_problems_checker_accepts_clean_and_fixed_cells_and_flags_the_rest() -> None:
    fixes = {"FIX-0001": _fix()}
    assert _cell_problems(_row({"id": "E1 2"}, {"id": "E1\n2"}), fixes) == []
    assert _cell_problems(_row({"id": "E827"}, {"id": "E82"}, ["FIX-0001"]), fixes) == []
    # Una diferencia sin corrección, una corrección desconocida y una corrección mal aplicada se detectan.
    assert _cell_problems(_row({"id": "E827"}, {"id": "E82"}), fixes)
    assert _cell_problems(_row({"id": "E827"}, {"id": "E82"}, ["FIX-0009"]), fixes)
    assert _cell_problems(_row({"id": "E828"}, {"id": "E82"}, ["FIX-0001"]), fixes)
    assert _cell_problems(_row({"id": "E827"}, {"id": "E81"}, ["FIX-0001"]), fixes)


# --- referencias: válidas y una sola fila por referencia -------------------------------------------


@BY_REVISION
def test_every_ref_is_valid_and_resolves_to_exactly_one_row(doc: str, sha12: str) -> None:
    rows = rows_of(doc, sha12)
    problems = []
    by_ref: dict[tuple[int, str, int], list[RawRow]] = defaultdict(list)
    seen_occ: dict[tuple[int, str], list[int]] = defaultdict(list)
    for row in rows:
        by_ref[(row.page, row.key, row.occ)].append(row)
        seen_occ[(row.page, row.key)].append(row.occ)
        try:
            ROW_REF.validate_python(row.ref)
            parsed = parse_ref(row.ref)
        except (ValidationError, ValueError) as e:
            problems.append(f"{row.ref}: referencia inválida ({e.__class__.__name__})")
            continue
        if parsed != {
            "doc": doc,
            "sha12": sha12,
            "page": row.page,
            "key": row.key,
            "occ": row.occ,
            "attr": None,
        }:
            problems.append(f"{row.ref}: parse_ref no devuelve la fila ({parsed})")
        for attr in row.cells:
            try:
                CELL_REF.validate_python(f"{row.ref}#{attr}")
            except ValidationError:
                problems.append(f"{row.ref}#{attr}: CellRef inválida")
    problems += [
        f"{page}/{key}~{occ}: {len(r)} filas con la misma referencia"
        for (page, key, occ), r in by_ref.items()
        if len(r) > 1
    ]
    # `occ` desambigua un mismo `key` en la misma página: 1, 2, 3… en el orden de lectura (orden del archivo).
    problems += [
        f"p{page}:{key}: occ={occs}, se esperaba {list(range(1, len(occs) + 1))}"
        for (page, key), occs in seen_occ.items()
        if occs != list(range(1, len(occs) + 1))
    ]
    assert not problems, _report(problems)

    # RawStore (lo que usa kb/ para resolver) devuelve esa misma fila y la celda citada.
    store = rawio.RawStore(ROOT)
    for row in rows:
        assert store.row(row.ref) == row
        for attr, text in row.cells.items():
            assert store.cell(f"{row.ref}#{attr}") == text


# --- index.json y pages/pNNN.txt ------------------------------------------------------------------


@BY_REVISION
def test_index_pages_match_the_page_files(doc: str, sha12: str) -> None:
    index = index_of(doc, sha12)
    pages = index["pages"]
    problems = []
    if index["doc"] != doc or not SHA256.match(index["sha256"]) or index["sha256"][:12] != sha12:
        problems.append(
            f"doc/sha256 de index.json no son los de la carpeta: {index['doc']} {index['sha256']}"
        )
    if [p["page_pdf"] for p in pages] != list(range(1, len(pages) + 1)):
        problems.append("page_pdf no es 1..N consecutivo")
    pages_dir = rawio.rev_dir(ROOT, doc, sha12) / "pages"
    on_disk = sorted(p.name for p in pages_dir.iterdir())
    if on_disk != [f"p{n:03d}.txt" for n in range(1, len(pages) + 1)]:
        problems.append(f"pages/ no tiene exactamente un pNNN.txt por página del PDF (hay {len(on_disk)})")

    printed = []
    for entry in pages:
        if set(entry) != {"page_pdf", "page_printed", "sha256", "chars"}:
            problems.append(f"p{entry.get('page_pdf')}: campos {sorted(entry)}")
            continue
        path = rawio.page_path(ROOT, doc, sha12, entry["page_pdf"])
        if not path.is_file():
            problems.append(f"falta {path.name}")
            continue
        data = path.read_bytes()
        text = data.decode("utf-8")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            problems.append(f"{path.name}: sha256 distinto del de index.json")
        if len(text) != entry["chars"]:
            problems.append(f"{path.name}: {len(text)} caracteres, index.json dice {entry['chars']}")
        if "\r" in text or (text and not text.endswith("\n")):
            problems.append(f"{path.name}: debe usar LF y terminar en LF (o estar vacía)")
        if entry["page_printed"] is not None:
            printed.append(entry["page_printed"])
            if doc != MT or not _is_int(entry["page_printed"]) or entry["page_printed"] < 1:
                problems.append(
                    f"{path.name}: page_printed={entry['page_printed']!r} solo es válida en el MT"
                )
    if printed != sorted(set(printed)):
        problems.append("page_printed del MT no es estrictamente creciente")
    assert not problems, _report(problems)


@BY_REVISION
def test_index_summarizes_tables_jsonl(doc: str, sha12: str) -> None:
    index = index_of(doc, sha12)
    counts = Counter(row.table for row in rows_of(doc, sha12))
    assert index["tables"] == {t: counts.get(t, 0) for t in ("fields", "validations", "dates")}
    assert isinstance(index["tagged"], bool)
    assert index["tagged"] == index["extractor"]["engine"].startswith("tagged")
    assert (doc.startswith("NT_")) == ("nt_info" in index)


@BY_REVISION
def test_files_use_the_canonical_serialization(doc: str, sha12: str) -> None:
    # rawio: «toda escritura es determinista: UTF-8, LF, JSON con claves ordenadas y sin escapar Unicode».
    base = rawio.rev_dir(ROOT, doc, sha12)
    index_bytes = (base / "index.json").read_bytes()
    assert index_bytes.decode("utf-8") == rawio.index_text(json.loads(index_bytes))
    rows_bytes = (base / "tables.jsonl").read_bytes()
    assert rows_bytes.decode("utf-8") == rawio.rows_text(
        [json.loads(line) for line in rows_bytes.splitlines()]
    )
    assert b"\r" not in rows_bytes + index_bytes


# --- el texto de cada celda está en el de su página ------------------------------------------------


@cache
def _page_text(doc: str, sha12: str, pages: tuple[int, ...]) -> str:
    return normalize_text("\n".join(rawio.read_page(ROOT, doc, sha12, p) or "" for p in pages))


def _missing_cells(row: RawRow) -> set[str]:
    """Atributos de `row` cuyo texto normalizado NO está, entero, en el texto normalizado de sus páginas."""
    text = _page_text(row.doc, row.sha12, tuple(row.pages))
    return {attr for attr, cell in row.cells.items() if cell and cell not in text}


@BY_REVISION
def test_cell_text_is_in_the_normalized_page_text(doc: str, sha12: str) -> None:
    problems = []
    failing: set[tuple[str, int, str]] = set()
    for row in rows_of(doc, sha12):
        missing = _missing_cells(row)
        if not missing:
            continue
        ident = (doc, row.page, row.key)
        if (
            missing != {"observation"}
            or row.table != "validations"
            or row.occ != 1
            or ident not in MULTICELL_OBSERVATIONS
        ):
            problems.append(f"{row.ref}: {sorted(missing)} no está en la página {row.pages}")
            continue
        failing.add(ident)
        # La excepción exige que CADA celda componente esté en la página, y que sea de verdad una unión.
        parts = [normalize_text(p) for p in row.raw_cells["observation"].split("\n")]
        text = _page_text(doc, sha12, tuple(row.pages))
        lost = [p for p in parts if p and p not in text]
        if len(parts) < 2 or lost:
            problems.append(
                f"{row.ref}: la observación no es una unión de celdas presentes en la página: {lost}"
            )
    # Una excepción que ya cumple la regla estricta (o que no existe) sobra: la lista debe ser exacta.
    stale = sorted(i for i in MULTICELL_OBSERVATIONS if i[0] == doc and i not in failing)
    problems += [f"excepción obsoleta en MULTICELL_OBSERVATIONS: {i}" for i in stale]
    assert not problems, _report(problems)


def test_multicell_exception_checker_flags_text_that_is_not_in_the_page() -> None:
    # Control: `_missing_cells` detecta una celda que la página no contiene (fila sintética sobre una página real).
    doc, sha12 = next(r for r in REVISIONS if r[0] == "NT_024")
    row = rows_of(doc, sha12)[0]
    assert _missing_cells(row) == set()
    altered = dataclasses.replace(row, cells={**row.cells, "id": "texto que no está en la página"})
    assert "id" in _missing_cells(altered)


# --- RawRow.current sobre las marcas reales ---------------------------------------------------------


@BY_REVISION
def test_current_text_removes_deleted_spans_and_normalizes(doc: str, sha12: str) -> None:
    problems = []
    for row in rows_of(doc, sha12):
        if row.fix_ids:  # una celda corregida no sale de raw_cells: la cubre el test de las correcciones
            continue
        for attr, raw in row.raw_cells.items():
            deleted = sorted(
                (m["start"], m["end"]) for m in row.marks if m["attr"] == attr and m["change"] == "deleted"
            )
            # Implementación independiente: se arma el texto vigente de izquierda a derecha.
            kept, pos = [], 0
            for start, end in deleted:
                kept.append(raw[pos:start])
                pos = end
            kept.append(raw[pos:])
            expected = normalize_text("".join(kept))
            if row.current(attr) != expected:
                problems.append(f"{row.ref}#{attr}: current={row.current(attr)!r} != {expected!r}")
    assert not problems, _report(problems)


# --- raw/_ledger/changes.jsonl ----------------------------------------------------------------------


def _refs_in(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """(ruta, referencia) de todo texto `raw:…` dentro de una línea del libro, a cualquier profundidad."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _refs_in(item, f"{path}/{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _refs_in(item, f"{path}[{i}]")
    elif isinstance(value, str) and value.startswith("raw:"):
        yield path, value


def _resolve(ref: str) -> list[RawRow]:
    """Filas de raw/ a las que apunta `ref` (una referencia válida debe dar exactamente una)."""
    parsed = parse_ref(ref)
    key = (parsed["page"], parsed["key"], parsed["occ"])
    doc, sha12 = str(parsed["doc"]), str(parsed["sha12"])
    if (doc, sha12) not in REVISIONS:
        return []
    return [r for r in rows_of(doc, sha12) if (r.page, r.key, r.occ) == key]


def test_ledger_refs_resolve_to_existing_rows() -> None:
    lines = list(rawio.iter_ledger(ROOT))
    assert lines, "raw/_ledger/changes.jsonl vacío o ausente"
    problems = []
    refs = 0
    for n, line in enumerate(lines, 1):
        for path, ref in _refs_in(line):
            refs += 1
            try:
                found = _resolve(ref)
            except ValueError as e:
                problems.append(f"línea {n} {path}: {e}")
                continue
            if len(found) != 1:
                problems.append(f"línea {n} {path}: {ref} resuelve a {len(found)} filas")
    assert refs >= len(lines)
    assert not problems, _report(problems)


def test_ledger_lines_point_at_the_rows_they_describe() -> None:
    problems = []
    for n, line in enumerate(rawio.iter_ledger(ROOT), 1):
        where = f"línea {n} ({line['nt']} {line['id']})"
        if line["nt_ref"] is None:
            problems.append(f"{where}: sin nt_ref")
            continue
        found = _resolve(line["nt_ref"])
        if len(found) != 1:
            problems.append(f"{where}: nt_ref {line['nt_ref']} resuelve a {len(found)} filas")
            continue
        nt = found[0]
        if (nt.doc, nt.key, nt.table, nt.page) != (line["nt"], line["id"], line["table"], line["nt_page"]):
            problems.append(f"{where}: nt_ref {line['nt_ref']} no es la fila que dice ser")
        if (line["mt_ref"] is None) != (line["mt_page"] is None):
            problems.append(f"{where}: mt_ref y mt_page deben faltar juntos")
        elif line["mt_ref"] is not None:
            mt = (_resolve(line["mt_ref"]) or [None])[0]
            if mt is None or (mt.doc, mt.key, mt.table, mt.page) != (
                MT,
                line["id"],
                line["table"],
                line["mt_page"],
            ):
                problems.append(f"{where}: mt_ref {line['mt_ref']} no es la fila vigente del MT")
        if line["dates_ref"] is not None:
            dates = (_resolve(line["dates_ref"]) or [None])[0]
            if dates is None or (dates.doc, dates.key, dates.table) != (line["nt"], rawio.DATES_KEY, "dates"):
                problems.append(f"{where}: dates_ref {line['dates_ref']} no es la fila de fechas de la NT")
            else:
                problems += [
                    f"{where}: {env}={line[env]!r} != celda de {line['dates_ref']}"
                    for env in ("test", "prod")
                    if line[env] != dates.cells.get(env)
                ]
    assert not problems, _report(problems)


def test_ledger_index_agrees_with_changes_and_with_raw() -> None:
    index = json.loads((rawio.ledger_dir(ROOT) / "index.json").read_text(encoding="utf-8"))
    lines = list(rawio.iter_ledger(ROOT))
    assert index["unresolved_refs"] == 0
    assert sum(index["counts"].values()) == len(lines)
    assert index["mt"] == {"doc": MT, "sha12": dict(REVISIONS)[MT]}
    notes = {(n["doc"], n["sha12"]) for n in index["notes"]}
    assert notes == {(d, s) for d, s in REVISIONS if d.startswith("NT_")}

"""`sifen extract`: genera `raw/` desde las revisiones PDF de `sources.manifest.yaml` (determinista).

    sifen extract                 todo el corpus PDF (revisión más reciente de cada DocId) + _ledger
    sifen extract --doc NT_024    solo esos documentos (no regenera raw/_ledger, que depende de todos)
    sifen extract --check         regenera en memoria y compara byte a byte con raw/ (exit 1 si difiere)

Motor (docs/arquitectura.md §I): el extractor determinista de pdf_to_md vendorizado en
`sifen_kb.pdf` (árbol de etiquetas por MCID con pdfplumber; ruta geométrica para los PDF sin
etiquetas). Un solo motor para el texto de página y para las celdas:

- `pages/pNNN.txt` es el texto de la IR por página ANTES de unir tablas (`verify.ir_page_text`):
  conserva el tachado y los encabezados repetidos, y una celda multilínea queda contigua (con
  `pdftotext -layout` o `extract_text` los renglones de celdas vecinas se intercalan). El texto de
  una celda de tables.jsonl está, así, en el texto de su página, salvo una excepción estructural:
  una observación de validación hecha de varias celdas combinadas verticalmente (MT AA01–AD02,
  NT_016, NT_019 GDI002c) se une con `\n`, y el árbol lee la columna E entre esas celdas; ahí cada
  renglón está en la página, no la unión (lista exacta en tests/extraction/test_raw_contract.py).
- La página impresa del MT es el pie "septiembre de 2019 NNN", que queda fuera del árbol: se lee
  con pypdfium2 (solo ese número; no aporta texto).
- Filas y libro de cambios: `extract_tables` y `extract_ledger`.

Rendimiento: las páginas se extraen en paralelo (`SIFEN_EXTRACT_JOBS`, por defecto hasta 6
procesos). Un PDF largo se parte en tramos de páginas; como el orden de lectura de `tagged` es por
página, juntar los tramos da la misma IR que una sola corrida (lo prueba
`tests/extraction/test_extract_determinism.py`). Sin red.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from sifen_kb import __version__
from sifen_kb.extract_ledger import LedgerDoc, build_ledger
from sifen_kb.extract_tables import ExtractionError, Fix, apply_fixes, build_rows, parse_fixes
from sifen_kb.load import find_root, load_manifest
from sifen_kb.model import SourcesManifest
from sifen_kb.normalize import sha12 as to_sha12
from sifen_kb.rawio import LEDGER_DIR, index_text, rows_text
from sifen_kb.yamlio import KBYamlError, load_kb_file

ORIGIN = {"project": "pdf_to_md", "commit": "8603b5bd572fb0a1563e216d3ec658fb5666e678"}
NAME = "sifen_kb.extract"
FIXES_PATH = Path("extraction") / "fixes.yaml"
CHUNK_PAGES = 36  # el MT (217 págs.) se reparte en 6 tramos
MAX_JOBS = 6
_FOOTER = re.compile(r"^\s*septiembre de 2019\s+(\d{1,3})\s*$")
_NT = re.compile(r"^NT_\d{3}$")


@dataclass(frozen=True)
class Source:
    """Revisión PDF a extraer, tomada del manifiesto."""

    doc: str
    sha256: str
    path: Path

    @property
    def sha12(self) -> str:
        return to_sha12(self.sha256)


@dataclass(frozen=True)
class Chunk:
    """Resultado de extraer un tramo de páginas en un proceso."""

    extractor: str
    blocks: list[Any]
    printed: dict[int, int | None]


@dataclass
class DocOutput:
    source: Source
    files: dict[str, str]  # ruta relativa a la raíz del repo → contenido
    ledger: LedgerDoc
    rows: int
    pages: int


# --- fuentes ------------------------------------------------------------------------------------


def pdf_sources(root: Path, manifest: SourcesManifest, docs: Sequence[str] | None = None) -> list[Source]:
    """Revisión más reciente (última del manifiesto, que es append-only) de cada DocId PDF."""
    latest: dict[str, Any] = {}
    for rev in manifest.revisions:
        latest[rev.doc] = rev
    pdfs = {doc: rev for doc, rev in latest.items() if rev.path.lower().endswith(".pdf")}
    if docs:
        unknown = sorted(set(docs) - set(pdfs))
        if unknown:
            raise ExtractionError(f"sin revisión PDF en el manifiesto: {', '.join(unknown)}")
        pdfs = {doc: pdfs[doc] for doc in docs}
    return [Source(doc, rev.sha256, root / rev.path) for doc, rev in sorted(pdfs.items())]


def verify_source(src: Source) -> None:
    if not src.path.is_file():
        raise ExtractionError(f"{src.doc}: no existe {src.path}")
    digest = hashlib.sha256(src.path.read_bytes()).hexdigest()
    if digest != src.sha256:
        raise ExtractionError(f"{src.doc}: sha256 de {src.path.name} no coincide con el manifiesto")


def load_fixes(root: Path) -> list[Fix]:
    p = root / FIXES_PATH
    if not p.exists():
        return []
    try:
        return parse_fixes(load_kb_file(p), str(FIXES_PATH))
    except KBYamlError as e:
        raise ExtractionError(str(e)) from None


# --- extracción en paralelo ---------------------------------------------------------------------


def page_count(path: Path) -> int:
    import pypdfium2

    pdf = pypdfium2.PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def printed_pages(path: Path, first: int, last: int) -> dict[int, int | None]:
    """Número del pie "septiembre de 2019 NNN" (MT V150) de cada página; None si no está o si hay
    más de uno (ambiguo)."""
    import pypdfium2

    out: dict[int, int | None] = {}
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        for number in range(first, last + 1):
            page = pdf[number - 1]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            textpage.close()
            page.close()
            found = [int(m.group(1)) for line in text.splitlines() if (m := _FOOTER.match(line))]
            out[number] = found[0] if len(found) == 1 else None
    finally:
        pdf.close()
    return out


def extract_chunk(path: str, first: int, last: int) -> Chunk:
    """IR (sin unir tablas) de las páginas first..last. Se ejecuta en un proceso aparte.

    `extract_tagged(pages=…)` emite todo bloque que TOCA el tramo; se conservan los que EMPIEZAN en
    él, así cada bloque sale en un solo tramo y en el mismo orden que en una corrida completa.
    """
    from pdfplumber.structure import StructTreeMissing

    from sifen_kb.pdf.geometry import extract_geometric
    from sifen_kb.pdf.tagged import extract_tagged

    pdf = Path(path)
    pages = range(first, last + 1)
    try:
        doc = extract_tagged(pdf, pages=pages)
    except StructTreeMissing:
        doc = extract_geometric(pdf, pages=pages)
    blocks = [b for b in doc.blocks if first <= b.page <= last]
    return Chunk(doc.extractor, blocks, printed_pages(pdf, first, last))


def _chunks(npages: int, size: int = CHUNK_PAGES) -> list[tuple[int, int]]:
    if npages <= 0:
        return []
    count = max(1, round(npages / size))
    bounds = [1 + (npages * i) // count for i in range(count + 1)]
    return [(bounds[i], bounds[i + 1] - 1) for i in range(count) if bounds[i] <= bounds[i + 1] - 1]


def _jobs() -> int:
    env = os.environ.get("SIFEN_EXTRACT_JOBS")
    if env:
        return max(1, int(env))
    return max(1, min(MAX_JOBS, os.cpu_count() or 1))


@dataclass(frozen=True)
class IR:
    extractor: str
    blocks: list[Any]
    printed: dict[int, int | None]
    npages: int


def extract_ir(
    sources: Sequence[Source], jobs: int | None = None, chunk_pages: int = CHUNK_PAGES
) -> dict[str, IR]:
    """IR sin unir de cada fuente, extraída por tramos de páginas en paralelo."""
    npages = {src.doc: page_count(src.path) for src in sources}
    plan = [(src, a, b) for src in sources for a, b in _chunks(npages[src.doc], chunk_pages)]
    plan.sort(key=lambda t: -(t[2] - t[1] + 1))  # los tramos largos primero: mejor reparto
    jobs = jobs or _jobs()
    args = [(str(src.path), a, b) for src, a, b in plan]
    if jobs == 1 or len(plan) == 1:
        results = [extract_chunk(*a) for a in args]
    else:
        with ProcessPoolExecutor(max_workers=min(jobs, len(plan))) as ex:
            results = list(ex.map(extract_chunk, *zip(*args, strict=True)))
    by_doc: dict[str, list[tuple[int, Chunk]]] = {}
    for (src, a, _), chunk in zip(plan, results, strict=True):
        by_doc.setdefault(src.doc, []).append((a, chunk))
    out: dict[str, IR] = {}
    for src in sources:
        chunks = [c for _, c in sorted(by_doc.get(src.doc, []), key=lambda t: t[0])]
        extractors = {c.extractor for c in chunks}
        if len(extractors) > 1:
            raise ExtractionError(f"{src.doc}: tramos con motores distintos {sorted(extractors)}")
        printed: dict[int, int | None] = {}
        for c in chunks:
            printed.update(c.printed)
        out[src.doc] = IR(
            extractor=extractors.pop() if extractors else "vacío",
            blocks=[b for c in chunks for b in c.blocks],
            printed=printed,
            npages=npages[src.doc],
        )
    return out


# --- armado de raw/ -----------------------------------------------------------------------------


def extractor_info(engine: str | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": NAME,
        "version": __version__,
        "origin": dict(ORIGIN),
        "page_printed_engine": f"pypdfium2-{metadata.version('pypdfium2')}",
    }
    if engine is not None:
        info["engine"] = engine
    return info


def build_doc(src: Source, ir: IR, fixes: Sequence[Fix]) -> DocOutput:
    from sifen_kb.pdf.continuity import merge_continued_tables
    from sifen_kb.pdf.ir import Document
    from sifen_kb.pdf.sifen.sections import promote_sections
    from sifen_kb.pdf.verify import ir_page_text

    unmerged = Document(source=src.path.name, sha256=src.sha256, extractor=ir.extractor, blocks=ir.blocks)
    texts = ir_page_text(unmerged)
    merged = promote_sections(merge_continued_tables(unmerged))
    is_nt = bool(_NT.match(src.doc))
    tablas, info = build_rows(merged, is_nt=is_nt)
    fix_ids = apply_fixes(src.doc, src.sha12, tablas.filas, fixes)
    rows = [f.to_dict() for f in tablas.filas]

    base = f"raw/{src.doc}/{src.sha12}"
    files: dict[str, str] = {}
    pages = []
    for number in range(1, ir.npages + 1):
        text = texts.get(number, "")
        content = text + "\n" if text else ""
        files[f"{base}/pages/p{number:03d}.txt"] = content
        pages.append(
            {
                "page_pdf": number,
                "page_printed": ir.printed.get(number),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "chars": len(content),
            }
        )
    extra = sorted(set(texts) - set(range(1, ir.npages + 1)))
    if extra:
        raise ExtractionError(f"{src.doc}: texto en páginas inexistentes {extra}")
    counts = {t: sum(1 for r in rows if r["table"] == t) for t in ("fields", "validations", "dates")}
    index: dict[str, Any] = {
        "doc": src.doc,
        "sha256": src.sha256,
        "extractor": extractor_info(ir.extractor),
        "tagged": ir.extractor.startswith("tagged"),
        "pages": pages,
        "tables": counts,
        "anomalies": tablas.anomalies,
        "fixes": fix_ids,
    }
    if is_nt:
        index["nt_info"] = info
    files[f"{base}/index.json"] = index_text(index)
    files[f"{base}/tables.jsonl"] = rows_text(rows)
    ledger = LedgerDoc(src.doc, src.sha12, merged, rows, info, dict(ir.printed))
    return DocOutput(src, files, ledger, len(rows), ir.npages)


def generate(
    root: Path,
    sources: Sequence[Source],
    fixes: Sequence[Fix],
    *,
    ledger: bool,
    jobs: int | None = None,
) -> tuple[dict[str, str], list[DocOutput]]:
    """Todo el contenido de raw/ para estas fuentes (ruta relativa → texto), en memoria."""
    for src in sources:
        verify_source(src)
    irs = extract_ir(sources, jobs)
    outputs = [build_doc(src, irs[src.doc], fixes) for src in sources]
    files: dict[str, str] = {}
    for out in outputs:
        files.update(out.files)
    if ledger:
        mts = [o.ledger for o in outputs if o.source.doc == "MT_V150"]
        notes = [o.ledger for o in outputs if _NT.match(o.source.doc)]
        if mts and notes:
            for name, content in build_ledger(mts[0], notes, extractor_info()).items():
                files[f"raw/{LEDGER_DIR}/{name}"] = content
    return files, outputs


def _owned_dirs(files: Iterable[str]) -> set[str]:
    """Carpetas que esta corrida regenera por completo: raw/<doc>/<sha12> y raw/_ledger."""
    owned = set()
    for rel in files:
        parts = rel.split("/")
        owned.add("/".join(parts[:2]) if parts[1] == LEDGER_DIR else "/".join(parts[:3]))
    return owned


def _existing(root: Path, owned: Iterable[str]) -> set[str]:
    found = set()
    for d in owned:
        base = root / d
        if base.is_dir():
            found.update(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
    return found


def diff_against_disk(root: Path, files: dict[str, str]) -> list[str]:
    diffs = []
    for rel in sorted(files):
        p = root / rel
        if not p.exists():
            diffs.append(f"falta     {rel}")
        elif p.read_bytes() != files[rel].encode("utf-8"):
            diffs.append(f"difiere   {rel}")
    for rel in sorted(_existing(root, _owned_dirs(files)) - set(files)):
        diffs.append(f"sobra     {rel}")
    return diffs


def write_files(root: Path, files: dict[str, str]) -> tuple[int, int]:
    """Escribe lo que cambió y borra lo que sobra en las carpetas regeneradas."""
    written = 0
    for rel in sorted(files):
        p = root / rel
        data = files[rel].encode("utf-8")
        if p.exists() and p.read_bytes() == data:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:  # bytes UTF-8 con LF: sin traducción de fin de línea
            f.write(data)
        written += 1
    removed = 0
    for rel in sorted(_existing(root, _owned_dirs(files)) - set(files)):
        (root / rel).unlink()
        removed += 1
    return written, removed


def cmd_extract(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    root = Path(args.root).resolve() if getattr(args, "root", None) else find_root()
    docs = list(dict.fromkeys(args.doc)) if getattr(args, "doc", None) else None
    try:
        manifest = load_manifest(root)
        sources = pdf_sources(root, manifest, docs)
        if not sources:
            print(f"sin revisiones PDF en {root / 'sources.manifest.yaml'}", file=sys.stderr)
            return 1
        fixes = load_fixes(root)
        if not docs:
            processed = {(s.doc, s.sha12) for s in sources}
            orphan = sorted(f.id for f in fixes if (f.doc, f.sha12) not in processed)
            if orphan:
                raise ExtractionError(f"correcciones sin revisión vigente que corregir: {', '.join(orphan)}")
        files, outputs = generate(root, sources, fixes, ledger=not docs)
    except ExtractionError as e:
        print(f"error de extracción: {e}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - t0
    resumen = (
        f"{len(outputs)} documentos, {sum(o.pages for o in outputs)} páginas, "
        f"{sum(o.rows for o in outputs)} filas{'' if docs else ' + _ledger'} en {elapsed:.1f} s"
    )
    if args.check:
        diffs = diff_against_disk(root, files)
        if diffs:
            print(f"raw/ NO coincide con la extracción ({len(diffs)} diferencias):")
            for line in diffs:
                print(f"  {line}")
            return 1
        print(f"raw/ coincide byte a byte: {resumen}")
        return 0
    written, removed = write_files(root, files)
    print(f"raw/: {written} archivos escritos, {removed} borrados; {resumen}")
    return 0

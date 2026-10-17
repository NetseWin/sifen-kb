"""Fuentes oficiales: descarga verificada, manifiesto *append-only* y chequeo del portal DNIT.

Referencia de diseño: docs/arquitectura.md §D.2, §D.3, §D.6, §F.1 y §C.2 n.º 23.

Piezas:

- `sources.manifest.yaml` (raíz del repo): revisiones (`SourceRevision`) y chequeos (`SourceCheck`).
  Solo lo escribe esta herramienta y SOLO se le agregan entradas (`check_append_only`).
- `sources/<DocId>/<sha12>.<ext>`: bytes originales, nombrados por el prefijo del sha256. Nunca se
  sobrescribe un archivo. `XSD_DIR` es la excepción: una carpeta `sources/XSD_DIR/<AAAA-MM-DD>/`
  con los `.xsd` y un `SHA256SUMS` (líneas `sha256␣␣nombre`, ordenadas por nombre).
- `cmd_source_add` (`sifen source add`) y `cmd_source_check` (`sifen source check`).
- `verify_sources(root)`: errores de integridad entre el manifiesto y `sources/` (lo usan los tests).

Seguridad de la descarga: solo `https` y solo los dominios de `ALLOWED_DOMAINS`; una redirección
fuera de la lista es un error (el manejador de redirecciones valida cada salto). El contenido se
contrasta con la firma de su tipo (un PDF debe empezar por `%PDF-`) para no registrar como
fuente una página de error servida con HTTP 200.

Particularidades del portal (verificadas el 2026-10-17):

- `https://www.dnit.gov.py` es un Liferay. Los archivos viven en
  `/documents/<groupId>/<carpeta>/<título.ext>/<uuid>?t=<n>`. Carpetas observadas: `20123/420595`
  (todas las NT), `20123/420592` (Manual, checksum, RAR de XSD, tablas), `20123/559197` (Decreto
  872/2023), `371863/0` (RAR de estructura XML).
- El título va codificado como formulario: el espacio es `+` y los acentos son UTF-8 porcentual
  (`Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf`). Por eso `NT_E_KUATIA_021_MT_V150+30.12.24.pdf` se
  llama realmente `NT_E_KUATIA_021_MT_V150 30.12.24.pdf` (lo confirma `Content-Disposition`).
  `filename` del manifiesto es el nombre decodificado (con espacios), no el de la URL.
- `?t=` es la marca de modificación del gestor de contenidos en MILISEGUNDOS desde la época Unix
  (UTC): `t=1687362295907` = 2023-06-21T15:44:55.907Z, igual que el `Last-Modified` HTTP del
  archivo. Es la fecha de SUBIDA, nunca de publicación ni de vigencia.
- El enlace del portal cambia (nuevo `t=` y a veces nuevo nombre/uuid) cuando DNIT re-sube un
  archivo; por eso `source check` vuelve a descargar y compara el hash, no solo la URL.
- El directorio `https://ekuatia.set.gov.py/sifen/xsd/` es un índice Apache (ISO-8859-1) cuyos
  `.xsd` devuelven todos el mismo `Last-Modified`: solo el hash detecta un cambio in situ.
- El portal antiguo (`ekuatia.set.gov.py/portal/...`) y `www.set.gov.py` redirigen (302) a
  `www.dnit.gov.py`; por eso `www.set.gov.py` figura en la lista permitida.
- `dnit.gov.py` (sin `www`) no resuelve en DNS; no se incluye.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import parse_qs, unquote, unquote_plus, urljoin, urlsplit

from pydantic import TypeAdapter, ValidationError

from sifen_kb.load import find_root
from sifen_kb.model import DocId, SourceCheck, SourceRevision, SourcesManifest
from sifen_kb.yamlio import KBYamlError, load_kb_file, write_kb_file

# --- Constantes --------------------------------------------------------------------------------
MANIFEST_NAME = "sources.manifest.yaml"
SOURCES_DIR = "sources"
XSD_DOC = "XSD_DIR"
SHA256SUMS = "SHA256SUMS"

ALLOWED_DOMAINS: frozenset[str] = frozenset({"www.dnit.gov.py", "ekuatia.set.gov.py", "www.set.gov.py"})
"""Hosts desde los que se puede descargar (y a los que puede redirigir una descarga)."""
ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})
ALLOWED_PORTS: frozenset[int | None] = frozenset({None, 443})

DOCS_PAGE_URL = "https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica"
TABLES_PAGE_URL = "https://www.dnit.gov.py/web/e-kuatia/tablas-y-codificaciones"
XSD_LISTING_URL = "https://ekuatia.set.gov.py/sifen/xsd/"

USER_AGENT = "sifen-kb/0.1 (+https://github.com/NetseWin/sifen-kb; verificador de fuentes oficiales DNIT)"
TIMEOUT_S = 60.0
RETRIES = 3
MAX_BYTES = 256 * 1024 * 1024

SCOPES: tuple[str, ...] = ("nt", "xsd", "manual", "tablas", "guias")
OPTIONAL_SCOPES: frozenset[str] = frozenset({"tablas", "guias"})
"""Ámbitos que solo se verifican si hay documentos registrados en ellos (sin línea base no hay qué comparar)."""

_sleep: Callable[[float], None] = time.sleep


class SourceError(ValueError):
    """Error de uso o de integridad de las fuentes (se informa en español y el comando falla)."""


# --- Utilidades de URL ----------------------------------------------------------------------------
def check_url_allowed(url: str) -> str:
    """Devuelve `url` si es `https` de un dominio de la lista permitida; si no, `SourceError`."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as e:
        raise SourceError(f"URL inválida {url!r}: {e}") from None
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SourceError(f"esquema no permitido ({parts.scheme or 'vacío'!r}) en {url!r}; solo https")
    if parts.username or parts.password:
        raise SourceError(f"las credenciales dentro de la URL no están permitidas: {url!r}")
    if host is None or host not in ALLOWED_DOMAINS:
        permitidos = ", ".join(sorted(ALLOWED_DOMAINS))
        raise SourceError(f"dominio no permitido {host!r} en {url!r}; permitidos: {permitidos}")
    if port not in ALLOWED_PORTS:
        raise SourceError(f"puerto no permitido ({port}) en {url!r}")
    return url


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def filename_from_url(url: str) -> str:
    """Nombre de archivo decodificado de la URL.

    En las URL de Liferay (`/documents/<g>/<c>/<título.ext>/<uuid>`) es el penúltimo segmento y el
    espacio viene como `+`; en el resto (p. ej. `.../xsd/DE_v150.xsd`) es el último.
    """
    segs = [s for s in urlsplit(url).path.split("/") if s]
    if not segs:
        raise SourceError(f"la URL no contiene nombre de archivo: {url!r}")
    ends_in_uuid = len(segs) >= 2 and _UUID.match(segs[-1]) is not None
    liferay = ends_in_uuid or segs[0] == "documents"
    raw = segs[-2] if ends_in_uuid else segs[-1]
    name = unquote_plus(raw) if liferay else unquote(raw)
    if not name or any(c in name for c in "/\\\x00"):
        raise SourceError(f"nombre de archivo no válido en la URL: {url!r}")
    return name


def parse_portal_t(url: str) -> datetime | None:
    """`?t=` del portal (milisegundos desde la época Unix, UTC) como datetime con zona; `None` si falta o es inválido."""
    values = parse_qs(urlsplit(url).query).get("t")
    if not values or not re.fullmatch(r"\d{1,16}", values[0]):
        return None
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=int(values[0]))
    except OverflowError:
        return None


# --- Descarga ----------------------------------------------------------------------------------
@dataclass(frozen=True)
class Fetched:
    url: str
    final_url: str
    data: bytes
    content_type: str


class _StrictRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Valida cada salto de una redirección contra la lista de dominios permitidos."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        check_url_allowed(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_limited(resp: http.client.HTTPResponse) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := resp.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_BYTES:
            raise SourceError(f"la descarga supera el máximo de {MAX_BYTES} bytes")
        chunks.append(chunk)
    data = b"".join(chunks)
    expected = resp.headers.get("Content-Length")
    if expected is not None and expected.isdigit() and int(expected) != len(data):
        raise http.client.IncompleteRead(data, int(expected) - len(data))
    return data


def fetch(url: str, *, timeout: float = TIMEOUT_S, retries: int = RETRIES) -> Fetched:
    """Descarga `url` (User-Agent identificable, timeout, reintentos simples ante errores transitorios)."""
    check_url_allowed(url)
    opener = urllib.request.build_opener(_StrictRedirectHandler)
    last = "sin detalle"
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                final = resp.geturl()
                check_url_allowed(final)
                data = _read_limited(resp)
                ctype = resp.headers.get("Content-Type", "")
            return Fetched(url=url, final_url=final, data=data, content_type=ctype)
        except SourceError:
            raise
        except urllib.error.HTTPError as e:
            code = e.code
            e.close()
            if code < 500:
                raise SourceError(f"HTTP {code} al descargar {url}") from None
            last = f"HTTP {code}"
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.HTTPException,
            OSError,
        ) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < retries:
            _sleep(1.5 * attempt)
    raise SourceError(f"no se pudo descargar {url} tras {retries} intentos ({last})")


# --- Hashes y contenido ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Digests:
    sha256: str
    md5: str
    size: int


def digest(data: bytes) -> Digests:
    return Digests(
        sha256=hashlib.sha256(data).hexdigest(),
        md5=hashlib.md5(data, usedforsecurity=False).hexdigest(),
        size=len(data),
    )


def _ext(filename: str) -> str:
    ext = PurePosixPath(filename).suffix.lower()
    return ext if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else ".bin"


def check_content(filename: str, data: bytes) -> None:
    """Rechaza contenido que no coincide con la firma de su extensión (p. ej. HTML de error como `.pdf`)."""
    ext = _ext(filename)
    ok = True
    if ext == ".pdf":
        ok = b"%PDF-" in data[:1024]
    elif ext == ".rar":
        ok = data.startswith(b"Rar!")
    elif ext in (".xlsx", ".zip"):
        ok = data.startswith(b"PK")
    elif ext == ".xsd":
        ok = data.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")
    if not ok:
        raise SourceError(
            f"el contenido de {filename!r} no parece un archivo {ext} (¿página de error del portal?)"
        )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


_DOC_ADAPTER: TypeAdapter[str] = TypeAdapter(DocId)


def validate_doc(doc: str) -> str:
    try:
        return _DOC_ADAPTER.validate_python(doc)
    except ValidationError:
        raise SourceError(
            f"DocId inválido: {doc!r} (p. ej. MT_V150, NT_024, XSD_DIR, XSD_RAR, CHECKSUM_MT, NORMA_<...>)"
        ) from None


# --- Manifiesto (append-only) -----------------------------------------------------------------------
def manifest_path(root: Path) -> Path:
    return root / MANIFEST_NAME


def load_manifest(root: Path) -> SourcesManifest:
    p = manifest_path(root)
    if not p.exists():
        return SourcesManifest()
    try:
        return SourcesManifest.model_validate(load_kb_file(p) or {})
    except (KBYamlError, ValidationError) as e:
        raise SourceError(f"manifiesto inválido ({p.name}): {e}") from None


def check_append_only(old: SourcesManifest, new: SourcesManifest) -> list[str]:
    """Errores si `new` no es una extensión de `old` (se modificó o se borró alguna entrada)."""
    errors: list[str] = []
    for kind, a, b in (
        ("revisión", old.revisions, new.revisions),
        ("chequeo", old.checks, new.checks),
    ):
        if len(b) < len(a):
            errors.append(f"se eliminaron {len(a) - len(b)} entradas de tipo {kind}")
        for i, (x, y) in enumerate(zip(a, b, strict=False), 1):
            if x != y:
                errors.append(f"la {kind} n.º {i} fue modificada")
    return errors


def _scalars_as_str(value: Any) -> Any:
    """El dumper canónico no declara tipos implícitos: todo escalar va como `str` (Pydantic los coerciona al leer)."""
    if isinstance(value, dict):
        return {k: _scalars_as_str(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scalars_as_str(v) for v in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def save_manifest(root: Path, manifest: SourcesManifest) -> None:
    """Escribe el manifiesto en formato canónico; falla si no extiende al que hay en disco."""
    errors = check_append_only(load_manifest(root), manifest)
    if errors:
        raise SourceError("el manifiesto es append-only: " + "; ".join(errors))
    write_kb_file(manifest_path(root), _scalars_as_str(manifest.model_dump(mode="json", exclude_none=True)))


def latest_revision(manifest: SourcesManifest, doc: str) -> SourceRevision | None:
    revs = [r for r in manifest.revisions if r.doc == doc]
    return revs[-1] if revs else None


def last_clean_check(manifest: SourcesManifest) -> SourceCheck | None:
    """Último chequeo sin pendientes: su fecha es el horizonte de fuentes (derivado, no se almacena)."""
    clean = [c for c in manifest.checks if not c.unregistered]
    return clean[-1] if clean else None


# --- Registro de una revisión -----------------------------------------------------------------------
def _write_new(dest: Path, data: bytes) -> None:
    """Crea `dest` con `data`; si ya existe con el mismo contenido no hace nada; nunca sobrescribe."""
    if dest.exists():
        if dest.read_bytes() != data:
            raise SourceError(
                f"{dest.name}: ya existe con distinto contenido (colisión de sha12); no se sobrescribe"
            )
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as f:
        f.write(data)


def register_file(
    root: Path,
    manifest: SourcesManifest,
    *,
    doc: str,
    data: bytes,
    url: str,
    filename: str,
    portal_t: datetime | None,
    origin: Literal["portal", "offline"],
    note: str | None,
    retrieved_at: datetime,
) -> tuple[SourceRevision, bool]:
    """Guarda `data` en sources/<doc>/<sha12>.<ext> y agrega la revisión. `(revisión, creada)`."""
    d = digest(data)
    for r in manifest.revisions:
        if r.doc == doc and r.sha256 == d.sha256:
            return r, False
    check_content(filename, data)
    rel = f"{SOURCES_DIR}/{doc}/{d.sha256[:12]}{_ext(filename)}"
    _write_new(root / rel, data)
    rev = SourceRevision(
        doc=doc,
        sha256=d.sha256,
        md5=d.md5,
        size=d.size,
        url=url,
        filename=filename,
        portal_t=portal_t,
        retrieved_at=retrieved_at,
        origin=origin,
        path=rel,
        note=note,
    )
    save_manifest(root, SourcesManifest(revisions=[*manifest.revisions, rev], checks=manifest.checks))
    return rev, True


# --- Directorio XSD ------------------------------------------------------------------------------------
class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v and v not in self.hrefs:
                    self.hrefs.append(v.strip())


def parse_hrefs(html: str) -> list[str]:
    p = _Anchors()
    p.feed(html)
    p.close()
    return p.hrefs


_XSD_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.xsd$")


def xsd_names(listing_html: str) -> list[str]:
    """Nombres de los `.xsd` enlazados en el índice (solo nombres planos: nada de rutas ni `..`)."""
    names: set[str] = set()
    for href in parse_hrefs(listing_html):
        path = urlsplit(href).path
        name = unquote(path)
        if "/" not in name and _XSD_NAME.match(name):
            names.add(name)
    return sorted(names)


def download_xsd_set(listing_url: str, get: Callable[[str], Fetched] | None = None) -> dict[str, bytes]:
    """Descarga todos los `.xsd` enlazados desde el listado (nombre -> bytes)."""
    get = get or fetch
    base = listing_url if listing_url.endswith("/") else listing_url + "/"
    names = xsd_names(get(base).data.decode("utf-8", errors="replace"))
    if not names:
        raise SourceError(f"el listado {base} no enlaza ningún .xsd (¿cambió el portal?)")
    files: dict[str, bytes] = {}
    for n in names:
        data = get(urljoin(base, n)).data
        check_content(n, data)
        files[n] = data
    return files


def sha256sums_text(files: dict[str, bytes]) -> str:
    """Contenido de SHA256SUMS: `sha256␣␣nombre`, ordenado por nombre, LF final."""
    return "".join(f"{hashlib.sha256(files[n]).hexdigest()}  {n}\n" for n in sorted(files))


_SUMS_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9_.-]*)$")


def parse_sha256sums(text: str) -> dict[str, str]:
    """nombre -> sha256; `ValueError` si una línea no tiene el formato exacto."""
    out: dict[str, str] = {}
    for n, line in enumerate(text.split("\n"), 1):
        if not line:
            continue
        m = _SUMS_LINE.match(line)
        if not m:
            raise ValueError(f"línea {n} de {SHA256SUMS} con formato inválido: {line!r}")
        out[m.group(2)] = m.group(1)
    return out


def _add_xsd_dir(
    root: Path, manifest: SourcesManifest, listing_url: str, note: str | None, now: datetime
) -> tuple[SourceRevision | None, int]:
    """Instantánea del directorio XSD. `(revisión nueva | None si no cambió, n.º de archivos)`."""
    files = download_xsd_set(listing_url)
    sums = sha256sums_text(files).encode("utf-8")
    d = digest(sums)
    last = latest_revision(manifest, XSD_DOC)
    if last is not None and last.sha256 == d.sha256:
        return None, len(files)
    base = root / SOURCES_DIR / XSD_DOC
    day = now.date().isoformat()
    name, n = day, 1
    while (base / name).exists():
        n += 1
        name = f"{day}-{n}"
    target = base / name
    target.mkdir(parents=True)
    try:
        for fname, data in files.items():
            with (target / fname).open("xb") as f:
                f.write(data)
        with (target / SHA256SUMS).open("xb") as f:
            f.write(sums)
        rev = SourceRevision(
            doc=XSD_DOC,
            sha256=d.sha256,
            md5=d.md5,
            size=d.size,
            url=listing_url,
            filename=SHA256SUMS,
            retrieved_at=now,
            origin="portal",
            path=f"{SOURCES_DIR}/{XSD_DOC}/{name}",
            note=note,
        )
        save_manifest(root, SourcesManifest(revisions=[*manifest.revisions, rev], checks=manifest.checks))
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return rev, len(files)


# --- source add -------------------------------------------------------------------------------------------
def _root(args: argparse.Namespace) -> Path:
    given = getattr(args, "root", None)
    return Path(given).resolve() if given else find_root()


def _source_add(args: argparse.Namespace) -> int:
    root = _root(args)
    doc = validate_doc(args.doc)
    url = (args.url or "").strip() or None
    file = args.file
    note = (args.note or "").strip() or None
    manifest = load_manifest(root)
    now = _now()

    if file:
        if doc == XSD_DOC:
            raise SourceError("XSD_DIR es una instantánea del directorio del portal: no admite --file")
        if not note:
            raise SourceError("--file (copia offline) exige --note: explique de dónde sale la copia")
        path = Path(file).expanduser()
        if not path.is_file():
            raise SourceError(f"--file: no existe el archivo {file!r}")
        if url:
            check_url_allowed(url)
        filename = path.name
        rev, created = register_file(
            root,
            manifest,
            doc=doc,
            data=path.read_bytes(),
            url=url or f"offline:{filename}",
            filename=filename,
            portal_t=parse_portal_t(url) if url else None,
            origin="offline",
            note=note,
            retrieved_at=now,
        )
    elif doc == XSD_DOC:
        listing = url or XSD_LISTING_URL
        check_url_allowed(listing)
        rev_x, count = _add_xsd_dir(root, manifest, listing, note, now)
        if rev_x is None:
            print(
                f"XSD_DIR: sin cambios respecto de la última instantánea ({count} archivos); no se crea carpeta nueva."
            )
            return 0
        print(f"registrado XSD_DIR: {rev_x.path}/ ({count} archivos .xsd + {SHA256SUMS})")
        print(f"  sha256 de {SHA256SUMS}: {rev_x.sha256}")
        return 0
    else:
        if not url:
            raise SourceError("indique --url (dominio DNIT permitido) o --file con --note")
        check_url_allowed(url)
        fetched = fetch(url)
        rev, created = register_file(
            root,
            manifest,
            doc=doc,
            data=fetched.data,
            url=url,
            filename=filename_from_url(url),
            portal_t=parse_portal_t(url),
            origin="portal",
            note=note,
            retrieved_at=now,
        )

    if not created:
        print(f"{doc}: el sha256 {rev.sha256[:12]} ya está registrado ({rev.path}); no se hace nada.")
        return 0
    print(f"registrado {doc}: {rev.path}")
    print(f"  sha256 {rev.sha256}")
    print(f"  md5    {rev.md5}   tamaño {rev.size} bytes   origen {rev.origin}")
    if rev.portal_t:
        print(f"  portal_t (subida) {rev.portal_t.isoformat()}")
    return 0


def cmd_source_add(args: argparse.Namespace) -> int:
    """`sifen source add --doc DocId (--url URL | --file RUTA --note TEXTO)`; 0 = ok, 1 = error."""
    try:
        return _source_add(args)
    except SourceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


# --- Integridad (manifiesto <-> sources/) ------------------------------------------------------------------
def _safe_rel(rel: str, doc: str, sha256: str) -> bool:
    p = PurePosixPath(rel)
    parts = p.parts
    if p.is_absolute() or ".." in parts or len(parts) != 3:
        return False
    if parts[0] != SOURCES_DIR or parts[1] != doc:
        return False
    return doc == XSD_DOC or parts[2].startswith(sha256[:12])


def _verify_file(root: Path, rev: SourceRevision, tag: str, registered: set[str]) -> list[str]:
    registered.add(rev.path)
    target = root / rev.path
    if not target.is_file():
        return [f"{tag}: falta el archivo {rev.path}"]
    d = digest(target.read_bytes())
    errors = []
    if d.sha256 != rev.sha256:
        errors.append(
            f"{tag}: el sha256 de {rev.path} no coincide (disco {d.sha256[:12]}, manifiesto {rev.sha256[:12]})"
        )
    elif d.md5 != rev.md5.lower() or d.size != rev.size:
        errors.append(f"{tag}: md5 o tamaño de {rev.path} no coinciden con el manifiesto")
    return errors


def _verify_xsd_dir(root: Path, rev: SourceRevision, tag: str, registered: set[str]) -> list[str]:
    folder = root / rev.path
    sums_file = folder / SHA256SUMS
    if not sums_file.is_file():
        return [f"{tag}: falta {rev.path}/{SHA256SUMS}"]
    registered.add(f"{rev.path}/{SHA256SUMS}")
    raw = sums_file.read_bytes()
    d = digest(raw)
    if d.sha256 != rev.sha256 or d.md5 != rev.md5.lower() or d.size != rev.size:
        return [f"{tag}: {rev.path}/{SHA256SUMS} no coincide con el manifiesto"]
    try:
        listed = parse_sha256sums(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return [f"{tag}: {e}"]
    errors = []
    for name, sha in listed.items():
        rel = f"{rev.path}/{name}"
        registered.add(rel)
        f = root / rel
        if not f.is_file():
            errors.append(f"{tag}: falta el archivo {rel}")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            errors.append(f"{tag}: el sha256 de {rel} no coincide con {SHA256SUMS}")
    return errors


def verify_sources(root: Path) -> list[str]:
    """Errores de integridad: archivo faltante o alterado, ruta inválida y archivos de `sources/` sin registrar."""
    try:
        manifest = load_manifest(root)
    except SourceError as e:
        return [str(e)]
    errors: list[str] = []
    registered: set[str] = set()
    seen: set[tuple[str, str]] = set()
    for i, rev in enumerate(manifest.revisions, 1):
        tag = f"revisión n.º {i} ({rev.doc} {rev.sha256[:12]})"
        if (rev.doc, rev.sha256) in seen:
            errors.append(f"{tag}: sha256 duplicado para el mismo documento")
        seen.add((rev.doc, rev.sha256))
        if not _safe_rel(rev.path, rev.doc, rev.sha256):
            errors.append(f"{tag}: ruta inválida {rev.path!r} (se espera sources/{rev.doc}/<sha12>.<ext>)")
            continue
        if rev.doc == XSD_DOC:
            errors += _verify_xsd_dir(root, rev, tag, registered)
        else:
            errors += _verify_file(root, rev, tag, registered)
    sdir = root / SOURCES_DIR
    if sdir.is_dir():
        for p in sorted(sdir.rglob("*")):
            if p.is_file() and p.relative_to(root).as_posix() not in registered:
                errors.append(f"archivo no registrado en el manifiesto: {p.relative_to(root).as_posix()}")
    return errors


# --- source check ----------------------------------------------------------------------------------------------
_NT_RE = re.compile(r"NT_E_KUATIA_(\d{3})", re.IGNORECASE)
_MT_RE = re.compile(r"^Manual[ _]T.cnico[ _]Versi.n[ _](\d+)\b", re.IGNORECASE)
_CHECKSUM_MT_RE = re.compile(r"^Listado Checksum MD5 de las versiones del Manual", re.IGNORECASE)
_XSD_RAR_RE = re.compile(r"^Estructura_DE xsd\.rar$", re.IGNORECASE)
_GEO_RE = re.compile(r"REFERENCIA GEOGRAFICA.*\.xlsx$", re.IGNORECASE)


def classify_filename(filename: str) -> tuple[str, str] | None:
    """`(DocId, ámbito)` de un archivo del portal, o `None` si no es una fuente que vigilemos."""
    if m := _NT_RE.search(filename):
        return f"NT_{m.group(1)}", "nt"
    if m := _MT_RE.match(filename):
        return f"MT_V{m.group(1)}", "manual"
    if _CHECKSUM_MT_RE.match(filename):
        return "CHECKSUM_MT", "manual"
    if _XSD_RAR_RE.match(filename):
        return "XSD_RAR", "xsd"
    if _GEO_RE.search(filename):
        return "TABLA_GEO", "tablas"
    return None


def scope_of(doc: str) -> str | None:
    """Ámbito de `source check` al que pertenece un documento registrado."""
    if doc.startswith("NT_"):
        return "nt"
    if doc in (XSD_DOC, "XSD_RAR"):
        return "xsd"
    if doc.startswith("TABLA_"):
        return "tablas"
    if doc.startswith(("GUIA_", "COM_")):
        return "guias"
    if doc.startswith(("MT_", "NORMA_")) or doc == "CHECKSUM_MT":
        return "manual"
    return None


@dataclass(frozen=True)
class PortalLink:
    url: str
    filename: str
    doc: str
    scope: str


def portal_links(html: str, base_url: str) -> list[PortalLink]:
    """Enlaces `/documents/...` de una página del portal que corresponden a fuentes vigiladas."""
    out: list[PortalLink] = []
    for href in parse_hrefs(html):
        url = urljoin(base_url, href)
        if not urlsplit(url).path.startswith("/documents/"):
            continue
        try:
            check_url_allowed(url)
            filename = filename_from_url(url)
        except SourceError:
            continue
        cls = classify_filename(filename)
        if cls and url not in {link.url for link in out}:
            out.append(PortalLink(url=url, filename=filename, doc=cls[0], scope=cls[1]))
    return out


@dataclass
class CheckReport:
    at: datetime
    scopes: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    unregistered: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def parse_scopes(text: str) -> list[str]:
    wanted = [s.strip() for s in text.split(",") if s.strip()]
    bad = [s for s in wanted if s not in SCOPES]
    if bad or not wanted:
        raise SourceError(f"--scope inválido {bad or text!r}; valores: {', '.join(SCOPES)}")
    return [s for s in SCOPES if s in wanted]


def _unreg(url: str, doc: str, reason: str) -> str:
    return f"{url} [{doc}; {reason}]"


def _xsd_diff(old_sums: dict[str, str], new_files: dict[str, bytes]) -> str:
    new = {n: hashlib.sha256(b).hexdigest() for n, b in new_files.items()}
    changed = sorted(n for n in new if n in old_sums and old_sums[n] != new[n])
    added = sorted(set(new) - set(old_sums))
    removed = sorted(set(old_sums) - set(new))
    parts = []
    for label, names in (("modificados", changed), ("nuevos", added), ("eliminados", removed)):
        if names:
            parts.append(f"{label} {' '.join(names)}")
    return ", ".join(parts) or "el conjunto de hashes cambió"


def run_check(root: Path, manifest: SourcesManifest, scopes: Iterable[str], *, at: datetime) -> CheckReport:
    """Compara el portal con el manifiesto. Lanza `SourceError` si algo no se pudo consultar."""
    cache: dict[str, Fetched] = {}

    def get(url: str) -> Fetched:
        if url not in cache:
            cache[url] = fetch(url)
        return cache[url]

    docs: dict[str, list[SourceRevision]] = {}
    for r in manifest.revisions:
        docs.setdefault(r.doc, []).append(r)

    rep = CheckReport(at=at)

    def verify_url(doc: str, url: str, known: set[str], label: str) -> None:
        f = get(url)
        check_content(filename_from_url(url), f.data)
        sha = hashlib.sha256(f.data).hexdigest()
        if sha in known:
            rep.lines.append(f"  ok      {doc}  {label}  sin cambios ({sha[:12]})")
        else:
            rep.unregistered.append(_unreg(url, doc, f"hash nuevo {sha[:12]}"))
            rep.lines.append(f"  NUEVO   {doc}  {label}  hash nuevo {sha[:12]}")

    for scope in scopes:
        scope_docs = sorted(d for d in docs if scope_of(d) == scope)
        if scope in OPTIONAL_SCOPES and not scope_docs:
            rep.skipped.append(scope)
            continue
        rep.scopes.append(scope)

        # 1) cada documento registrado: se vuelve a descargar su URL más reciente y se compara el hash
        for doc in scope_docs:
            if doc == XSD_DOC:
                continue
            revs = docs[doc]
            latest = next((r for r in reversed(revs) if r.origin == "portal"), None)
            if latest is None:
                rep.lines.append(f"  --      {doc}  solo copias offline: no hay URL que verificar")
                continue
            verify_url(doc, latest.url, {r.sha256 for r in revs}, "(URL registrada)")

        # 2) enlaces de la página del portal que no están registrados (o cuyo contenido cambió)
        if scope in ("nt", "manual", "xsd", "tablas"):
            page_url = TABLES_PAGE_URL if scope == "tablas" else DOCS_PAGE_URL
            html = get(page_url).data.decode("utf-8", errors="replace")
            if "/documents/" not in html:
                raise SourceError(
                    f"la página {page_url} no contiene enlaces /documents/ (¿cambió el portal?)"
                )
            for link in portal_links(html, page_url):
                if link.scope != scope:
                    continue
                revs = docs.get(link.doc, [])
                if not revs:
                    rep.unregistered.append(_unreg(link.url, link.doc, "enlace nuevo no registrado"))
                    rep.lines.append(f"  NUEVO   {link.doc}  enlace no registrado {link.filename}")
                    continue
                latest = next((r for r in reversed(revs) if r.origin == "portal"), None)
                if latest is not None and latest.url == link.url:
                    continue  # ya verificado en el paso 1
                verify_url(link.doc, link.url, {r.sha256 for r in revs}, "(enlace actual del portal)")

        # 3) directorio XSD: el conjunto de hashes (SHA256SUMS) frente a la última instantánea
        if scope == "xsd":
            files = download_xsd_set(XSD_LISTING_URL, get)
            sums = digest(sha256sums_text(files).encode("utf-8"))
            last = latest_revision(manifest, XSD_DOC)
            if last is None:
                rep.unregistered.append(_unreg(XSD_LISTING_URL, XSD_DOC, "sin instantánea registrada"))
                rep.lines.append(
                    f"  NUEVO   {XSD_DOC}  sin instantánea registrada ({len(files)} .xsd en el portal)"
                )
            elif last.sha256 == sums.sha256:
                rep.lines.append(f"  ok      {XSD_DOC}  sin cambios ({len(files)} archivos)")
            else:
                try:
                    old = parse_sha256sums((root / last.path / SHA256SUMS).read_text(encoding="utf-8"))
                except OSError, ValueError:
                    old = {}
                detail = _xsd_diff(old, files) if old else "el conjunto de hashes cambió"
                rep.unregistered.append(_unreg(XSD_LISTING_URL, XSD_DOC, f"cambió el conjunto: {detail}"))
                rep.lines.append(f"  NUEVO   {XSD_DOC}  cambió el conjunto: {detail}")
    return rep


def _source_check(args: argparse.Namespace) -> int:
    root = _root(args)
    scopes = parse_scopes(args.scope)
    manifest = load_manifest(root)
    errors = verify_sources(root)
    if errors:
        print(
            f"Integridad de sources/: {len(errors)} error(es). No se registra ningún chequeo.",
            file=sys.stderr,
        )
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    n_files = len(manifest.revisions)
    clean = last_clean_check(manifest)
    horizon = clean.at.isoformat() if clean else "ninguno"
    if args.offline:
        print(
            f"Verificación local: {n_files} revisión(es) y {len(manifest.checks)} chequeo(s); "
            f"hashes y archivos íntegros. --offline: no se consultó la red ni se agregó chequeo."
        )
        print(f"Horizonte de fuentes (último chequeo limpio): {horizon}")
        return 0

    rep = run_check(root, manifest, scopes, at=_now())
    print(f"Chequeo de fuentes oficiales - {rep.at.isoformat()}")
    print(f"Ámbitos verificados: {', '.join(rep.scopes) or 'ninguno'}")
    if rep.skipped:
        print(f"Ámbitos omitidos (sin documentos registrados para comparar): {', '.join(rep.skipped)}")
    for line in rep.lines:
        print(line)
    if not rep.scopes:
        print("Nada que verificar: no se agregó chequeo al manifiesto.")
        return 0
    check = SourceCheck(at=rep.at, scope=rep.scopes, unregistered=rep.unregistered)  # type: ignore[arg-type]
    save_manifest(root, SourcesManifest(revisions=manifest.revisions, checks=[*manifest.checks, check]))
    if rep.unregistered:
        print(f"Resultado: {len(rep.unregistered)} cambio(s) sin registrar; el horizonte NO avanza.")
        for u in rep.unregistered:
            print(f"  - {u}")
        print("Registre cada uno con: sifen source add --doc <DocId> --url <url>")
        return 1
    print(f"Resultado: LIMPIO. Horizonte de fuentes: {rep.at.isoformat()}")
    return 0


def cmd_source_check(args: argparse.Namespace) -> int:
    """`sifen source check [--scope nt,xsd,manual,tablas,guias] [--offline]`.

    0 = limpio (o `--offline` sin errores), 1 = hay cambios sin registrar o la integridad falla,
    2 = no se pudo consultar el portal (en ese caso NO se registra chequeo: el horizonte no avanza).
    """
    try:
        return _source_check(args)
    except SourceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

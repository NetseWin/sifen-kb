"""Pruebas de `sifen_kb.sources` sin red real: servidor HTTP local en 127.0.0.1 con la lista permitida parcheada."""

import argparse
import hashlib
import http.server
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from sifen_kb import sources
from sifen_kb.cli import main
from sifen_kb.model import SourcesManifest
from sifen_kb.sources import (
    SourceError,
    check_append_only,
    check_url_allowed,
    cmd_source_add,
    cmd_source_check,
    filename_from_url,
    last_clean_check,
    load_manifest,
    parse_portal_t,
    save_manifest,
    verify_sources,
)
from sifen_kb.yamlio import is_canonical

PDF_A = b"%PDF-1.7\ncontenido A\n%%EOF\n"
PDF_B = b"%PDF-1.7\ncontenido B (re-subida)\n%%EOF\n"
NOW = datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)

NT1_PATH = "/documents/20123/420595/NT_E_KUATIA_001_MT_V150.pdf/c4d2ab8e-632b-dc8f-d3f6-6a144a3a3d9c"
NT2_PATH = "/documents/20123/420595/NT_E_KUATIA_002_MT_V150+v2.pdf/b3656789-f42a-e578-4141-45046e452f41"
MT_PATH = (
    "/documents/20123/420592/Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf/e706f7c7-6d93-21d4-b45b-5d22d07b2d22"
)


# --- Servidor local --------------------------------------------------------------------------------
@pytest.fixture
def portal(monkeypatch):
    """Portal falso. `routes[path]` = (estado, cabeceras, cuerpo) o una lista que se consume en orden."""
    routes: dict[str, object] = {}
    hits: list[str] = []
    counts: dict[str, int] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            key = urlsplit(self.path).path
            hits.append(key)
            entry = routes.get(key)
            if entry is None:
                self.send_error(404)
                return
            if isinstance(entry, list):
                n = counts.get(key, 0)
                counts[key] = n + 1
                entry = entry[min(n, len(entry) - 1)]
            status, headers, body = entry
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setattr(sources, "ALLOWED_DOMAINS", frozenset({"127.0.0.1"}))
    monkeypatch.setattr(sources, "ALLOWED_SCHEMES", frozenset({"http"}))
    monkeypatch.setattr(sources, "ALLOWED_PORTS", frozenset({port}))
    monkeypatch.setattr(sources, "DOCS_PAGE_URL", f"{base}/web/e-kuatia/documentacion-tecnica")
    monkeypatch.setattr(sources, "TABLES_PAGE_URL", f"{base}/web/e-kuatia/tablas-y-codificaciones")
    monkeypatch.setattr(sources, "XSD_LISTING_URL", f"{base}/sifen/xsd/")
    monkeypatch.setattr(sources, "_sleep", lambda _s: None)
    monkeypatch.setattr(sources, "_now", lambda: NOW)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    try:
        yield SimpleNamespace(base=base, routes=routes, hits=hits)
    finally:
        srv.shutdown()
        srv.server_close()


def ok(body: bytes, ctype: str = "application/pdf") -> tuple[int, dict[str, str], bytes]:
    return 200, {"Content-Type": ctype}, body


def add_args(root: Path, doc: str, url: str | None = None, file: str | None = None, note: str | None = None):
    return argparse.Namespace(root=str(root), doc=doc, url=url, file=file, note=note)


def check_args(root: Path, scope: str = "nt,xsd,manual", offline: bool = False):
    return argparse.Namespace(root=str(root), scope=scope, offline=offline)


def add_offline(root: Path, doc: str, data: bytes, name: str = "copia.pdf") -> int:
    src = root / "_entrada" / f"{doc}_{name}"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(data)
    return cmd_source_add(add_args(root, doc, file=str(src), note="copia de la empresa"))


def docs_page(*paths: str) -> bytes:
    links = "".join(f'<a href="{p}?t=1687362295907">PDF</a>\n' for p in paths)
    return f"<html><body>{links}<a href='https://www.youtube.com/x'>video</a></body></html>".encode()


# --- Dominios y redirecciones ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a.pdf",
        "http://www.dnit.gov.py/a.pdf",
        "ftp://www.dnit.gov.py/a.pdf",
        "https://www.dnit.gov.py.evil.com/a.pdf",
        "https://www.dnit.gov.py@evil.com/a.pdf",
        "https://user:clave@www.dnit.gov.py/a.pdf",
        "https://www.dnit.gov.py:8443/a.pdf",
        "https://dnit.gov.py/a.pdf",
        "/documents/a.pdf",
    ],
)
def test_url_fuera_de_la_lista_es_error(url):
    with pytest.raises(SourceError):
        check_url_allowed(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_001_MT_V150.pdf/c4d2ab8e-632b?t=1",
        "https://ekuatia.set.gov.py/sifen/xsd/",
        "https://www.dnit.gov.py:443/web/e-kuatia/documentacion-tecnica",
    ],
)
def test_url_de_la_lista_es_valida(url):
    assert check_url_allowed(url) == url


def test_add_con_dominio_no_permitido_falla_y_no_escribe(tmp_path, capsys):
    rc = cmd_source_add(add_args(tmp_path, "NT_001", url="https://example.com/NT_E_KUATIA_001_MT_V150.pdf"))
    assert rc == 1
    assert "dominio no permitido" in capsys.readouterr().err
    assert not (tmp_path / "sources").exists()
    assert not (tmp_path / "sources.manifest.yaml").exists()


def test_redireccion_fuera_de_la_lista_es_error(portal, tmp_path, capsys):
    portal.routes["/a.pdf"] = (302, {"Location": "http://evil.example/b.pdf"}, b"")
    rc = cmd_source_add(add_args(tmp_path, "NT_001", url=f"{portal.base}/a.pdf"))
    assert rc == 1
    assert "dominio no permitido" in capsys.readouterr().err
    assert not (tmp_path / "sources").exists()


def test_redireccion_dentro_de_la_lista_se_sigue(portal, tmp_path):
    portal.routes["/a.pdf"] = (302, {"Location": "/b.pdf"}, b"")
    portal.routes["/b.pdf"] = ok(PDF_A)
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=f"{portal.base}/a.pdf")) == 0
    rev = load_manifest(tmp_path).revisions[0]
    assert rev.url == f"{portal.base}/a.pdf"  # se registra la URL pedida, no la final
    assert rev.sha256 == hashlib.sha256(PDF_A).hexdigest()


def test_reintenta_ante_5xx_pero_no_ante_404(portal, tmp_path, capsys):
    portal.routes["/a.pdf"] = [(503, {}, b""), ok(PDF_A)]
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=f"{portal.base}/a.pdf")) == 0
    assert portal.hits.count("/a.pdf") == 2
    assert cmd_source_add(add_args(tmp_path, "NT_002", url=f"{portal.base}/no-existe.pdf")) == 1
    assert portal.hits.count("/no-existe.pdf") == 1
    assert "HTTP 404" in capsys.readouterr().err


def test_html_de_error_no_se_registra_como_pdf(portal, tmp_path, capsys):
    portal.routes["/a.pdf"] = ok(b"<html>pagina de error</html>", "text/html")
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=f"{portal.base}/a.pdf")) == 1
    assert "no parece un archivo .pdf" in capsys.readouterr().err
    assert not (tmp_path / "sources").exists()


# --- source add: hash, no-op, offline ---------------------------------------------------------------
def test_add_guarda_por_sha12_y_registra_el_manifiesto(portal, tmp_path):
    portal.routes[NT1_PATH] = ok(PDF_A)
    url = f"{portal.base}{NT1_PATH}?t=1687364545680"
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=url)) == 0
    sha = hashlib.sha256(PDF_A).hexdigest()
    dest = tmp_path / "sources" / "NT_001" / f"{sha[:12]}.pdf"
    assert dest.read_bytes() == PDF_A
    (rev,) = load_manifest(tmp_path).revisions
    assert (rev.doc, rev.sha256, rev.size, rev.origin) == ("NT_001", sha, len(PDF_A), "portal")
    assert rev.md5 == hashlib.md5(PDF_A, usedforsecurity=False).hexdigest()
    assert rev.path == f"sources/NT_001/{sha[:12]}.pdf"
    assert rev.filename == "NT_E_KUATIA_001_MT_V150.pdf"
    assert rev.url == url
    assert rev.portal_t == datetime(2023, 6, 21, 16, 22, 25, 680000, tzinfo=UTC)
    assert rev.retrieved_at == NOW
    assert verify_sources(tmp_path) == []


def test_manifiesto_escrito_es_canonico(portal, tmp_path):
    portal.routes[NT1_PATH] = ok(PDF_A)
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=f"{portal.base}{NT1_PATH}?t=1687364545680")) == 0
    assert add_offline(tmp_path, "NT_002", PDF_B) == 0
    text = (tmp_path / "sources.manifest.yaml").read_text(encoding="utf-8")
    assert "\r" not in text
    assert is_canonical(text)


def test_mismo_sha256_es_no_op(portal, tmp_path, capsys):
    portal.routes[NT1_PATH] = ok(PDF_A)
    url = f"{portal.base}{NT1_PATH}?t=1687364545680"
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=url)) == 0
    before = (tmp_path / "sources.manifest.yaml").read_bytes()
    capsys.readouterr()
    # misma URL y también una URL distinta (otro ?t=) con el mismo contenido
    for u in (url, f"{portal.base}{NT1_PATH}?t=1999999999999"):
        assert cmd_source_add(add_args(tmp_path, "NT_001", url=u)) == 0
        assert "ya está registrado" in capsys.readouterr().out
    assert (tmp_path / "sources.manifest.yaml").read_bytes() == before
    assert len(list((tmp_path / "sources" / "NT_001").iterdir())) == 1


def test_resubida_con_otro_contenido_agrega_revision_y_conserva_la_anterior(portal, tmp_path):
    portal.routes[NT1_PATH] = ok(PDF_A)
    url = f"{portal.base}{NT1_PATH}?t=1687364545680"
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=url)) == 0
    portal.routes[NT1_PATH] = ok(PDF_B)
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=url)) == 0
    revs = load_manifest(tmp_path).revisions
    assert [r.sha256 for r in revs] == [hashlib.sha256(PDF_A).hexdigest(), hashlib.sha256(PDF_B).hexdigest()]
    assert len(list((tmp_path / "sources" / "NT_001").iterdir())) == 2
    assert verify_sources(tmp_path) == []


def test_file_sin_note_es_error(tmp_path, capsys):
    f = tmp_path / "x.pdf"
    f.write_bytes(PDF_A)
    assert cmd_source_add(add_args(tmp_path, "NT_001", file=str(f))) == 1
    assert "--note" in capsys.readouterr().err
    assert cmd_source_add(add_args(tmp_path, "NT_001", file=str(f), note="   ")) == 1
    assert not (tmp_path / "sources").exists()


def test_file_offline_con_note(tmp_path):
    f = tmp_path / "NT_E_KUATIA_021_MT_V150_original.pdf"
    f.write_bytes(PDF_A)
    assert (
        cmd_source_add(
            add_args(tmp_path, "NT_021", file=str(f), note="versión anterior que conserva la empresa")
        )
        == 0
    )
    (rev,) = load_manifest(tmp_path).revisions
    assert rev.origin == "offline"
    assert rev.note == "versión anterior que conserva la empresa"
    assert rev.filename == "NT_E_KUATIA_021_MT_V150_original.pdf"
    assert rev.portal_t is None
    assert verify_sources(tmp_path) == []


def test_docid_invalido_es_error(tmp_path, capsys):
    assert cmd_source_add(add_args(tmp_path, "nt_1", url="https://www.dnit.gov.py/x.pdf")) == 1
    assert "DocId inválido" in capsys.readouterr().err


# --- append-only -------------------------------------------------------------------------------------
def test_manifiesto_append_only(tmp_path):
    assert add_offline(tmp_path, "NT_001", PDF_A) == 0
    assert add_offline(tmp_path, "NT_002", PDF_B) == 0
    old = load_manifest(tmp_path)
    nueva = old.revisions[0].model_copy(update={"doc": "NT_003", "sha256": "0" * 64})

    assert check_append_only(old, SourcesManifest(revisions=[*old.revisions, nueva], checks=old.checks)) == []

    modificada = SourcesManifest(
        revisions=[old.revisions[0].model_copy(update={"size": 1}), *old.revisions[1:]], checks=old.checks
    )
    assert any("n.º 1 fue modificada" in e for e in check_append_only(old, modificada))
    assert any(
        "eliminaron" in e for e in check_append_only(old, SourcesManifest(revisions=old.revisions[1:]))
    )

    before = (tmp_path / "sources.manifest.yaml").read_bytes()
    with pytest.raises(SourceError, match="append-only"):
        save_manifest(tmp_path, modificada)
    with pytest.raises(SourceError, match="append-only"):
        save_manifest(tmp_path, SourcesManifest())
    assert (tmp_path / "sources.manifest.yaml").read_bytes() == before


# --- verify_sources ----------------------------------------------------------------------------------
def test_verify_sources_detecta_alterado_faltante_y_no_registrado(tmp_path):
    assert verify_sources(tmp_path) == []
    assert add_offline(tmp_path, "NT_001", PDF_A) == 0
    assert add_offline(tmp_path, "NT_002", PDF_B) == 0
    assert verify_sources(tmp_path) == []

    rev1, rev2 = load_manifest(tmp_path).revisions
    (tmp_path / rev1.path).write_bytes(PDF_A + b"alterado")
    errs = verify_sources(tmp_path)
    assert len(errs) == 1 and "sha256" in errs[0] and rev1.path in errs[0]

    (tmp_path / rev1.path).write_bytes(PDF_A)
    (tmp_path / rev2.path).unlink()
    errs = verify_sources(tmp_path)
    assert len(errs) == 1 and "falta el archivo" in errs[0]

    (tmp_path / rev2.path).write_bytes(PDF_B)
    extra = tmp_path / "sources" / "NT_099" / "intruso.pdf"
    extra.parent.mkdir(parents=True)
    extra.write_bytes(PDF_A)
    errs = verify_sources(tmp_path)
    assert errs == ["archivo no registrado en el manifiesto: sources/NT_099/intruso.pdf"]


def test_verify_sources_rechaza_rutas_fuera_de_sources(tmp_path):
    assert add_offline(tmp_path, "NT_001", PDF_A) == 0
    p = tmp_path / "sources.manifest.yaml"
    p.write_text(
        p.read_text(encoding="utf-8").replace("path: sources/NT_001/", "path: sources/../NT_001/"),
        encoding="utf-8",
    )
    errs = verify_sources(tmp_path)
    assert any("ruta inválida" in e for e in errs)


# --- ?t=, nombres de archivo ----------------------------------------------------------------------------
def test_parse_portal_t_es_epoch_en_milisegundos_utc():
    url = "https://www.dnit.gov.py/documents/20123/420592/Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf/e706f7c7?t=1687362295907"
    assert parse_portal_t(url) == datetime(2023, 6, 21, 15, 44, 55, 907000, tzinfo=UTC)
    assert parse_portal_t("https://www.dnit.gov.py/documents/a.pdf/u?x=1&t=0") == datetime(
        1970, 1, 1, tzinfo=UTC
    )
    assert parse_portal_t("https://www.dnit.gov.py/documents/a.pdf/u") is None
    assert parse_portal_t("https://www.dnit.gov.py/documents/a.pdf/u?t=") is None
    assert parse_portal_t("https://www.dnit.gov.py/documents/a.pdf/u?t=abc") is None
    assert parse_portal_t("https://www.dnit.gov.py/documents/a.pdf/u?t=-5") is None
    assert parse_portal_t("https://www.dnit.gov.py/documents/a.pdf/u?t=9999999999999999") is None


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        (
            "https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_021_MT_V150+30.12.24.pdf/ab12f22b-42a2-9bd4-e3a0-7141d9e4b8d0?t=1",
            "NT_E_KUATIA_021_MT_V150 30.12.24.pdf",
        ),
        (
            "https://www.dnit.gov.py/documents/20123/420592/Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf/e706f7c7-6d93-21d4-b45b-5d22d07b2d22?t=1",
            "Manual Técnico Versión 150.pdf",
        ),
        (
            "https://www.dnit.gov.py/documents/20123/399315/Decreto+N%C2%B0+872-23.pdf/c86edb49-54e2-367c-8626-13390cea60b1",
            "Decreto N° 872-23.pdf",
        ),
        (
            "https://www.dnit.gov.py/documents/20123/420595/a%2Bb.pdf/c86edb49-54e2-367c-8626-13390cea60b1",
            "a+b.pdf",
        ),
        ("https://ekuatia.set.gov.py/sifen/xsd/DE_v150.xsd", "DE_v150.xsd"),
        ("https://ekuatia.set.gov.py/sifen/xsd/a+b.xsd", "a+b.xsd"),
    ],
)
def test_filename_from_url_decodifica(url, esperado):
    assert filename_from_url(url) == esperado


# --- XSD_DIR ----------------------------------------------------------------------------------------------------
XSD_A = b'<?xml version="1.0"?>\r\n<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"/>\r\n'
XSD_B = (
    b'<?xml version="1.0"?>\n<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><!-- b --></xs:schema>\n'
)
XSD_LISTING = (
    b'<html><body><a href="?C=N;O=D">Name</a><a href="/sifen/">Parent Directory</a>'
    b'<a href="protProcesDE_v150.xsd">p</a><a href="DE_v150.xsd">d</a><a href="Alpha.xsd">a</a>'
    b'<a href="../evil.xsd">x</a><a href="leeme.txt">t</a></body></html>'
)


def serve_xsd(portal, *, de=XSD_A):
    portal.routes["/sifen/xsd/"] = ok(XSD_LISTING, "text/html")
    portal.routes["/sifen/xsd/DE_v150.xsd"] = ok(de, "application/xml")
    portal.routes["/sifen/xsd/Alpha.xsd"] = ok(XSD_B, "application/xml")
    portal.routes["/sifen/xsd/protProcesDE_v150.xsd"] = ok(XSD_B, "application/xml")


def test_xsd_dir_instantanea_sha256sums_y_sin_carpeta_nueva_si_no_cambia(portal, tmp_path):
    serve_xsd(portal)
    assert cmd_source_add(add_args(tmp_path, "XSD_DIR")) == 0
    folder = tmp_path / "sources" / "XSD_DIR" / "2026-10-17"
    assert sorted(p.name for p in folder.iterdir()) == [
        "Alpha.xsd",
        "DE_v150.xsd",
        "SHA256SUMS",
        "protProcesDE_v150.xsd",
    ]
    assert (folder / "DE_v150.xsd").read_bytes() == XSD_A  # bytes exactos, CRLF incluido
    sums = (folder / "SHA256SUMS").read_text(encoding="utf-8")
    assert sums == (
        f"{hashlib.sha256(XSD_B).hexdigest()}  Alpha.xsd\n"
        f"{hashlib.sha256(XSD_A).hexdigest()}  DE_v150.xsd\n"
        f"{hashlib.sha256(XSD_B).hexdigest()}  protProcesDE_v150.xsd\n"
    )
    (rev,) = load_manifest(tmp_path).revisions
    assert rev.sha256 == hashlib.sha256(sums.encode()).hexdigest()
    assert (rev.path, rev.filename, rev.origin, rev.url) == (
        "sources/XSD_DIR/2026-10-17",
        "SHA256SUMS",
        "portal",
        f"{portal.base}/sifen/xsd/",
    )
    assert "/sifen/evil.xsd" not in portal.hits and "/evil.xsd" not in portal.hits
    assert verify_sources(tmp_path) == []

    # sin cambios: no se crea carpeta ni revisión
    before = (tmp_path / "sources.manifest.yaml").read_bytes()
    assert cmd_source_add(add_args(tmp_path, "XSD_DIR")) == 0
    assert (tmp_path / "sources.manifest.yaml").read_bytes() == before
    assert [p.name for p in (tmp_path / "sources" / "XSD_DIR").iterdir()] == ["2026-10-17"]

    # un XSD cambia in situ: carpeta nueva; la anterior se conserva intacta
    serve_xsd(portal, de=XSD_A + b"<!-- cambio in situ -->\n")
    assert cmd_source_add(add_args(tmp_path, "XSD_DIR")) == 0
    assert sorted(p.name for p in (tmp_path / "sources" / "XSD_DIR").iterdir()) == [
        "2026-10-17",
        "2026-10-17-2",
    ]
    assert (folder / "DE_v150.xsd").read_bytes() == XSD_A
    assert len(load_manifest(tmp_path).revisions) == 2
    assert verify_sources(tmp_path) == []


def test_verify_sources_detecta_xsd_alterado_y_extra(portal, tmp_path):
    serve_xsd(portal)
    assert cmd_source_add(add_args(tmp_path, "XSD_DIR")) == 0
    folder = tmp_path / "sources" / "XSD_DIR" / "2026-10-17"
    (folder / "Alpha.xsd").write_bytes(XSD_A)
    errs = verify_sources(tmp_path)
    assert len(errs) == 1 and "Alpha.xsd" in errs[0] and "SHA256SUMS" in errs[0]
    (folder / "Alpha.xsd").write_bytes(XSD_B)
    (folder / "otro.xsd").write_bytes(XSD_A)
    assert verify_sources(tmp_path) == [
        "archivo no registrado en el manifiesto: sources/XSD_DIR/2026-10-17/otro.xsd"
    ]


def test_xsd_dir_no_admite_file(tmp_path, capsys):
    f = tmp_path / "x.xsd"
    f.write_bytes(XSD_A)
    assert cmd_source_add(add_args(tmp_path, "XSD_DIR", file=str(f), note="n")) == 1
    assert "XSD_DIR" in capsys.readouterr().err


# --- source check ---------------------------------------------------------------------------------------------------
def serve_portal(portal, *, nt1=PDF_A, nt2=PDF_B):
    portal.routes["/web/e-kuatia/documentacion-tecnica"] = ok(
        docs_page(NT1_PATH, NT2_PATH, MT_PATH), "text/html"
    )
    portal.routes[NT1_PATH] = ok(nt1)
    portal.routes[NT2_PATH] = ok(nt2)
    portal.routes[MT_PATH] = ok(b"%PDF-1.7\nmanual\n")
    serve_xsd(portal)


def test_source_check_detecta_enlaces_nuevos_hash_nuevo_y_xsd_y_fija_el_horizonte(portal, tmp_path, capsys):
    serve_portal(portal)
    url1 = f"{portal.base}{NT1_PATH}?t=1687362295907"
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=url1)) == 0
    assert cmd_source_add(add_args(tmp_path, "XSD_DIR")) == 0

    # NT_002, el Manual y el chequeo no están registrados: se informan y el horizonte NO avanza
    assert cmd_source_check(check_args(tmp_path)) == 1
    out = capsys.readouterr().out
    (c1,) = load_manifest(tmp_path).checks
    assert c1.scope == ["nt", "xsd", "manual"]
    assert len(c1.unregistered) == 2
    assert any("NT_002" in u and "enlace nuevo" in u and NT2_PATH in u for u in c1.unregistered)
    assert any("MT_V150" in u for u in c1.unregistered)
    assert "NT_002" in out and "NO avanza" in out
    assert last_clean_check(load_manifest(tmp_path)) is None

    # se registran y el chequeo queda limpio
    assert cmd_source_add(add_args(tmp_path, "NT_002", url=f"{portal.base}{NT2_PATH}?t=1687362295907")) == 0
    assert cmd_source_add(add_args(tmp_path, "MT_V150", url=f"{portal.base}{MT_PATH}?t=1687362295907")) == 0
    assert cmd_source_check(check_args(tmp_path)) == 0
    m = load_manifest(tmp_path)
    assert m.checks[-1].unregistered == []
    assert last_clean_check(m) == m.checks[-1]
    assert "LIMPIO" in capsys.readouterr().out

    # DNIT re-sube NT_001 en el mismo enlace y cambia un XSD in situ
    serve_portal(portal, nt1=PDF_B + b"otra")
    serve_xsd(portal, de=XSD_A + b"<!-- in situ -->\n")
    assert cmd_source_check(check_args(tmp_path)) == 1
    unreg = load_manifest(tmp_path).checks[-1].unregistered
    assert len(unreg) == 2
    assert any("NT_001" in u and "hash nuevo" in u for u in unreg)
    assert any("XSD_DIR" in u and "modificados DE_v150.xsd" in u for u in unreg)

    # el manifiesto sigue siendo canónico y las revisiones previas no se tocaron
    text = (tmp_path / "sources.manifest.yaml").read_text(encoding="utf-8")
    assert is_canonical(text)
    assert verify_sources(tmp_path) == []


def test_source_check_enlace_con_url_nueva_y_mismo_contenido_no_es_novedad(portal, tmp_path, capsys):
    serve_portal(portal)
    assert cmd_source_add(add_args(tmp_path, "NT_001", url=f"{portal.base}{NT1_PATH}?t=111")) == 0
    # el portal publica el enlace con otro ?t=, pero el archivo es idéntico
    capsys.readouterr()
    assert cmd_source_check(check_args(tmp_path, scope="nt")) == 1  # NT_002 sigue sin registrar
    unreg = load_manifest(tmp_path).checks[-1].unregistered
    assert len(unreg) == 1 and "NT_002" in unreg[0]


def test_source_check_offline_no_usa_red_ni_agrega_chequeo(portal, tmp_path, monkeypatch, capsys):
    assert add_offline(tmp_path, "NT_001", PDF_A) == 0
    n_hits = len(portal.hits)

    def sin_red(*_a, **_k):
        raise AssertionError("--offline no debe consultar la red")

    monkeypatch.setattr(sources, "fetch", sin_red)
    assert cmd_source_check(check_args(tmp_path, offline=True)) == 0
    assert load_manifest(tmp_path).checks == []
    assert len(portal.hits) == n_hits
    assert "--offline" in capsys.readouterr().out

    # --offline también falla si el repo está alterado
    rev = load_manifest(tmp_path).revisions[0]
    (tmp_path / rev.path).write_bytes(b"%PDF-alterado")
    assert cmd_source_check(check_args(tmp_path, offline=True)) == 1
    assert "sha256" in capsys.readouterr().err


def test_source_check_si_falla_la_red_no_registra_chequeo(portal, tmp_path, capsys):
    assert cmd_source_add(add_args(tmp_path, "NT_001", file=str(_pdf(tmp_path)), note="n")) == 0
    # la página de documentación devuelve 404
    assert cmd_source_check(check_args(tmp_path, scope="nt")) == 2
    assert "HTTP 404" in capsys.readouterr().err
    assert load_manifest(tmp_path).checks == []


def _pdf(tmp_path: Path) -> Path:
    f = tmp_path / "entrada.pdf"
    f.write_bytes(PDF_A)
    return f


def test_source_check_omite_ambitos_opcionales_sin_documentos(portal, tmp_path, capsys):
    assert cmd_source_check(check_args(tmp_path, scope="tablas,guias")) == 0
    assert "omitidos" in capsys.readouterr().out
    assert not (tmp_path / "sources.manifest.yaml").exists()


def test_source_check_scope_invalido(tmp_path, capsys):
    assert cmd_source_check(check_args(tmp_path, scope="nt,foo")) == 2
    assert "--scope inválido" in capsys.readouterr().err


def test_cli_source_check_offline_en_repo_vacio(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "source", "check", "--offline"]) == 0
    assert "Horizonte de fuentes" in capsys.readouterr().out

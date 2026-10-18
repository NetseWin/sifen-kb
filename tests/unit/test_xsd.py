"""Tests de `sifen_kb.xsd` (docs/arquitectura.md §K.6): todo sin red.

La lógica se prueba contra un XSD sintético (`tests/fixtures/xsd_mini/`) y contra XML sintéticos
(`tests/fixtures/xml/`). Las pruebas de integración usan la instantánea oficial registrada en
`sources/XSD_DIR/` (vía `sources.manifest.yaml`) y se omiten si no existe.
"""

from __future__ import annotations

import hashlib
import re
import socket
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from sifen_kb import xsd
from sifen_kb.xsd import (
    PII_ELEMENTS,
    SIFEN_NS,
    Facets,
    XmlReadError,
    XsdError,
    XsdIndex,
    XsdOfflineError,
    anachronistic,
    load_schema,
    mask,
    paraguay_tz_is_exact,
    parse_occurrence,
    read_emission_date,
    read_processing_date,
    read_values,
    snapshot_from_manifest,
    to_paraguay_date,
    validate_xml,
)

REPO = Path(__file__).resolve().parents[2]
MINI = REPO / "tests" / "fixtures" / "xsd_mini"
XML = REPO / "tests" / "fixtures" / "xml"

# Campos del piloto -> (xml_name, padre directo), verificados contra la instantánea oficial
# (`test_real_pilot_paths`). El KB real los trae de `Field.xml_name`; aquí se fijan para probar la lectura.
PILOT: dict[str, tuple[str, str | None]] = {
    "D002": ("dFeEmiDE", "gDatGralOpe"),
    "D011": ("iTipTra", "gOpeCom"),
    "D015": ("cMoneOpe", "gOpeCom"),
    "D201": ("iNatRec", "gDatRec"),
    "D202": ("iTiOpe", "gDatRec"),
    "D208": ("iTipIDRec", "gDatRec"),
    "D209": ("dDTipIDRec", "gDatRec"),
    "D210": ("dNumIDRec", "gDatRec"),
    "C002": ("iTiDE", "gTimb"),
    "F014": ("dTotGralOpe", "gTotSub"),
    "F023": ("dTotalGs", "gTotSub"),
}


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier intento de conectar (o resolver un nombre) falla el test."""

    def boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("intento de acceso a red")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket.socket, "connect_ex", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


@pytest.fixture(scope="module")
def mini_schema() -> Any:
    return load_schema(MINI, entries=("mini_root.xsd",))


@pytest.fixture(scope="module")
def mini_index(mini_schema: Any) -> XsdIndex:
    return XsdIndex(mini_schema)


# --- Carga sin red -----------------------------------------------------------------------------------
def test_xsd_loads_offline(no_network: None) -> None:
    schema = load_schema(MINI, entries=("mini_root.xsd",))
    # el include por URL HTTPS absoluta (mini_types.xsd) y el import relativo (mini_firma.xsd) se resolvieron local
    assert "{http://ekuatia.set.gov.py/sifen/xsd}fecHhmmss" in schema.maps.types
    assert "{urn:sifen-kb:mini-firma}Firma" in schema.maps.elements
    assert "rMini" in schema.elements


def _schema_with_includes(folder: Path, *urls: str) -> Path:
    body = "".join(f'<xs:include schemaLocation="{u}"/>' for u in urls)
    path = folder / "raiz.xsd"
    path.write_text(
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:x" xmlns="urn:x">'
        f'{body}<xs:element name="a" type="xs:string"/></xs:schema>',
        encoding="utf-8",
    )
    return path


def test_unmapped_remote_include_is_an_error_not_a_download(tmp_path: Path, no_network: None) -> None:
    _schema_with_includes(tmp_path, "https://evil.example.com/x.xsd")
    with pytest.raises(XsdOfflineError, match="evil.example.com"):
        load_schema(tmp_path, entries=("raiz.xsd",))


def test_portal_include_missing_from_snapshot_is_an_error(tmp_path: Path, no_network: None) -> None:
    _schema_with_includes(tmp_path, "https://ekuatia.set.gov.py/sifen/xsd/NoExiste_v1.xsd")
    with pytest.raises(XsdOfflineError, match="no está en la instantánea"):
        load_schema(tmp_path, entries=("raiz.xsd",))


@pytest.mark.parametrize(
    "url",
    [
        "https://ekuatia.set.gov.py/sifen/xsd/../raiz.xsd",
        "https://ekuatia.set.gov.py/sifen/xsd/sub/raiz.xsd",
        "https://ekuatia.set.gov.py/sifen/xsd/raiz.xsd?x=1",
    ],
)
def test_portal_include_with_odd_names_is_refused(tmp_path: Path, url: str, no_network: None) -> None:
    _schema_with_includes(tmp_path, url)
    with pytest.raises(XsdOfflineError):
        load_schema(tmp_path, entries=("raiz.xsd",))


def test_load_schema_rejects_missing_folder_and_entry(tmp_path: Path) -> None:
    with pytest.raises(XsdError, match="no existe"):
        load_schema(tmp_path / "nada")
    with pytest.raises(XsdError, match="falta"):
        load_schema(tmp_path, entries=("raiz.xsd",))


# --- Índice: declaraciones y facetas ---------------------------------------------------------------------
def test_lookup_paths_parents_and_occurrence(mini_index: XsdIndex) -> None:
    (d,) = mini_index.lookup("iTipIDRec")
    assert d.xpath == "/rMini/DE/gDatGralOpe/gDatRec/iTipIDRec"
    assert d.parent == "gDatRec"
    assert (d.min_occurs, d.max_occurs, d.occurrence) == (0, 1, "0-1")
    assert d.type_name == "tiTipDocRec"
    assert d.namespace == SIFEN_NS
    assert d.facets.patterns == ("[1-6]|9",)

    (root,) = mini_index.lookup("rMini")
    assert root.parent is None
    assert root.xpath == "/rMini"
    assert mini_index.lookup("noExiste") == []
    assert "dNomRec" in mini_index
    assert "noExiste" not in mini_index
    assert len(mini_index) == sum(len(mini_index.lookup(n)) for n in mini_index.names())


def test_lookup_same_name_under_several_parents(mini_index: XsdIndex) -> None:
    assert len(mini_index.lookup("dObs")) == 3
    (d,) = mini_index.lookup("dObs", parent="gTotSub")
    assert d.occurrence == "1-1"
    assert mini_index.lookup("dObs", parent="gDatRec")[0].occurrence == "0-1"
    assert mini_index.lookup("dObs", parent="gEmis") == []


def test_facets_from_xsd_mini(mini_index: XsdIndex) -> None:
    assert mini_index.lookup("cMoneOpe")[0].facets.enumeration == ("PYG", "USD")
    nom = mini_index.lookup("dNomRec")[0].facets
    assert (nom.min_length, nom.max_length) == (4, 255)
    assert mini_index.lookup("dCodSeg")[0].facets.length == 9
    tot = mini_index.lookup("dTotGralOpe")[0].facets
    assert (tot.total_digits, tot.fraction_digits) == (23, 8)
    assert mini_index.lookup("dNumIDRec")[0].facets.patterns == (r"[0-9A-Za-z\-]{1,20}",)
    # sin facetas: tipo builtin
    assert mini_index.lookup("dItem")[0].facets == Facets()


def test_union_reports_no_facets_and_anonymous_type_has_no_name(mini_index: XsdIndex) -> None:
    union = mini_index.lookup("dDTipIDRec")[0]
    assert union.type_name == "tdDtipDoc"
    assert union.facets == Facets()
    assert mini_index.lookup("dVerFor")[0].type_name is None


def test_other_namespace_elements_are_indexed_by_local_name(mini_index: XsdIndex) -> None:
    (cert,) = mini_index.lookup("Certificado")
    assert cert.xpath == "/rMini/Firma/Certificado"
    assert cert.parent == "Firma"
    assert cert.namespace == "urn:sifen-kb:mini-firma"


def test_effective_occurrence_of_choice_and_repeated_sequence(mini_index: XsdIndex) -> None:
    # los miembros de una choice con varias alternativas no son obligatorios
    assert mini_index.lookup("dA")[0].occurrence == "0-1"
    assert mini_index.lookup("dB")[0].occurrence == "0-1"
    # sequence 1..3 que contiene dX 1..2 -> 1-6
    assert mini_index.lookup("dX")[0].occurrence == "1-6"
    assert mini_index.lookup("gLista")[0].occurrence == "0-n"


# --- Ocurrencia del manual vs XSD ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        ("0-1", (0, 1)),
        ("1-1", (1, 1)),
        ("1-999", (1, 999)),
        ("0-n", (0, None)),
        ("1-N", (1, None)),
        (" 0 - 9 ", (0, 9)),
        ("0–99", (0, 99)),
        ("1", (1, 1)),
        ("-", None),
        ("", None),
        ("n", None),
        ("2-1", None),
        ("a-b", None),
        ("0-1-2", None),
    ],
)
def test_parse_occurrence(literal: str, expected: tuple[int, int | None] | None) -> None:
    assert parse_occurrence(literal) == expected


@pytest.mark.parametrize(
    ("name", "parent", "literal", "status"),
    [
        ("dNomRec", "gDatRec", "1-1", "match"),
        ("dNomRec", "gDatRec", "0-1", "mismatch"),
        ("dNomRec", None, "1-1", "match"),
        ("iTipIDRec", "gDatRec", "0-1", "match"),
        ("gLista", "DE", "0-n", "match"),
        ("gLista", "DE", "0-999", "mismatch"),  # el XSD es unbounded: 0-999 no es lo mismo que 0-n
        ("dX", "gRep", "1-6", "match"),
        ("dObs", None, "0-1", "not_checked"),  # el XSD lo declara con ocurrencias distintas según el padre
        ("dObs", "gTotSub", "1-1", "match"),
        ("noExiste", None, "0-1", "not_checked"),
        ("dNomRec", "gTotSub", "1-1", "not_checked"),  # padre equivocado
        ("dNomRec", "gDatRec", "-", "not_checked"),
        ("dNomRec", "gDatRec", "", "not_checked"),
    ],
)
def test_check_occurrence(
    mini_index: XsdIndex, name: str, parent: str | None, literal: str, status: str
) -> None:
    result = mini_index.check_occurrence(name, parent, literal)
    assert result.status == status
    assert result.detail  # siempre explica
    st, detail = result  # NamedTuple: también se desempaqueta
    assert (st, detail) == (result.status, result.detail)


def test_check_occurrence_detail_mentions_both_sides(mini_index: XsdIndex) -> None:
    result = mini_index.check_occurrence("dNomRec", "gDatRec", "0-1")
    assert "manual 0-1" in result.detail
    assert "XSD 1-1" in result.detail
    assert "/rMini/DE/gDatGralOpe/gDatRec/dNomRec" in result.detail


# --- Enumeración: documentado (MT/NT) frente a aceptado (XSD), decisión 8 del usuario (2026-10-17) ---------
def test_check_enumeration_pattern_is_enumerated_exhaustively(mini_index: XsdIndex) -> None:
    ok = mini_index.check_enumeration("iTipIDRec", "gDatRec", ["1", "2", "3", "4", "5", "6", "9"])
    assert (ok.status, ok.accepted, ok.exhaustive) == ("match", ("1", "2", "3", "4", "5", "6", "9"), True)
    bad = mini_index.check_enumeration("iTipIDRec", "gDatRec", ["1", "2", "3", "4", "5", "6", "7"])
    assert (bad.status, bad.only_documented, bad.only_accepted) == ("mismatch", ("7",), ("9",))
    assert "aceptados 1, 2, 3, 4, 5, 6, 9" in bad.detail


def test_check_enumeration_uses_xs_enumeration(mini_index: XsdIndex) -> None:
    c = mini_index.check_enumeration("cMoneOpe", "gOpeCom", ["PYG"])
    assert (c.status, c.accepted, c.only_accepted, c.exhaustive) == (
        "mismatch",
        ("PYG", "USD"),
        ("USD",),
        True,
    )


def test_check_enumeration_unbounded_type_only_tests_documented_codes(mini_index: XsdIndex) -> None:
    """`tiTipTra` (1–13 por minInclusive/maxInclusive, sin cota de dígitos): no se enumera; solo se
    prueba cada código documentado y nada cuenta como «solo en el XSD»."""
    c = mini_index.check_enumeration("iTipTra", "gOpeCom", ["1", "13", "14"])
    assert (c.status, c.exhaustive, c.accepted, c.only_documented, c.only_accepted) == (
        "mismatch",
        False,
        ("1", "13"),
        ("14",),
        (),
    )
    assert mini_index.check_enumeration("iTipTra", "gOpeCom", ["1", "13"]).status == "match"


def test_check_enumeration_not_declared(mini_index: XsdIndex) -> None:
    c = mini_index.check_enumeration("iNoExiste", "gDatRec", ["1"])
    assert (c.status, c.accepted) == ("not_checked", None)


def test_real_itide_documented_vs_accepted(real_index: XsdIndex) -> None:
    """C002 (ISS-0013): el MT documenta 1–8; la instantánea acepta 1, 4–7, 9 y 10 (patrón «1|[4-7]|9|10»)."""
    c = real_index.check_enumeration("iTiDE", "gTimb", [str(n) for n in range(1, 9)])
    assert c.accepted == ("1", "4", "5", "6", "7", "9", "10") and c.exhaustive
    assert (c.status, c.only_documented, c.only_accepted) == ("mismatch", ("2", "3", "8"), ("9", "10"))


# --- Validación con rutas -------------------------------------------------------------------------------------
def test_validate_xml_valid(mini_schema: Any) -> None:
    assert validate_xml(mini_schema, MINI / "mini_valido.xml") == []


def test_validate_xml_errors_have_local_paths(mini_schema: Any) -> None:
    errors = validate_xml(mini_schema, MINI / "mini_invalido.xml")
    joined = "\n".join(errors)
    assert any(e.startswith("/rMini/DE/gDatGralOpe/dFeEmiDE: ") for e in errors)
    assert any(e.startswith("/rMini/DE/gDatGralOpe/gOpeCom/cMoneOpe: ") for e in errors)
    assert any(e.startswith("/rMini/DE/gDatGralOpe/gDatRec/iTipIDRec: ") for e in errors)
    assert any(e.startswith("/rMini/DE/gDatGralOpe/gDatRec: ") and "dNomRec" in e for e in errors)
    assert any(e.startswith("/rMini/DE/gTotSub: ") and "dObs" in e for e in errors)
    assert "{" not in joined  # sin espacios de nombres en notación Clark
    assert "ns0:" not in joined


def test_validate_xml_caps_errors(mini_schema: Any) -> None:
    errors = validate_xml(mini_schema, MINI / "mini_invalido.xml", max_errors=2)
    assert len(errors) == 3
    assert "más errores" in errors[-1]


def test_validate_xml_unreadable_is_a_single_error(mini_schema: Any, tmp_path: Path) -> None:
    bad = tmp_path / "roto.xml"
    bad.write_text("<rMini><DE></rMini>", encoding="utf-8")
    errors = validate_xml(mini_schema, bad)
    assert len(errors) == 1
    assert "roto.xml" in errors[0]
    assert len(validate_xml(mini_schema, tmp_path / "noexiste.xml")) == 1


# --- Lectura segura ---------------------------------------------------------------------------------------------
def _expected(
    emision: str,
    f014: str,
    *,
    moneda: str = "PYG",
    f023: str | None = None,
    receptor: str = "innominado",
) -> dict[str, str | None]:
    base: dict[str, str | None] = {
        "D002": f"{emision}T09:30:00",
        "D011": "1",
        "D015": moneda,
        "D201": "2",
        "D202": "2",
        "C002": "1",
        "F014": f014,
        "F023": f023,
    }
    if receptor == "innominado":
        base |= {"D208": "5", "D209": "Innominado", "D210": "0"}
    elif receptor == "cedula":
        base |= {"D208": "1", "D209": "Cédula paraguaya", "D210": "4567890"}
    else:  # sin tipo de documento
        base |= {"D208": None, "D209": None, "D210": None}
    return base


DE_FIXTURES: dict[str, dict[str, str | None]] = {
    "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml": _expected("2025-02-10", "7000000"),
    "de_innominado_pyg_f014_6999999_emision_2025-02-10.xml": _expected("2025-02-10", "6999999"),
    "de_innominado_pyg_f014_8000000_emision_2024-06-10.xml": _expected("2024-06-10", "8000000"),
    "de_innominado_usd_f023_8000000_emision_2025-02-10.xml": _expected(
        "2025-02-10", "1000", moneda="USD", f023="8000000"
    ),
    "de_innominado_usd_f014_7500000_f023_6000000_emision_2025-02-10.xml": _expected(
        "2025-02-10", "7500000", moneda="USD", f023="6000000"
    ),
    "de_receptor_sin_tipo_documento_pyg_f014_10000000_emision_2025-02-10.xml": _expected(
        "2025-02-10", "10000000", receptor="sin_tipo"
    ),
    "de_innominado_pyg_f014_10000000_emision_2024-12-30.xml": _expected("2024-12-30", "10000000"),
    "de_receptor_cedula_pyg_f014_5000000_emision_2025-02-10.xml": _expected(
        "2025-02-10", "5000000", receptor="cedula"
    ),
}
RESPONSES: dict[str, date] = {
    "respuesta_recepcion_dfecproc_2025-01-02.xml": date(2025, 1, 2),
    "respuesta_recepcion_soap_dfecproc_utc_cruza_medianoche.xml": date(2025, 1, 2),
}


def test_every_xml_fixture_is_covered() -> None:
    on_disk = {p.name for p in XML.glob("*.xml")}
    assert on_disk == set(DE_FIXTURES) | set(RESPONSES)


@pytest.mark.parametrize("name", sorted(DE_FIXTURES))
def test_read_values_pilot_fields(name: str) -> None:
    assert read_values(XML / name, PILOT) == DE_FIXTURES[name]


def test_read_values_respects_parent_and_document_order() -> None:
    path = XML / "de_innominado_pyg_f014_7000000_emision_2025-02-10.xml"
    got = read_values(
        path,
        {
            "sin_padre": ("dNumIDRec", None),
            "padre_ok": ("dNumIDRec", "gDatRec"),
            "padre_equivocado": ("dNumIDRec", "gEmis"),
            "no_es_padre_directo": ("dNumIDRec", "gDatGralOpe"),  # abuelo, no padre directo
            "ausente": ("dNoExiste", None),
            "otro_ns_ausente": ("X509Certificate", None),
        },
    )
    assert got == {
        "sin_padre": "0",
        "padre_ok": "0",
        "padre_equivocado": None,
        "no_es_padre_directo": None,
        "ausente": None,
        "otro_ns_ausente": None,
    }


def test_read_values_distinguishes_empty_from_absent(tmp_path: Path) -> None:
    p = tmp_path / "de.xml"
    p.write_text(
        f'<rDE xmlns="{SIFEN_NS}"><DE><gDatGralOpe><gDatRec><dNomRec>  </dNomRec>'
        "<dNumIDRec> 123 </dNumIDRec></gDatRec></gDatGralOpe></DE></rDE>",
        encoding="utf-8",
    )
    got = read_values(
        p, {"nom": ("dNomRec", "gDatRec"), "num": ("dNumIDRec", "gDatRec"), "tel": ("dTelRec", "gDatRec")}
    )
    assert got == {"nom": "", "num": "123", "tel": None}


def test_read_values_only_looks_inside_the_first_de(tmp_path: Path) -> None:
    p = tmp_path / "lote.xml"
    p.write_text(
        f'<rLote xmlns="{SIFEN_NS}"><dNumIDRec>FUERA</dNumIDRec>'
        "<rDE><DE><gDatRec><dNumIDRec>PRIMERO</dNumIDRec></gDatRec></DE></rDE>"
        "<rDE><DE><gDatRec><dNumIDRec>SEGUNDO</dNumIDRec></gDatRec></DE></rDE></rLote>",
        encoding="utf-8",
    )
    assert read_values(p, {"x": ("dNumIDRec", None)}) == {"x": "PRIMERO"}


def test_read_values_ignores_elements_outside_the_sifen_namespace(tmp_path: Path) -> None:
    p = tmp_path / "de.xml"
    p.write_text(
        f'<rDE xmlns="{SIFEN_NS}" xmlns:o="urn:otro"><DE><o:dNumIDRec>AJENO</o:dNumIDRec></DE></rDE>',
        encoding="utf-8",
    )
    assert read_values(p, {"x": ("dNumIDRec", None)}) == {"x": None}


def test_read_values_without_de_is_an_error_not_all_absent() -> None:
    with pytest.raises(XmlReadError, match="DE"):
        read_values(XML / "respuesta_recepcion_dfecproc_2025-01-02.xml", PILOT)


# --- Fechas --------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(DE_FIXTURES))
def test_read_emission_date(name: str) -> None:
    expected = DE_FIXTURES[name]["D002"]
    assert expected is not None
    assert read_emission_date(XML / name) == date.fromisoformat(expected[:10])


def test_read_emission_date_missing(tmp_path: Path) -> None:
    p = tmp_path / "de.xml"
    p.write_text(f'<rDE xmlns="{SIFEN_NS}"><DE><gDatGralOpe/></DE></rDE>', encoding="utf-8")
    assert read_emission_date(p) is None


@pytest.mark.parametrize(("name", "expected"), sorted(RESPONSES.items()))
def test_read_processing_date(name: str, expected: date) -> None:
    assert read_processing_date(XML / name) == expected


def test_read_processing_date_converts_the_offset() -> None:
    # 2025-01-03T01:30:00+00:00 es el 2 de enero a las 22:30 en Asunción: la fecha de Paraguay es el día 2
    soap = (XML / "respuesta_recepcion_soap_dfecproc_utc_cruza_medianoche.xml").read_text(encoding="utf-8")
    assert "2025-01-03T01:30:00+00:00" in soap
    assert read_processing_date(XML / "respuesta_recepcion_soap_dfecproc_utc_cruza_medianoche.xml") == date(
        2025, 1, 2
    )


def test_read_processing_date_absent_and_malformed(tmp_path: Path) -> None:
    sin = tmp_path / "sin.xml"
    sin.write_text(
        f'<rRetEnviDe xmlns="{SIFEN_NS}"><rProtDe><dEstRes>Aprobado</dEstRes></rProtDe></rRetEnviDe>'
    )
    assert read_processing_date(sin) is None
    # dFecProc fuera de rProtDe (p. ej. la consulta de DE) no es la fecha de procesamiento del DE
    otro = tmp_path / "otro.xml"
    otro.write_text(f'<r xmlns="{SIFEN_NS}"><dFecProc>2025-01-02T10:00:00-03:00</dFecProc></r>')
    assert read_processing_date(otro) is None
    mal = tmp_path / "mal.xml"
    mal.write_text(f'<r xmlns="{SIFEN_NS}"><rProtDe><dFecProc>02/01/2025</dFecProc></rProtDe></r>')
    with pytest.raises(XmlReadError, match="fecha no interpretable"):
        read_processing_date(mal)
    vacio = tmp_path / "vacio.xml"
    vacio.write_text(f'<r xmlns="{SIFEN_NS}"><rProtDe><dFecProc/></rProtDe></r>')
    with pytest.raises(XmlReadError, match="vacío"):
        read_processing_date(vacio)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-02-10", date(2025, 2, 10)),
        ("2025-02-10T09:30:00", date(2025, 2, 10)),  # sin zona: la parte de fecha tal cual (dFeEmiDE)
        ("2025-02-10T23:59:59", date(2025, 2, 10)),
        ("2025-01-02T10:15:30-03:00", date(2025, 1, 2)),
        ("2025-01-03T01:30:00+00:00", date(2025, 1, 2)),  # UTC -> Asunción (-03:00 en enero)
        ("2025-01-02T02:00:00Z", date(2025, 1, 1)),
        ("2025-01-02T23:30:00-04:00", date(2025, 1, 3)),  # -04:00 -> 00:30 del día siguiente en Asunción
        ("2025-01-02T10:15:30.250-03:00", date(2025, 1, 2)),
        (" 2025-01-02T10:15:30-03:00 ", date(2025, 1, 2)),
    ],
)
def test_to_paraguay_date(value: str, expected: date) -> None:
    assert to_paraguay_date(value) == expected


def test_to_paraguay_date_uses_asuncion_winter_time_when_tzdata_is_available() -> None:
    # En invierno de 2024 Asunción estaba en UTC-4: 00:30-03:00 del 10 de junio es el 9 a las 23:30 allí.
    got = to_paraguay_date("2024-06-10T00:30:00-03:00")
    if paraguay_tz_is_exact():
        assert got == date(2024, 6, 9)
    else:  # sin tzdata cae a UTC-03:00 fijo (documentado en el docstring del módulo)
        assert got == date(2024, 6, 10)


@pytest.mark.parametrize(
    "value", ["", "10/02/2025", "2025-13-01", "2025-02-30", "2025-02-30T09:00:00", "ayer", "20250210"]
)
def test_to_paraguay_date_rejects_garbage(value: str) -> None:
    with pytest.raises(XmlReadError):
        to_paraguay_date(value)


def test_anachronistic_marks_queries_before_the_snapshot() -> None:
    retrieved = datetime(2026, 10, 17, 19, 4, 34, tzinfo=UTC)
    assert anachronistic(date(2024, 6, 10), retrieved)
    assert anachronistic(date(2026, 10, 16), retrieved)
    assert not anachronistic(date(2026, 10, 17), retrieved)  # desde ese día el XSD es evidencia
    assert not anachronistic(date(2027, 1, 1), retrieved)


# --- Seguridad ----------------------------------------------------------------------------------------------------
def test_xml_untouched() -> None:
    files = sorted(XML.glob("*.xml")) + [MINI / "mini_valido.xml", MINI / "mini_invalido.xml"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    mtimes = {p: p.stat().st_mtime_ns for p in files}
    schema = load_schema(MINI, entries=("mini_root.xsd",))
    for p in files:
        validate_xml(schema, p)
        try:
            read_values(p, PILOT)
            read_emission_date(p)
        except XmlReadError:
            pass
        read_processing_date(p)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert after == before
    assert {p: p.stat().st_mtime_ns for p in files} == mtimes


XXE = (
    '<?xml version="1.0"?>\n<!DOCTYPE rDE [<!ENTITY x SYSTEM "file:///etc/hostname">]>\n'
    f'<rDE xmlns="{SIFEN_NS}"><DE><dNomRec>&x;</dNomRec></DE></rDE>'
)
LAUGHS = (
    '<?xml version="1.0"?>\n<!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>\n'
    f'<rDE xmlns="{SIFEN_NS}"><DE><dNomRec>&b;</dNomRec></DE></rDE>'
)


@pytest.mark.parametrize("text", [XXE, LAUGHS], ids=["entidad_externa", "expansion_de_entidades"])
def test_dtd_and_entities_are_refused(tmp_path: Path, mini_schema: Any, text: str, no_network: None) -> None:
    p = tmp_path / "malo.xml"
    p.write_text(text, encoding="utf-8")
    with pytest.raises(XmlReadError, match="malo.xml"):
        read_values(p, {"x": ("dNomRec", None)})
    with pytest.raises(XmlReadError):
        read_emission_date(p)
    with pytest.raises(XmlReadError):
        read_processing_date(p)
    assert len(validate_xml(mini_schema, p)) == 1


def test_not_well_formed_missing_and_oversized_xml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mal = tmp_path / "mal.xml"
    mal.write_text("<rDE><DE></rDE>", encoding="utf-8")
    with pytest.raises(XmlReadError):
        read_values(mal, {})
    with pytest.raises(XmlReadError, match="noexiste.xml"):
        read_values(tmp_path / "noexiste.xml", {})
    with pytest.raises(XmlReadError, match="no es un archivo"):
        read_values(tmp_path, {})
    grande = tmp_path / "grande.xml"
    grande.write_text(f'<rDE xmlns="{SIFEN_NS}"><DE/></rDE>', encoding="utf-8")
    monkeypatch.setattr(xsd, "MAX_XML_BYTES", 10)
    with pytest.raises(XmlReadError, match="excede"):
        read_values(grande, {})


def test_xsi_schema_location_in_the_xml_is_not_followed(
    tmp_path: Path, mini_schema: Any, no_network: None
) -> None:
    p = tmp_path / "hint.xml"
    p.write_text(
        f'<rMini xmlns="{SIFEN_NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xsi:schemaLocation="{SIFEN_NS} https://evil.example/x.xsd"><dVerFor>150</dVerFor></rMini>',
        encoding="utf-8",
    )
    assert validate_xml(mini_schema, p)  # incompleto frente al esquema local, y sin tocar la red


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("4567890", "****890"),
        ("1234", "****4"),
        ("123", "****3"),
        ("12", "****"),
        ("A", "****"),
        ("", ""),
        ("RECEPTOR DE PRUEBA", "****EBA"),
    ],
)
def test_mask(value: str, expected: str) -> None:
    assert mask(value) == expected


def test_mask_reveals_less_than_half_and_does_not_leak_length() -> None:
    for n in range(1, 40):
        value = "".join(chr(ord("A") + i % 26) for i in range(n))
        masked = mask(value)
        visible = masked.removeprefix("****")
        assert masked.startswith("****")
        assert len(visible) <= 3
        assert len(visible) * 2 < n  # menos de la mitad
        assert value.endswith(visible)
    assert mask("4567890", keep=0) == "****"
    assert mask("x" * 30, keep=5) == "****xxxxx"


def test_pii_elements_cover_the_spec_list() -> None:
    required = {
        "dRucEm", "dRucRec", "dNumIDRec", "dNomEmi", "dNomRec", "dDirEmi", "dDirRec",
        "dTelRec", "dEmailRec", "dCarQR", "X509Certificate", "dCodSeg",
    }  # fmt: skip
    assert required <= PII_ELEMENTS
    assert all(re.fullmatch(r"[A-Za-z0-9]+", n) for n in PII_ELEMENTS)


def test_pii_values_in_fixtures_are_masked_by_name() -> None:
    values = read_values(
        XML / "de_receptor_cedula_pyg_f014_5000000_emision_2025-02-10.xml",
        {
            "dNumIDRec": ("dNumIDRec", "gDatRec"),
            "dNomRec": ("dNomRec", "gDatRec"),
            "dRucEm": ("dRucEm", "gEmis"),
        },
    )
    assert values == {"dNumIDRec": "4567890", "dNomRec": "RECEPTOR DE PRUEBA", "dRucEm": "80000000"}
    shown = {k: mask(v) if k in PII_ELEMENTS and v else v for k, v in values.items()}
    assert shown["dNumIDRec"] == "****890"
    assert "4567890" not in " ".join(str(v) for v in shown.values())


# --- Manifiesto -----------------------------------------------------------------------------------------------------
def _manifest(*revisions: tuple[str, str, str]) -> str:
    """`(sha256, retrieved_at, path)` por revisión de XSD_DIR."""
    out = ["revisions:"]
    for sha, at, path in revisions:
        out += [
            "  - doc: XSD_DIR",
            f"    sha256: {sha}",
            f"    md5: {'0' * 32}",
            "    size: 10",
            "    url: https://ekuatia.set.gov.py/sifen/xsd/",
            "    filename: SHA256SUMS",
            f"    retrieved_at: {at}",
            "    origin: portal",
            f"    path: {path}",
        ]
    return "\n".join(out) + "\n"


def test_snapshot_from_manifest_picks_the_latest_revision(tmp_path: Path) -> None:
    for d in ("2026-01-05", "2026-02-01"):
        (tmp_path / "sources" / "XSD_DIR" / d).mkdir(parents=True)
    old, new = "a" * 64, "b" * 64
    (tmp_path / "sources.manifest.yaml").write_text(
        _manifest(
            (old, "2026-01-05T12:00:00Z", "sources/XSD_DIR/2026-01-05"),
            (new, "2026-02-01T08:30:00Z", "sources/XSD_DIR/2026-02-01"),
        ),
        encoding="utf-8",
    )
    snap = snapshot_from_manifest(tmp_path)
    assert snap is not None
    folder, sha12, retrieved_at = snap
    assert folder == (tmp_path / "sources" / "XSD_DIR" / "2026-02-01").resolve()
    assert sha12 == "b" * 12
    assert retrieved_at == datetime(2026, 2, 1, 8, 30, tzinfo=UTC)


def test_snapshot_from_manifest_none_cases(tmp_path: Path) -> None:
    assert snapshot_from_manifest(tmp_path) is None  # sin manifiesto
    (tmp_path / "sources.manifest.yaml").write_text("revisions: []\n", encoding="utf-8")
    assert snapshot_from_manifest(tmp_path) is None  # sin revisión de XSD_DIR
    (tmp_path / "sources.manifest.yaml").write_text(
        _manifest(("c" * 64, "2026-01-05T12:00:00Z", "sources/XSD_DIR/2026-01-05")), encoding="utf-8"
    )
    assert snapshot_from_manifest(tmp_path) is None  # la carpeta no existe


def test_snapshot_from_manifest_rejects_escaping_paths_and_bad_manifests(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    kb.mkdir()
    (tmp_path / "fuera").mkdir()
    (kb / "sources.manifest.yaml").write_text(
        _manifest(("d" * 64, "2026-01-05T12:00:00Z", "../fuera")), encoding="utf-8"
    )
    with pytest.raises(XsdError, match="sale del repositorio"):
        snapshot_from_manifest(kb)
    (kb / "sources.manifest.yaml").write_text("revisions: [no es un mapa]\n", encoding="utf-8")
    with pytest.raises(XsdError, match="manifiesto"):
        snapshot_from_manifest(kb)


# --- Integración con la instantánea oficial (sources/XSD_DIR) ----------------------------------------------------------
@pytest.fixture(scope="module")
def real_snapshot() -> tuple[Path, str, datetime]:
    snap = snapshot_from_manifest(REPO)
    if snap is None or not (snap[0] / "DE_v150.xsd").is_file():
        pytest.skip("no hay instantánea XSD_DIR registrada en sources.manifest.yaml")
    return snap


@pytest.fixture(scope="module")
def real_schema(real_snapshot: tuple[Path, str, datetime]) -> Any:
    return load_schema(real_snapshot[0])


@pytest.fixture(scope="module")
def real_index(real_schema: Any) -> XsdIndex:
    return XsdIndex(real_schema)


def test_real_snapshot_identity_matches_its_sha256sums(real_snapshot: tuple[Path, str, datetime]) -> None:
    folder, sha12, retrieved_at = real_snapshot
    assert hashlib.sha256((folder / "SHA256SUMS").read_bytes()).hexdigest()[:12] == sha12
    assert retrieved_at.tzinfo is not None


def test_real_schema_loads_offline(real_snapshot: tuple[Path, str, datetime], no_network: None) -> None:
    schema = load_schema(real_snapshot[0])
    assert {"rDE", "rEnviDe", "rRetEnviDe"} <= set(schema.elements)
    # tipos que solo llegan por los xs:include de URL HTTPS absoluta
    assert f"{{{SIFEN_NS}}}fecUTC" in schema.maps.types
    assert f"{{{SIFEN_NS}}}tiTipDocRec" in schema.maps.types


def test_real_pilot_paths(real_index: XsdIndex) -> None:
    """Rutas reales del XML de cada campo del piloto (padre directo y ocurrencia)."""
    base = "/rDE/DE/gDatGralOpe"
    expected = {
        "D002": (f"{base}/dFeEmiDE", "1-1"),
        "D011": (f"{base}/gOpeCom/iTipTra", "0-1"),
        "D015": (f"{base}/gOpeCom/cMoneOpe", "1-1"),
        "D201": (f"{base}/gDatRec/iNatRec", "1-1"),
        "D202": (f"{base}/gDatRec/iTiOpe", "1-1"),
        "D208": (f"{base}/gDatRec/iTipIDRec", "0-1"),
        "D209": (f"{base}/gDatRec/dDTipIDRec", "0-1"),
        "D210": (f"{base}/gDatRec/dNumIDRec", "0-1"),
        "C002": ("/rDE/DE/gTimb/iTiDE", "1-1"),
        "F014": ("/rDE/DE/gTotSub/dTotGralOpe", "1-1"),
        "F023": ("/rDE/DE/gTotSub/dTotalGs", "0-1"),
    }
    assert set(expected) == set(PILOT)
    for field_id, (xml_name, parent) in PILOT.items():
        (decl,) = real_index.lookup(xml_name, parent)
        assert (decl.xpath, decl.occurrence) == expected[field_id], field_id
        assert decl.namespace == SIFEN_NS
        assert decl.parent == parent
        # el nombre es único en todo el esquema: no hace falta el padre para localizarlo
        assert len(real_index.lookup(xml_name)) == 1, field_id


def test_real_itipidrec_under_gdatrec_and_totals_exist(real_index: XsdIndex) -> None:
    (rec,) = real_index.lookup("iTipIDRec", parent="gDatRec")
    assert rec.facets.patterns == ("[1-6]|9",)  # el XSD solo trae un patrón, no el significado (D.5)
    assert real_index.lookup("dTotGralOpe", parent="gTotSub")
    assert real_index.lookup("dTotalGs", parent="gTotSub")


def test_real_dfecproc_is_declared_in_rprotde_as_fecutc(real_index: XsdIndex) -> None:
    (decl,) = real_index.lookup("dFecProc", parent="rProtDe")
    assert decl.xpath == "/rRetEnviDe/rProtDe/dFecProc"
    assert decl.occurrence == "1-1"  # obligatorio (G.4)
    assert decl.type_name == "fecUTC"
    (pattern,) = decl.facets.patterns
    # fecUTC exige el desplazamiento: AAAA-MM-DDThh:mm:ss±hh:mm, sin fracciones y sin "Z"
    assert re.fullmatch(pattern, "2025-01-02T10:15:30-03:00")
    assert re.fullmatch(pattern, "2025-01-03T01:30:00+00:00")
    assert not re.fullmatch(pattern, "2025-01-02T10:15:30")
    assert not re.fullmatch(pattern, "2025-01-02T10:15:30Z")
    assert not re.fullmatch(pattern, "2025-01-02T10:15:30.5-03:00")
    # dFeEmiDE, en cambio, no lleva zona
    (emi,) = real_index.lookup("dFeEmiDE", parent="gDatGralOpe")
    assert emi.type_name == "fecHhmmss"
    assert not re.fullmatch(emi.facets.patterns[0], "2025-02-10T09:30:00-03:00")


def test_real_occurrence_vs_manual_gobl_afe(real_index: XsdIndex) -> None:
    """El caso del diseño (§D.5): gOblAfe es 0-12 en el XSD y el manual dice 0-11."""
    assert real_index.check_occurrence("gOblAfe", "gOpeCom", "0-12").status == "match"
    result = real_index.check_occurrence("gOblAfe", "gOpeCom", "0-11")
    assert result.status == "mismatch"
    assert "XSD 0-12" in result.detail


def test_xsd_anachronism_flag(real_snapshot: tuple[Path, str, datetime]) -> None:
    _, _, retrieved_at = real_snapshot
    assert anachronistic(date(2024, 6, 10), retrieved_at)  # D208=6 "pasa el esquema" solo de forma anacrónica
    assert not anachronistic(retrieved_at.date(), retrieved_at)


def test_real_pii_elements_exist_in_xsd(real_index: XsdIndex) -> None:
    missing = sorted(n for n in PII_ELEMENTS if n not in real_index)
    assert missing == []
    # X509Certificate es del espacio de firma, no del de SIFEN
    assert real_index.lookup("X509Certificate")[0].namespace == "http://www.w3.org/2000/09/xmldsig#"
    assert real_index.lookup("dCarQR")[0].parent == "gCamFuFD"


@pytest.mark.parametrize("name", sorted(DE_FIXTURES))
def test_real_fixture_values_are_valid_for_their_xsd_types(
    real_schema: Any, real_index: XsdIndex, name: str
) -> None:
    """Cada valor de los DE sintéticos es válido para el tipo de su elemento (y el elemento existe donde dice)."""
    ns = {"s": SIFEN_NS}
    checked = 0
    for field_id, value in read_values(XML / name, PILOT).items():
        if value is None:
            continue
        xml_name, parent = PILOT[field_id]
        (decl,) = real_index.lookup(xml_name, parent)
        element = real_schema.find("/".join(f"s:{p}" for p in decl.xpath.strip("/").split("/")), ns)
        assert element is not None, decl.xpath
        assert element.type.is_valid(value), f"{field_id}={value!r} no es válido para {decl.type_name}"
        checked += 1
    assert checked >= 7


@pytest.mark.parametrize("name", sorted(DE_FIXTURES))
def test_real_de_fixtures_fail_only_for_structure(real_schema: Any, name: str) -> None:
    """Los DE sintéticos son mínimos (sin firma ni QR): fallan por estructura, no se presentan como válidos."""
    errors = validate_xml(real_schema, XML / name)
    assert errors
    assert any(e.startswith("/rDE: ") and "Signature" in e for e in errors)  # falta la firma
    assert all(re.search(r"is not complete|Unexpected child", e) for e in errors)


@pytest.mark.parametrize("name", sorted(RESPONSES))
def test_real_response_fixtures(real_schema: Any, name: str) -> None:
    errors = validate_xml(real_schema, XML / name)
    if name == "respuesta_recepcion_dfecproc_2025-01-02.xml":
        assert errors == []  # una respuesta directa es válida frente a rRetEnviDe
    else:  # el sobre SOAP no forma parte del XSD
        assert len(errors) == 1
        assert "Envelope" in errors[0]


def test_real_fecutc_requires_an_offset(real_schema: Any, tmp_path: Path) -> None:
    original = (XML / "respuesta_recepcion_dfecproc_2025-01-02.xml").read_text(encoding="utf-8")
    for variante in ("2025-01-02T10:15:30", "2025-01-02T10:15:30Z", "2025-01-02"):
        p = tmp_path / "r.xml"
        p.write_text(original.replace("2025-01-02T10:15:30-03:00", variante), encoding="utf-8")
        errors = validate_xml(real_schema, p)
        assert any("dFecProc" in e for e in errors), variante


def test_real_snapshot_from_manifest_is_the_latest_registered(
    real_snapshot: tuple[Path, str, datetime],
) -> None:
    folder, _, _ = real_snapshot
    assert folder.parent.name == "XSD_DIR"
    assert (folder / "protProcesDE_v150.xsd").is_file()

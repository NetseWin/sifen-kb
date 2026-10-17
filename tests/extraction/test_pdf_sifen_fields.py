# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_sifen_fields.py), integrado en sifen-kb bajo MIT.
"""Capa 3 — `campos.json`: un registro por fila de las tablas de formato de campos del MT V150.

Unitarios con Documents sintéticos (estado y anomalías) y verificación sobre el PDF real.
"""

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Cell, Change, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.pipeline import load
from sifen_kb.pdf.sifen.fields import (
    ENCABEZADO,
    TIPOS_DATO,
    FieldRecord,
    check_fields,
    field_anomalies,
    field_records,
    to_json,
)
from sifen_kb.pdf.tagged import extract_tagged

MANUAL = corpus_pdf.MANUAL

# Fila de ejemplo con las 9 columnas, en el orden del encabezado.
FILA = ["A", "A003", "dFeFirma", "Fecha y hora de la firma", "A001", "F", "19", "1-1", "Formato"]


def celda(*runs: Run, header: bool = False) -> Cell:
    return Cell(list(runs), header=header)


def fila(valores: list[str], change: Change | None = None) -> Row:
    return Row([celda(Run(v, change)) for v in valores])


def encabezado(titulos: list[str] | None = None) -> Row:
    return Row([celda(Run(t), header=True) for t in (titulos or list(ENCABEZADO))])


def documento(*tablas: Table) -> Document:
    return Document(source="MT.pdf", sha256="abc123", extractor="test", blocks=list(tablas))


def tabla_campos(*filas: Row, page: int = 62, titulos: list[str] | None = None) -> Table:
    return Table(page=page, rows=[encabezado(titulos), *filas])


def solo(doc: Document) -> FieldRecord:
    registros = field_records(doc)
    assert len(registros) == 1, registros
    return registros[0]


# --- Registros ------------------------------------------------------------------------------


def test_cada_fila_de_cuerpo_da_un_registro_con_su_procedencia() -> None:
    registro = solo(documento(tabla_campos(fila(FILA), page=62)))

    assert (registro.grupo, registro.id, registro.campo) == ("A", "A003", "dFeFirma")
    assert registro.descripcion == "Fecha y hora de la firma"
    assert (registro.nodo_padre, registro.tipo_dato) == ("A001", "F")
    assert (registro.longitud, registro.ocurrencia) == ("19", "1-1")
    assert registro.observaciones == "Formato"
    assert (registro.source, registro.sha256) == ("MT.pdf", "abc123")


def test_la_pagina_impresa_es_la_del_pdf_menos_uno() -> None:
    registro = solo(documento(tabla_campos(fila(FILA), page=62)))

    assert (registro.pdf_page, registro.printed_page) == (62, 61)


def test_una_fila_partida_usa_la_pagina_de_la_fila_no_la_de_la_tabla() -> None:
    # Una tabla unida entre páginas lleva la página en cada fila (T-104).
    tabla = tabla_campos(fila(FILA), page=62)
    tabla.rows[1].page = 63

    assert solo(documento(tabla)).pdf_page == 63


def test_las_observaciones_conservan_los_saltos_de_parrafo() -> None:
    valores = [*FILA[:8], "1= Normal\n2= Contingencia"]

    registro = solo(documento(tabla_campos(fila(valores))))
    assert registro.observaciones == "1= Normal\n2= Contingencia"


def test_solo_las_tablas_con_el_encabezado_de_campos_dan_registros() -> None:
    cabeza = Row([celda(Run("Guaraníes"), header=True)])
    otra = Table(page=70, rows=[cabeza, Row([celda(Run("1"))])])
    doc = documento(tabla_campos(fila(FILA)), otra)

    assert [r.id for r in field_records(doc)] == ["A003"]


def test_el_encabezado_se_reconoce_aunque_el_pdf_parta_una_palabra() -> None:
    # 4 tablas de campos del MT traen 'Longit ud': el hueco lo inserta la extracción, no el autor.
    partido = [*ENCABEZADO[:6], "Longit ud", *ENCABEZADO[7:]]

    assert [r.id for r in field_records(documento(tabla_campos(fila(FILA), titulos=partido)))] == ["A003"]


@pytest.mark.parametrize(
    ("longitud", "ocurrencia"), [("Longitud", "Ocu"), ("Longitud", "Ocu."), ("Long.", "Ocu.")]
)
def test_el_encabezado_se_reconoce_con_las_abreviaturas_del_autor(longitud: str, ocurrencia: str) -> None:
    # D-015: las tablas de eventos del MT (págs. PDF 121-123) y las NT abrevian los títulos.
    abreviado = [*ENCABEZADO[:6], longitud, ocurrencia, ENCABEZADO[8]]

    doc = documento(tabla_campos(fila(FILA), titulos=abreviado))

    assert [r.id for r in field_records(doc)] == ["A003"]


def test_una_tabla_sin_columna_grupo_no_es_de_campos() -> None:
    # Los esquemas de WS (ID, Campo, …, Ocu, Observaciones) tienen 8 columnas: no son campos del DE.
    esquema = list(ENCABEZADO[1:7]) + ["Ocu", "Observaciones"]
    tabla = Table(page=46, rows=[encabezado(esquema), fila(FILA[1:])])

    assert field_records(documento(tabla)) == []


def test_los_bloques_que_no_son_tablas_se_ignoran() -> None:
    texto = TextBlock(page=62, role="P", runs=[Run("A. Campos firmados")])
    doc = documento(tabla_campos(fila(FILA)))
    doc.blocks.append(texto)

    assert len(field_records(doc)) == 1


# --- Estado de la fila ----------------------------------------------------------------------


def test_fila_entera_en_rojo_es_eliminado() -> None:
    registro = solo(documento(tabla_campos(fila(FILA, Change.DELETED))))

    assert registro.estado == "eliminado"
    assert [c.columna for c in registro.cambios] == list(FieldRecord.COLUMNAS)
    assert {c.change for c in registro.cambios} == {"deleted"}


def test_fila_entera_en_verde_es_agregado() -> None:
    registro = solo(documento(tabla_campos(fila(FILA, Change.ADDED))))

    assert registro.estado == "agregado"
    assert {c.change for c in registro.cambios} == {"added"}


def test_fila_sin_resaltado_no_tiene_estado_ni_cambios() -> None:
    registro = solo(documento(tabla_campos(fila(FILA))))

    assert registro.estado is None
    assert registro.cambios == ()


def test_un_resaltado_parcial_hace_modificado_y_detalla_solo_ese_tramo() -> None:
    observaciones = celda(Run("Texto previo. "), Run("Oración agregada.", Change.ADDED))
    row = Row([*fila(FILA).cells[:8], observaciones])
    registro = solo(documento(tabla_campos(row)))

    assert registro.estado == "modificado"
    assert [(c.columna, c.change, c.texto) for c in registro.cambios] == [
        ("observaciones", "added", "Oración agregada.")
    ]


def test_fila_entera_en_amarillo_es_modificado() -> None:
    assert solo(documento(tabla_campos(fila(FILA, Change.MODIFIED)))).estado == "modificado"


def test_los_espacios_no_deciden_el_estado() -> None:
    # El tramo de espacios sin marca entre dos rojos no convierte la fila en 'modificado'.
    campo = celda(Run("dFe", Change.DELETED), Run(" "), Run("FinT", Change.DELETED))
    row = Row([*fila(FILA, Change.DELETED).cells[:2], campo, *fila(FILA, Change.DELETED).cells[3:]])

    assert solo(documento(tabla_campos(row))).estado == "eliminado"


# --- Anomalías ------------------------------------------------------------------------------


def test_una_fila_sin_nueve_celdas_va_a_anomalias_y_no_a_registros() -> None:
    corta = Row([celda(Run(v)) for v in FILA[:8]])
    doc = documento(tabla_campos(corta, fila(FILA), page=64))

    assert [r.id for r in field_records(doc)] == ["A003"]
    anomalias = field_anomalies(doc)
    assert len(anomalias) == 1
    assert (anomalias[0].celdas, anomalias[0].pdf_page, anomalias[0].printed_page) == (8, 64, 63)
    assert anomalias[0].textos == tuple(FILA[:8])


def test_sin_filas_raras_no_hay_anomalias() -> None:
    assert field_anomalies(documento(tabla_campos(fila(FILA)))) == []


# --- V4: esquema de campos ------------------------------------------------------------------


def registros(*filas: list[str]) -> list[FieldRecord]:
    return field_records(documento(tabla_campos(*(fila(f) for f in filas))))


def incidencias(*filas: list[str]) -> list[tuple[str, str]]:
    return [(i.check, i.id) for i in check_fields(registros(*filas))]


def test_los_prefijos_de_dos_letras_son_ids_validos() -> None:
    # Medido en las páginas 62-112: 18 filas usan 'AA' o 'EA'; el patrón admite 1 o 2 letras.
    assert incidencias(["AA", "AA001", "dVerFor", "Versión", "Raíz", "N", "3", "1-1", ""]) == []
    padre = ["E", "E001", "gTimb", "Grupo del timbrado", "Raíz", "G", "", "1-1", ""]
    hijo = ["E8", "EA790", "dDenSuc", "Sucursal", "E001", "A", "1-30", "0-1", ""]

    assert incidencias(padre, hijo) == []


def test_un_id_fuera_de_formato_se_reporta() -> None:
    mal = ["A", "X1", "dRaro", "Desc", "Raíz", "A", "1", "1-1", ""]

    assert incidencias(mal) == [("id-formato", "X1")]


def test_una_ocurrencia_vacia_se_reporta_aparte_de_una_malformada() -> None:
    vacia = ["A", "A002", "Id", "Identificador", "Raíz", "A", "44", "", ""]
    mala = ["A", "A003", "dFeFirma", "Fecha", "Raíz", "F", "19", "uno", ""]

    assert incidencias(vacia, mala) == [
        ("ocurrencia-vacia", "A002"),
        ("ocurrencia-formato", "A003"),
    ]


def test_un_tipo_de_dato_fuera_del_conjunto_observado_se_reporta() -> None:
    raro = ["A", "A003", "dFeFirma", "Fecha", "Raíz", "Z", "19", "1-1", ""]

    assert incidencias(raro) == [("tipo-dato-desconocido", "A003")]
    assert TIPOS_DATO == frozenset({"A", "F", "G", "N"})


def test_la_raiz_es_un_nodo_padre_valido() -> None:
    raiz = ["AA", "AA001", "dVerFor", "Versión", "Raíz", "N", "3", "1-1", ""]

    assert incidencias(raiz) == []


def test_un_nodo_padre_que_no_es_ningun_id_se_reporta() -> None:
    huerfano = ["A", "A003", "dFeFirma", "Fecha", "Z999", "F", "19", "1-1", ""]

    assert incidencias(huerfano) == [("nodo-padre-ausente", "A003")]


def test_un_id_repetido_en_dos_filas_vigentes_se_reporta_como_duplicado() -> None:
    doble = ["A", "A003", "dFeFirma", "Fecha", "Raíz", "F", "19", "1-1", ""]

    assert incidencias(doble, doble) == [("id-duplicado", "A003")]


def test_una_fila_eliminada_y_otra_vigente_con_el_mismo_id_se_distinguen() -> None:
    valores = ["A", "A003", "dFeFirma", "Fecha", "Raíz", "F", "19", "1-1", ""]
    doc = documento(tabla_campos(fila(valores, Change.DELETED), fila(valores, Change.ADDED)))

    issues = check_fields(field_records(doc))
    assert [(i.check, i.id) for i in issues] == [("id-duplicado-reemplazo", "A003")]
    assert "eliminado" in issues[0].detalle and "agregado" in issues[0].detalle


def test_un_id_eliminado_no_sirve_como_nodo_padre_de_una_fila_vigente() -> None:
    borrado = ["C", "C009", "dFeFinT", "Fecha fin", "Raíz", "F", "10", "1-1", ""]
    hijo = ["C", "C010", "dSerieNum", "Serie", "C009", "A", "2", "0-1", ""]
    doc = documento(tabla_campos(fila(borrado, Change.DELETED), fila(hijo)))

    assert [(i.check, i.id) for i in check_fields(field_records(doc))] == [("nodo-padre-eliminado", "C010")]


def test_v4_no_corrige_nada_solo_reporta() -> None:
    # D-005: la incidencia nombra el valor tal como vino del PDF.
    mal = ["A", "a003", "dFeFirma", "Fecha", "Raíz", "F", "19", "1-1", ""]
    registro = registros(mal)[0]

    assert registro.id == "a003"
    assert "a003" in check_fields([registro])[0].detalle


# --- Serialización --------------------------------------------------------------------------


def test_el_json_es_determinista_y_lleva_registros_incidencias_y_anomalias() -> None:
    doc = documento(tabla_campos(fila(FILA), page=62))

    primero = to_json(doc, pages=range(62, 67))
    assert primero == to_json(doc, pages=range(62, 67))
    assert '"campos"' in primero and '"incidencias"' in primero and '"anomalias"' in primero
    assert "Ocurrencia" not in primero  # claves en snake_case, no el encabezado del PDF
    assert "\\u" not in primero  # ensure_ascii=False
    assert primero.startswith("{\n ")  # indent=1


def test_to_dict_expone_los_cambios_como_texto_plano() -> None:
    observaciones = celda(Run("Previo. "), Run("Nuevo.", Change.MODIFIED))
    row = Row([*fila(FILA).cells[:8], observaciones])
    datos = solo(documento(tabla_campos(row))).to_dict()

    assert datos["estado"] == "modificado"
    assert datos["cambios"] == [{"columna": "observaciones", "change": "modified", "texto": "Nuevo."}]


# --- Sobre el PDF real ----------------------------------------------------------------------


real = pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")


@pytest.fixture(scope="module")
def piloto() -> list[FieldRecord]:
    return field_records(extract_tagged(MANUAL, pages=range(62, 67)))


def uno(registros: list[FieldRecord], field_id: str) -> FieldRecord:
    encontrados = [r for r in registros if r.id == field_id]
    assert len(encontrados) == 1, f"{field_id}: {encontrados}"
    return encontrados[0]


@real
def test_real_c009_esta_eliminado(piloto: list[FieldRecord]) -> None:
    c009 = uno(piloto, "C009")

    assert c009.estado == "eliminado"
    assert (c009.campo, c009.nodo_padre, c009.ocurrencia) == ("dFeFinT", "C001", "1-1")
    assert [c.columna for c in c009.cambios] == list(FieldRecord.COLUMNAS)


@real
def test_real_a005_esta_agregado(piloto: list[FieldRecord]) -> None:
    a005 = uno(piloto, "A005")

    assert a005.estado == "agregado"
    assert a005.campo == "dSisFact"
    assert {c.change for c in a005.cambios} == {"added"}


@real
def test_real_b006_esta_modificado_solo_en_observaciones(piloto: list[FieldRecord]) -> None:
    b006 = uno(piloto, "B006")

    assert b006.estado == "modificado"
    assert [(c.columna, c.change) for c in b006.cambios] == [("observaciones", "added")]
    assert b006.cambios[0].texto.startswith("Cuando el tipo de documento es Nota de remisión")
    assert b006.observaciones.startswith("Esta información debe ser impresa en el")


@real
def test_real_a004_tiene_las_observaciones_cambiadas(piloto: list[FieldRecord]) -> None:
    a004 = uno(piloto, "A004")

    assert a004.estado == "modificado"
    assert [(c.columna, c.change) for c in a004.cambios] == [("observaciones", "modified")]
    assert a004.cambios[0].texto == a004.observaciones


@real
def test_real_aa002_no_tiene_cambios(piloto: list[FieldRecord]) -> None:
    aa002 = uno(piloto, "AA002")

    assert aa002.estado is None
    assert aa002.cambios == ()
    assert (aa002.grupo, aa002.nodo_padre, aa002.tipo_dato) == ("AA", "AA001", "N")


@real
def test_real_la_pagina_impresa_va_uno_atras_de_la_del_pdf(piloto: list[FieldRecord]) -> None:
    assert piloto
    assert all(r.printed_page == r.pdf_page - 1 for r in piloto)
    assert {r.pdf_page for r in piloto} <= set(range(62, 67))
    assert uno(piloto, "C009").printed_page == 64  # página impresa 64, PDF 65


@real
def test_real_el_piloto_no_deja_filas_sin_nueve_celdas() -> None:
    doc = extract_tagged(MANUAL, pages=range(62, 67))

    assert field_anomalies(doc) == []


@real
def test_real_a002_viene_sin_ocurrencia_y_v4_lo_reporta(piloto: list[FieldRecord]) -> None:
    assert uno(piloto, "A002").ocurrencia == ""
    vacias = [i for i in check_fields(piloto) if i.check == "ocurrencia-vacia"]

    assert [(i.id, i.pdf_page) for i in vacias] == [("A002", 62)]


@real
def test_real_los_ids_del_piloto_cumplen_el_formato(piloto: list[FieldRecord]) -> None:
    assert [i for i in check_fields(piloto) if i.check == "id-formato"] == []


@real
def test_real_las_tablas_de_eventos_con_ocu_dan_registros() -> None:
    # D-015: antes de aceptar 'Ocu' estas 20 filas quedaban fuera de campos.json. Con `load`, como
    # la CLI: la tabla de la 122 sigue desde la 121 sin repetir el encabezado (T-104).
    registros = field_records(load(MANUAL, pages=range(121, 124), sifen=True))
    por_pagina: dict[int, list[str]] = {}
    for registro in registros:
        por_pagina.setdefault(registro.pdf_page, []).append(registro.id)

    assert {pagina: len(ids) for pagina, ids in por_pagina.items()} == {121: 3, 122: 9, 123: 8}
    gei008 = uno(registros, "GEI008")
    assert (gei008.campo, gei008.longitud, gei008.ocurrencia) == ("mOtEve", "5-500", "1-1")

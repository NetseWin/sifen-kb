# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_sifen_validations.py), integrado en sifen-kb bajo MIT.
"""Capa 3 — `validaciones.json`: una ficha por validación (fila lógica) del MT V150.

Unitarios con Documents sintéticos (formatos de encabezado, combinaciones verticales, unidad de
observación, ruta de secciones, estado, anomalías y V5) y verificación sobre el PDF real
(páginas 151-154, 163 y el manual entero, 135-193).
"""

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Cell, Change, Document, Row, Run, Table, TextBlock
from sifen_kb.pdf.pipeline import load
from sifen_kb.pdf.sifen.validations import (
    EFECTOS,
    ID_VALIDACION,
    VINETA,
    ValidationRecord,
    check_validations,
    is_validation_table,
    to_json,
    validation_anomalies,
    validation_records,
)
from sifen_kb.pdf.tagged import extract_tagged

MANUAL = corpus_pdf.MANUAL

# Encabezado de 5 columnas (páginas 151-159) y fila de ejemplo en ese orden.
CINCO = ["ID", "Resultado de validación", "Código", "Observación", "E"]
FILA = ["AA02", "Plazo de validez del Certificado digital", "0002", "", "R"]
# Encabezado de 6 columnas de la sección 12.4 (páginas 135-145 y 160-192).
SEIS = ["N° Val", "ID", "Mensaje de la Validación", "Código", "Observación", "E"]
FILA_124 = ["19", "D002", "La fecha y hora de emisión es inválida", "1150", "Cuando la fecha", "R"]


def celda(*runs: Run, header: bool = False, col: int | None = None) -> Cell:
    return Cell(list(runs), header=header, col=col)


def fila(valores: list[str], change: Change | None = None) -> Row:
    """Fila completa: sus celdas van en la columna que les toca por orden (como la IR)."""
    return Row([celda(Run(v, change), col=i) for i, v in enumerate(valores)])


def continuacion(*textos: tuple[int, str], change: Change | None = None) -> Row:
    """Fila de continuación de una combinación vertical: solo las columnas que trae."""
    return Row([celda(Run(texto, change), col=col) for col, texto in textos])


def encabezado(titulos: list[str]) -> Row:
    return Row([celda(Run(t), header=True, col=i) for i, t in enumerate(titulos)])


def documento(*blocks: Table | TextBlock) -> Document:
    return Document(source="MT.pdf", sha256="abc123", extractor="test", blocks=list(blocks))


def tabla(*filas: Row, page: int = 151, titulos: list[str] | None = None) -> Table:
    return Table(page=page, rows=[encabezado(titulos or CINCO), *filas])


def solo(doc: Document) -> ValidationRecord:
    fichas = validation_records(doc)
    assert len(fichas) == 1, fichas
    return fichas[0]


# --- Fichas ---------------------------------------------------------------------------------


def test_cada_fila_da_una_ficha_con_su_procedencia() -> None:
    ficha = solo(documento(tabla(fila(FILA), page=151)))

    assert (ficha.id, ficha.codigo, ficha.efecto) == ("AA02", "0002", "R")
    assert ficha.resultado == "Plazo de validez del Certificado digital"
    assert ficha.observaciones == ()
    assert (ficha.numero, ficha.version) == ("", "")
    assert (ficha.source, ficha.sha256) == ("MT.pdf", "abc123")


def test_la_pagina_impresa_es_la_del_pdf_menos_uno() -> None:
    ficha = solo(documento(tabla(fila(FILA), page=151)))

    assert (ficha.pdf_page, ficha.printed_page) == (151, 150)


def test_una_fila_partida_usa_la_pagina_de_la_fila_no_la_de_la_tabla() -> None:
    # Una tabla unida entre páginas lleva la página en cada fila (T-104).
    con_filas = tabla(fila(FILA), page=153)
    con_filas.rows[1].page = 154

    assert solo(documento(con_filas)).pdf_page == 154


def test_las_filas_de_continuacion_aportan_una_observacion_cada_una() -> None:
    # AA01 (página 151): la celda del ID abarca 4 filas y cada una trae una observación.
    valores = ["AA01", "Certificado de Transmisor Inválido", "0001", "inexistente", "R"]
    doc = documento(
        tabla(
            fila(valores),
            continuacion((3, "Versión incorrecta")),
            continuacion((3, "No se aceptan certificados de la AC")),
            continuacion((3, "ExtendKeyUsage no define “ClientAuth“")),
        )
    )
    ficha = solo(doc)

    assert ficha.observaciones == (
        "inexistente",
        "Versión incorrecta",
        "No se aceptan certificados de la AC",
        "ExtendKeyUsage no define “ClientAuth“",
    )
    assert validation_anomalies(doc) == []


def test_una_observacion_vacia_no_deja_entrada_en_la_lista() -> None:
    doc = documento(tabla(fila(FILA), continuacion((3, ""))))

    assert solo(doc).observaciones == ()


def test_las_observaciones_conservan_los_saltos_de_parrafo() -> None:
    valores = [*FILA[:3], "• Dirección de la LCR no informada\n(CRLDistributionPoint)", "R"]

    assert solo(documento(tabla(fila(valores)))).observaciones == (valores[3],)


# --- Unidad 'observación' -------------------------------------------------------------------


def con_observacion(texto: str, change: Change | None = None) -> Document:
    """Ficha de una sola fila cuya celda de observaciones trae `texto`."""
    return documento(tabla(fila([*FILA[:3], texto, FILA[4]], change)))


def test_cada_parrafo_con_vineta_abre_una_observacion() -> None:
    # AC05 (páginas 153-154) unido: tres viñetas, una con su paréntesis en el párrafo siguiente.
    texto = (
        "• Dirección de la LCR no informada\n(CRLDistributionPoint)\n"
        "• Error en el acceso a la LCR\n• LCR inexistente"
    )

    assert solo(con_observacion(texto)).observaciones == (
        "• Dirección de la LCR no informada\n(CRLDistributionPoint)",
        "• Error en el acceso a la LCR",
        "• LCR inexistente",
    )


def test_una_celda_sin_vinetas_es_una_sola_observacion() -> None:
    texto = "Se debe respetar la secuencialidad.\nEj: AA, AB, AC… AZ"

    assert solo(con_observacion(texto)).observaciones == (texto,)


def test_el_asterisco_y_el_parentesis_asterisco_tambien_son_vinetas() -> None:
    # GCO002c (página 139) usa '*' y C010 (página 162) usa '(*)': son las otras dos marcas de
    # lista medidas en las celdas de observaciones del manual.
    con_asterisco = "Regla para plazo inválido:\n*Si es el primero\n*Si no es el primero"
    con_parentesis = "Casos no permitidos:\n(*) Primera serie distinta a AA\n(*) Serie no vecina"

    assert solo(con_observacion(con_asterisco)).observaciones == (
        "Regla para plazo inválido:",
        "*Si es el primero",
        "*Si no es el primero",
    )
    assert solo(con_observacion(con_parentesis)).observaciones == (
        "Casos no permitidos:",
        "(*) Primera serie distinta a AA",
        "(*) Serie no vecina",
    )


def test_un_guion_al_principio_del_parrafo_no_abre_observacion() -> None:
    # Ningún párrafo del manual empieza con guion y al principio de un renglón es ambiguo (puede
    # ser un rango o una palabra partida), así que no cuenta como viñeta.
    texto = "Cuando el plazo vence\n- 45 días desde la emisión"

    assert solo(con_observacion(texto)).observaciones == (texto,)


def test_las_observaciones_de_una_celda_no_pierden_ni_duplican_texto() -> None:
    texto = "Intro:\n• Uno\n(detalle)\n• Dos"
    observaciones = solo(con_observacion(texto)).observaciones

    assert "\n".join(observaciones) == texto


def test_un_parrafo_en_blanco_no_deja_una_observacion_vacia() -> None:
    assert solo(con_observacion("• Uno\n\n• Dos")).observaciones == ("• Uno\n", "• Dos")


def test_un_tramo_resaltado_que_cruza_dos_observaciones_se_divide() -> None:
    # H-3 de la auditoría: la celda entera en rojo es un solo `Run` que abarca las dos viñetas;
    # cada mitad tiene que quedar con el índice de su observación.
    ficha = solo(con_observacion("• Dirección no informada\n• Error en el acceso", Change.DELETED))

    assert [(c.indice, c.texto) for c in ficha.cambios if c.columna == "observaciones"] == [
        (0, "• Dirección no informada"),
        (1, "• Error en el acceso"),
    ]


def test_el_indice_del_cambio_apunta_a_la_observacion_que_lo_contiene() -> None:
    observacion = celda(Run("• Uno\n"), Run("• Dos", Change.ADDED), Run("\n• Tres", Change.ADDED), col=3)
    row = Row([*fila(FILA).cells[:3], observacion, fila(FILA).cells[4]])
    ficha = solo(documento(tabla(row)))

    assert ficha.observaciones == ("• Uno", "• Dos", "• Tres")
    assert [(c.indice, c.texto) for c in ficha.cambios] == [(1, "• Dos"), (2, "• Tres")]


def test_el_encabezado_de_la_seccion_12_4_se_normaliza_a_los_mismos_campos() -> None:
    ficha = solo(documento(tabla(fila(FILA_124), page=163, titulos=SEIS)))

    assert (ficha.numero, ficha.id, ficha.codigo) == ("19", "D002", "1150")
    assert ficha.resultado == "La fecha y hora de emisión es inválida"
    assert ficha.observaciones == ("Cuando la fecha",)


def test_la_columna_v_se_guarda_como_version() -> None:
    titulos = ["ID", "Resultado de validación", "Código", "Obs.", "E", "V"]
    valores = ["AB01", "Fallo de schema XML del área de datos", "0100", "", "R", "150"]

    assert solo(documento(tabla(fila(valores), page=153, titulos=titulos))).version == "150"


def test_los_titulos_no_dependen_de_los_espacios_ni_de_las_mayusculas() -> None:
    # 'Resultado de Validación', 'Resultado de la Validación' y 'Obs' son variantes del autor;
    # el hueco lo puede insertar además la extracción al partir una palabra entre renglones.
    partido = ["ID", "Resultado de la\nValida ción", "Código", "Obs", "E"]

    assert [f.id for f in validation_records(documento(tabla(fila(FILA), titulos=partido)))] == ["AA02"]


@pytest.mark.parametrize(
    "titulos",
    [
        ["ID", "Mensaje de validación", "Código", "Observación", "E"],  # NT-001
        ["ID", "Mensaje de la validación", "Código", "Observación", "E"],  # NT-018
        ["ID", "Resultado de validación", "C;odigo", "Observación", "E"],  # NT-016, errata
    ],
)
def test_se_reconocen_las_variantes_de_titulo_de_las_notas_tecnicas(titulos: list[str]) -> None:
    # D-015: títulos que el autor escribió así en las NT; el MT V150 no los usa.
    assert [f.id for f in validation_records(documento(tabla(fila(FILA), titulos=titulos)))] == ["AA02"]


def test_nro_val_es_el_numero_de_validacion() -> None:
    # NT-016 escribe 'Nro. Val' donde el MT escribe 'N° Val'.
    titulos = ["Nro. Val", "ID", "Mensaje de validación", "Código", "Observación", "E"]
    valores = ["278", *FILA]

    assert solo(documento(tabla(fila(valores), titulos=titulos))).numero == "278"


def test_solo_las_tablas_con_encabezado_de_validaciones_dan_fichas() -> None:
    guia = ["Inicio ID", "Inicio código de respuesta", "Fin ID", "Fin código de respuesta"]
    otra = Table(page=151, rows=[encabezado(guia), fila(["GEI002", "4050", "GEI006a", "4099"])])
    doc = documento(tabla(fila(FILA)), otra)

    assert not is_validation_table(otra)
    assert [f.id for f in validation_records(doc)] == ["AA02"]


def test_los_bloques_que_no_son_tablas_se_ignoran() -> None:
    doc = documento(TextBlock(page=151, role="P", runs=[Run("Aclaramos que")]), tabla(fila(FILA)))

    assert len(validation_records(doc)) == 1


# --- Sección ---------------------------------------------------------------------------------


def titulo(texto: str, page: int = 151) -> TextBlock:
    """Encabezado del árbol: `tagged` le pone el nivel según la etiqueta (`H3` → 3)."""
    return TextBlock(page=page, role="H3", runs=[Run(texto)], level=3)


def test_la_seccion_es_el_encabezado_previo() -> None:
    doc = documento(titulo("12.2.1. Validaciones del certificado"), tabla(fila(FILA)))

    assert solo(doc).seccion == "12.2.1. Validaciones del certificado"


def test_la_seccion_trae_la_ruta_de_encabezados_desde_el_mas_alto() -> None:
    doc = documento(
        TextBlock(page=146, role="H1", runs=[Run("12. Validaciones")], level=1),
        TextBlock(page=151, role="H2", runs=[Run("12.2. Codificación de respuestas")], level=2),
        titulo("12.2.1. Validaciones del certificado"),
        tabla(fila(FILA)),
    )

    assert solo(doc).seccion == (
        "12. Validaciones > 12.2. Codificación de respuestas > 12.2.1. Validaciones del certificado"
    )


def test_un_encabezado_reemplaza_a_los_de_su_nivel_y_a_los_de_abajo() -> None:
    doc = documento(
        TextBlock(page=151, role="H2", runs=[Run("12.1. Estructura de los códigos")], level=2),
        titulo("12.1.3. Códigos de los eventos"),
        TextBlock(page=151, role="H2", runs=[Run("12.2. Codificación de respuestas")], level=2),
        titulo("12.2.1. Validaciones del certificado"),
        tabla(fila(FILA)),
    )

    assert solo(doc).seccion == ("12.2. Codificación de respuestas > 12.2.1. Validaciones del certificado")


def test_el_titulo_de_grupo_cuelga_del_encabezado_del_arbol_aunque_compartan_nivel() -> None:
    # 'D.' y '12.4.' son los dos de nivel 2 (uno por su forma, el otro por la etiqueta `H2`),
    # pero el grupo de campos está dentro de la sección del manual, no al lado.
    doc = documento(
        TextBlock(page=160, role="H2", runs=[Run("12.4. Validaciones del formato")], level=2),
        TextBlock(page=163, role="P", runs=[Run("D. Datos generales del DE (D001 – D299)")]),
        TextBlock(page=163, role="P", runs=[Run("D1. Campos de la operación (D010-D099)")]),
        tabla(fila(FILA_124), page=163, titulos=SEIS),
    )

    assert solo(doc).seccion == (
        "12.4. Validaciones del formato > D. Datos generales del DE (D001 – D299) > "
        "D1. Campos de la operación (D010-D099)"
    )


def test_un_encabezado_nuevo_deja_atras_los_titulos_de_grupo() -> None:
    doc = documento(
        TextBlock(page=160, role="H2", runs=[Run("12.4. Validaciones del formato")], level=2),
        TextBlock(page=163, role="P", runs=[Run("D. Datos generales del DE (D001 – D299)")]),
        TextBlock(page=193, role="H2", runs=[Run("12.5. Validaciones de los eventos")], level=2),
        tabla(fila(FILA_124), page=193, titulos=SEIS),
    )

    assert solo(doc).seccion == "12.5. Validaciones de los eventos"


def test_el_titulo_de_grupo_de_campos_tambien_sirve_de_seccion() -> None:
    # En la sección 12.4 los títulos de grupo son `LI`/`P` sin nivel en el árbol (D-008 no los
    # promueve): se reconocen por su forma, como en `sifen.sections`.
    texto = "D. Datos generales del Documento Electrónico (D001 – D299)"
    doc = documento(
        TextBlock(page=163, role="LI", runs=[Run(texto)]),
        tabla(fila(FILA_124), page=163, titulos=SEIS),
    )

    assert solo(doc).seccion == texto


def test_un_parrafo_cualquiera_no_es_seccion() -> None:
    doc = documento(
        titulo("12.2.1. Validaciones del certificado"),
        TextBlock(page=151, role="P", runs=[Run("El área de datos tiene las siguientes")]),
        tabla(fila(FILA)),
    )

    assert solo(doc).seccion == "12.2.1. Validaciones del certificado"


def test_sin_encabezado_previo_la_seccion_es_none() -> None:
    assert solo(documento(tabla(fila(FILA)))).seccion is None


# --- Tablas sin encabezado en la página siguiente --------------------------------------------


def test_una_tabla_sin_encabezado_continua_la_de_validaciones_de_la_pagina_anterior() -> None:
    # Páginas 157, 159 y 193: Word cortó la tabla y no repitió el encabezado, así que T-104 no
    # la une. Sus filas tienen tantas celdas como el encabezado anterior.
    sigue = Table(page=152, rows=[fila(["AA05", "Certificado revocado", "0005", "", "R"])])
    doc = documento(tabla(fila(FILA), page=151), sigue)

    assert [f.id for f in validation_records(doc)] == ["AA02", "AA05"]
    assert [f.pdf_page for f in validation_records(doc)] == [151, 152]
    assert validation_anomalies(doc) == []


def test_una_tabla_sin_encabezado_que_no_sigue_a_una_de_validaciones_se_ignora() -> None:
    suelta = Table(page=152, rows=[fila(["AA05", "Certificado revocado", "0005", "", "R"])])

    assert validation_records(documento(suelta)) == []
    assert validation_anomalies(documento(suelta)) == []


def test_una_tabla_sin_encabezado_de_otra_forma_no_continua_la_anterior() -> None:
    otra = Table(page=152, rows=[fila(["Guaraníes", "Redondeo"])])
    doc = documento(tabla(fila(FILA), page=151), otra)

    assert [f.id for f in validation_records(doc)] == ["AA02"]


# --- Estado de la fila lógica ----------------------------------------------------------------


def test_fila_entera_en_rojo_es_eliminado() -> None:
    ficha = solo(documento(tabla(fila(FILA, Change.DELETED))))

    assert ficha.estado == "eliminado"
    assert {c.change for c in ficha.cambios} == {"deleted"}


def test_fila_en_verde_con_el_numero_sin_resaltar_es_agregado() -> None:
    # Medido en 135-193: 83 fichas traen todo el cuerpo en verde y el `N° Val` sin resaltar. Si
    # el número votara, esas 83 altas quedarían como 'modificado'.
    row = Row(
        [
            celda(Run("21"), col=0),
            *[celda(Run(v, Change.ADDED), col=i + 1) for i, v in enumerate(FILA_124[1:])],
        ]
    )
    ficha = solo(documento(tabla(row, page=163, titulos=SEIS)))

    assert ficha.estado == "agregado"
    assert "numero" not in [c.columna for c in ficha.cambios]


def test_el_numero_resaltado_si_decide_el_estado_y_queda_en_cambios() -> None:
    # Las 25 bajas de 135-193 traen también el `N° Val` en rojo.
    ficha = solo(documento(tabla(fila(FILA_124, Change.DELETED), page=163, titulos=SEIS)))

    assert ficha.estado == "eliminado"
    assert ("numero", "deleted", "19") in [(c.columna, c.change, c.texto) for c in ficha.cambios]


def test_un_resaltado_parcial_es_modificado_y_detalla_columna_y_tramo() -> None:
    observacion = celda(Run("Texto previo. "), Run("Oración agregada.", Change.ADDED), col=3)
    row = Row([*fila(FILA).cells[:3], observacion, fila(FILA).cells[4]])
    ficha = solo(documento(tabla(row)))

    assert ficha.estado == "modificado"
    assert [(c.columna, c.indice, c.change, c.texto) for c in ficha.cambios] == [
        ("observaciones", 0, "added", "Oración agregada.")
    ]


def test_una_observacion_de_continuacion_resaltada_lleva_su_indice() -> None:
    doc = documento(
        tabla(
            fila(["AC04", "Cadena de certificación inválida", "0123", "• PSC no habilitado", "R"]),
            continuacion((3, "• Certificado del PSC revocado"), change=Change.MODIFIED),
        )
    )
    ficha = solo(doc)

    assert ficha.estado == "modificado"
    assert [(c.columna, c.indice, c.texto) for c in ficha.cambios] == [
        ("observaciones", 1, "• Certificado del PSC revocado")
    ]


def test_fila_sin_resaltado_no_tiene_estado_ni_cambios() -> None:
    ficha = solo(documento(tabla(fila(FILA))))

    assert ficha.estado is None
    assert ficha.cambios == ()


def test_los_espacios_no_deciden_el_estado() -> None:
    resultado = celda(Run("Plazo", Change.DELETED), Run(" "), Run("vencido", Change.DELETED), col=1)
    borrada = fila(FILA, Change.DELETED)
    row = Row([borrada.cells[0], resultado, *borrada.cells[2:]])

    assert solo(documento(tabla(row))).estado == "eliminado"


# --- Anomalías -------------------------------------------------------------------------------


def test_una_continuacion_sin_ficha_abierta_es_anomalia() -> None:
    # Página 154 sin unir: la mitad de AC05 que quedó en la página siguiente no trae ID. No se
    # pega a nada por cuenta propia (T-104 une las tablas); se avisa.
    huerfana = Table(
        page=154,
        rows=[
            encabezado(CINCO),
            continuacion((1, "Problema en la LCR"), (3, "• Error en el acceso a la LCR")),
        ],
    )
    doc = documento(huerfana)

    assert validation_records(doc) == []
    anomalias = validation_anomalies(doc)
    assert len(anomalias) == 1
    assert anomalias[0].motivo == "continuacion-sin-ficha"
    assert (anomalias[0].pdf_page, anomalias[0].printed_page) == (154, 153)
    assert anomalias[0].columnas == ("resultado", "observaciones")
    assert anomalias[0].textos == ("Problema en la LCR", "• Error en el acceso a la LCR")


def test_una_continuacion_con_columnas_de_mas_se_avisa_y_conserva_la_observacion() -> None:
    doc = documento(tabla(fila(FILA), continuacion((1, "Otro resultado"), (3, "Otra observación"))))
    ficha = solo(doc)

    assert ficha.resultado == FILA[1]  # la columna de la ficha no se sobreescribe
    assert ficha.observaciones == ("Otra observación",)
    anomalias = validation_anomalies(doc)
    assert [(a.motivo, a.columnas) for a in anomalias] == [
        ("continuacion-con-columnas-de-mas", ("resultado",))
    ]


def test_una_fila_con_columnas_sin_inferir_es_anomalia() -> None:
    sin_columna = Row([celda(Run("AA05")), celda(Run("Certificado revocado"))])
    doc = documento(tabla(fila(FILA), sin_columna))

    assert [f.id for f in validation_records(doc)] == ["AA02"]
    assert [a.motivo for a in validation_anomalies(doc)] == ["columnas-sin-inferir"]


def test_una_fila_con_dos_celdas_en_la_misma_columna_es_anomalia() -> None:
    repetida = Row([celda(Run("AA05"), col=0), celda(Run("otra vez"), col=0)])
    doc = documento(tabla(repetida))

    assert validation_records(doc) == []
    assert [a.motivo for a in validation_anomalies(doc)] == ["columna-repetida"]


def test_una_celda_fuera_del_encabezado_es_anomalia() -> None:
    sobrante = Row([celda(Run("AA05"), col=0), celda(Run("de más"), col=9)])
    doc = documento(tabla(sobrante))

    assert validation_records(doc) == []
    anomalias = validation_anomalies(doc)
    assert [(a.motivo, a.textos) for a in anomalias] == [("columna-fuera-del-encabezado", ("AA05", "de más"))]


def test_una_fila_completa_sin_columnas_inferidas_se_ubica_por_orden() -> None:
    # La ruta geométrica (Fase 2) puede no inferir columnas: con tantas celdas como el
    # encabezado el orden alcanza, sin geometría.
    cruda = Row([celda(Run(v)) for v in FILA])

    assert solo(documento(tabla(cruda))).id == "AA02"


def test_sin_filas_raras_no_hay_anomalias() -> None:
    assert validation_anomalies(documento(tabla(fila(FILA)))) == []


# --- V5: esquema de las validaciones ---------------------------------------------------------


def fichas(*filas: list[str]) -> list[ValidationRecord]:
    return validation_records(documento(tabla(*(fila(f) for f in filas))))


def incidencias(*filas: list[str]) -> list[tuple[str, str]]:
    return [(i.check, i.id) for i in check_validations(fichas(*filas))]


def test_los_ids_observados_cumplen_el_formato() -> None:
    for valido in ("AA01", "D002", "H016a", "GEC002c", "E715", "BO03"):
        assert ID_VALIDACION.match(valido), valido


def test_un_id_fuera_del_formato_observado_se_reporta() -> None:
    mal = ["aa01", "Certificado inválido", "0001", "", "R"]

    assert incidencias(mal) == [("id-formato", "aa01")]


def test_un_codigo_no_numerico_se_reporta() -> None:
    mal = ["AA01", "Certificado inválido", "01xx", "", "R"]

    assert incidencias(mal) == [("codigo-no-numerico", "AA01")]


def test_un_efecto_fuera_de_la_leyenda_se_reporta() -> None:
    # La leyenda del propio manual (página PDF 134) define A, AO y R; 'N' aparece una vez.
    assert EFECTOS == frozenset({"A", "AO", "R"})
    assert incidencias(["BC01", "Autorización satisfactoria", "0260", "", "N"]) == [
        ("efecto-desconocido", "BC01")
    ]


def test_un_efecto_vacio_se_reporta_aparte() -> None:
    assert incidencias(["BO03", "Éxito en la consulta", "0502", "", ""]) == [("efecto-vacio", "BO03")]


def test_una_columna_ausente_se_reporta_como_hueco() -> None:
    # AC05 (página 153) sin unir: el resultado quedó en la página siguiente.
    partida = Row([celda(Run("AC05"), col=0), celda(Run("0124"), col=2), celda(Run("R"), col=4)])
    ficha = solo(documento(tabla(partida, page=153)))

    assert ficha.resultado == ""
    issues = [(i.check, i.id) for i in check_validations([ficha])]
    assert issues == [("columna-ausente", "AC05")]
    assert "resultado" in check_validations([ficha])[0].detalle


def test_una_columna_ausente_que_traen_las_continuaciones_no_se_reporta() -> None:
    sin_obs = Row([celda(Run(v), col=i) for i, v in enumerate(FILA) if i != 3])
    doc = documento(tabla(sin_obs, continuacion((3, "Versión incorrecta"))))

    assert solo(doc).observaciones == ("Versión incorrecta",)
    assert check_validations(validation_records(doc)) == []


def test_un_id_repetido_en_dos_fichas_vigentes_se_reporta() -> None:
    doble = ["H002", "Fallo de schema", "2100", "", "R"]

    assert incidencias(doble, doble) == [("id-duplicado", "H002")]


def test_una_ficha_eliminada_y_otra_vigente_con_el_mismo_id_se_distinguen() -> None:
    valores = ["H002", "Fallo de schema", "2100", "", "R"]
    doc = documento(tabla(fila(valores, Change.DELETED), fila(valores)))

    issues = check_validations(validation_records(doc))
    assert [(i.check, i.id) for i in issues] == [("id-duplicado-reemplazo", "H002")]
    assert "eliminado" in issues[0].detalle


def test_v5_no_corrige_nada_solo_reporta() -> None:
    # D-005: la incidencia nombra el valor tal como vino del PDF.
    mal = ["aa01", "Certificado inválido", "0001", "", "R"]

    assert fichas(mal)[0].id == "aa01"
    assert "aa01" in check_validations(fichas(mal))[0].detalle


# --- Serialización ---------------------------------------------------------------------------


def test_el_json_es_determinista_y_lleva_fichas_incidencias_y_anomalias() -> None:
    doc = documento(tabla(fila(FILA), page=151))

    primero = to_json(doc, pages=range(151, 155))
    assert primero == to_json(doc, pages=range(151, 155))
    assert '"validaciones"' in primero
    assert '"incidencias"' in primero and '"anomalias"' in primero
    assert "Resultado de validación" not in primero  # claves normalizadas, no el título del PDF
    assert "\\u" not in primero  # ensure_ascii=False
    assert primero.startswith("{\n ")  # indent=1


def test_to_dict_expone_las_observaciones_como_lista_y_los_cambios_planos() -> None:
    observacion = celda(Run("Previo. "), Run("Nuevo.", Change.MODIFIED), col=3)
    row = Row([*fila(FILA).cells[:3], observacion, fila(FILA).cells[4]])
    datos = solo(documento(tabla(row))).to_dict()

    assert datos["observaciones"] == ["Previo. Nuevo."]
    assert datos["estado"] == "modificado"
    assert datos["cambios"] == [
        {"columna": "observaciones", "indice": 0, "change": "modified", "texto": "Nuevo."}
    ]


# --- Sobre el PDF real -----------------------------------------------------------------------


real = pytest.mark.skipif(not MANUAL.exists(), reason="fuente MT V150 no copiada")


@pytest.fixture(scope="module")
def doc_151() -> Document:
    return extract_tagged(MANUAL, pages=range(151, 155))


@pytest.fixture(scope="module")
def doc_163() -> Document:
    return extract_tagged(MANUAL, pages=range(163, 164))


@pytest.fixture(scope="module")
def doc_manual() -> Document:
    """Todas las tablas de validaciones del manual (135-193), como las arma el CLI."""
    return load(MANUAL, pages=range(135, 194), sifen=True)


def una(fichas: list[ValidationRecord], validacion_id: str) -> ValidationRecord:
    encontradas = [f for f in fichas if f.id == validacion_id]
    assert len(encontradas) == 1, f"{validacion_id}: {encontradas}"
    return encontradas[0]


@real
def test_real_aa01_tiene_cuatro_observaciones_y_codigo_0001(doc_151: Document) -> None:
    aa01 = una(validation_records(doc_151), "AA01")

    assert aa01.codigo == "0001"
    assert aa01.resultado == "Certificado de Transmisor Inválido"
    assert len(aa01.observaciones) == 4
    assert aa01.observaciones[0] == "Certificado de Transmisor inexistente en el mensaje"
    assert aa01.observaciones[3] == "ExtendKeyUsage no define “ClientAuth“"
    assert (aa01.efecto, aa01.estado, aa01.version) == ("R", None, "")
    assert (aa01.pdf_page, aa01.printed_page) == (151, 150)


@real
def test_real_la_tabla_ab_esta_entera_eliminada(doc_151: Document) -> None:
    # Página 153: la tabla de la validación de forma del Request está toda en rojo, con la
    # columna V (versión) que no aparece en ninguna otra.
    ab = [f for f in validation_records(doc_151) if f.id.startswith("AB")]

    assert [f.id for f in ab] == ["AB01", "AB02", "AB03", "AB05", "AB06", "AB07", "AB08"]
    assert {f.estado for f in ab} == {"eliminado"}
    assert {f.version for f in ab} == {"150"}
    assert {f.pdf_page for f in ab} == {153}
    assert una(ab, "AB01").seccion == (
        "12.2. Codificación de respuestas de los Servicios WEB del SIFEN > "
        "12.2.3. Validación de forma del área de datos del Request"
    )


@real
def test_real_la_seccion_de_aa01_trae_su_encabezado_y_el_ancestro(doc_151: Document) -> None:
    aa01 = una(validation_records(doc_151), "AA01")

    assert aa01.seccion == (
        "12.2. Codificación de respuestas de los Servicios WEB del SIFEN > "
        "12.2.1. Validaciones del certificado de transmisión. Protocolo TLS"
    )


@real
def test_real_ad02_esta_modificado_y_abarca_ocho_observaciones(doc_151: Document) -> None:
    ad02 = una(validation_records(doc_151), "AD02")

    assert ad02.estado == "modificado"
    assert len(ad02.observaciones) == 8
    assert {c.change for c in ad02.cambios} == {"modified"}
    assert [c.indice for c in ad02.cambios if c.columna == "observaciones"] == list(range(8))


@real
def test_real_ac05_sin_unir_deja_la_continuacion_como_anomalia(doc_151: Document) -> None:
    # La fila de AC05 se parte entre las páginas 153 y 154; sin T-104 la mitad sin ID se avisa.
    ac05 = una(validation_records(doc_151), "AC05")

    assert (ac05.pdf_page, ac05.codigo, ac05.estado) == (153, "0124", "eliminado")
    assert ac05.resultado == ""
    anomalias = validation_anomalies(doc_151)
    assert [(a.motivo, a.pdf_page) for a in anomalias] == [
        ("continuacion-sin-ficha", 154),
        ("continuacion-sin-ficha", 154),
    ]
    assert [i.check for i in check_validations([ac05])] == ["columna-ausente"]


@real
def test_real_ac05_unido_da_una_sola_ficha(doc_151: Document) -> None:
    continuity = pytest.importorskip("sifen_kb.pdf.continuity")
    unido = continuity.merge_continued_tables(doc_151)
    fichas_unidas = validation_records(unido)
    ac05 = una(fichas_unidas, "AC05")

    assert ac05.resultado == "Problema en la LCR del certificado de firma"
    assert ac05.observaciones[-1] == "• LCR inexistente"
    assert ac05.estado == "eliminado"
    assert validation_anomalies(unido) == []
    assert [i.check for i in check_validations([ac05])] == []


@real
def test_real_ac05_unido_cuenta_tres_observaciones_con_cambios_coherentes(
    doc_151: Document,
) -> None:
    # H-3 de la auditoría: las tres viñetas de la validación 0124 son tres observaciones, y cada
    # tramo rojo apunta a la suya (antes dos entradas distintas dec­laraban `indice: 0`).
    continuity = pytest.importorskip("sifen_kb.pdf.continuity")
    ac05 = una(validation_records(continuity.merge_continued_tables(doc_151)), "AC05")

    assert ac05.observaciones == (
        "• Dirección de la LCR no informada\n(CRLDistributionPoint)",
        "• Error en el acceso a la LCR",
        "• LCR inexistente",
    )
    assert [(c.indice, c.texto) for c in ac05.cambios if c.columna == "observaciones"] == [
        (0, "• Dirección de la LCR no informada\n(CRLDistributionPoint)"),
        (1, "• Error en el acceso a la LCR"),
        (2, "• LCR inexistente"),
    ]


@real
def test_real_las_tres_vinetas_de_la_lcr_se_cuentan_igual_en_ac05_y_en_ad02(
    doc_151: Document,
) -> None:
    # La misma lista sale en AC05 (partida entre las páginas 153 y 154, dos viñetas en una celda)
    # y en AD02 (una viñeta por fila): la unidad no puede depender de cómo quedó armada la celda.
    continuity = pytest.importorskip("sifen_kb.pdf.continuity")
    fichas_unidas = validation_records(continuity.merge_continued_tables(doc_151))
    lcr = [
        "• Dirección de la LCR no informada\n(CRLDistributionPoint)",
        "• Error en el acceso a la LCR",
        "• LCR inexistente",
    ]

    assert list(una(fichas_unidas, "AC05").observaciones) == lcr
    assert list(una(fichas_unidas, "AD02").observaciones[3:6]) == lcr


@real
def test_real_el_efecto_del_piloto_es_siempre_rechazo(doc_151: Document) -> None:
    assert {f.efecto for f in validation_records(doc_151)} == {"R"}


@real
def test_real_d002_y_d013_cambian_y_d010_no(doc_163: Document) -> None:
    fichas_163 = validation_records(doc_163)

    assert (una(fichas_163, "D002").numero, una(fichas_163, "D002").estado) == ("19", "modificado")
    assert una(fichas_163, "D002a").estado == "agregado"  # su `N° Val` no está resaltado
    assert una(fichas_163, "D013").estado == "eliminado"
    d010 = una(fichas_163, "D010")
    assert (d010.numero, d010.estado, d010.cambios) == ("22", None, ())
    assert d010.seccion == (
        "D. Datos generales del Documento Electrónico (D001 – D299) > "
        "D1. Campos inherentes a la operación comercial (D010-D099)"
    )
    assert una(fichas_163, "D002").seccion == ("D. Datos generales del Documento Electrónico (D001 – D299)")


@real
def test_real_la_pagina_impresa_va_uno_atras_de_la_del_pdf(doc_163: Document) -> None:
    fichas_163 = validation_records(doc_163)

    assert fichas_163
    assert all(f.printed_page == f.pdf_page - 1 for f in fichas_163)
    assert una(fichas_163, "D002").printed_page == 162


@real
def test_real_el_piloto_no_deja_incidencias_de_formato(doc_163: Document) -> None:
    assert check_validations(validation_records(doc_163)) == []


# --- Sobre el manual entero (páginas PDF 135-193) ---------------------------------------------


def sin_espacios(texto: str) -> str:
    return "".join(texto.split())


@real
def test_real_cada_cambio_esta_dentro_de_la_observacion_que_dice_su_indice(
    doc_manual: Document,
) -> None:
    fichas_manual = validation_records(doc_manual)

    assert len(fichas_manual) == 445
    for ficha in fichas_manual:
        # Los tramos de una misma observación van en orden y no se pisan: se buscan uno tras
        # otro desde donde terminó el anterior.
        leido: dict[int, int] = {}
        for cambio in ficha.cambios:
            if cambio.columna != "observaciones":
                assert cambio.indice is None, (ficha.id, cambio)
                continue
            assert cambio.indice is not None, (ficha.id, cambio)
            observacion = sin_espacios(ficha.observaciones[cambio.indice])
            desde = leido.get(cambio.indice, 0)
            encontrado = observacion.find(sin_espacios(cambio.texto), desde)
            assert encontrado >= 0, (ficha.id, cambio, observacion)
            leido[cambio.indice] = encontrado + len(sin_espacios(cambio.texto))


@real
def test_real_las_observaciones_del_manual_no_pierden_ni_duplican_texto(
    doc_manual: Document,
) -> None:
    # Las observaciones de una ficha son sus celdas partidas: juntas tienen que dar el mismo
    # texto que las celdas, salvo los saltos de línea que separan una viñeta de la siguiente.
    from sifen_kb.pdf.sifen import validations

    celdas: list[str] = []
    for tabla_ in validations._tablas(doc_manual):
        for row in tabla_.cuerpo:
            mapa = validations._mapa(row, tabla_.columnas)
            if isinstance(mapa, str):
                continue
            cell = mapa.get("observaciones")
            if cell is not None and cell.text.strip():
                celdas.append(cell.text)
    fichas_manual = validation_records(doc_manual)
    observaciones = [o for ficha in fichas_manual for o in ficha.observaciones]

    assert len(observaciones) == 437  # 426 celdas con texto; 11 se parten en viñetas
    assert sin_espacios("".join(observaciones)) == sin_espacios("".join(celdas))


@real
def test_real_solo_cuatro_fichas_cambian_de_cantidad_de_observaciones(
    doc_manual: Document,
) -> None:
    # Medido en 135-193: la unidad por viñeta solo parte las celdas de estas cuatro fichas
    # (antes tenían 1, 1, 2 y 1 observación, una por celda con texto).
    fichas_manual = validation_records(doc_manual)
    partidas = {
        ficha.id: len(ficha.observaciones)
        for ficha in fichas_manual
        if ficha.id in {"GCO002c", "GDI002c", "AC05", "C010"}
    }

    assert partidas == {"GCO002c": 4, "GDI002c": 4, "AC05": 3, "C010": 5}


@real
def test_real_ninguna_observacion_del_manual_esconde_otra_vineta(doc_manual: Document) -> None:
    # Que no quede ninguna celda a medio partir: dentro de una observación, los párrafos que
    # siguen al primero son continuaciones y no empiezan con viñeta.
    for ficha in validation_records(doc_manual):
        for observacion in ficha.observaciones:
            for parrafo in observacion.split("\n")[1:]:
                assert not VINETA.match(parrafo.lstrip()), (ficha.id, observacion)


@real
def test_real_la_seccion_del_manual_entero_trae_la_ruta_completa(doc_manual: Document) -> None:
    # H-9 de la auditoría: con el manual entero, el grupo de campos cuelga de su 12.x.
    fichas_manual = validation_records(doc_manual)

    assert una(fichas_manual, "D002").seccion == (
        "12. Validaciones > 12.4. Validaciones del formato > "
        "D. Datos generales del Documento Electrónico (D001 – D299)"
    )
    assert una(fichas_manual, "D010").seccion == (
        "12. Validaciones > 12.4. Validaciones del formato > "
        "D. Datos generales del Documento Electrónico (D001 – D299) > "
        "D1. Campos inherentes a la operación comercial (D010-D099)"
    )
    assert una(fichas_manual, "AA01").seccion == (
        "12. Validaciones > 12.2. Codificación de respuestas de los Servicios WEB del SIFEN > "
        "12.2.1. Validaciones del certificado de transmisión. Protocolo TLS"
    )

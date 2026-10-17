# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (tests/test_sifen_changes.py), integrado en sifen-kb bajo MIT.
"""T-302 — libro de cambios: filas de campos y validaciones de las NT emparejadas con el MT V150.

Unitarios con Documents sintéticos y verificación sobre las NT reales (020, 023, 013).
"""

import json

import corpus_pdf
import pytest

from sifen_kb.pdf.ir import Block, Cell, Change, Document, Figure, Row, Run, Table, TextBlock
from sifen_kb.pdf.sifen.changes import (
    Alerta,
    Cambio,
    LibroDeCambios,
    cited_pages,
    libro_de_cambios,
    note_info,
    to_json,
)
from sifen_kb.pdf.sifen.fields import ENCABEZADO, FieldRecord

FUENTES = corpus_pdf.FUENTES
MANUAL = FUENTES / "Manual_Tecnico_SIFEN_V150.pdf"
NOTAS = FUENTES / "Notas_Tecnicas"

VALIDACION_MT = ["N° Val", "ID", "Mensaje de la Validación", "Código", "Observación", "E"]
VALIDACION_NT = ["ID", "Mensaje de la Validación", "Código", "Observación", "E"]
ESQUEMA = ["ID", "Campo", "Descripción", "Nodo Padre", "Tipo Dato", "Longitud", "Ocu", "Obs"]

D208 = ["D3", "D208", "iTipIDRec", "Tipo de documento", "D200", "N", "1", "0-1", "Obligatorio"]


def celda(*runs: Run) -> Cell:
    return Cell(list(runs))


def fila(valores: list[str], change: Change | None = None) -> Row:
    return Row([celda(Run(v, change)) for v in valores])


def tabla(titulos: list[str], *filas: Row, page: int = 1) -> Table:
    return Table(page=page, rows=[fila(titulos), *filas])


def campos(*filas: Row, page: int = 1) -> Table:
    return tabla(list(ENCABEZADO), *filas, page=page)


def texto(contenido: str, page: int = 1) -> TextBlock:
    return TextBlock(page=page, role="P", runs=[Run(contenido)])


def nota(*blocks: Table | TextBlock, numero: int = 23, fecha: str = "27/08/2024") -> Document:
    cabecera = [texto(f"NOTA TÉCNICA N° {numero}"), texto(f"Fecha: {fecha}")]
    return Document(
        source=f"NT_E_KUATIA_{numero:03d}_MT_V150.pdf",
        sha256=f"nt{numero}",
        extractor="test",
        blocks=[*cabecera, *blocks],
    )


def manual(*blocks: Block) -> Document:
    return Document(source="MT.pdf", sha256="mt", extractor="test", blocks=list(blocks))


# MT con D208 en la página PDF 72 (impresa 71) y la validación D210 en la 168 (impresa 167).
MT = manual(
    campos(fila(D208), page=72),
    tabla(
        VALIDACION_MT,
        fila(["71", "D210", "Es obligatorio", "1314", "Si D201=2", "R"]),
        page=168,
    ),
)


def unico(libro: LibroDeCambios) -> Cambio:
    assert len(libro.cambios) == 1, libro.cambios
    return libro.cambios[0]


def tipos(alertas: list[Alerta]) -> list[str]:
    return [a.tipo for a in alertas]


# --- Metadatos de la NT -------------------------------------------------------------------------


def test_numero_y_fecha_de_la_nota() -> None:
    info = note_info(nota(numero=20, fecha="17/11/2023"))

    assert (info.numero, info.fecha) == (20, "2023-11-17")


def test_las_notas_antiguas_escriben_numero_y_la_fecha_con_guiones() -> None:
    doc = Document(
        source="NT_E_KUATIA_001_MT_V150.pdf",
        sha256="x",
        extractor="test",
        blocks=[
            texto("Nota Técnica Número 1"),
            texto("Fecha: 14-10-2019"),
            texto("Cambios desde la fecha 10-09-2019 al 14-10-2019"),
        ],
    )
    info = note_info(doc)

    assert (info.numero, info.fecha) == (1, "2019-10-14")
    assert info.periodo == ("2019-09-10", "2019-10-14")
    assert (info.vigencia_test, info.vigencia_prod) == (None, None)


@pytest.mark.parametrize(
    ("test", "prod", "esperado"),
    [
        ("15 de diciembre de 2023", "31 de enero del 2024", ("2023-12-15", "2024-01-31")),
        ("21 de Abril del 2023", "17 de Junio del 2023", ("2023-04-21", "2023-06-17")),
        ("30 de agosto de 2024", "27 de setiembre de 2024", ("2024-08-30", "2024-09-27")),
        ("25 de Agosto del 2023", "22 de Septiembre del 2023", ("2023-08-25", "2023-09-22")),
        ("15/12/2023", "31/01/2024", ("2023-12-15", "2024-01-31")),
    ],
)
def test_vigencia_de_test_y_produccion(test: str, prod: str, esperado: tuple[str, str]) -> None:
    vigencia = Table(
        page=1,
        rows=[
            fila(["Fecha puesta a disposición para el Ambiente de Test", test]),
            fila(["Fecha puesta a disposición para el Ambiente de Producción", prod]),
        ],
    )
    info = note_info(nota(vigencia))

    assert (info.vigencia_test, info.vigencia_prod) == esperado


# --- Páginas citadas ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("contenido", "paginas"),
    [
        ("se modifican los siguientes campos: (Página 86)", (86,)),
        ("(Páginas 165, 166, 167, 189)", (165, 166, 167, 189)),
        ("(Página 90 y 91)", (90, 91)),
        ("(Páginas 66,67)", (66, 67)),
        ("Páginas: 152.", (152,)),
        ("Se amplía el listado (Páginas 211 y 212).", (211, 212)),
        ("Conforme al Art 6° (Numeral 1) del Decreto N° 872/2023", ()),
    ],
)
def test_paginas_citadas(contenido: str, paginas: tuple[int, ...]) -> None:
    assert cited_pages(contenido) == paginas


# --- Tipo de cambio -----------------------------------------------------------------------------


def test_fila_en_verde_con_id_nuevo_es_agregado_sin_antes() -> None:
    h018 = ["H", "H018", "dRucFus", "RUC fusionado", "H001", "A", "3-8", "0-1", "Obligatorio"]
    libro = libro_de_cambios(
        MT, [nota(texto("1.4. se incorpora el campo"), campos(fila(h018, Change.ADDED)))]
    )
    cambio = unico(libro)

    assert (cambio.tipo, cambio.id, cambio.cambio) == ("campo", "H018", "agregado")
    assert cambio.antes is None
    assert cambio.despues is not None and cambio.despues["campo"] == "dRucFus"
    assert libro.alertas == []


def test_fila_sin_color_con_id_nuevo_es_agregado() -> None:
    # NT-020: E827 viene sin resaltar; el título dice 'Se agrega'.
    e827 = ["E9.5", "E827", "dCodConDncp", "Código DNCP", "E820", "A", "1-30", "0-1", "Código"]
    libro = libro_de_cambios(MT, [nota(texto("1.1. Se agrega el campo"), campos(fila(e827)))])

    assert unico(libro).cambio == "agregado"
    assert libro.alertas == []


def test_fila_sin_color_con_id_del_mt_es_modificado_y_dice_que_columnas() -> None:
    nuevo = [*D208[:6], "1-2", "0-1", "Obligatorio si D201 = 2"]
    libro = libro_de_cambios(MT, [nota(texto("1.1. se modifica el campo"), campos(fila(nuevo)))])
    cambio = unico(libro)

    assert cambio.cambio == "modificado"
    assert cambio.columnas_distintas == ("longitud", "observaciones")
    assert cambio.antes is not None and cambio.antes["longitud"] == "1"
    assert cambio.mt_pdf_page == 72
    assert cambio.evidencia["color"] is None


def test_el_resaltado_parcial_es_modificado_y_despues_no_lleva_lo_tachado() -> None:
    obs = celda(
        Run("Obligatorio "),
        Run("y D202 ≠ 4", Change.DELETED),
        Run("\nNo informar si D201 = 1", Change.ADDED),
    )
    row = Row([*fila(D208[:8]).cells, obs])
    cambio = unico(libro_de_cambios(MT, [nota(texto("1.1. se modifican"), campos(row))]))

    assert cambio.cambio == "modificado"
    assert cambio.despues is not None
    assert cambio.despues["observaciones"] == "Obligatorio \nNo informar si D201 = 1"
    assert [(c["change"], c["texto"]) for c in cambio.marcas] == [
        ("deleted", "y D202 ≠ 4"),
        ("added", "No informar si D201 = 1"),
    ]


def test_la_base_es_lo_que_la_nt_imprime_sin_lo_agregado() -> None:
    # Es lo que la NT dice que había antes: T-303 lo compara con el estado vigente.
    obs = celda(
        Run("Obligatorio "),
        Run("y D202 ≠ 4", Change.DELETED),
        Run("\nNo informar si D201 = 1", Change.ADDED),
    )
    row = Row([*fila(D208[:8]).cells, obs])
    cambio = unico(libro_de_cambios(MT, [nota(texto("1.1. se modifican"), campos(row))]))

    assert cambio.base is not None and cambio.base["observaciones"] == "Obligatorio y D202 ≠ 4"
    assert cambio.columnas == FieldRecord.COLUMNAS


def test_las_columnas_son_las_que_trae_la_tabla_de_la_nt() -> None:
    valores = ["D210", "Es obligatorio", "1314", "Otra", "R"]
    cambio = unico(
        libro_de_cambios(MT, [nota(texto("2.1. se modifica"), tabla(VALIDACION_NT, fila(valores)))])
    )

    assert cambio.columnas == ("id", "resultado", "codigo", "observaciones", "efecto")
    assert cambio.to_dict()["columnas"] == list(cambio.columnas)


def test_fila_entera_en_rojo_es_eliminado_sin_despues() -> None:
    libro = libro_de_cambios(
        MT, [nota(texto("1.1. se elimina el campo"), campos(fila(D208, Change.DELETED)))]
    )
    cambio = unico(libro)

    assert (cambio.cambio, cambio.despues) == ("eliminado", None)
    assert cambio.antes is not None


def test_sin_color_el_verbo_eliminar_decide_la_baja() -> None:
    libro = libro_de_cambios(MT, [nota(texto("1.2. Se eliminan los siguientes campos"), campos(fila(D208)))])

    assert unico(libro).cambio == "eliminado"


# --- Alertas ------------------------------------------------------------------------------------


def test_modificar_un_id_que_no_esta_en_el_mt_ni_en_una_nt_previa_es_alerta() -> None:
    d299 = ["D3", "D299", "dX", "X", "D200", "A", "1", "0-1", "Nuevo texto"]
    row = Row([*fila(d299[:8]).cells, celda(Run("Nuevo", Change.MODIFIED), Run(" texto"))])
    libro = libro_de_cambios(MT, [nota(texto("1.1. se modifica"), campos(row))])

    assert tipos(libro.alertas) == ["id-no-existe"]
    assert libro.alertas[0].id == "D299"


def test_modificar_un_id_que_agrego_una_nt_previa_no_es_alerta_y_la_nombra() -> None:
    # H004g: lo agrega NT-010 y lo modifica NT-023.
    valores = ["H004g", "El CDC asociado", "2439", "Si H002=1", "R"]
    agrega = nota(
        texto("2.3. se agrega"),
        tabla(VALIDACION_NT, fila(valores, Change.ADDED)),
        numero=10,
        fecha="04/02/2022",
    )
    modificada = Row(
        [
            *fila(valores[:3]).cells,
            celda(Run("Si H002=1 "), Run("y/o RUC", Change.MODIFIED)),
            celda(Run("R")),
        ]
    )
    modifica = nota(texto("2.2. se modifica"), tabla(VALIDACION_NT, modificada))
    libro = libro_de_cambios(MT, [modifica, agrega])  # el orden de entrada no importa

    assert [(c.nt, c.cambio) for c in libro.cambios] == [(10, "agregado"), (23, "modificado")]
    assert libro.cambios[1].nt_previas == (10,)
    assert "id-no-existe" not in tipos(libro.alertas)
    assert "varias-nt" in tipos(libro.alertas)


def test_agregar_un_id_que_ya_esta_en_el_mt_es_alerta() -> None:
    libro = libro_de_cambios(MT, [nota(texto("1.1. se agrega"), campos(fila(D208, Change.ADDED)))])

    assert tipos(libro.alertas) == ["agregado-ya-existe"]


def test_pagina_citada_que_no_contiene_el_id_es_alerta() -> None:
    # NT-023 cita la página 86 para D208, que en el MT está en la impresa 71.
    nuevo = [*D208[:8], "Otro texto"]
    libro = libro_de_cambios(
        MT, [nota(texto("1.1. se modifican los campos: (Página 86)"), campos(fila(nuevo)))]
    )
    cambio = unico(libro)

    assert cambio.paginas_citadas == (86,)
    assert tipos(libro.alertas) == ["pagina-no-coincide"]
    assert "71" in libro.alertas[0].detalle


def test_pagina_citada_que_contiene_el_id_no_es_alerta() -> None:
    nuevo = [*D208[:8], "Otro texto"]
    libro = libro_de_cambios(MT, [nota(texto("1.1. se modifican: (Página 71)"), campos(fila(nuevo)))])

    assert libro.alertas == []


def test_el_verbo_del_titulo_que_contradice_el_cambio_es_alerta() -> None:
    h018 = ["H", "H018", "dRucFus", "RUC", "H001", "A", "3-8", "0-1", "Obligatorio"]
    libro = libro_de_cambios(MT, [nota(texto("1.4. se elimina el campo"), campos(fila(h018, Change.ADDED)))])

    assert tipos(libro.alertas) == ["verbo-contradice"]


def test_se_modifica_es_generico_si_la_fila_trae_color() -> None:
    # NT-019 y NT-023 titulan 'se modifican los siguientes campos' secciones con filas enteras
    # en verde o en rojo: con color, la fila no deja dudas.
    h018 = ["H", "H018", "dRucFus", "RUC", "H001", "A", "3-8", "0-1", "Obligatorio"]
    libro = libro_de_cambios(
        MT,
        [nota(texto("2.2. se modifica la siguiente validación"), campos(fila(h018, Change.ADDED)))],
    )

    assert (unico(libro).cambio, libro.alertas) == ("agregado", [])


def test_eliminar_una_observacion_es_una_fila_modificada_por_tachado() -> None:
    # NT-010 1.6: 'se elimina la siguiente observación' y la fila trae solo texto en rojo.
    obs = celda(Run("Obligatorio"), Run(" 5= Comprobante de retención", Change.DELETED))
    row = Row([*fila(D208[:8]).cells, obs])
    libro = libro_de_cambios(MT, [nota(texto("1.6. se elimina la siguiente observación"), campos(row))])

    assert (unico(libro).cambio, libro.alertas) == ("modificado", [])


@pytest.mark.parametrize(
    "titulo",
    [
        "1- Especificación de la fórmula del descuento (incluidos impuestos) (Página 71)",
        "11.6.7. REGLAS DE VALIDACIÓN PARA EL EVENTO POR ACTUALIZACIÓN DE DATOS",
    ],
)
def test_solo_cuenta_el_verbo_conjugado_no_la_palabra_suelta(titulo: str) -> None:
    # 'incluidos' (NT-001) no dice que se agregue nada; 'ACTUALIZACIÓN' (NT-018) es un nombre.
    nuevo = [*D208[:8], "Otro texto"]
    libro = libro_de_cambios(MT, [nota(texto(titulo), campos(fila(nuevo)))])

    assert (unico(libro).evidencia["verbos"], libro.alertas) == ([], [])


def test_el_id_tachado_da_de_baja_la_fila_aunque_quede_una_columna_sin_tachar() -> None:
    # NT-002 D208d y D210a: todo en rojo salvo la columna E.
    valores = ["D210", "Es obligatorio", "1314", "Si D201=2"]
    row = Row([*fila(valores, Change.DELETED).cells, celda(Run("R"))])
    libro = libro_de_cambios(
        MT, [nota(texto("2.1. Se eliminan las siguientes validaciones"), tabla(VALIDACION_NT, row))]
    )

    assert (unico(libro).cambio, unico(libro).despues, libro.alertas) == ("eliminado", None, [])


def test_un_id_repetido_en_la_misma_nt_no_es_varias_nt() -> None:
    # NT-014 trae dos validaciones GENFE012 (códigos 4467 y 4477).
    primera = ["GENFE012", "Es obligatorio", "4467", "Si GENFE004=2", "R"]
    segunda = ["GENFE012", "El número de documento", "4477", "Si GENFE004=2", "R"]
    doc = nota(
        texto("2.1 SE AGREGAN LAS SIGUIENTES REGLAS"),
        tabla(VALIDACION_NT, fila(primera), fila(segunda)),
        numero=14,
    )
    libro = libro_de_cambios(MT, [doc])

    assert [c.cambio for c in libro.cambios] == ["agregado", "agregado"]
    assert [c.nt_previas for c in libro.cambios] == [(), ()]
    assert tipos(libro.alertas) == ["id-repetido-en-nt"]


def test_la_pagina_citada_puede_ser_la_del_comienzo_de_la_tabla_del_mt() -> None:
    # NT-001 cita la 103 para F034: la tabla del MT empieza en la impresa 103; la fila, en la 104.
    f001 = ["F", "F001", "gTotSub", "Totales", "E001", "G", "", "0-1", ""]
    f034 = ["F", "F034", "dTBasGraIVA", "Base gravada", "F001", "N", "1-15", "0-1", "Suma"]
    partida = Table(page=104, rows=[fila(list(ENCABEZADO)), fila(f001), Row(fila(f034).cells, page=105)])
    nuevo = [*f034[:8], "Suma de todas las bases"]
    libro = libro_de_cambios(
        manual(partida), [nota(texto("1.2. se modifica (Página 103)"), campos(fila(nuevo)))]
    )

    assert libro.alertas == []


def test_una_fila_sin_color_igual_al_mt_es_alerta() -> None:
    libro = libro_de_cambios(MT, [nota(texto("1.1. se modifica"), campos(fila(D208)))])

    # NT-019 repite la raíz del evento (GEN001) como contexto, sin tocarla.
    assert (unico(libro).cambio, unico(libro).columnas_distintas) == ("sin_cambio", ())
    assert tipos(libro.alertas) == ["sin-diferencia"]


def test_una_fila_sin_id_va_a_alertas_y_no_a_cambios() -> None:
    sin_id = ["D3", "", "iTipIDRec", "Tipo", "D200", "N", "1", "0-1", "x"]
    libro = libro_de_cambios(MT, [nota(texto("1.1. se modifica"), campos(fila(sin_id)))])

    assert libro.cambios == []
    assert tipos(libro.alertas) == ["id-invalido"]


# --- Validaciones -------------------------------------------------------------------------------


def test_validacion_compara_solo_las_columnas_que_trae_la_nt() -> None:
    # La NT no trae 'N° Val': no por eso el número del MT cuenta como cambio.
    valores = ["D210", "Es obligatorio", "1314", "Si D201=2, debe informarse", "R"]
    cambio = unico(
        libro_de_cambios(MT, [nota(texto("2.1. se modifica"), tabla(VALIDACION_NT, fila(valores)))])
    )

    assert (cambio.tipo, cambio.cambio) == ("validacion", "modificado")
    assert cambio.columnas_distintas == ("observaciones",)
    assert cambio.mt_pdf_page == 168


def test_un_campo_y_una_validacion_con_el_mismo_id_no_se_confunden() -> None:
    # D210 es validación en el MT, no campo: como campo es nuevo.
    d210 = ["D3", "D210", "dNumIDRec", "Número", "D200", "A", "1-20", "0-1", "x"]
    cambio = unico(libro_de_cambios(MT, [nota(texto("1.1. se agrega"), campos(fila(d210)))]))

    assert (cambio.tipo, cambio.cambio, cambio.antes) == ("campo", "agregado", None)


# --- Antes: la fila vigente del MT -------------------------------------------------------------


def test_antes_es_la_fila_vigente_del_mt_sin_lo_tachado() -> None:
    obs = celda(Run("Obligatorio"), Run(" viejo", Change.DELETED))
    mt = manual(campos(Row([*fila(D208[:8]).cells, obs]), page=72))
    nuevo = [*D208[:8], "Obligatorio nuevo"]
    cambio = unico(libro_de_cambios(mt, [nota(texto("1.1. se modifica"), campos(fila(nuevo)))]))

    assert cambio.antes is not None and cambio.antes["observaciones"] == "Obligatorio"


def test_una_fila_eliminada_en_el_mt_no_es_el_antes() -> None:
    reemplazada = [*D208[:8], "Versión anterior"]
    mt = manual(campos(fila(reemplazada, Change.DELETED), fila(D208, Change.ADDED), page=72))
    nuevo = [*D208[:8], "Otra"]
    cambio = unico(libro_de_cambios(mt, [nota(texto("1.1. se modifica"), campos(fila(nuevo)))]))

    assert cambio.antes is not None and cambio.antes["observaciones"] == "Obligatorio"


def test_una_tabla_del_mt_entera_en_rojo_con_su_encabezado_no_rompe_el_indice() -> None:
    # MT pág. 151: la tabla AB está eliminada entera, encabezado incluido.
    roja = Table(
        page=151,
        rows=[
            fila(VALIDACION_NT, Change.DELETED),
            fila(["AB01", "Fallo de schema", "0100", "", "R"], Change.DELETED),
        ],
    )
    mt = manual(roja, *MT.blocks)
    valores = ["AB01", "Fallo de schema", "0100", "", "R"]
    libro = libro_de_cambios(mt, [nota(texto("2.1. se agrega"), tabla(VALIDACION_NT, fila(valores)))])

    # AB01 solo existe eliminado en el MT: volver a agregarlo no es 'ya existe'.
    assert (unico(libro).cambio, libro.alertas) == ("agregado", [])


# --- Otros cambios y contexto -------------------------------------------------------------------


def test_las_tablas_que_no_son_campos_ni_validaciones_ni_esquemas_van_a_otros() -> None:
    # NT-011 9.8.2 (Tabla L) y NT-023 3.1 (unidades): no son campos, validaciones ni esquemas.
    condiciones = tabla(["Condición", "Mensaje generado"], fila(["Devuelve el archivo", "0520"]))
    unidades = tabla(["Código", "Representación", "Descripción"], fila(["111", "4A", "Bovinas"]))
    libro = libro_de_cambios(
        MT,
        [
            nota(
                texto("9.8.2. Descripción del procesamiento (Página 147)"),
                condiciones,
                texto("3.1. Se amplía (Páginas 211 y 212)"),
                unidades,
            )
        ],
    )

    assert libro.cambios == []
    assert [(o.encabezado[0], o.paginas_citadas) for o in libro.otros] == [
        ("Condición", (147,)),
        ("Código", (211, 212)),
    ]


def test_historial_y_vigencia_no_son_cambios_ni_otros() -> None:
    historial = tabla(["AUTOR", "FECHA DE ELABORACIÓN", "REVISOR"], fila(["Norma Rojas", "25/08/2023", ""]))
    vigencia = Table(
        page=1, rows=[fila(["Fecha puesta a disposición para el Ambiente de Test", "01/01/2024"])]
    )
    libro = libro_de_cambios(MT, [nota(vigencia, texto("Histórico del Documento"), historial)])

    assert (libro.cambios, libro.otros) == ([], [])


def test_el_contexto_es_desde_el_ultimo_titulo_numerado() -> None:
    # Los párrafos de un punto anterior (la URL de NT-010) no le prestan su página a la tabla.
    unidades = tabla(["Código", "Descripción"], fila(["1", "Gravado IVA"]))
    doc = nota(
        texto("3.1. Se modifica la URL de Consulta QR: (Página 208)"),
        texto("Ambiente de Producción: https://ekuatia.set.gov.py/consultas/qr?"),
        texto("5.1. Se Corrige la descripción en la Tabla 6 (Página 213)"),
        unidades,
    )
    libro = libro_de_cambios(MT, [doc])

    assert [o.paginas_citadas for o in libro.otros if o.encabezado] == [(213,)]
    assert [(o.encabezado, o.paginas_citadas) for o in libro.otros if not o.encabezado] == [((), (208,))]


def test_un_punto_de_texto_lleva_sus_parrafos_hasta_el_punto_siguiente() -> None:
    # NT-010 3.1: las URL nuevas están en los párrafos, no en el título del punto.
    doc = nota(
        texto("3.1. Se modifica la URL de Consulta QR: (Página 208)"),
        texto("Ambiente de Producción: https://ekuatia.set.gov.py/consultas/qr?"),
        texto("Ambiente de Test: https://ekuatia.set.gov.py/consultas-test/qr?"),
        texto("4. Conformación del Código QR C18"),
    )
    (otro,) = libro_de_cambios(MT, [doc]).otros

    assert otro.paginas_citadas == (208,)
    assert "consultas-test/qr?" in otro.contexto
    assert "4. Conformación" not in otro.contexto


def test_una_figura_sin_texto_dentro_del_punto_queda_anotada() -> None:
    # NT-010 6.1: el ejemplo de namespace es una imagen (pág. 5); hay que mirarla.
    doc = nota(
        texto("6.1. Se modifica el ejemplo de namespace utilizado en Eventos: (Página 31)"),
        Figure(page=5, alt_text=None),
        texto("7. Convenciones referenciadas en tablas"),
    )
    (otro,) = libro_de_cambios(MT, [doc]).otros

    assert "[figura sin texto extraíble, pág. 5]" in otro.contexto


def test_una_lista_numerada_dentro_del_punto_no_lo_corta() -> None:
    # NT-010 4: la lista '1.', '2.' es contenido del punto 4; el punto siguiente es el 5.
    doc = nota(
        texto("4. Conformación del Código QR C18"),
        texto("En la Sección 13.8.2. se agregan las observaciones del QR: (Página 205)"),
        texto("1. Cuando el documento electrónico no tiene IVA se debe especificar 0."),
        texto("2. Si el Código de Seguridad no está vigente se retornará el error 2501."),
        texto("5. Codificaciones"),
    )
    (otro,) = libro_de_cambios(MT, [doc]).otros

    assert "error 2501" in otro.contexto
    assert "5. Codificaciones" not in otro.contexto


def test_un_punto_sin_tabla_ni_cita_que_cambia_prosa_va_a_otros() -> None:
    # NT-019 5: agrega cuatro párrafos sobre el registro de eventos y no cita página.
    historial = tabla(["AUTOR", "FECHA DE ELABORACIÓN"], fila(["Jonathan Garay", "21/12/2022"]))
    doc = nota(
        texto("5. Se incluye la siguiente descripción respecto al registro de eventos del receptor"),
        texto("En el SIFEN se podrá realizar el registro de cualquier evento del receptor."),
        texto("✓ Para los Documentos Electrónicos: el plazo comienza en la fecha de emisión."),
        texto("Histórico del Documento"),
        historial,
    )
    (otro,) = libro_de_cambios(MT, [doc]).otros

    assert (otro.encabezado, otro.paginas_citadas) == ((), ())
    assert "fecha de emisión" in otro.contexto
    assert "Histórico" not in otro.contexto


def test_un_titulo_que_solo_agrupa_subpuntos_no_va_a_otros() -> None:
    # NT-011 1.1 'Se incluye el siguiente Web Service:' abre 9.8, que trae sus tablas.
    esquema = tabla(ESQUEMA, fila(["ESch01", "rEnvi", "Raíz", "-", "-", "-", "-", "x"]))
    doc = nota(texto("1.1. Se incluye el siguiente Web Service:"), texto("9.8. WS consulta"), esquema)

    libro = libro_de_cambios(MT, [doc])

    assert libro.otros == []  # ni el título ni la tabla, que es un esquema (D-021)
    assert [(c.tipo, c.id) for c in libro.cambios] == [("esquema", "ESch01")]


def test_la_cita_despues_de_la_tabla_vale_si_la_tabla_no_tiene_otra() -> None:
    # NT-016 escribe 'Páginas: 152.' debajo de la tabla.
    valores = ["D210", "Es obligatorio", "1314", "Otra observación", "R"]
    doc = nota(
        texto("1.3 Se modifican las siguientes observaciones"),
        tabla(VALIDACION_NT, fila(valores)),
        texto("Páginas: 167."),
    )
    libro = libro_de_cambios(MT, [doc])

    assert unico(libro).paginas_citadas == (167,)
    assert libro.alertas == []


# --- Serialización ------------------------------------------------------------------------------


def test_el_json_es_determinista_y_trae_notas_cambios_otros_y_alertas() -> None:
    h018 = ["H", "H018", "dRucFus", "RUC", "H001", "A", "3-8", "0-1", "x"]
    vigencia = Table(
        page=1,
        rows=[
            fila(["Fecha puesta a disposición para el Ambiente de Test", "30 de agosto de 2024"]),
            fila(["Fecha puesta a disposición para el Ambiente de Producción", "27/09/2024"]),
        ],
    )
    libro = libro_de_cambios(
        MT, [nota(vigencia, texto("1.4. se incorpora"), campos(fila(h018, Change.ADDED)))]
    )
    salida = to_json(libro)
    datos = json.loads(salida)

    assert salida == to_json(libro)
    assert set(datos) == {"alertas", "cambios", "notas", "otros", "procedencia"}
    assert datos["notas"][0]["vigencia_prod"] == "2024-09-27"
    primero = datos["cambios"][0]
    assert (primero["id"], primero["nt"], primero["vigencia_test"]) == ("H018", 23, "2024-08-30")


# --- Sobre las NT reales ------------------------------------------------------------------------

real = pytest.mark.skipif(not MANUAL.exists(), reason="fuentes SIFEN V150 no copiadas")


@pytest.fixture(scope="module")
def libro_real() -> LibroDeCambios:
    from sifen_kb.pdf.pipeline import load

    # Páginas PDF del MT donde están los ID que tocan NT-013, 020 y 023.
    paginas = [72, 73, 87, 91, 94, 102, 111, 166, 168, 179, 187, 192]
    mt = load(MANUAL, pages=paginas, sifen=True)
    notas = [load(NOTAS / f"NT_E_KUATIA_{n}_MT_V150.pdf", sifen=True) for n in ("013", "020", "023")]
    return libro_de_cambios(mt, notas)


def de(libro: LibroDeCambios, nt: int, tipo: str, id_: str) -> Cambio:
    encontrados = [c for c in libro.cambios if (c.nt, c.tipo, c.id) == (nt, tipo, id_)]
    assert len(encontrados) == 1, encontrados
    return encontrados[0]


@real
def test_real_vigencias(libro_real: LibroDeCambios) -> None:
    notas = {n.numero: (n.fecha, n.vigencia_test, n.vigencia_prod) for n in libro_real.notas}

    assert notas == {
        13: ("2023-03-20", "2023-04-21", "2023-06-17"),
        20: ("2023-11-17", "2023-12-15", "2024-01-31"),
        23: ("2024-08-27", "2024-08-30", "2024-09-27"),
    }


@real
def test_real_nt020_e827_y_d202b_son_nuevos_sin_color(libro_real: LibroDeCambios) -> None:
    e827 = de(libro_real, 20, "campo", "E827")
    d202b = de(libro_real, 20, "validacion", "D202b")

    assert (e827.cambio, e827.evidencia["color"], e827.antes) == ("agregado", None, None)
    assert (d202b.cambio, d202b.paginas_citadas) == ("agregado", (165,))
    # El título dice 'se modifica la siguiente validación', pero D202b no existe en el MT.
    assert any((a.nt, a.id, a.tipo) == (20, "D202b", "verbo-contradice") for a in libro_real.alertas)


@real
def test_real_nt023_d208_quita_texto_y_cita_mal_la_pagina(libro_real: LibroDeCambios) -> None:
    d208 = de(libro_real, 23, "campo", "D208")

    assert d208.cambio == "modificado"
    assert ("deleted", "y D202 ≠ 4") in [(m["change"], m["texto"]) for m in d208.marcas]
    assert d208.despues is not None and "D202 ≠ 4" not in d208.despues["observaciones"]
    assert (d208.paginas_citadas, d208.mt_pdf_page) == ((86,), 72)
    assert any((a.nt, a.id, a.tipo) == (23, "D208", "pagina-no-coincide") for a in libro_real.alertas)


@real
def test_real_nt023_e711_cambia_solo_la_longitud(libro_real: LibroDeCambios) -> None:
    e711 = de(libro_real, 23, "campo", "E711")

    assert e711.columnas_distintas == ("longitud",)
    assert e711.despues is not None and e711.despues["longitud"] == "1-10p(0-8)"


@real
def test_real_nt023_h018_campo_y_validaciones_nuevas(libro_real: LibroDeCambios) -> None:
    assert de(libro_real, 23, "campo", "H018").cambio == "agregado"
    assert de(libro_real, 23, "validacion", "H018").cambio == "agregado"
    assert de(libro_real, 23, "validacion", "H018a").cambio == "agregado"


@real
def test_real_nt023_unidades_de_medida_van_a_otros(libro_real: LibroDeCambios) -> None:
    otros = [o for o in libro_real.otros if o.nt == 23 and o.encabezado]

    assert [(o.paginas_citadas, o.filas) for o in otros] == [((211, 212), 31)]


@real
def test_real_nt013_sin_etiquetas_e737_agregado_y_e735_modificado(
    libro_real: LibroDeCambios,
) -> None:
    # NT-013 va por la ruta geométrica (PDF sin etiquetas).
    assert de(libro_real, 13, "campo", "E737").cambio == "agregado"
    assert de(libro_real, 13, "campo", "E735").cambio == "modificado"
    assert de(libro_real, 13, "validacion", "E737").cambio == "agregado"

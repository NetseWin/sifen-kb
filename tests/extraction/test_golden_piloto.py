"""Golden del dominio piloto (receptor/identidad) en `raw/` (docs/HANDOFF.md §5 paso 1; arquitectura §I, §K.3).

Cada valor esperado se transcribió A MANO desde el PDF oficial de `sources/` —no desde `raw/`
ni de memoria— con motores distintos al del extractor (árbol de etiquetas + pdfplumber):

- texto: poppler `pdftotext -raw`/`-layout` por página, normalizado con `normalize_text`
  (saltos de línea → espacio; guion final une sin espacio);
- resaltado (`changes`, `row_change`, tramos de `current`): página renderizada a PNG e
  inspeccionada a ojo, y contrastada con los rectángulos de relleno de PDFium (pypdfium2) bajo las
  cajas de carácter de PDFium. Leyenda del MT: verde = added, amarillo = modified, rojo = deleted.

El test solo lee `raw/` (rápido; no re-extrae). Cada revisión está fijada por su sha12: los valores
valen para ESE PDF. Un esperado que `raw/` no cumple y que el PDF confirma se marca con
`xfail(strict=True)` con la evidencia; nunca se ajusta el esperado a `raw/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from sifen_kb.normalize import parse_date_literal
from sifen_kb.rawio import RawRow, iter_rows, read_index, rev_dir

ROOT = Path(__file__).resolve().parents[2]

# Revisiones contra las que se verificó cada valor (DocId, sha12 del PDF en sources/<DocId>/).
MT = ("MT_V150", "976cd88c05c3")
NT21 = ("NT_021", "1e716577d874")
NT23 = ("NT_023", "9cb063673358")
NT24 = ("NT_024", "ccc2d1550e92")

ADD, MOD, DEL = "added", "modified", "deleted"

H_VAL_MT = ["N° Val", "ID", "Mensaje de la Validación", "Código", "Observación", "E"]
H_VAL_NT = ["ID", "Mensaje de la Validación", "Código", "Observación", "E"]
H_CAMPO_MT = [
    "Grupo",
    "ID",
    "Campo",
    "Descripción",
    "Nodo Padre",
    "Tipo Dato",
    "Longitud",
    "Ocurrencia",
    "Observaciones",
]
H_FECHAS = [
    "Fecha:",
    "Fecha puesta a disposición para el Ambiente de Test",
    "Fecha puesta a disposición para el Ambiente de Producción",
]
# Fila entera resaltada: todos los atributos salvo el N° Val sin color (regla de `rawio`).
TODA_VAL = ("id", "message", "code", "observation", "severity")


@dataclass(frozen=True)
class Esperada:
    rev: tuple[str, str]
    page: int
    key: str
    table: str
    header: list[str]
    cells: dict[str, str]
    occ: int = 1
    changes: dict[str, str] = field(default_factory=dict)
    row_change: str | None = None
    # Texto vigente (`RawRow.current`) solo donde difiere de `cells` (hay tramos rojos).
    current: dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.rev[0]}:p{self.page}:{self.key}" + (f"~{self.occ}" if self.occ != 1 else "")


def val_mt(
    page: int,
    num: str,
    id_: str,
    message: str,
    code: str,
    observation: str,
    *,
    changes: dict[str, str] | None = None,
    row_change: str | None = None,
    current: dict[str, str] | None = None,
) -> Esperada:
    cells = {
        "num": num,
        "id": id_,
        "message": message,
        "code": code,
        "observation": observation,
        "severity": "R",
    }
    return Esperada(
        MT,
        page,
        id_,
        "validations",
        H_VAL_MT,
        cells,
        changes=changes or {},
        row_change=row_change,
        current=current or {},
    )


def campo_mt(
    page: int,
    group: str,
    id_: str,
    xml_name: str,
    description: str,
    parent: str,
    data_type: str,
    length: str,
    occurrence: str,
    observations: str,
    *,
    changes: dict[str, str] | None = None,
) -> Esperada:
    cells = {
        "group": group,
        "id": id_,
        "xml_name": xml_name,
        "description": description,
        "parent": parent,
        "data_type": data_type,
        "length": length,
        "occurrence": occurrence,
        "observations": observations,
    }
    return Esperada(MT, page, id_, "fields", H_CAMPO_MT, cells, changes=changes or {})


# --- MT V150, §12.4 validaciones del receptor (D200-D299) -----------------------------------------
VALIDACIONES_MT = [
    # PDF 167 / impresa 166. Tramo verde "y el tipo de operación es diferente a B2F (D202≠4),".
    val_mt(
        167,
        "59",
        "D208",
        "Es obligatorio informar el tipo de documento de identidad del receptor",
        "1310",
        "Si la naturaleza del receptor es NO contribuyente (D201=2) y el tipo de operación es diferente a "
        "B2F (D202≠4), el tipo de documento de identidad debe ser informado",
        changes={"observation": MOD},
    ),
    # PDF 167 / impresa 166. Solo "inválido" en amarillo.
    val_mt(
        167,
        "60",
        "D208a",
        "Tipo de documento de identidad del receptor inválido",
        "1311",
        "Si la naturaleza del receptor es contribuyente (D201=1), el tipo de documento de identidad del "
        "receptor (D208) no debe ser informado",
        changes={"message": MOD},
    ),
    # PDF 167 / impresa 166. Fila verde (agregada), N° Val sin color.
    val_mt(
        167,
        "61",
        "D208b",
        "Tipo de documento de identidad del receptor incorrecto para el tipo de operación",
        "1319",
        "El Tipo de documento de identidad del receptor no puede ser innominado (D208=5), cuando el tipo "
        "de operación es distinto a B2C (D202 ≠ 2)",
        changes=dict.fromkeys(TODA_VAL, ADD),
        row_change=ADD,
    ),
    # PDF 167 / impresa 166. Fila verde; umbral 60.000.000; "el Tipo" en minúscula en el MT.
    val_mt(
        167,
        "62",
        "D208c",
        "Tipo de documento de identidad del receptor incorrecto para el total general de la operación en "
        "guaraníes",
        "1321",
        "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), el Tipo de documento de "
        "identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación "
        "en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la "
        "moneda es PYG) es mayor o igual a 60.000.000 (F023 >= 60000000 o F014 >= 60000000)",
        changes=dict.fromkeys(TODA_VAL, ADD),
        row_change=ADD,
    ),
    # PDF 167 / impresa 166. Fila VERDE (agregada en el MT; la elimina después NT 2), no roja.
    val_mt(
        167,
        "63",
        "D208d",
        "El tipo de documento de identidad del receptor no es requerido",
        "1322",
        "Si la naturaleza del receptor es Contribuyente (D201=1) o el tipo de operación es igual a B2F "
        "(D202=4), el tipo de documento de identidad no debe ser informado",
        changes=dict.fromkeys(TODA_VAL, ADD),
        row_change=ADD,
    ),
    # PDF 167 / impresa 166. Fila ROJA entera, N° Val "60" incluido (eliminada en el MT): sin texto vigente.
    val_mt(
        167,
        "60",
        "D209",
        "Descripción del tipo de documento de identidad del receptor no informada",
        "1312",
        "Si se informa el código de tipo de documento de identidad (D208), es obligatorio indicar la "
        "descripción correspondiente",
        changes=dict.fromkeys(("num", *TODA_VAL), DEL),
        row_change=DEL,
        current=dict.fromkeys(("num", *TODA_VAL), ""),
    ),
    # PDF 168 / impresa 167. Sin resaltado.
    val_mt(
        168,
        "64",
        "D209a",
        "Descripción del tipo de documento de identidad del receptor no corresponde al código",
        "1313",
        "La descripción del tipo de documento de identidad del receptor no coincidente con lo informado en "
        "el campo D208",
    ),
    # PDF 168 / impresa 167. Tramo verde "y el tipo de operación es diferente a B2F (D202≠4),".
    val_mt(
        168,
        "65",
        "D210",
        "Es obligatorio informar el número de documento de identidad del receptor",
        "1314",
        "Si la naturaleza del receptor es NO contribuyente (D201=2) y el tipo de operación es diferente a "
        "B2F (D202≠4), el número de documento de identidad debe ser informado",
        changes={"observation": MOD},
    ),
    # PDF 168 / impresa 167. Fila VERDE (agregada en el MT; la elimina después NT 2), no roja.
    val_mt(
        168,
        "66",
        "D210a",
        "El número de documento de identidad del receptor no es requerido",
        "1323",
        "Si la naturaleza del receptor es contribuyente (D201=1) o el tipo de operación es igual a B2F "
        "(D202=4), el número de documento de identidad no debe ser informado",
        changes=dict.fromkeys(TODA_VAL, ADD),
        row_change=ADD,
    ),
    # D208e, D208f, D208g y D210b no están en el MT (grep en las 217 páginas): vienen de NT 10/23.
]

# --- MT V150, tablas de campos ---------------------------------------------------------------------
CAMPOS_MT = [
    # PDF 64 / impresa 63. Opciones 2, 3 y 8 en amarillo.
    campo_mt(
        64,
        "C",
        "C002",
        "iTiDE",
        "Tipo de Documento Electrónico",
        "C001",
        "N",
        "1-2",
        "1-1",
        "1= Factura electrónica 2= Factura electrónica de exportación (Futuro) 3= Factura electrónica de "
        "importación (Futuro) 4= Autofactura electrónica 5= Nota de crédito electrónica 6= Nota de débito "
        "electrónica 7= Nota de remisión electrónica 8= Comprobante de retención electrónico (Futuro)",
        changes={"observations": MOD},
    ),
    # PDF 67 / impresa 66. "13=Muestras médicas (Art. 3 RG 24/2014)" en verde.
    campo_mt(
        67,
        "D1",
        "D011",
        "iTipTra",
        "Tipo de transacción",
        "D010",
        "N",
        "1-2",
        "0-1",
        "Obligatorio si C002 = 1 o 4 No informar si C002 ≠ 1 o 4 Tipo de transacción para el emisor "
        "1= Venta de mercadería 2= Prestación de servicios 3= Mixto (Venta de mercadería y servicios) "
        "4= Venta de activo fijo 5= Venta de divisas 6= Compra de divisas 7= Promoción o entrega de "
        "muestras 8= Donación 9= Anticipo 10= Compra de productos 11= Compra de servicios 12= Venta de "
        "crédito fiscal 13=Muestras médicas (Art. 3 RG 24/2014)",
        changes={"observations": MOD},
    ),
    # PDF 68 / impresa 67. Sin resaltado.
    campo_mt(
        68,
        "D1",
        "D015",
        "cMoneOpe",
        "Moneda de la operación",
        "D010",
        "A",
        "3",
        "1-1",
        "Según tabla de códigos para monedas de acuerdo con la norma ISO 4217 Se requiere la misma moneda "
        "para todos los ítems del DE",
    ),
    # PDF 72 / impresa 71. Sin resaltado.
    campo_mt(
        72,
        "D3",
        "D201",
        "iNatRec",
        "Naturaleza del receptor",
        "D200",
        "N",
        "1",
        "1-1",
        "1= contribuyente 2= no contribuyente",
    ),
    # PDF 72 / impresa 71. "4= B2F (Esta última opción … exterior)" en verde.
    campo_mt(
        72,
        "D3",
        "D202",
        "iTiOpe",
        "Tipo de operación",
        "D200",
        "N",
        "1",
        "1-1",
        "1= B2B 2= B2C 3= B2G 4= B2F (Esta última opción debe utilizarse solo en caso de servicios para "
        "empresas o personas físicas del exterior)",
        changes={"observations": MOD},
    ),
    # PDF 72 / impresa 71. Verde: "y D202 ≠ 4", "o D202=4", opción 6 y "9= Otro".
    campo_mt(
        72,
        "D3",
        "D208",
        "iTipIDRec",
        "Tipo de documento de identidad del receptor",
        "D200",
        "N",
        "1",
        "0-1",
        "Obligatorio si D201 = 2 y D202 ≠ 4 No informar si D201 = 1 o D202=4 1= Cédula paraguaya "
        "2= Pasaporte 3= Cédula extranjera 4= Carnet de residencia 5= Innominado 6=Tarjeta Diplomática de "
        "exoneración fiscal 9= Otro",
        changes={"observations": MOD},
    ),
    # PDF 73 / impresa 72. Longitud entera en amarillo; opción 6 y "Si D208 = 9 …" en verde.
    campo_mt(
        73,
        "D3",
        "D209",
        "dDTipIDRec",
        "Descripción del tipo de documento de identidad",
        "D200",
        "A",
        "9-41",
        "0-1",
        "Obligatorio si existe el campo D208 1= “Cédula paraguaya” 2= “Pasaporte” 3= “Cédula extranjera” "
        "4= “Carnet de residencia” 5 = “Innominado” 6= “Tarjeta Diplomática de exoneración fiscal” "
        "Si D208 = 9 informar el tipo de documento de identidad del receptor",
        changes={"length": MOD, "observations": MOD},
    ),
    # PDF 73 / impresa 72. Verde: "y D202 ≠ 4" y "o D202=4".
    campo_mt(
        73,
        "D3",
        "D210",
        "dNumIDRec",
        "Número de documento de identidad",
        "D200",
        "A",
        "1-20",
        "0-1",
        "Obligatorio si D201 = 2 y D202 ≠ 4 No informar si D201 = 1 o D202=4 En caso de DE innominado, "
        "completar con 0 (cero)",
        changes={"observations": MOD},
    ),
    # PDF 105 / impresa 104. ID y longitud enteros en amarillo; "F008 - F013 + F025" en amarillo.
    # La descripción dice "Total Neto de la operación" (las validaciones lo llaman "total general").
    campo_mt(
        105,
        "F",
        "F014",
        "dTotGralOpe",
        "Total Neto de la operación",
        "F001",
        "N",
        "1-15p(0-8)",
        "1-1",
        "Corresponde al cálculo aritmético F008 - F013 + F025",
        changes={"id": MOD, "length": MOD, "observations": MOD},
    ),
    # PDF 107 / impresa 106. ID y longitud en amarillo; "F014", "EA0" amarillo y la última oración verde.
    campo_mt(
        107,
        "F",
        "F023",
        "dTotalGs",
        "Total general de la operación en Guaraníes",
        "F001",
        "N",
        "1-15p(0-8)",
        "0-1",
        "Si D015 ≠ PYG y D017 = 1, corresponde al cálculo aritmético: F014 * D018 Si D015 ≠ PYG y "
        "D017 = 2, corresponde a la suma de todas las ocurrencias de EA009 Este campo no debe existir si "
        "D015=PYG No informar si D015 = PYG Cuando C002=4 corresponde a F014",
        changes={"id": MOD, "length": MOD, "observations": MOD},
    ),
]

# --- D208c en NT 021 y NT 024 -------------------------------------------------------------------------
# Rojo (PDFium y PNG): "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13),", "o igual" y
# el "=" de cada ">="; amarillo: la "E" de "El" y los tres importes. `rawio` lee el rojo como "deleted" y
# `current` lo quita; OJO: según docs/investigacion/sifen.md §5 ese texto rojo SIGUE VIGENTE en las NT 21
# y 24 (el color no tiene semántica fiable). Aquí solo se fija el contrato mecánico de raw/; para curar
# se usa `cells` y la acción sale del verbo del encabezado (arquitectura §I.4).
_D208C_MSG = "Tipo de documento de identidad del receptor incorrecto para el total general de la operación en guaraníes"
_D208C_ROJO = "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), "
_D208C_CUERPO = (
    "El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total "
    "general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la "
    "operación (cuando la moneda es PYG) es mayor"
)


def d208c_nt(rev: tuple[str, str], importe: str, en_formula: str) -> Esperada:
    impreso = (
        f"{_D208C_ROJO}{_D208C_CUERPO} o igual a {importe} (F023 >= {en_formula} o F014 >= {en_formula})"
    )
    vigente = f"{_D208C_CUERPO} a {importe} (F023 > {en_formula} o F014 > {en_formula})"
    cells = {"id": "D208c", "message": _D208C_MSG, "code": "1321", "observation": impreso, "severity": "R"}
    return Esperada(
        rev,
        1,
        "D208c",
        "validations",
        H_VAL_NT,
        cells,
        changes={"observation": MOD},
        current={"observation": vigente},
    )


D208C_NT = [
    # NT 021, PDF 1 (página única; "(Página 166)" del MT). Umbral 35.000.000.
    d208c_nt(NT21, "35.000.000", "35000000"),
    # NT 024, PDF 1 (página única; "(Página 166)" del MT). Umbral 7.000.000, con puntos también en la fórmula.
    d208c_nt(NT24, "7.000.000", "7.000.000"),
]


# --- Fila `fechas` de NT 021, 023 y 024 -----------------------------------------------------------------
def fechas(rev: tuple[str, str], fecha: str, test: str, prod: str) -> Esperada:
    return Esperada(rev, 1, "fechas", "dates", H_FECHAS, {"fecha": fecha, "test": test, "prod": prod})


FECHAS_NT = [
    # NT 021, PDF 1: "Fecha: 29/12/2023"; rótulo de Producción partido en dos renglones.
    fechas(NT21, "29/12/2023", "01/01/2024", "01/01/2024"),
    # NT 023, PDF 1: "Fecha: 27/08/2024"; vigencias EN PALABRAS ("setiembre").
    fechas(NT23, "27/08/2024", "30 de agosto de 2024", "27 de setiembre de 2024"),
    # NT 024, PDF 1: "Fecha: 17/12/2024"; rótulo de Producción partido en dos renglones.
    fechas(NT24, "17/12/2024", "01/01/2025", "01/01/2025"),
]

FILAS = [*VALIDACIONES_MT, *CAMPOS_MT, *D208C_NT, *FECHAS_NT]

# Página impresa (pie "septiembre de 2019 NNN", leído con pdftotext) de cada página PDF del MT usada.
PAGINAS_IMPRESAS_MT = {64: 63, 67: 66, 68: 67, 72: 71, 73: 72, 105: 104, 107: 106, 167: 166, 168: 167}

# Valor de cada fecha (lo que debe dar `parse_date_literal` sobre la celda), y número de la NT.
FECHAS_VALOR = {
    NT21: (21, date(2023, 12, 29), date(2024, 1, 1), date(2024, 1, 1)),
    NT23: (23, date(2024, 8, 27), date(2024, 8, 30), date(2024, 9, 27)),
    NT24: (24, date(2024, 12, 17), date(2025, 1, 1), date(2025, 1, 1)),
}


# --- Acceso a raw/ ---------------------------------------------------------------------------------------
@cache
def filas_raw(doc: str, sha12: str) -> tuple[RawRow, ...]:
    if not (rev_dir(ROOT, doc, sha12) / "tables.jsonl").is_file():
        pytest.skip(f"raw/{doc}/{sha12}/tables.jsonl no existe (corpus no extraído)")
    return tuple(iter_rows(ROOT, doc, sha12))


def fila_raw(e: Esperada) -> RawRow:
    encontradas = [r for r in filas_raw(*e.rev) if (r.page, r.key, r.occ) == (e.page, e.key, e.occ)]
    assert len(encontradas) == 1, f"{e.id}: {len(encontradas)} filas en raw/ (se esperaba una)"
    return encontradas[0]


def indice(doc: str, sha12: str) -> dict:
    idx = read_index(ROOT, doc, sha12)
    if idx is None:
        pytest.skip(f"raw/{doc}/{sha12}/index.json no existe (corpus no extraído)")
    return idx


# --- Pruebas ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("e", FILAS, ids=lambda e: e.id)
def test_celdas(e: Esperada) -> None:
    r = fila_raw(e)
    assert (r.table, r.pages, r.header) == (e.table, [e.page], e.header)
    assert {a: r.cells.get(a) for a in e.cells} == e.cells


@pytest.mark.parametrize("e", FILAS, ids=lambda e: e.id)
def test_resaltado(e: Esperada) -> None:
    r = fila_raw(e)
    assert r.changes == e.changes
    assert r.row_change == e.row_change


@pytest.mark.parametrize("e", FILAS, ids=lambda e: e.id)
def test_texto_vigente(e: Esperada) -> None:
    r = fila_raw(e)
    assert {a: r.current(a) for a in e.cells} == {a: e.current.get(a, t) for a, t in e.cells.items()}


@pytest.mark.parametrize("e", FILAS, ids=lambda e: e.id)
def test_clave_unica_en_su_tabla(e: Esperada) -> None:
    """La referencia del piloto no es ambigua: en el documento, su (tabla, clave) es UNA fila.

    Verificado en el PDF: en las 217 páginas del MT cada ID es fila de tabla una sola vez (`pdftotext -raw`:
    renglón que empieza con grupo + ID en campos, o N° Val + ID en validaciones).
    """
    hits = [(r.page, r.occ) for r in filas_raw(*e.rev) if (r.table, r.key) == (e.table, e.key)]
    assert hits == [(e.page, e.occ)]


@pytest.mark.parametrize("page, impresa", sorted(PAGINAS_IMPRESAS_MT.items()))
def test_pagina_impresa_mt(page: int, impresa: int) -> None:
    entrada = indice(*MT)["pages"][page - 1]
    assert (entrada["page_pdf"], entrada["page_printed"]) == (page, impresa)


@pytest.mark.parametrize("e", FECHAS_NT, ids=lambda e: e.id)
def test_fechas_valor_y_nt_info(e: Esperada) -> None:
    numero, *valores = FECHAS_VALOR[e.rev]
    r = fila_raw(e)
    assert [parse_date_literal(r.cells[a]) for a in ("fecha", "test", "prod")] == valores
    assert indice(*e.rev)["nt_info"] == {
        "numero": numero,
        "fecha_literal": e.cells["fecha"],
        "test_literal": e.cells["test"],
        "prod_literal": e.cells["prod"],
        "page": e.page,
    }

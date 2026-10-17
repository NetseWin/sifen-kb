# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Capa 3 — `validaciones.json`: una ficha por validación (fila lógica) de las tablas del MT V150.

Las reglas de validación del manual viven en tablas con varios encabezados distintos, escritos por
el autor a lo largo de los años. Medidos en el manual completo (páginas PDF 135-193, 94 tablas):

| encabezado                                                            | tablas |
| --------------------------------------------------------------------- | ------ |
| `N° Val` `ID` `Mensaje de la Validación` `Código` `Observación` `E`    | 68     |
| `ID` `Resultado de la Validación` `Código` `Obs` `E`                   | 9      |
| `ID` `Resultado de Validación` `Código` `Obs` `E`                      | 6      |
| `ID` `Resultado de validación` `Código` `Observación` `E`              | 5      |
| `N° Val` `ID` `Resultado de la Validación` `Código` `Observación` `E`  | 2      |
| `ID` `Resultado de validación` `Código` `Obs.` `E` `V`                 | 1      |
| sin encabezado (Word no lo repitió al cortar la tabla): 157, 159, 193  | 3      |

Los seis se normalizan a los mismos campos, así que la IA que lea el JSON no tiene que saber en
qué tabla estaba la validación. `observaciones` es una **lista** y su unidad es el ítem de la
lista impresa, no la celda ni la fila: cada párrafo que empieza con viñeta (`VINETA`) abre una
observación y los párrafos siguientes sin viñeta se le suman (`(CRLDistributionPoint)` pertenece
a la viñeta anterior); una celda sin viñetas es una sola observación. Así una validación que
abarca varias filas (combinación vertical, D-008) aporta al menos una observación por fila
(AA01, página 151, tiene 4) y una celda con dos viñetas aporta dos.

Medido en 135-193: 426 celdas con texto → 437 observaciones. Solo 4 fichas cambian de cuenta al
partir sus celdas: AC05 (2→3), GCO002c (1→4), GDI002c (1→4) y C010 (1→5); juntas, las
observaciones de una ficha dan el mismo texto que sus celdas, sin perder ni duplicar nada. Lo
que la regla no puede saber es que un párrafo final sin viñeta cierre la lista en vez de
continuar el último ítem: en C010, 'Referirse a la sección Manejo del timbrado…' queda dentro de
la última observación. Separarlo pide una regla que el documento no declara, así que no se hace.

Aquí también vive V5 (esquema de las validaciones). V5 **reporta, no corrige** (D-005): la ficha
conserva el valor tal como salió del PDF y la incidencia lo nombra.

Una fila partida entre páginas (AC05, páginas 153-154) no se pega desde acá: unir tablas es de
`continuity.merge_continued_tables` (T-104). Si el documento viene unido sale una sola ficha; si
no, la mitad sin ID queda como anomalía explícita y V5 avisa qué columna falta. Medido en
135-193: 445 fichas de las dos maneras; sin unir quedan 2 anomalías y 1 hueco (AC05), unido,
ninguno. En el documento unido T-104 concatena las dos mitades de la celda partida de AC05 con
un salto de línea: como cada mitad empieza con viñeta, la ficha cuenta 3 observaciones, las
mismas 3 que AD02 (página 154) trae una por fila.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from sifen_kb.pdf.ir import Cell, Change, Document, Row, Run, Table, TextBlock, runs_text
from sifen_kb.pdf.sifen import sections

# Columnas normalizadas, en el orden en que se leen y se serializan.
COLUMNAS: tuple[str, ...] = (
    "numero",
    "id",
    "resultado",
    "codigo",
    "observaciones",
    "efecto",
    "version",
)
# Sin estas cinco la tabla no es de validaciones. `numero` (`N° Val`) y `version` (`V`) son de
# algunos encabezados nada más.
REQUERIDAS = frozenset({"id", "resultado", "codigo", "observaciones", "efecto"})

# Título del PDF (sin espacios ni mayúsculas) → columna normalizada. El autor alterna
# 'Resultado de validación', 'Resultado de la Validación' y 'Mensaje de la Validación' para la
# misma columna, y 'Observación' / 'Obs' / 'Obs.' para la siguiente; comparar sin espacios además
# aguanta el hueco que inserta la extracción cuando el título se parte entre renglones (D-009).
TITULOS: dict[str, str] = {
    "n°val": "numero",
    "nºval": "numero",  # la otra grafía del ordinal; el MT V150 usa '°'
    "nro.val": "numero",  # NT-016 (D-015)
    "id": "id",
    "resultadodevalidación": "resultado",
    "resultadodelavalidación": "resultado",
    "mensajedelavalidación": "resultado",
    "mensajedevalidación": "resultado",  # NT-001 y NT-016 (D-015)
    "código": "codigo",
    "c;odigo": "codigo",  # errata del título en NT-016 (D-015): es el encabezado que se imprimió
    "observación": "observaciones",
    "obs": "observaciones",
    "obs.": "observaciones",
    "e": "efecto",
    "v": "version",
}

# La página impresa del MT va una atrás de la del PDF (portada sin numerar).
DESPLAZAMIENTO_IMPRESO = 1

# Marca de ítem al principio de un párrafo de la columna `Observación`. Es el juego medido en
# 135-193: '•' (19 párrafos), '*' (6, GCO002c y GDI002c) y '(*)' (4, C010). El guion queda
# afuera a propósito: ningún párrafo del manual empieza con uno y al principio de un renglón es
# ambiguo (rango, palabra partida). '(' sola tampoco: abre '(CRLDistributionPoint)' y '(C002=7)',
# que son continuaciones del párrafo anterior.
VINETA = re.compile(r"\(\*\)|[•*]")
# Separador entre la ruta de secciones ('12.4. Validaciones del formato > D. Datos generales…').
RUTA = " > "

# ID de la validación. Medido en las 445 fichas de 135-193: 1 a 3 letras mayúsculas (D002, AA01,
# GEC002), 2 o 3 dígitos y un sufijo opcional de una minúscula (H016a, GEC002c, D002f). Las 445
# cumplen.
ID_VALIDACION = re.compile(r"^[A-Z]{1,3}\d{2,3}[a-z]?$")
# Código de respuesta: las 445 fichas traen 4 dígitos.
CODIGO = re.compile(r"^\d+$")
# Efecto (`E`) según la leyenda del propio manual (tabla 'REFERENCIA ESTADO DE VALIDACIÓN',
# página PDF 134): A = aprobado, AO = aprobado con observación, R = rechazado. Lo observado en
# las 445 fichas: R=433, AO=3, A=3, N=1 (BC01) y 5 vacías (BL01, BL02, BO01, BO02, BO03). La 'N'
# y las vacías quedan fuera de la leyenda, así que V5 las reporta.
EFECTOS = frozenset({"A", "AO", "R"})


@dataclass(frozen=True)
class ValidationChange:
    """Un tramo de texto con marca de cambio, con la columna donde está.

    `indice` es la posición de la observación **que contiene el tramo** cuando la columna es esa
    (una validación tiene varias); en las demás columnas es None. Un resaltado que abarca dos
    observaciones se parte en dos cambios, uno por índice, así que resolver
    `observaciones[indice]` siempre devuelve el texto donde está el tramo.
    """

    columna: str
    indice: int | None
    change: str  # 'added' | 'modified' | 'deleted'
    texto: str

    def to_dict(self) -> dict[str, object]:
        return {
            "columna": self.columna,
            "indice": self.indice,
            "change": self.change,
            "texto": self.texto,
        }


@dataclass(frozen=True)
class ValidationRecord:
    """Una validación del MT V150, con su estado de cambio y su procedencia."""

    # Columnas de un solo valor, en el orden del encabezado normalizado.
    SIMPLES: ClassVar[tuple[str, ...]] = tuple(c for c in COLUMNAS if c != "observaciones")

    numero: str  # 'N° Val' cuando la tabla lo trae; '' si no
    id: str
    resultado: str  # 'Resultado de validación' o 'Mensaje de la Validación'
    codigo: str
    observaciones: tuple[str, ...]
    efecto: str  # 'E'
    version: str  # 'V' cuando la tabla lo trae; '' si no
    # Ruta de títulos hasta la tabla, del más alto al más hondo, separados por ' > '
    # ('12.4. Validaciones del formato > D. Datos generales…'); None si no hay ninguno antes.
    # Solo trae los títulos de las páginas leídas: un recorte deja la ruta incompleta, no la
    # completa por su cuenta.
    seccion: str | None
    # Columnas requeridas que la fila no trae: el hueco de una fila partida (D-009), no un valor.
    ausentes: tuple[str, ...]
    estado: str | None
    cambios: tuple[ValidationChange, ...]
    pdf_page: int
    source: str
    sha256: str

    @property
    def printed_page(self) -> int:
        return self.pdf_page - DESPLAZAMIENTO_IMPRESO

    def to_dict(self) -> dict[str, object]:
        datos: dict[str, object] = {columna: getattr(self, columna) for columna in self.SIMPLES}
        datos["observaciones"] = list(self.observaciones)
        datos["seccion"] = self.seccion
        datos["columnas_ausentes"] = list(self.ausentes)
        datos["estado"] = self.estado
        datos["cambios"] = [cambio.to_dict() for cambio in self.cambios]
        datos["pdf_page"] = self.pdf_page
        datos["printed_page"] = self.printed_page
        datos["source"] = self.source
        datos["sha256"] = self.sha256
        return datos


@dataclass(frozen=True)
class RowAnomaly:
    """Fila de una tabla de validaciones que no entra en ninguna ficha: se avisa, no se acomoda.

    `columnas` nombra las columnas cuando se conocen y va emparejada con `textos`; cuando las
    columnas son justo el problema queda vacía y `textos` trae la fila entera.
    """

    motivo: str
    columnas: tuple[str, ...]
    textos: tuple[str, ...]
    pdf_page: int
    source: str
    sha256: str

    @property
    def printed_page(self) -> int:
        return self.pdf_page - DESPLAZAMIENTO_IMPRESO

    def to_dict(self) -> dict[str, object]:
        return {
            "motivo": self.motivo,
            "columnas": list(self.columnas),
            "textos": list(self.textos),
            "pdf_page": self.pdf_page,
            "printed_page": self.printed_page,
            "source": self.source,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class Issue:
    """Incidencia de V5: qué verificación falló, en qué validación y con qué valor."""

    check: str
    id: str
    pdf_page: int
    detalle: str

    @property
    def printed_page(self) -> int:
        return self.pdf_page - DESPLAZAMIENTO_IMPRESO

    def to_dict(self) -> dict[str, object]:
        return {
            "check": self.check,
            "id": self.id,
            "detalle": self.detalle,
            "pdf_page": self.pdf_page,
            "printed_page": self.printed_page,
        }


def _clave(titulo: str) -> str:
    return "".join(titulo.split()).lower()


def header_columns(table: Table) -> tuple[str, ...] | None:
    """Columnas normalizadas de la primera fila, o None si no es un encabezado de validaciones."""
    if not table.rows or not table.rows[0].cells:
        return None
    columnas = tuple(TITULOS.get(_clave(cell.text), "") for cell in table.rows[0].cells)
    if "" in columnas or len(set(columnas)) != len(columnas):
        return None
    return columnas if REQUERIDAS <= set(columnas) else None


def is_validation_table(table: Table) -> bool:
    """True si la primera fila es uno de los encabezados de validaciones del manual."""
    return header_columns(table) is not None


@dataclass(frozen=True)
class _Tabla:
    """Una tabla de validaciones ya reconocida, con su cuerpo y la ruta que la ubica."""

    table: Table
    columnas: tuple[str, ...]
    seccion: str | None
    cuerpo: tuple[Row, ...]


def _ultima_pagina(table: Table) -> int:
    """Última página que ocupa la tabla (una ya unida por T-104 ocupa varias)."""
    return max((row.page or table.page for row in table.rows), default=table.page)


@dataclass
class _Ruta:
    """Dónde va quedando la lectura dentro del índice del manual.

    Dos pilas, porque los títulos de grupo de campos de 12.4 (`D.`, `D1.`) son `LI`/`P` en el
    árbol y `sections` les da nivel por su forma: '12.4. Validaciones del formato' (`H2`) y 'D.'
    dan los dos nivel 2, pero el grupo está **dentro** de la sección, no al lado. Con una sola
    pila el grupo desalojaría a su propio ancestro (H-9 de la auditoría: la ficha salía con 'D.'
    y sin el 12.x).
    """

    encabezados: list[tuple[int, str]]  # H1-H6 declarados por el árbol
    grupos: list[tuple[int, str]]  # títulos de grupo de campos, colgados del encabezado vigente

    def anotar(self, block: TextBlock) -> None:
        """Ubica el bloque si es título; los demás párrafos no mueven la ruta."""
        nivel_grupo = sections.level_of(block.text)
        if nivel_grupo is not None:
            _apilar(self.grupos, nivel_grupo, block.text)
        elif block.level is not None:
            _apilar(self.encabezados, block.level, block.text)
            self.grupos.clear()  # otra sección: los grupos de la anterior ya no la ubican

    @property
    def seccion(self) -> str | None:
        """Ruta completa, del título más alto al más hondo; None si aún no hubo ninguno.

        Solo lleva los títulos que estén en las páginas leídas: con un recorte que empieza en la
        163 el 12.4 queda fuera y la ruta arranca en 'D.'. Falta ese ancestro, no se inventa.
        """
        titulos = [texto for _, texto in self.encabezados + self.grupos]
        return RUTA.join(titulos) if titulos else None


def _apilar(pila: list[tuple[int, str]], nivel: int, texto: str) -> None:
    """Deja el título en su nivel: saca los de su nivel y los de abajo, que ya se cerraron."""
    while pila and pila[-1][0] >= nivel:
        pila.pop()
    pila.append((nivel, texto))


def _continua(previa: _Tabla, table: Table) -> bool:
    """`table` es el resto de `previa`, que Word cortó sin repetir el encabezado.

    Pasa 3 veces en el manual (páginas 157, 159 y 193) y T-104 no puede unirlas porque no hay
    encabezado que comparar. Se exige la página siguiente y filas de la misma forma: sin eso la
    tabla no se reconoce y no se lee.
    """
    return (
        bool(table.rows)
        and table.page == _ultima_pagina(previa.table) + 1
        and all(len(row.cells) == len(previa.columnas) for row in table.rows)
    )


def _tablas(doc: Document) -> list[_Tabla]:
    """Tablas de validaciones del documento, en orden, con la ruta de secciones que las ubica."""
    encontradas: list[_Tabla] = []
    ruta = _Ruta(encabezados=[], grupos=[])
    previa: _Tabla | None = None
    for block in doc.blocks:
        if isinstance(block, TextBlock):
            ruta.anotar(block)
            continue
        if not isinstance(block, Table):
            continue
        columnas = header_columns(block)
        if columnas is not None:
            previa = _Tabla(block, columnas, ruta.seccion, tuple(block.rows[1:]))
        elif previa is not None and _continua(previa, block):
            previa = _Tabla(block, previa.columnas, ruta.seccion, tuple(block.rows))
        else:
            previa = None
            continue
        encontradas.append(previa)
    return encontradas


def _mapa(row: Row, columnas: tuple[str, ...]) -> dict[str, Cell] | str:
    """Celdas de la fila por columna normalizada, o el motivo por el que no se puede leer."""
    cols = [cell.col for cell in row.cells]
    if len(row.cells) == len(columnas) and all(col is None for col in cols):
        # Sin columnas inferidas (otra ruta de extracción) el orden alcanza: hay tantas como el
        # encabezado, que es la misma regla que usa `tagged._assign_columns`.
        cols = list(range(len(columnas)))
    if any(col is None for col in cols):
        return "columnas-sin-inferir"
    if len(set(cols)) != len(cols):
        return "columna-repetida"
    if any(col is not None and not 0 <= col < len(columnas) for col in cols):
        return "columna-fuera-del-encabezado"
    return {columnas[col]: cell for col, cell in zip(cols, row.cells, strict=True) if col is not None}


@dataclass
class _Grupo:
    """Una ficha en construcción: la fila con la primera columna y sus filas de continuación."""

    filas: list[dict[str, Cell]]
    page: int


def _tramos(
    grupo: _Grupo, observaciones: Sequence[tuple[Run, ...]]
) -> list[tuple[str, int | None, tuple[Run, ...]]]:
    """Texto que la ficha guarda, en el orden de las columnas; las observaciones con su índice.

    Va por tramos (`Run`) y no por celdas porque un resaltado puede abarcar dos observaciones de
    la misma celda: partido así, cada mitad queda con el índice de la suya (H-3 de la auditoría).
    Una columna que trae de más una fila de continuación no está acá: no entra en la ficha (se
    reporta como anomalía), así que tampoco decide su estado ni aparece en sus cambios.
    """
    tenidos: list[tuple[str, int | None, tuple[Run, ...]]] = []
    for columna in COLUMNAS:
        if columna != "observaciones":
            cell = grupo.filas[0].get(columna)
            if cell is not None:
                tenidos.append((columna, None, tuple(cell.runs)))
            continue
        for indice, runs in enumerate(observaciones):
            tenidos.append((columna, indice, runs))
    return tenidos


def _observaciones(grupo: _Grupo) -> list[tuple[Run, ...]]:
    """Observaciones de la ficha: las celdas de la columna, cada una partida por sus viñetas."""
    return [
        observacion
        for mapa in grupo.filas
        if (cell := mapa.get("observaciones")) is not None
        for observacion in _partir(cell)
    ]


def _partir(cell: Cell) -> list[tuple[Run, ...]]:
    """Celda → observaciones, conservando los tramos y sus marcas de cambio.

    Los saltos de línea que separan una observación de la siguiente son separadores y no van en
    ninguna de las dos; los de adentro (la continuación de una viñeta) se conservan. Las demás
    celdas salen enteras, así que juntas las observaciones dan el texto de la celda.
    """
    cortes = _cortes(cell.text)
    trozos: list[list[Run]] = [[]]
    inicio = 0
    for run in cell.runs:
        fin = inicio + len(run.text)
        anterior = 0
        for corte in [c - inicio for c in cortes if inicio <= c < fin]:
            trozos[-1].append(Run(run.text[anterior:corte], run.change))
            trozos.append([])
            anterior = corte + 1  # el salto separador no pertenece a ninguna observación
        trozos[-1].append(Run(run.text[anterior:], run.change))
        inicio = fin
    return [
        tuple(run for run in trozo if run.text)
        for trozo in trozos
        if runs_text(trozo).strip()  # una observación en blanco no es una observación
    ]


def _cortes(texto: str) -> list[int]:
    """Posiciones de los saltos de línea que abren otra observación: los que preceden viñeta."""
    return [
        salto.start()
        for salto in re.finditer("\n", texto)
        if VINETA.match(texto[salto.end() :].split("\n", 1)[0].lstrip())
    ]


def _estado(tenidos: Sequence[tuple[str, int | None, tuple[Run, ...]]]) -> str | None:
    """Estado de la ficha según los resaltados de todo su texto no-espacio.

    El `N° Val` solo vota cuando está resaltado: al agregar una validación el autor deja el
    número sin resaltar (83 de las 445 fichas traen todo el cuerpo en verde y el número sin
    marca; si votara, esas 83 altas se leerían como 'modificado'). Al darla de baja sí lo
    resalta, y esas 25 fichas siguen saliendo 'eliminado'.
    """
    marcas = {
        run.change
        for columna, _, runs in tenidos
        for run in runs
        if run.text.strip() and not (columna == "numero" and run.change is None)
    }
    if not marcas - {None}:  # sin resaltados (o ficha sin texto): nada cambió
        return None
    if marcas == {Change.DELETED}:
        return "eliminado"
    if marcas == {Change.ADDED}:
        return "agregado"
    return "modificado"


def _cambios(
    tenidos: Sequence[tuple[str, int | None, tuple[Run, ...]]],
) -> tuple[ValidationChange, ...]:
    """Tramos resaltados de la ficha, columna por columna. Los espacios sueltos no son contenido.

    `indice` es el de la observación que contiene el tramo, porque los tramos ya vienen partidos
    por observación: `observaciones[cambio.indice]` siempre contiene `cambio.texto`.
    """
    return tuple(
        ValidationChange(columna, indice, run.change.value, run.text.strip())
        for columna, indice, runs in tenidos
        for run in runs
        if run.change is not None and run.text.strip()
    )


def _ficha(grupo: _Grupo, tabla: _Tabla, doc: Document) -> ValidationRecord:
    observaciones = _observaciones(grupo)
    tenidos = _tramos(grupo, observaciones)
    principal = grupo.filas[0]
    presentes = {columna for mapa in grupo.filas for columna in mapa}
    valores = {
        columna: principal[columna].text if columna in principal else ""
        for columna in ValidationRecord.SIMPLES
    }
    return ValidationRecord(
        **valores,
        observaciones=tuple(runs_text(list(runs)) for runs in observaciones),
        seccion=tabla.seccion,
        ausentes=tuple(columna for columna in COLUMNAS if columna in REQUERIDAS - presentes),
        estado=_estado(tenidos),
        cambios=_cambios(tenidos),
        pdf_page=grupo.page,
        source=doc.source,
        sha256=doc.sha256,
    )


def _anomalia(motivo: str, pares: Sequence[tuple[str, Cell]], page: int, doc: Document) -> RowAnomaly:
    return RowAnomaly(
        motivo=motivo,
        columnas=tuple(columna for columna, _ in pares),
        textos=tuple(cell.text for _, cell in pares),
        pdf_page=page,
        source=doc.source,
        sha256=doc.sha256,
    )


@dataclass(frozen=True)
class _Lectura:
    """Lo que salió de recorrer el documento una vez."""

    fichas: tuple[ValidationRecord, ...]
    anomalias: tuple[RowAnomaly, ...]
    tablas: int
    continuadas: tuple[int, ...]  # páginas de las tablas sin encabezado repetido


def _leer(doc: Document) -> _Lectura:
    """Recorre las tablas de validaciones y arma las fichas y las anomalías de una sola pasada."""
    fichas: list[ValidationRecord] = []
    anomalias: list[RowAnomaly] = []
    tablas = _tablas(doc)
    continuadas = tuple(t.table.page for t in tablas if header_columns(t.table) is None)
    for tabla in tablas:
        abierto: _Grupo | None = None
        for row in tabla.cuerpo:
            page = row.page if row.page is not None else tabla.table.page
            mapa = _mapa(row, tabla.columnas)
            if isinstance(mapa, str):
                # Fila ilegible: ni se sabe qué columna es cada celda, ni si abre una ficha o
                # continúa la anterior. Se avisa con la fila entera y la ficha abierta sigue.
                anomalias.append(
                    RowAnomaly(
                        motivo=mapa,
                        columnas=(),
                        textos=tuple(cell.text for cell in row.cells),
                        pdf_page=page,
                        source=doc.source,
                        sha256=doc.sha256,
                    )
                )
                continue
            if tabla.columnas[0] in mapa:
                # Trae la primera columna: empieza otra ficha (D-009).
                if abierto is not None:
                    fichas.append(_ficha(abierto, tabla, doc))
                abierto = _Grupo(filas=[mapa], page=page)
                continue
            if abierto is None:
                # Continuación al principio de la tabla: su ficha quedó en la página anterior y
                # nadie unió las tablas (T-104). No se pega por cuenta propia.
                anomalias.append(_anomalia("continuacion-sin-ficha", list(mapa.items()), page, doc))
                continue
            de_mas = [
                (columna, cell)
                for columna, cell in mapa.items()
                if columna != "observaciones" and cell.text.strip()
            ]
            if de_mas:
                anomalias.append(_anomalia("continuacion-con-columnas-de-mas", de_mas, page, doc))
            observacion = mapa.get("observaciones")
            abierto.filas.append({} if observacion is None else {"observaciones": observacion})
        if abierto is not None:
            fichas.append(_ficha(abierto, tabla, doc))
    return _Lectura(tuple(fichas), tuple(anomalias), len(tablas), continuadas)


def validation_records(doc: Document) -> list[ValidationRecord]:
    """Una ficha por validación de las tablas de validaciones del documento."""
    return list(_leer(doc).fichas)


def validation_anomalies(doc: Document) -> list[RowAnomaly]:
    """Filas de tablas de validaciones que no entraron en ninguna ficha."""
    return list(_leer(doc).anomalias)


def check_validations(records: Sequence[ValidationRecord]) -> list[Issue]:
    """V5 — esquema de las validaciones. Devuelve las incidencias; no toca ningún dato."""
    issues: list[Issue] = []
    for r in records:
        if not ID_VALIDACION.match(r.id):
            issues.append(_issue("id-formato", r, f"ID {r.id!r} fuera de {ID_VALIDACION.pattern}"))
        if not CODIGO.match(r.codigo):
            issues.append(_issue("codigo-no-numerico", r, f"código {r.codigo!r} no es numérico"))
        if not r.efecto:
            issues.append(_issue("efecto-vacio", r, "columna E vacía en el PDF"))
        elif r.efecto not in EFECTOS:
            observados = ", ".join(sorted(EFECTOS))
            issues.append(
                _issue(
                    "efecto-desconocido",
                    r,
                    f"efecto {r.efecto!r} fuera de la leyenda del manual ({observados})",
                )
            )
        if r.ausentes:
            faltan = ", ".join(r.ausentes)
            issues.append(
                _issue(
                    "columna-ausente",
                    r,
                    f"la fila no trae la columna {faltan}: está en otra página o no existe",
                )
            )
    return issues + _duplicados(records)


def _issue(check: str, record: ValidationRecord, detalle: str) -> Issue:
    return Issue(check=check, id=record.id, pdf_page=record.pdf_page, detalle=detalle)


def _duplicados(records: Sequence[ValidationRecord]) -> list[Issue]:
    """IDs repetidos. Una ficha eliminada más otra vigente con el mismo ID es un reemplazo
    legítimo del documento (el MT deja impreso lo que quita), así que se reporta aparte."""
    por_id: dict[str, list[ValidationRecord]] = {}
    for record in records:
        por_id.setdefault(record.id, []).append(record)
    issues = []
    for validacion_id, filas in sorted(por_id.items()):
        if len(filas) < 2:
            continue
        eliminadas = sum(1 for r in filas if r.estado == "eliminado")
        reemplazo = 0 < eliminadas < len(filas)
        detalle = "; ".join(f"página PDF {r.pdf_page} ({r.estado or 'sin cambio'})" for r in filas)
        issues.append(
            Issue(
                check="id-duplicado-reemplazo" if reemplazo else "id-duplicado",
                id=validacion_id,
                pdf_page=filas[0].pdf_page,
                detalle=f"{len(filas)} fichas con el ID {validacion_id!r}: {detalle}",
            )
        )
    return issues


def to_json(doc: Document, pages: Iterable[int] | None = None) -> str:
    """Serialización determinista de las validaciones, sus incidencias V5 y las filas anómalas."""
    lectura = _leer(doc)
    estados: dict[str, int] = {}
    efectos: dict[str, int] = {}
    for ficha in lectura.fichas:
        clave = ficha.estado or "sin_cambio"
        estados[clave] = estados.get(clave, 0) + 1
        efectos[ficha.efecto or "vacio"] = efectos.get(ficha.efecto or "vacio", 0) + 1
    paginas = sorted(set(pages)) if pages is not None else sorted({f.pdf_page for f in lectura.fichas})
    datos = {
        "anomalias": [a.to_dict() for a in lectura.anomalias],
        "incidencias": [i.to_dict() for i in check_validations(lectura.fichas)],
        "procedencia": {
            "efectos": efectos,
            "estados": estados,
            "extractor": doc.extractor,
            "paginas_pdf": paginas,
            "sha256": doc.sha256,
            "source": doc.source,
            "tablas": lectura.tablas,
            "tablas_sin_encabezado": list(lectura.continuadas),
            "total_validaciones": len(lectura.fichas),
        },
        "validaciones": [f.to_dict() for f in lectura.fichas],
    }
    return json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True)


def _page_range(value: str) -> range:
    """`151-154` o `163` → rango de páginas PDF (base 1)."""
    first, dash, last = value.partition("-")
    try:
        start, end = int(first), int(last if dash else first)
    except ValueError:
        start, end = 0, -1
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError(f"rango de páginas inválido: {value!r} (ej.: 151-154)")
    return range(start, end + 1)


def main() -> None:
    from sifen_kb.pdf.pipeline import load

    parser = argparse.ArgumentParser(description="Tablas de validaciones del MT SIFEN → validaciones.json")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", type=_page_range, required=True, help="rango PDF, p. ej. 151-154")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"no existe el PDF: {args.pdf}")
    doc = load(args.pdf, pages=args.pages, sifen=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(to_json(doc, pages=args.pages), encoding="utf-8")
    lectura = _leer(doc)
    issues = check_validations(lectura.fichas)
    print(
        f"{len(lectura.fichas)} validaciones en {lectura.tablas} tablas, "
        f"{len(lectura.anomalias)} filas anómalas, {len(issues)} V5"
    )


if __name__ == "__main__":
    main()

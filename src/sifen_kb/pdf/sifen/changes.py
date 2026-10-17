# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""T-302 — `cambios.json`: libro de cambios de las Notas Técnicas sobre el MT V150.

Cada fila de una tabla de campos o de validaciones de una NT se empareja por ID (y por tipo: un
campo y una validación pueden compartir ID, como H018) con la fila vigente del MT V150 y queda
como un cambio con su NT, sus fechas de vigencia, la página del MT que la NT cita, el `antes`
(MT) y el `despues` (NT). Decisiones del usuario (2026-09-28):

- Alcance: campos y validaciones. Las demás tablas (codificaciones, esquemas de WS, cuadros) y
  los puntos de texto que citan página van a `otros`, con NT y página, sin emparejar.
- Tipo de cambio: si la fila tiene resaltados, manda el color (misma regla que el MT). Sin
  color —NT-014, 015, 020 y 022 no traen ninguno— se compara con el MT: ID ausente (y no agregado
  por una NT anterior) → agregado; presente → modificado, con las columnas que difieren. El verbo
  del título ('se agrega', 'se modifica', 'se elimina') queda como evidencia y solo decide la baja
  de una fila sin color; si contradice el tipo, alerta.
- `antes` es siempre la fila vigente del MT V150 (sin lo tachado); cada cambio nombra las NT
  anteriores que tocaron el mismo ID. El estado encadenado es de T-303.

Nada se inventa: una fila que no se puede emparejar o una cita que no coincide va a `alertas`.
El MT V150 es del 10/09/2019, anterior a todas las NT, y las NT son acumulativas.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from sifen_kb.pdf.ir import Change, Document, Figure, Row, Table, TextBlock
from sifen_kb.pdf.sifen.fields import (
    DESPLAZAMIENTO_IMPRESO,
    FieldRecord,
    field_records,
    is_field_table,
)
from sifen_kb.pdf.sifen.validations import (
    COLUMNAS as COLUMNAS_VALIDACION,
)
from sifen_kb.pdf.sifen.validations import (
    ValidationRecord,
    header_columns,
    validation_records,
)

# 'NOTA TÉCNICA N° 20', 'NOTA TÉCNICA Nº 16', 'Nota Técnica Número 1'.
_NUMERO = re.compile(r"NOTA\s+T[ÉE]CNICA\s+(?:N[°º]|N[úu]mero)\s*(\d+)", re.IGNORECASE)
_FECHA_NUMERICA = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
_FECHA_TEXTO = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+del?\s+(\d{4})", re.IGNORECASE)
_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "setiembre": 9,  # grafía de NT-023
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_VIGENCIA = re.compile(
    r"Fecha puesta a disposici[óo]n para el Ambiente de (Test|Producci[óo]n)", re.IGNORECASE
)

# Cita de página del MT: '(Página 86)', '(Páginas 165, 166, 167, 189)', '(Página 90 y 91)',
# 'Páginas: 152.' (NT-016). Las páginas son las impresas del MT.
_CITA = re.compile(r"P[áa]ginas?\s*:?\s*(\d+(?:\s*(?:,|y|-|al)\s*\d+)*)", re.IGNORECASE)
_TRAMO = re.compile(r"(\d+)(?:\s*(?:-|al)\s*(\d+))?")
# Párrafo que es solo una cita: NT-016 la escribe debajo de la tabla.
_SOLO_CITA = re.compile(r"\(?\s*P[áa]ginas?\s*:?\s*[\d\s,y-]+\)?\s*\.?", re.IGNORECASE)
# Punto numerado de la NT ('1.1. En …', '1.1 Se agrega …', '3. 1. Se amplía …', '1- Especifica…'):
# abre el contexto de las tablas que siguen.
_NUMERADO = re.compile(r"\d+(?:\s?[.-]\s?\d+)*[.-]?\s+\S")

# Verbos del título, por tipo de cambio. Solo la forma conjugada ('se agrega', 'SE MODIFICAN',
# 'se Corrige'): la palabra suelta engaña ('incluidos impuestos' en NT-001, 'ACTUALIZACIÓN DE
# DATOS' en NT-018 es el nombre de un evento).
_VERBOS = {
    "agregado": re.compile(r"\bse\s+(agreg|incorpor|inclu[iy]|adicion|ampl[íi])", re.IGNORECASE),
    "modificado": re.compile(r"\bse\s+(modific|ajust|corrig|actualiz|reemplaz|sustitu)", re.IGNORECASE),
    "eliminado": re.compile(r"\bse\s+(elimin|suprim|quit)", re.IGNORECASE),
}
# ID de una fila de campos o de validaciones: 1 a 6 mayúsculas, 2 o 3 dígitos y un sufijo opcional
# (D208, AA01, GENFE002a). Los esquemas de WS ('ASch03') no llegan acá: no son tablas de campos.
_ID = re.compile(r"^[A-Z]{1,6}\d{2,3}[a-z]?$")


@dataclass(frozen=True)
class NoteInfo:
    """Identidad y vigencia de una NT. Las NT 001-012 no traen fechas de Test/Producción."""

    numero: int | None
    fecha: str | None  # 'Fecha:' de la NT, ISO
    periodo: tuple[str, str] | None  # 'Cambios desde la fecha X al Y' (NT antiguas), ISO
    vigencia_test: str | None
    vigencia_prod: str | None
    source: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "numero": self.numero,
            "fecha": self.fecha,
            "periodo": list(self.periodo) if self.periodo else None,
            "vigencia_test": self.vigencia_test,
            "vigencia_prod": self.vigencia_prod,
            "source": self.source,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class Cambio:
    """Una fila de campo o validación de una NT, emparejada con el MT."""

    nt: int
    tipo: str  # 'campo' | 'validacion'
    id: str
    cambio: str  # 'agregado' | 'modificado' | 'eliminado' | 'sin_cambio'
    # Lo que decidió el tipo: {'color': estado por resaltado o None, 'verbos': [...], 'en_mt': bool}
    evidencia: dict[str, object]
    contexto: str
    paginas_citadas: tuple[int, ...]  # impresas del MT, tal como las cita la NT
    nt_pdf_page: int
    mt_pdf_page: int | None
    antes: dict[str, object] | None  # fila vigente del MT; None si el ID no está
    despues: dict[str, object] | None  # fila de la NT sin lo tachado; None si se elimina
    # Fila de la NT sin lo agregado: lo que la NT dice que había antes. Solo sirve en las columnas
    # sin tramos 'modified' (el amarillo muestra el texto nuevo, no el viejo).
    base: dict[str, object]
    columnas: tuple[str, ...]  # las que trae la tabla de la NT
    columnas_distintas: tuple[str, ...]  # columnas que trae la NT y difieren del MT
    marcas: tuple[dict[str, object], ...]  # tramos resaltados en la NT, por columna
    nt_previas: tuple[int, ...]  # NT anteriores que tocaron el mismo ID
    fecha_nt: str | None
    vigencia_test: str | None
    vigencia_prod: str | None
    source: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "nt": self.nt,
            "tipo": self.tipo,
            "id": self.id,
            "cambio": self.cambio,
            "evidencia": self.evidencia,
            "contexto": self.contexto,
            "paginas_citadas": list(self.paginas_citadas),
            "nt_pdf_page": self.nt_pdf_page,
            "mt_pdf_page": self.mt_pdf_page,
            "mt_printed_page": _impresa(self.mt_pdf_page),
            "antes": self.antes,
            "despues": self.despues,
            "base_nt": self.base,
            "columnas": list(self.columnas),
            "columnas_distintas": list(self.columnas_distintas),
            "marcas": list(self.marcas),
            "nt_previas": list(self.nt_previas),
            "fecha_nt": self.fecha_nt,
            "vigencia_test": self.vigencia_test,
            "vigencia_prod": self.vigencia_prod,
            "source": self.source,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class Otro:
    """Cambio de la NT fuera del alcance del emparejamiento: una tabla o un punto de texto."""

    nt: int
    encabezado: tuple[str, ...]  # primera fila de la tabla; () si es un punto de texto
    filas: int  # filas debajo del encabezado; 0 si es texto
    contexto: str
    paginas_citadas: tuple[int, ...]
    nt_pdf_page: int

    def to_dict(self) -> dict[str, object]:
        return {
            "nt": self.nt,
            "encabezado": list(self.encabezado),
            "filas": self.filas,
            "contexto": self.contexto,
            "paginas_citadas": list(self.paginas_citadas),
            "nt_pdf_page": self.nt_pdf_page,
        }


@dataclass(frozen=True)
class Alerta:
    """Algo que el libro no puede afirmar solo: va a revisión humana contra la imagen."""

    nt: int
    tipo: str
    id: str | None
    nt_pdf_page: int | None
    detalle: str

    def to_dict(self) -> dict[str, object]:
        return {
            "nt": self.nt,
            "tipo": self.tipo,
            "id": self.id,
            "nt_pdf_page": self.nt_pdf_page,
            "detalle": self.detalle,
        }


@dataclass
class LibroDeCambios:
    mt_source: str
    mt_sha256: str
    notas: list[NoteInfo] = field(default_factory=list)
    cambios: list[Cambio] = field(default_factory=list)
    otros: list[Otro] = field(default_factory=list)
    alertas: list[Alerta] = field(default_factory=list)


# --- Metadatos ----------------------------------------------------------------------------------


def _iso(texto: str) -> str | None:
    """Primera fecha del texto ('17/11/2023', '14-10-2019', '31 de enero del 2024') en ISO."""
    numerica = _FECHA_NUMERICA.search(texto)
    escrita = _FECHA_TEXTO.search(texto)
    if escrita and escrita.group(2).lower() in _MESES:
        if numerica is None or escrita.start() < numerica.start():
            dia, mes, anio = (
                int(escrita.group(1)),
                _MESES[escrita.group(2).lower()],
                escrita.group(3),
            )
            return f"{anio}-{mes:02d}-{dia:02d}"
    if numerica:
        dia, mes, anio = int(numerica.group(1)), int(numerica.group(2)), numerica.group(3)
        return f"{anio}-{mes:02d}-{dia:02d}"
    return None


def _lineas(doc: Document) -> Iterator[str]:
    """Texto de los párrafos y de cada fila de tabla (celdas unidas), en orden."""
    for block in doc.blocks:
        if isinstance(block, TextBlock):
            yield block.text
        elif isinstance(block, Table):
            for row in block.rows:
                yield " ".join(cell.text for cell in row.cells)


def note_info(doc: Document) -> NoteInfo:
    numero = fecha = test = prod = None
    periodo: tuple[str, str] | None = None
    for linea in _lineas(doc):
        if numero is None and (m := _NUMERO.search(linea)):
            numero = int(m.group(1))
        elif fecha is None and linea.lstrip().startswith("Fecha:"):
            fecha = _iso(linea)
        elif periodo is None and linea.lstrip().startswith("Cambios desde"):
            fechas = [_iso(m.group(0)) for m in _FECHA_NUMERICA.finditer(linea)]
            if len(fechas) == 2 and all(fechas):
                periodo = (str(fechas[0]), str(fechas[1]))
        if m := _VIGENCIA.search(linea):
            valor = _iso(linea[m.end() :])
            if m.group(1).lower() == "test":
                test = test or valor
            else:
                prod = prod or valor
    return NoteInfo(numero, fecha, periodo, test, prod, doc.source, doc.sha256)


def cited_pages(texto: str) -> tuple[int, ...]:
    """Páginas impresas del MT citadas en el texto, en orden y sin repetir; los rangos se abren."""
    paginas: list[int] = []
    for cita in _CITA.finditer(texto):
        for tramo in _TRAMO.finditer(cita.group(1)):
            desde = int(tramo.group(1))
            hasta = int(tramo.group(2) or desde)
            paginas.extend(range(desde, max(desde, hasta) + 1))
    return tuple(dict.fromkeys(paginas))


def _verbos(texto: str) -> set[str]:
    return {tipo for tipo, patron in _VERBOS.items() if patron.search(texto)}


# --- Lectura de filas ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fila:
    """Una fila de campo o validación, leída de la IR con sus tres lecturas del texto."""

    tipo: str  # 'campo' | 'validacion'
    id: str
    estado: str | None  # según los resaltados
    columnas: tuple[str, ...]  # las que trae la tabla
    valores: dict[str, object]  # texto vigente (sin lo tachado)
    base: dict[str, object]  # sin lo agregado: lo que el documento dice que había antes
    marcas: tuple[dict[str, object], ...]
    pdf_page: int


def _marca(tramo: Mapping[str, object]) -> dict[str, object]:
    return dict(tramo)


def _sin(table: Table, change: Change) -> Table:
    """La tabla sin los tramos de un tipo de cambio: sin los rojos, el texto vigente; sin los
    verdes, lo que había antes según el documento.

    El encabezado de una tabla de campos o validaciones queda como está: no es dato, y una tabla
    eliminada entera (MT pág. 151, tabla AB) lo trae en rojo; sin él la tabla no se reconocería.
    """
    reconocida = is_field_table(table) or header_columns(table) is not None
    rows = [
        row
        if reconocida and i == 0
        else Row(
            [replace(cell, runs=[r for r in cell.runs if r.change is not change]) for cell in row.cells],
            page=row.page,
        )
        for i, row in enumerate(table.rows)
    ]
    return replace(table, rows=rows)


def _sin_doc(doc: Document, change: Change) -> Document:
    blocks = [_sin(b, change) if isinstance(b, Table) else b for b in doc.blocks]
    return replace(doc, blocks=blocks)


def _campos(doc: Document) -> list[Fila]:
    return [
        Fila(
            tipo="campo",
            id=impresa.id.strip(),
            estado=impresa.estado,
            columnas=FieldRecord.COLUMNAS,
            valores={c: getattr(vigente, c) for c in FieldRecord.COLUMNAS},
            base={c: getattr(base, c) for c in FieldRecord.COLUMNAS},
            marcas=tuple(_marca(c.to_dict()) for c in impresa.cambios),
            pdf_page=impresa.pdf_page,
        )
        for impresa, vigente, base in zip(
            field_records(doc),
            field_records(_sin_doc(doc, Change.DELETED)),
            field_records(_sin_doc(doc, Change.ADDED)),
            strict=True,
        )
    ]


def _valores_validacion(record: ValidationRecord) -> dict[str, object]:
    return {
        c: list(record.observaciones) if c == "observaciones" else getattr(record, c)
        for c in COLUMNAS_VALIDACION
    }


def _validaciones(doc: Document, columnas: tuple[str, ...] = COLUMNAS_VALIDACION) -> list[Fila]:
    return [
        Fila(
            tipo="validacion",
            id=impresa.id.strip(),
            estado=impresa.estado,
            columnas=columnas,
            valores=_valores_validacion(vigente),
            base=_valores_validacion(base),
            marcas=tuple(_marca(c.to_dict()) for c in impresa.cambios),
            pdf_page=impresa.pdf_page,
        )
        for impresa, vigente, base in zip(
            validation_records(doc),
            validation_records(_sin_doc(doc, Change.DELETED)),
            validation_records(_sin_doc(doc, Change.ADDED)),
            strict=True,
        )
    ]


# --- Esquemas de WS y de firma (D-021) -----------------------------------------------------------

# Tablas de los esquemas XML de los WS y de la firma (MT págs. PDF 39-57): como las de campos pero
# sin 'Grupo'. Dos formatos: 8 columnas (WS) y 6 (firma, sin tipo ni longitud; su columna
# 'Descripción' trae en realidad el tipo G/A/E, y se conserva tal como está impresa).
COLUMNAS_ESQUEMA: tuple[str, ...] = (
    "id",
    "campo",
    "descripcion",
    "nodo_padre",
    "tipo_dato",
    "longitud",
    "ocurrencia",
    "observaciones",
)
_TITULOS_ESQUEMA = {
    "id": "id",
    "campo": "campo",
    "descripción": "descripcion",
    "descripcion": "descripcion",
    "nodopadre": "nodo_padre",
    "tipodato": "tipo_dato",
    "longitud": "longitud",
    "long.": "longitud",
    "ocu": "ocurrencia",
    "ocu.": "ocurrencia",
    "ocurrencia": "ocurrencia",
    "observaciones": "observaciones",
    "obs": "observaciones",
    "obs.": "observaciones",
}
# 'Schema XML 2: siRecepDE_v150.xsd (WS Recepción DE)'; el de la firma trae un espacio en el nombre
# ('xmldsig-core-schema- v150.xsd').
_ESQUEMA = re.compile(r"Schema XML\s*(\d+)\s*:\s*(.+?\.xsd)", re.IGNORECASE)
# ID de esquema: mayúsculas y minúsculas (ASch03, ContDE01, CRSch055, PP053, XS02).
_ID_ESQUEMA = re.compile(r"^[A-Z][A-Za-z]{0,7}\d{2,3}[a-z]?$")


def _columnas_esquema(table: Table) -> tuple[str, ...] | None:
    if not table.rows or is_field_table(table):
        return None
    columnas = tuple(_TITULOS_ESQUEMA.get("".join(c.text.split()).lower(), "") for c in table.rows[0].cells)
    if "" in columnas or len(set(columnas)) != len(columnas) or columnas[:2] != ("id", "campo"):
        return None
    return columnas if {"nodo_padre", "ocurrencia"} <= set(columnas) else None


def is_schema_table(table: Table) -> bool:
    """True si la primera fila es el encabezado de una tabla de esquema de WS o de firma."""
    return _columnas_esquema(table) is not None


def _esquema_en(texto: str) -> str:
    """El último 'Schema XML n: archivo.xsd' del texto, normalizado; '' si no hay."""
    todos = list(_ESQUEMA.finditer(texto))
    return f"Schema XML {todos[-1].group(1)}: {todos[-1].group(2).strip()}" if todos else ""


def _filas_esquema(table: Table, esquema: str) -> list[Fila]:
    """Filas de una tabla de esquema. Una fila de otro ancho queda sin ID: no se adivina."""
    columnas = _columnas_esquema(table) or ()
    filas = []
    for row in table.rows[1:]:
        page = row.page if row.page is not None else table.page
        if len(row.cells) != len(columnas):
            filas.append(Fila("esquema", "", None, columnas, {}, {}, (), page))
            continue
        vigente: dict[str, object] = {c: "" for c in COLUMNAS_ESQUEMA}
        vigente["esquema"] = esquema
        base: dict[str, object] = dict(vigente)
        marcas: list[dict[str, object]] = []
        estados: set[Change | None] = set()
        for columna, cell in zip(columnas, row.cells, strict=True):
            vigente[columna] = "".join(r.text for r in cell.runs if r.change is not Change.DELETED)
            base[columna] = "".join(r.text for r in cell.runs if r.change is not Change.ADDED)
            for run in cell.runs:
                if run.text.strip():
                    estados.add(run.change)
                    if run.change is not None:
                        marcas.append(
                            {
                                "columna": columna,
                                "change": run.change.value,
                                "texto": run.text.strip(),
                            }
                        )
        codigo = "".join(r.text for r in row.cells[0].runs).strip()
        filas.append(
            Fila("esquema", codigo, _estado_de(estados), columnas, vigente, base, tuple(marcas), page)
        )
    return filas


def _estado_de(marcas: set[Change | None]) -> str | None:
    if not marcas - {None}:
        return None
    if marcas == {Change.DELETED}:
        return "eliminado"
    if marcas == {Change.ADDED}:
        return "agregado"
    return "modificado"


def _esquemas(doc: Document) -> list[Fila]:
    """Filas de las tablas de esquema del documento, cada una con el esquema que la titula."""
    filas: list[Fila] = []
    esquema = ""
    for block in doc.blocks:
        if isinstance(block, TextBlock):
            esquema = _esquema_en(block.text) or esquema
        elif isinstance(block, Table) and is_schema_table(block):
            filas.extend(_filas_esquema(block, esquema))
    return filas


def mt_rows(mt: Document) -> list[Fila]:
    """Filas vigentes del MT en su orden: campos, validaciones y esquemas. Las eliminadas en el
    propio MT (tachadas en la V150) no son vigentes y no están."""
    todas = [*_campos(mt), *_validaciones(mt), *_esquemas(mt)]
    return [f for f in todas if f.estado != "eliminado" and f.id]


@dataclass(frozen=True)
class _EnMT:
    fila: Fila
    repetidas: tuple[int, ...]  # páginas PDF de otras filas vigentes con el mismo ID
    inicio_tabla: int  # página PDF donde empieza la tabla del MT que contiene la fila


def _indice_mt(mt: Document) -> dict[tuple[str, str], _EnMT]:
    """Filas vigentes del MT por (tipo, ID). Una fila eliminada en el MT no es un 'antes'."""
    inicios = sorted(
        b.page
        for b in mt.blocks
        if isinstance(b, Table) and (is_field_table(b) or header_columns(b) is not None or is_schema_table(b))
    )
    por_clave: dict[tuple[str, str], list[Fila]] = {}
    for fila in mt_rows(mt):
        por_clave.setdefault((fila.tipo, fila.id), []).append(fila)
    return {
        clave: _EnMT(
            filas[0],
            tuple(f.pdf_page for f in filas[1:]),
            max((p for p in inicios if p <= filas[0].pdf_page), default=filas[0].pdf_page),
        )
        for clave, filas in por_clave.items()
    }


# --- Contexto de cada tabla ---------------------------------------------------------------------


@dataclass(frozen=True)
class TablaNT:
    table: Table
    contexto: str
    verbos: frozenset[str]
    paginas: tuple[int, ...]


def _es_vigencia(table: Table) -> bool:
    return bool(table.rows) and bool(_VIGENCIA.search(" ".join(c.text for c in table.rows[0].cells)))


def _es_historial(table: Table) -> bool:
    return bool(table.rows and table.rows[0].cells) and (
        table.rows[0].cells[0].text.strip().upper() == "AUTOR"
    )


def _texto(blocks: Sequence[TextBlock]) -> str:
    return "\n".join(b.text for b in blocks)


@dataclass(frozen=True)
class _Punto:
    """Un punto de texto de la NT que no es tabla: su primer bloque y los párrafos que lo siguen."""

    bloque: TextBlock
    texto: str
    paginas: tuple[int, ...]


# Título fijo del final de cada NT: ahí termina el último punto.
_HISTORIAL = "Histórico del Documento"


def _numero(texto: str) -> int:
    """Primer número de un punto numerado ('3.1. Se …' → 3); 0 si no empieza con número."""
    cifras = re.match(r"\d+", texto.strip())
    return int(cifras.group(0)) if cifras else 0


def _parrafos(blocks: Sequence[object], i: int, tope: int) -> tuple[list[TextBlock | Figure], bool]:
    """Los párrafos que siguen al bloque `i` hasta el punto siguiente, y si ahí empieza una tabla.

    El punto siguiente es un numerado **mayor** que `tope` (el punto que gobierna): una lista
    '1.', '2.' dentro del punto 4 de NT-010 es contenido, el '5.' no.
    """
    parrafos: list[TextBlock | Figure] = []
    for block in blocks[i + 1 :]:
        if isinstance(block, Table):
            return parrafos, True
        if isinstance(block, Figure):
            parrafos.append(block)  # el contenido puede estar en la imagen (NT-010 6.1)
            continue
        if not isinstance(block, TextBlock):
            continue
        texto = block.text.strip()
        if texto == _HISTORIAL or (_NUMERADO.match(texto) and _numero(texto) > tope):
            break
        parrafos.append(block)
    return parrafos, False


def _texto_punto(blocks: Sequence[TextBlock | Figure]) -> str:
    """Texto de un punto; una figura aporta el texto dibujado o, si no tiene, una nota con su
    página para ir a mirarla."""
    partes = []
    for b in blocks:
        if isinstance(b, Figure) and not b.text.strip():
            partes.append(f"[figura sin texto extraíble, pág. {b.page}]")
        else:
            partes.append(b.text)
    return "\n".join(partes)


def _puntos(doc: Document, usados: set[int]) -> list[_Punto]:
    """Puntos de texto que ninguna tabla explica: con cita de página o con un verbo de cambio.

    - Un párrafo con cita que ninguna tabla tomó (NT-010 3.1, URL del QR).
    - Un punto numerado sin cita que dice que cambia algo y trae párrafos propios, no una tabla
      (NT-019 5). Uno que solo agrupa subpuntos (NT-011 1.1) no trae párrafos: no entra.
    Cada punto lleva sus párrafos, hasta el punto siguiente.
    """
    puntos: list[_Punto] = []
    tomados: set[int] = set()
    tope = 0
    for i, block in enumerate(doc.blocks):
        if not isinstance(block, TextBlock):
            continue
        texto = block.text.strip()
        numerado = bool(_NUMERADO.match(texto))
        if numerado:
            tope = _numero(texto)
        if id(block) in tomados or id(block) in usados:
            continue
        paginas = cited_pages(texto)
        parrafos, a_tabla = _parrafos(doc.blocks, i, tope)
        con_cita = bool(paginas)
        con_verbo = numerado and bool(_verbos(texto)) and parrafos and not a_tabla
        if not (con_cita or con_verbo):
            continue
        tomados.update(id(b) for b in parrafos)
        puntos.append(_Punto(block, _texto_punto([block, *parrafos]), paginas))
    return puntos


def tablas_de_nota(doc: Document) -> list[TablaNT]:
    """Tablas de una NT (sin la de vigencia ni el historial) con su contexto y su cita."""
    return _recorrer(doc)[0]


def _recorrer(doc: Document) -> tuple[list[TablaNT], list[_Punto]]:
    """Tablas con su contexto y los puntos de texto que no quedaron en ninguna tabla.

    El contexto de una tabla va desde el último punto numerado. La cita que vale es la más
    cercana: la de los párrafos desde la tabla anterior; si no hay, la del punto; si tampoco, un
    párrafo que sea solo una cita justo debajo de la tabla (NT-016).
    """
    tablas: list[TablaNT] = []
    ventana: list[TextBlock] = []  # desde el último punto numerado
    recientes: list[TextBlock] = []  # desde la última tabla o punto numerado
    usados: set[int] = set()
    consumidos: set[int] = set()
    for i, block in enumerate(doc.blocks):
        if isinstance(block, TextBlock):
            if i in consumidos:
                continue
            if _NUMERADO.match(block.text.strip()):
                ventana, recientes = [block], [block]
            else:
                ventana.append(block)
                recientes.append(block)
            continue
        if not isinstance(block, Table) or _es_vigencia(block) or _es_historial(block):
            continue
        fuente = next((grupo for grupo in (recientes, ventana) if cited_pages(_texto(grupo))), [])
        siguiente = doc.blocks[i + 1] if i + 1 < len(doc.blocks) else None
        if not fuente and isinstance(siguiente, TextBlock):
            if _SOLO_CITA.fullmatch(siguiente.text.strip()):
                fuente = [siguiente]
                consumidos.add(i + 1)
        usados.update(id(b) for b in fuente)
        tablas.append(
            TablaNT(
                table=block,
                contexto=_texto(ventana),
                verbos=frozenset(_verbos(_texto(ventana))),
                paginas=cited_pages(_texto(fuente)),
            )
        )
        recientes = []
    return tablas, _puntos(doc, usados | {id(doc.blocks[i]) for i in consumidos})


# --- Libro --------------------------------------------------------------------------------------


def comparable(valor: object) -> str:
    """Texto para comparar celdas: una lista (observaciones) unida y los espacios colapsados."""
    texto = "\n".join(valor) if isinstance(valor, list) else str(valor)
    return " ".join(texto.split())


def _impresa(pdf_page: int | None) -> int | None:
    return None if pdf_page is None else pdf_page - DESPLAZAMIENTO_IMPRESO


def _filas_de(tabla: TablaNT, doc: Document) -> list[Fila] | None:
    """Filas de campos, validaciones o esquemas de la tabla; None si no es de ninguno."""
    sola = replace(doc, blocks=[tabla.table])
    if is_field_table(tabla.table):
        return _campos(sola)
    columnas = header_columns(tabla.table)
    if columnas is not None:
        return _validaciones(sola, columnas)
    if is_schema_table(tabla.table):
        return _filas_esquema(tabla.table, _esquema_en(tabla.contexto))
    return None


@dataclass
class _Historia:
    """Qué NT tocó cada (tipo, ID) y si alguna lo agregó."""

    tocadas: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    agregadas: dict[tuple[str, str], int] = field(default_factory=dict)


def libro_de_cambios(mt: Document, notas: Sequence[Document]) -> LibroDeCambios:
    indice = _indice_mt(mt)
    libro = LibroDeCambios(mt_source=mt.source, mt_sha256=mt.sha256)
    historia = _Historia()
    leidas = sorted(
        ((note_info(doc), doc) for doc in notas),
        key=lambda par: (par[0].numero is None, par[0].numero or 0, par[0].source),
    )
    fecha_previa: tuple[int, str] | None = None
    for info, doc in leidas:
        libro.notas.append(info)
        nt = info.numero if info.numero is not None else -1
        if info.numero is None:
            libro.alertas.append(Alerta(nt, "sin-numero", None, None, f"{info.source}: sin número"))
        if info.fecha and fecha_previa and info.fecha < fecha_previa[1]:
            detalle = f"fecha {info.fecha} anterior a la de la NT {fecha_previa[0]} ({fecha_previa[1]})"
            libro.alertas.append(Alerta(nt, "orden-fechas", None, None, detalle))
        if info.fecha:
            fecha_previa = (nt, info.fecha)
        tablas, sueltos = _recorrer(doc)
        for tabla in tablas:
            filas = _filas_de(tabla, doc)
            if filas is None:
                libro.otros.append(
                    Otro(
                        nt=nt,
                        encabezado=tuple(c.text for c in tabla.table.rows[0].cells)
                        if tabla.table.rows
                        else (),
                        filas=max(len(tabla.table.rows) - 1, 0),
                        contexto=tabla.contexto,
                        paginas_citadas=tabla.paginas,
                        nt_pdf_page=tabla.table.page,
                    )
                )
                continue
            for fila in filas:
                _registrar(libro, fila, tabla, info, nt, indice, historia)
        for punto in sueltos:
            libro.otros.append(Otro(nt, (), 0, punto.texto, punto.paginas, punto.bloque.page))
    return libro


def _color(fila: Fila) -> str | None:
    """Estado por resaltado. El ID tachado da de baja la fila aunque quede una columna sin tachar
    (NT-002 D208d y D210a: todo en rojo salvo la columna E); el ID en verde la da de alta."""
    en_id = {m["change"] for m in fila.marcas if m["columna"] == "id"}
    if en_id == {"deleted"}:
        return "eliminado"
    if en_id == {"added"}:
        return "agregado"
    return fila.estado


def _coherente(cambio: str, color: str | None, verbos: frozenset[str], fila: Fila) -> bool:
    """El verbo del título no contradice el cambio de la fila."""
    if not verbos or cambio in verbos:
        return True
    if color is not None and "modificado" in verbos:
        # 'se modifican los siguientes campos' titula secciones con filas enteras en verde o en
        # rojo (NT-019, NT-023): con color, la fila no deja dudas.
        return True
    marcas = {m["change"] for m in fila.marcas}
    # 'se elimina la siguiente observación' (NT-010) es una fila modificada por tachado; igual
    # 'se agrega' con texto en verde dentro de una fila que ya existía.
    return cambio == "modificado" and (
        ("eliminado" in verbos and "deleted" in marcas) or ("agregado" in verbos and "added" in marcas)
    )


def _cita_coincide(paginas: tuple[int, ...], en_mt: _EnMT) -> bool:
    """La página citada es la de la fila o una entre el comienzo de su tabla y la fila: la NT suele
    citar dónde empieza la tabla del MT (NT-001 cita la 103 para F034, que cae en la 104)."""
    fila = en_mt.fila.pdf_page - DESPLAZAMIENTO_IMPRESO
    inicio = en_mt.inicio_tabla - DESPLAZAMIENTO_IMPRESO
    return any(inicio <= p <= fila for p in paginas)


def _registrar(
    libro: LibroDeCambios,
    fila: Fila,
    tabla: TablaNT,
    info: NoteInfo,
    nt: int,
    indice: dict[tuple[str, str], _EnMT],
    historia: _Historia,
) -> None:
    def alerta(tipo: str, detalle: str) -> None:
        libro.alertas.append(Alerta(nt, tipo, fila.id or None, fila.pdf_page, detalle))

    if not (_ID_ESQUEMA if fila.tipo == "esquema" else _ID).match(fila.id):
        textos = " | ".join(comparable(v) for v in fila.valores.values() if comparable(v))
        alerta("id-invalido", f"fila de {fila.tipo} sin ID reconocible: {textos[:200]}")
        return
    clave = (fila.tipo, fila.id)
    en_mt = indice.get(clave)
    tocadas = historia.tocadas.get(clave, [])
    previas = tuple(n for n in dict.fromkeys(tocadas) if n != nt)
    # Una fila anterior de esta misma NT con el mismo ID (NT-014 trae dos GENFE012) no hace que
    # el ID exista antes de la NT.
    agregada_por = historia.agregadas.get(clave)
    agregada_antes = agregada_por if agregada_por != nt else None
    color = _color(fila)
    if color is not None:
        cambio = color
    elif tabla.verbos == {"eliminado"}:
        cambio = "eliminado"
    elif en_mt is not None or agregada_antes is not None:
        cambio = "modificado"
    else:
        cambio = "agregado"

    antes = en_mt.fila.valores if en_mt else None
    despues = None if cambio == "eliminado" else fila.valores
    distintas: tuple[str, ...] = ()
    if antes is not None and despues is not None:
        distintas = tuple(
            c for c in fila.columnas if comparable(antes.get(c, "")) != comparable(despues.get(c, ""))
        )
    if cambio == "modificado" and color is None and antes is not None and not distintas:
        # NT-019 repite la raíz del evento (GEN001) como contexto de la fila que sí cambia.
        cambio = "sin_cambio"
        alerta("sin-diferencia", f"{fila.id} sin resaltados e igual a la fila del MT")

    if cambio in ("modificado", "eliminado") and en_mt is None and agregada_antes is None:
        alerta(
            "id-no-existe",
            f"{fila.tipo} {fila.id} {cambio} pero no está en el MT ni en una NT previa",
        )
    if cambio == "agregado" and (en_mt is not None or agregada_antes is not None):
        donde = f"MT página PDF {en_mt.fila.pdf_page}" if en_mt else f"NT {agregada_antes}"
        alerta("agregado-ya-existe", f"{fila.tipo} {fila.id} agregado pero ya existe ({donde})")
    if cambio != "sin_cambio" and not _coherente(cambio, color, tabla.verbos, fila):
        verbos = ", ".join(sorted(tabla.verbos))
        alerta("verbo-contradice", f"el título dice {verbos}; la fila resulta {cambio}")
    if en_mt is not None and tabla.paginas and not _cita_coincide(tabla.paginas, en_mt):
        citadas = ", ".join(str(p) for p in tabla.paginas)
        alerta(
            "pagina-no-coincide",
            f"la NT cita la página {citadas}; en el MT {fila.id} está en la impresa "
            f"{_impresa(en_mt.fila.pdf_page)} (PDF {en_mt.fila.pdf_page})",
        )
    if en_mt is not None and en_mt.repetidas:
        otras = ", ".join(str(p) for p in en_mt.repetidas)
        alerta("mt-duplicado", f"el MT tiene otras filas vigentes con {fila.id} (PDF {otras})")
    if nt in tocadas:
        alerta("id-repetido-en-nt", f"{fila.id} aparece más de una vez en la NT {nt}")
    if previas:
        alerta("varias-nt", f"{fila.id} también lo tocan las NT {', '.join(map(str, previas))}")

    libro.cambios.append(
        Cambio(
            nt=nt,
            tipo=fila.tipo,
            id=fila.id,
            cambio=cambio,
            evidencia={
                "color": color,
                "verbos": sorted(tabla.verbos),
                "en_mt": en_mt is not None,
                "agregado_por_nt": agregada_antes,
            },
            contexto=tabla.contexto,
            paginas_citadas=tabla.paginas,
            nt_pdf_page=fila.pdf_page,
            mt_pdf_page=en_mt.fila.pdf_page if en_mt else None,
            antes=antes,
            despues=despues,
            base=fila.base,
            columnas=fila.columnas,
            columnas_distintas=distintas,
            marcas=fila.marcas,
            nt_previas=previas,
            fecha_nt=info.fecha,
            vigencia_test=info.vigencia_test,
            vigencia_prod=info.vigencia_prod,
            source=info.source,
            sha256=info.sha256,
        )
    )
    historia.tocadas.setdefault(clave, []).append(nt)
    if cambio == "agregado" and agregada_por is None:
        historia.agregadas[clave] = nt


# --- Serialización y CLI ------------------------------------------------------------------------


def _cuenta(valores: Sequence[str]) -> dict[str, int]:
    cuenta: dict[str, int] = {}
    for valor in valores:
        cuenta[valor] = cuenta.get(valor, 0) + 1
    return cuenta


def to_json(libro: LibroDeCambios) -> str:
    datos = {
        "procedencia": {
            "mt_source": libro.mt_source,
            "mt_sha256": libro.mt_sha256,
            "notas": len(libro.notas),
            "cambios": _cuenta([f"{c.tipo}:{c.cambio}" for c in libro.cambios]),
            "otros": len(libro.otros),
            "alertas": _cuenta([a.tipo for a in libro.alertas]),
        },
        "notas": [n.to_dict() for n in libro.notas],
        "cambios": [c.to_dict() for c in libro.cambios],
        "otros": [o.to_dict() for o in libro.otros],
        "alertas": [a.to_dict() for a in libro.alertas],
    }
    return json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True)


def main() -> None:
    from sifen_kb.pdf.pipeline import load

    parser = argparse.ArgumentParser(description="NT SIFEN → libro de cambios sobre el MT V150")
    parser.add_argument("mt", type=Path, help="PDF del Manual Técnico V150")
    parser.add_argument("notas", type=Path, help="carpeta con los PDF de las Notas Técnicas")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.mt.is_file():
        parser.error(f"no existe el PDF: {args.mt}")
    pdfs = sorted(args.notas.glob("*.pdf"))
    if not pdfs:
        parser.error(f"no hay PDF en {args.notas}")
    mt = load(args.mt, sifen=True)
    libro = libro_de_cambios(mt, [load(pdf, sifen=True) for pdf in pdfs])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(to_json(libro), encoding="utf-8")
    alertas = _cuenta([a.tipo for a in libro.alertas])
    print(
        f"{len(libro.notas)} NT, {len(libro.cambios)} cambios, {len(libro.otros)} otros, "
        f"{len(libro.alertas)} alertas {alertas}"
    )


if __name__ == "__main__":
    main()

# Origen: pdf_to_md (mismo autor), commit 8603b5bd572fb0a1563e216d3ec658fb5666e678, integrado en sifen-kb bajo MIT.
"""Capa 3 — `campos.json`: un registro por campo XML del MT V150, con su estado de cambio.

Una entrada por fila de cuerpo de toda tabla cuyo encabezado sea el de 9 columnas de campos.
El estado de la fila (eliminado / agregado / modificado / None) se deduce de los resaltados que
la IR guarda por tramo de texto, y `cambios` deja por escrito **qué** columna y qué tramo cambió:
un campo como B006 solo tiene agregada una oración de las observaciones, y el agente que lea el
JSON necesita esa distinción para no dar por nuevo todo el campo.

Aquí también vive V4 (esquema de campos). V4 **reporta, no corrige** (D-005): el registro conserva
el valor tal como salió del PDF y la incidencia lo nombra; las correcciones irán a
`corrections.yaml`.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from sifen_kb.pdf.ir import Change, Document, Row, Table

# Encabezado de las tablas de formato de campos, tal como lo escribió el autor.
ENCABEZADO: tuple[str, ...] = (
    "Grupo",
    "ID",
    "Campo",
    "Descripción",
    "Nodo Padre",
    "Tipo Dato",
    "Longitud",
    "Ocurrencia",
    "Observaciones",
)
# Se compara sin espacios: 4 de las 87 tablas de campos (páginas 62-112) traen 'Longit ud' porque
# el título viene partido en dos líneas y la extracción inserta el hueco. Reconocer la tabla no es
# corregir un dato: es leer el encabezado que el autor escribió.
_CLAVE = tuple("".join(titulo.split()) for titulo in ENCABEZADO)
# Abreviaturas del mismo título (D-015): las tablas de eventos del MT (páginas PDF 121-123) y
# varias NT escriben 'Ocu' / 'Ocu.' por 'Ocurrencia', y NT-018 'Long.' por 'Longitud'. Una tabla
# sin 'Grupo' (esquemas de WS: 'ID', 'Campo', …) sigue sin ser de campos: no tiene 9 columnas.
_ALIAS: dict[str, frozenset[str]] = {
    "Longitud": frozenset({"Long."}),
    "Ocurrencia": frozenset({"Ocu", "Ocu."}),
}
_CLAVES = tuple(frozenset({clave}) | _ALIAS.get(clave, frozenset()) for clave in _CLAVE)

# La página impresa del MT va una atrás de la del PDF (portada sin numerar).
DESPLAZAMIENTO_IMPRESO = 1

# ID del campo. La arquitectura anotó `[A-J]\d{3}[a-z]?`, pero el MT usa también prefijos de dos
# letras para los subgrupos que agotaron la numeración (AA001-AA002, EA790 y demás): 18 de las 389
# filas de las páginas 62-112. Con `{1,2}` las 389 cumplen; con una sola letra fallarían esas 18.
ID_CAMPO = re.compile(r"^[A-J]{1,2}\d{3}[a-z]?$")
# Ocurrencia `mínimo-máximo`. Medido en 62-112: 388 filas cumplen y 1 viene vacía (A002).
OCURRENCIA = re.compile(r"^\d+-\d+$")
# Conjunto observado en las 389 filas de 62-112: A=174, N=153, G=45, F=17. Nada más aparece.
TIPOS_DATO = frozenset({"A", "F", "G", "N"})
# Valor del nodo padre para el campo raíz del documento electrónico.
RAIZ = "Raíz"


@dataclass(frozen=True)
class FieldChange:
    """Un tramo de texto con marca de cambio, junto con la columna donde está."""

    columna: str
    change: str  # 'added' | 'modified' | 'deleted'
    texto: str

    def to_dict(self) -> dict[str, str]:
        return {"columna": self.columna, "change": self.change, "texto": self.texto}


@dataclass(frozen=True)
class FieldRecord:
    """Una fila de la tabla de formato de campos, con su estado de cambio y su procedencia."""

    # Columnas de datos, en el orden del encabezado.
    COLUMNAS: ClassVar[tuple[str, ...]] = (
        "grupo",
        "id",
        "campo",
        "descripcion",
        "nodo_padre",
        "tipo_dato",
        "longitud",
        "ocurrencia",
        "observaciones",
    )

    grupo: str
    id: str
    campo: str
    descripcion: str
    nodo_padre: str
    tipo_dato: str
    longitud: str
    ocurrencia: str
    observaciones: str
    estado: str | None
    cambios: tuple[FieldChange, ...]
    pdf_page: int
    source: str
    sha256: str

    @property
    def printed_page(self) -> int:
        return self.pdf_page - DESPLAZAMIENTO_IMPRESO

    def to_dict(self) -> dict[str, object]:
        datos: dict[str, object] = {columna: getattr(self, columna) for columna in self.COLUMNAS}
        datos["estado"] = self.estado
        datos["cambios"] = [cambio.to_dict() for cambio in self.cambios]
        datos["pdf_page"] = self.pdf_page
        datos["printed_page"] = self.printed_page
        datos["source"] = self.source
        datos["sha256"] = self.sha256
        return datos


@dataclass(frozen=True)
class RowAnomaly:
    """Fila de una tabla de campos cuyo número de celdas no es 9: no se inventa, se registra."""

    pdf_page: int
    celdas: int
    textos: tuple[str, ...]
    source: str
    sha256: str

    @property
    def printed_page(self) -> int:
        return self.pdf_page - DESPLAZAMIENTO_IMPRESO

    def to_dict(self) -> dict[str, object]:
        return {
            "celdas": self.celdas,
            "textos": list(self.textos),
            "pdf_page": self.pdf_page,
            "printed_page": self.printed_page,
            "source": self.source,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class Issue:
    """Incidencia de V4: qué verificación falló, en qué campo y con qué valor."""

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


def is_field_table(table: Table) -> bool:
    """True si la primera fila es el encabezado de 9 columnas de campos."""
    if not table.rows or len(table.rows[0].cells) != len(ENCABEZADO):
        return False
    titulos = ("".join(c.text.split()) for c in table.rows[0].cells)
    return all(titulo in claves for titulo, claves in zip(titulos, _CLAVES, strict=True))


def _rows(doc: Document) -> Iterator[tuple[int, Row]]:
    """Filas de cuerpo de las tablas de campos, con su página PDF."""
    for block in doc.blocks:
        if isinstance(block, Table) and is_field_table(block):
            for row in block.rows[1:]:
                # Una tabla unida entre páginas lleva la página en la fila (T-104).
                yield (row.page if row.page is not None else block.page), row


def _cambios(row: Row) -> tuple[FieldChange, ...]:
    """Tramos resaltados de la fila, columna por columna. Los espacios sueltos no son contenido."""
    return tuple(
        FieldChange(columna, run.change.value, run.text.strip())
        for columna, cell in zip(FieldRecord.COLUMNAS, row.cells, strict=True)
        for run in cell.runs
        if run.change is not None and run.text.strip()
    )


def _estado(row: Row) -> str | None:
    """Estado de la fila según los resaltados de todo su texto no-espacio."""
    marcas = {run.change for cell in row.cells for run in cell.runs if run.text.strip()}
    if not marcas - {None}:  # sin resaltados (o fila sin texto): nada cambió
        return None
    if marcas == {Change.DELETED}:
        return "eliminado"
    if marcas == {Change.ADDED}:
        return "agregado"
    return "modificado"


def field_records(doc: Document) -> list[FieldRecord]:
    """Un registro por fila de cuerpo de las tablas de campos; las filas raras quedan fuera."""
    registros = []
    for page, row in _rows(doc):
        if len(row.cells) != len(ENCABEZADO):
            continue
        valores = [cell.text for cell in row.cells]
        registros.append(
            FieldRecord(
                *valores,
                estado=_estado(row),
                cambios=_cambios(row),
                pdf_page=page,
                source=doc.source,
                sha256=doc.sha256,
            )
        )
    return registros


def field_anomalies(doc: Document) -> list[RowAnomaly]:
    """Filas de tablas de campos con un número de celdas distinto de 9."""
    return [
        RowAnomaly(
            pdf_page=page,
            celdas=len(row.cells),
            textos=tuple(cell.text for cell in row.cells),
            source=doc.source,
            sha256=doc.sha256,
        )
        for page, row in _rows(doc)
        if len(row.cells) != len(ENCABEZADO)
    ]


def check_fields(records: Sequence[FieldRecord]) -> list[Issue]:
    """V4 — esquema de campos. Devuelve las incidencias; no toca ningún dato."""
    ids = {r.id for r in records}
    vigentes = {r.id for r in records if r.estado != "eliminado"}
    issues: list[Issue] = []
    for r in records:
        if not ID_CAMPO.match(r.id):
            issues.append(_issue("id-formato", r, f"ID {r.id!r} fuera de {ID_CAMPO.pattern}"))
        if not r.ocurrencia:
            issues.append(_issue("ocurrencia-vacia", r, "ocurrencia vacía en el PDF"))
        elif not OCURRENCIA.match(r.ocurrencia):
            issues.append(_issue("ocurrencia-formato", r, f"ocurrencia {r.ocurrencia!r} no es 'n-m'"))
        if r.tipo_dato not in TIPOS_DATO:
            observados = ", ".join(sorted(TIPOS_DATO))
            issues.append(
                _issue(
                    "tipo-dato-desconocido",
                    r,
                    f"tipo de dato {r.tipo_dato!r} fuera del conjunto observado ({observados})",
                )
            )
        if r.nodo_padre != RAIZ:
            if r.nodo_padre not in ids:
                issues.append(_issue("nodo-padre-ausente", r, f"nodo padre {r.nodo_padre!r} no es ningún ID"))
            elif r.nodo_padre not in vigentes and r.estado != "eliminado":
                issues.append(
                    _issue(
                        "nodo-padre-eliminado",
                        r,
                        f"nodo padre {r.nodo_padre!r} está eliminado y la fila no",
                    )
                )
    return issues + _duplicados(records)


def _issue(check: str, record: FieldRecord, detalle: str) -> Issue:
    return Issue(check=check, id=record.id, pdf_page=record.pdf_page, detalle=detalle)


def _duplicados(records: Sequence[FieldRecord]) -> list[Issue]:
    """IDs repetidos. Una fila eliminada más otra vigente con el mismo ID es un reemplazo
    legítimo del documento (el MT deja impreso lo que quita), así que se reporta aparte."""
    por_id: dict[str, list[FieldRecord]] = {}
    for record in records:
        por_id.setdefault(record.id, []).append(record)
    issues = []
    for field_id, filas in sorted(por_id.items()):
        if len(filas) < 2:
            continue
        eliminadas = sum(1 for r in filas if r.estado == "eliminado")
        reemplazo = 0 < eliminadas < len(filas)
        detalle = "; ".join(f"página PDF {r.pdf_page} ({r.estado or 'sin cambio'})" for r in filas)
        issues.append(
            Issue(
                check="id-duplicado-reemplazo" if reemplazo else "id-duplicado",
                id=field_id,
                pdf_page=filas[0].pdf_page,
                detalle=f"{len(filas)} filas con el ID {field_id!r}: {detalle}",
            )
        )
    return issues


def to_json(doc: Document, pages: Iterable[int] | None = None) -> str:
    """Serialización determinista de los campos, sus incidencias V4 y las filas anómalas."""
    records = field_records(doc)
    anomalias = field_anomalies(doc)
    estados: dict[str, int] = {}
    for record in records:
        clave = record.estado or "sin_cambio"
        estados[clave] = estados.get(clave, 0) + 1
    paginas = sorted(set(pages)) if pages is not None else sorted({r.pdf_page for r in records})
    datos = {
        "anomalias": [a.to_dict() for a in anomalias],
        "campos": [r.to_dict() for r in records],
        "incidencias": [i.to_dict() for i in check_fields(records)],
        "procedencia": {
            "extractor": doc.extractor,
            "paginas_pdf": paginas,
            "sha256": doc.sha256,
            "source": doc.source,
            "estados": estados,
            "total_campos": len(records),
        },
    }
    return json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True)


def _page_range(value: str) -> range:
    """`62-66` o `62` → rango de páginas PDF (base 1)."""
    first, dash, last = value.partition("-")
    try:
        start, end = int(first), int(last if dash else first)
    except ValueError:
        start, end = 0, -1
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError(f"rango de páginas inválido: {value!r} (ej.: 62-66)")
    return range(start, end + 1)


def main() -> None:
    from sifen_kb.pdf.pipeline import load

    parser = argparse.ArgumentParser(description="Tablas de campos del MT SIFEN → campos.json")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", type=_page_range, required=True, help="rango PDF, p. ej. 62-66")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.pdf.is_file():
        parser.error(f"no existe el PDF: {args.pdf}")
    doc = load(args.pdf, pages=args.pages, sifen=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(to_json(doc, pages=args.pages), encoding="utf-8")
    records = field_records(doc)
    issues = check_fields(records)
    print(f"{len(records)} campos, {len(field_anomalies(doc))} filas anómalas, {len(issues)} V4")


if __name__ == "__main__":
    main()

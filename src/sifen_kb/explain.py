"""`sifen explain` y `sifen status` (docs/arquitectura.md §O; guía de usuario: docs/uso.md).

ESTADO: ESQUELETO. Solo documenta el contrato; `cmd_explain` y `cmd_status` todavía no
implementan la consulta y terminan con exit 1 y un mensaje claro (nunca con un traceback).
La implementación pendiente está descrita punto por punto en el informe de traspaso.

Solo lectura: nunca escribe en `kb/`, `raw/`, `sources/` ni en el XML que se le pasa.

Contrato de `explain --json` (estable; sin campos aleatorios ni dependientes de la hora, salvo los
que derivan de `--at`)::

    {
      "query": {"term": str, "at": "AAAA-MM-DD", "env": "prod"|"test", "history": bool,
                "xml": str|null, "response": str|null, "processed_at": "AAAA-MM-DD"|null},
      "kb": {"revision": str|null, "documents_curated": [DocId, ...],
             "sources_checked_at": "AAAA-MM-DD"|null},
      "results": [
        {"key": str|null,                       # val:DE:D208c, field:DE:D208, DocId o null (índice)
         "kind": "field" | "validation" | "document" | "index",
         "resolution": <Resolution.model_dump(mode="json")>,
         "version": <versión elegida .model_dump(mode="json")> | null,
         "related_fields": [{"id", "key", "xml_name", "xsd": str|null}, ...],
         "xsd": {...} | null,                   # XsdCheck de la instantánea, si hay
         "xml": {...} | null}                   # evaluación por eje (solo con --xml)
      ],
      "warnings": [str, ...]
    }

Códigos de salida: 0 = respuesta; 1 = la KB tiene errores de carga (se muestran) o error de uso;
2 = término desconocido (ni curado ni mencionado en `raw/`), con sugerencias.
"""

from __future__ import annotations

import argparse
import sys

NOT_IMPLEMENTED = (
    "sifen explain/status: todavía no implementado (src/sifen_kb/explain.py es un esqueleto). "
    "Ver el informe de traspaso y docs/arquitectura.md §O."
)


def cmd_explain(args: argparse.Namespace) -> int:
    """Punto de entrada de `sifen explain` (pendiente)."""
    print(NOT_IMPLEMENTED, file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Punto de entrada de `sifen status` (pendiente)."""
    print(NOT_IMPLEMENTED, file=sys.stderr)
    return 1

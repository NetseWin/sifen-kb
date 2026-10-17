"""Extractor determinista de PDF técnico (vendorizado de `pdf_to_md`, mismo autor, bajo MIT).

Origen: pdf_to_md, commit 8603b5bd572fb0a1563e216d3ec658fb5666e678 (rama main). Se trajo el
cierre mínimo para que `sifen extract` genere `raw/`:

- genérico: `ir` (IR), `tagged` (árbol de etiquetas), `geometry` (ruta para PDF sin etiquetas),
  `continuity` (tablas y filas partidas entre páginas), `pipeline` (`load`), `verify` (texto por
  página de la IR y V1 contra `pdftotext`), `hashing` (`sha256_of`);
- SIFEN (`sifen/`): `sections`, `artifacts`, `fields`, `validations` y `changes` (libro NT↔MT).

No se trajeron render/Markdown, vista consolidada, codificaciones, esquemas, XSD, reporte ni
testigo: `raw/` no los necesita. La lógica se conserva; las diferencias con el origen son solo de
imports y de formato (ruff).
"""

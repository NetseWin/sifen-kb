---
name: Nota Técnica nueva o re-subida
about: Avisar de una NT nueva, de una re-subida (mismo documento, otro contenido) o de un XSD que cambió en el portal de DNIT
title: "[nueva NT] "
labels: fuentes
---

<!--
Este aviso no registra nada por sí mismo: una persona mantenedora ejecuta `sifen source check` y
`sifen source add` (ver docs/curacion.md). Solo se registran documentos publicados en el portal oficial de DNIT.
-->

## Qué detectaste

- [ ] Nota Técnica nueva
- [ ] Re-subida de una NT ya registrada (cambió el archivo, o el enlace, o la fecha `?t=`)
- [ ] Cambio en un XSD o en el directorio de XSD
- [ ] Otro documento (Manual, listado, comunicado, norma):

## Documento

- Identificador (`NT_028`, `MT_V150`, `XSD_DIR`…):
- Título o nombre del archivo tal como lo muestra el portal:
- URL oficial (dominio `www.dnit.gov.py`, `ekuatia.set.gov.py` o `www.set.gov.py`):
- Fecha en que lo viste:

## Fechas que declara (si las conoces)

Cópialas tal como aparecen en el documento y di en qué página. No las interpretes.

| Fecha | Valor literal | Página |
|---|---|---|
| Fecha del documento | | |
| Puesta a disposición en ambiente de Test | | |
| Puesta a disposición en ambiente de Producción | | |

## Qué entidades podría afectar (opcional)

Códigos de rechazo, IDs de campo o validación, `xml_name`:

## Si es una re-subida

¿Qué cambió respecto de la revisión anterior (fechas, filas, solo la marca de agua)? Si no lo sabes, no hace falta: el diff de `raw/` lo mostrará después.

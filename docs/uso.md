# Guía de uso de la CLI `sifen`

La CLI es el único punto de entrada para consultar y mantener la base de conocimiento. Está basada en el diseño de [`arquitectura.md`](arquitectura.md) §O. Se ejecuta con `uv run sifen …` desde la raíz del repositorio (o con `--root RUTA`).

> **Estado.** La CLI está implementada por completo (`explain`, `status`, `source`, `extract`, `draft`, `check`, `fmt`); `sifen --help` y `sifen <comando> --help` muestran las opciones exactas de cada versión. Los bloques de salida de este documento son **reales**, ejecutados contra la rama `kb/piloto-receptor` (`e7d0f2c`, 2026-10-18); la línea `KB` muestra ese commit (checkout limpio), y las líneas con la fecha de «hoy» corresponden al día de ejecución.

## Resumen

```text
# Consulta
sifen explain <código|ID|xml_name|DocId> [--at AAAA-MM-DD] [--env prod|test] [--history] [--json]
sifen explain <código|ID> --xml RUTA [--response RUTA | --processed-at AAAA-MM-DD] [--env prod|test] [--json]
sifen status [--json]

# Mantenimiento
sifen source check [--scope nt,xsd,manual,tablas] [--offline]
sifen source add --doc <DocId> (--url <url> | --file RUTA --note TEXTO)
sifen extract [--doc <DocId>]... [--check]
sifen draft <DocId>|<DocId>#<n>|<clave-entidad> [--baseline FILA] [--update-revision] [--dry-run]
sifen check [--json] [--report]
sifen fmt [--check]
```

Opciones globales: `--root RUTA` (raíz del repositorio; por defecto se busca desde el directorio actual) y `--version`. No existe un comando `update`: el flujo ante una NT nueva es `source check` → `source add` → `extract` → `draft` → PR (ver [`curacion.md`](curacion.md)).

La salida va por stdout en UTF-8 con fin de línea LF, también cuando se redirige o se canaliza (caso típico de un agente o de Windows).

## `sifen explain`

Responde qué rige para un término a una fecha y en un ambiente. `<término>` puede ser:

| Término | Ejemplo | Qué devuelve |
|---|---|---|
| Código de rechazo | `1321` | Toda validación que alguna vez tuvo ese código, resuelta en la fecha (incluidas las eliminadas, que responden `removed`). Un código puede mapear a varias validaciones. |
| ID | `D208c`, `D208` | La entidad con ese ID. Si es a la vez campo y validación (como `D208`), devuelve ambas, etiquetadas (`field:DE:D208`, `val:DE:D208`). |
| `xml_name` | `iTipIDRec` | Los campos con ese nombre XML, con su contexto. |
| Documento | `NT_024`, `MT_V150` | Revisiones registradas en el manifiesto, calendario por ambiente, efectos y su estado. |

Opciones:

| Opción | Efecto |
|---|---|
| `--at AAAA-MM-DD` | Fecha de la consulta. Por defecto, hoy. Es la fecha de **procesamiento** (supuesto A2, pendiente de confirmar con DNIT). No se admite junto con `--xml`. |
| `--env prod\|test` | Ambiente. Por defecto, `prod`. Test y producción tienen fechas distintas: puede dar respuestas diferentes entre ambas. |
| `--history` | Toda la historia de la entidad con la fuente de cada frontera (cada versión, desde cuándo y por qué documento), en lugar de solo la versión de esa fecha. |
| `--json` | Salida JSON con contrato estable (ver más abajo). |
| `--xml RUTA` | Evalúa la regla contra un XML de un DE, **sin modificarlo**. Resuelve con la fecha de emisión (`dFeEmiDE`) y la de procesamiento. Imprime solo los campos que usa la regla y enmascara los datos personales. |
| `--response RUTA` | XML de respuesta de SIFEN: de él se toma la fecha de procesamiento (`dFecProc`). |
| `--processed-at AAAA-MM-DD` | Fecha de procesamiento explícita, si no hay respuesta. Nunca se asume "hoy": un rechazo de 2024 evaluado con la regla de hoy da un veredicto falso. |
| `--show-pii` | No enmascara datos personales. Solo para uso humano local; no lo uses con un agente. |

Los XML reales van siempre **fuera del repositorio** y nunca se abren con otras herramientas: ver [`SECURITY.md`](../SECURITY.md).

### Estados

El primer dato de la respuesta es el **estado**. Si no es `in_force`, léelo antes que nada.

| Estado | Significado |
|---|---|
| `in_force` | La versión curada rige en esa fecha y ambiente. |
| `removed` | La validación existió y fue eliminada: la versión lápida conserva su código. |
| `not_yet_existing` | Todavía no existía en esa fecha y ambiente. |
| `undetermined` | No se puede afirmar. Los motivos (`reasons`) dicen por qué; se muestra igualmente la última versión curada como referencia. |
| `outside_coverage` | Fecha anterior a `coverage_from`: la KB no garantiza respuestas temporales antes de esa fecha. Se muestra la mejor versión como referencia, con la base (`approx`) de su inicio. |
| `not_curated` | La entidad no está curada. Se listan sus menciones en `raw/` (documento, revisión, página impresa y PDF, extracto), de la más reciente a la más antigua por fecha de producción del documento (nunca por número de NT), con el aviso "vigencia no resuelta: una mención posterior puede modificar o eliminar la regla". No se infiere la regla. |

### Motivos (`reasons`)

Acompañan a `undetermined`:

| Motivo | Cuándo aparece |
|---|---|
| `pending_effect` | Hay una NT que afecta a la entidad y todavía no está curada (efecto `pending`), o con fecha ya alcanzada o sin fecha. |
| `blocking_issue` | Hay un Issue abierto y bloqueante cuya ventana y ambiente incluyen la consulta (por ejemplo, un posible reemplazo no declarado de una regla). |
| `revision_not_curated` | El manifiesto tiene una revisión de un documento relevante más reciente que la curada (una NT nueva o una re-subida). |
| `beyond_horizon` | La fecha supera el horizonte de fuentes más la gracia: una NT posterior podría regir. |
| `processing_date_unknown` | Con `--xml` falta la fecha de procesamiento y hay una frontera de versión entre la emisión y el horizonte. |
| `axis_split` | Con `--xml`, la fecha de emisión y la de procesamiento caen en versiones con veredictos distintos. Se muestran los dos resultados. |
| `test_date_missing` | En `--env test`, el documento no declara fecha de test y la de producción ya pasó. No se usa la de producción como sustituto. |

### Otros campos de la respuesta

- **Versión e intervalo**: qué efecto introdujo la versión, desde cuándo y hasta cuándo (derivados del calendario del ambiente), con la base de cada frontera (`stated` declarada, `approx` aproximada, `baseline` línea base).
- **Fuente**: efecto, documento, revisión (`sha12`) y página.
- **Literal** (observación, mensaje): copiado de la celda del documento oficial, no parafraseado.
- **Violación / condición**: la formalización, si existe, marcada como **interpretación** con su nivel (`full`, `partial`, `none`) y sus huecos. No sustituye al literal.
- **Campos relacionados**, con su identidad y ocurrencia.
- **XSD**: si la estructura coincide con la instantánea de los XSD. Si la instantánea es posterior a la fecha consultada, se marca como referencia y **no cambia el estado**. En un campo con enumeración curada (C002, D208…) muestra por separado los códigos que **documentan el MT/NT** y los que **acepta la instantánea XSD**, con `mismatch` y su Issue `source_conflict` si difieren; no los consolida ni inventa etiquetas para los valores que solo acepta el XSD.
- `upcoming`, `pending_effects`, `open_issues`: lo que viene o está abierto; nada futuro queda oculto.
- `warnings`: avisos no bloqueantes (inicio aproximado, horizonte en gracia, huecos de formalización, `open_questions`, Issues no bloqueantes, prórrogas).
- `sources_checked_at` (horizonte de fuentes) y `kb_snapshot` (versión de la KB: tag, último documento y alcance curado).

**Transmite siempre los avisos, los pendientes, los Issues abiertos y el horizonte**, tal cual salen. Cuando se evalúa un XML, la salida añade que SIFEN informa solo el **primer error** de un rechazo: otras reglas pueden no haberse evaluado ni informado.

### Ejemplos

Salida real de la consulta puntual (`uv run sifen explain 1321 --at 2025-01-10`, ejecutada el 2026-10-18 contra `e7d0f2c`):

```text
$ uv run sifen explain 1321 --at 2025-01-10
val:DE:D208c · código 1321 · R · IN_FORCE (2025-01-10 · prod · eje: procesamiento [supuesto A2])
  Versión     NT_024#1 · desde 2025-01-01 (declarada) [NT_024 «01/01/2025», rev ccc2d1550e92 p. 1 PDF] · hasta abierta
  Mensaje     «Tipo de documento de identidad del receptor incorrecto para el total general de la operación en guaraníes»
  Literal     «El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es mayor a 7.000.000 (F023 > 7.000.000 o F014 > 7.000.000)»
  Base legal  Decreto 872/2023, art. 6, numeral 2, inciso ii) (NT_024 rev ccc2d1550e92 · p. 1 PDF)
  Fuente      NT_024 rev ccc2d1550e92 · p. 1 PDF
  Historia    línea base (base) → NT_021#1 (2024-01-01) → [NT_024#1 (2025-01-01)]
  Violación   [interpretación, parcial] exists(D208) and D208 == 5 and ((exists(F023) and F023 > 7000000) or (exists(F014) and F014 > 7000000))
  Huecos      Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 > 7.000.000 y F023 <= 7.000.000, el paréntesis viola y la prosa no (ISS-0005). Que D208 ausente no viole es interpretación. Polaridad mixta: «(D208≠5)» es la restricción que debe cumplirse, no el disparador; la condición de violación es D208 = 5. Literal efectivo: NT 24 quita en rojo «Si el Tipo de transacción es distinto a Muestras médicas (D011≠13),», «o igual» y el «=» de los dos «>=» (rojo = contenido eliminado, decisión del usuario 2026-10-17): «mayor a» y sin la excepción D011 = 13 (ISS-0011).
  Campos      D208 iTipIDRec (D3/D200, N 1, 0-1) · F014 dTotGralOpe (F/F001, N 1-15p(0-8), 1-1) · F023 dTotalGs (F/F001, N 1-15p(0-8), 0-1)
              D208: XSD /rDE/DE/gDatGralOpe/gDatRec/iTipIDRec (0-1) · ocurrencia del manual 0-1: match
              F014: XSD /rDE/DE/gTotSub/dTotGralOpe (1-1) · ocurrencia del manual 1-1: match
              F023: XSD /rDE/DE/gTotSub/dTotalGs (0-1) · ocurrencia del manual 0-1: match
  XSD         instantánea posterior a la fecha consultada: referencia, no evidencia (instantánea 2026-10-17 (rev cdd1f03f1d29): match)
              D208: gDatRec/iTipIDRec: 0-1 (manual 0-1); F014: gTotSub/dTotGralOpe: 1-1 (manual 1-1); F023: gTotSub/dTotalGs: 0-1 (manual 0-1)
  Issues      ISS-0005 (ambiguity, no bloqueante) · ISS-0011 (ambiguity, no bloqueante)
  Avisos      gap de la formalización (partial): Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 > 7.000.000 y F023 <= 7.000.000, el paréntesis viola y la prosa no (ISS-0005). Que D208 ausente no viole es interpretación. Polaridad mixta: «(D208≠5)» es la restricción que debe cumplirse, no el disparador; la condición de violación es D208 = 5. Literal efectivo: NT 24 quita en rojo «Si el Tipo de transacción es distinto a Muestras médicas (D011≠13),», «o igual» y el «=» de los dos «>=» (rojo = contenido eliminado, decisión del usuario 2026-10-17): «mayor a» y sin la excepción D011 = 13 (ISS-0011).
              ISS-0005 (ambiguity, no bloqueante): La observación de D208c (1321) asocia en prosa el monto a la moneda («el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG)», es decir F023 con moneda extranjera y F014 con PYG, según D015), pero el paréntesis formal dice «(F023 >= X o F014 >= X)» (MT V150; desde NT 21, con el literal efectivo, «(F023 > X o F014 > X)») sin condicionar a la moneda. Con moneda extranjera, F014 por encima del umbral y F023 no, el paréntesis viola y la prosa no. Afecta las tres versiones (MT V150, NT 21, NT 24).
              ISS-0011 (ambiguity, no bloqueante): En la fila D208c (1321) de NT 21 y de NT 24 están resaltados en rojo «Si el Tipo de transacción es distinto a Muestras médicas (D011≠13),», «o igual» y el «=» de los dos «>=», y en amarillo la «E» de «El Tipo» (en el MT V150 es «el», en minúscula) y los montos. La curación inicial tomó todo el texto como vigente (celda completa). Indicios de la lectura rojo = eliminado (como en la leyenda del MT y en NT 2, 8, 10 y 23): la «E» pasa a mayúscula justo donde empezaría la oración si se quita la cláusula previa; y el Decreto 872/2023, art. 6, numeral 2, que ambas NT citan, dice «supere» y no exceptúa las muestras médicas (ISS-0012). Con esa lectura la regla sería: innominado prohibido cuando el monto es mayor a 35.000.000 (NT 21) o 7.000.000 (NT 24), sin la excepción D011 = 13. Los veredictos difieren solo con el monto exactamente igual al umbral o con D011 = 13.
              XSD anacrónico: instantánea posterior a la fecha consultada: referencia, no evidencia (instantánea del 2026-10-17)
  Fuentes     verificadas el 2026-10-17 (hace 1 días)
  KB          e7d0f2c · corpus MT_V150 + NT_001–NT_027 + CHECKSUM_MT + NORMA_DECRETO_872_2023 + XSD_DIR + XSD_RAR · curado: 32 documentos (dates_only 24, pilot 8) · 10 campos · 12 validaciones
```

La misma regla en otra fecha o ambiente. Lo que cambia con la fecha: el 2024-12-31 rige NT 21 («mayor a 35.000.000», sin la excepción D011) y el 2025-01-01, NT 24 («mayor a 7.000.000», también sin la excepción D011); el MT V150 era «mayor o igual a 60.000.000» con la excepción de muestras médicas (D011≠13). El ejemplo del campo `D208` muestra la divergencia de ambientes de NT 23 (test: 30/08/2024; producción: 27/09/2024). El valor 6 de la enumeración («Tarjeta Diplomática de exoneración fiscal») ya existe desde el MT V150 y NT 23 no lo agrega: está presente en ambientes y fechas, en las tres versiones del campo (MT V150, NT 2 y NT 23); lo que cambia con NT 23 es la observación del campo (quita «y D202 ≠ 4» y agrega «No informar si D201 = 1») y que la validación D208 (1310) pasa a `undetermined` (ISS-0003):

```bash
uv run sifen explain 1321 --at 2024-12-31              # rige NT 21: «mayor a 35.000.000», sin la excepción D011
uv run sifen explain 1321 --at 2025-01-01              # rige NT 24: «mayor a 7.000.000», sin la excepción D011
uv run sifen explain D208 --at 2024-09-15 --env test   # rige NT 23 (test: 30/08/2024); el valor 6 ya estaba desde el MT V150
uv run sifen explain D208 --at 2024-09-15 --env prod   # todavía rige NT 2 (producción: 27/09/2024); el valor 6 también está
```

Historia completa y documentos:

```bash
uv run sifen explain D208c --history
uv run sifen explain NT_024            # revisiones, calendario por ambiente, efectos y su estado
```

Un código fuera de lo curado (modo índice):

```bash
uv run sifen explain 1400              # not_curated: menciones por fecha de producción del documento
```

Salida real de `uv run sifen explain 1400` (ejecutada el 2026-10-18 contra `e7d0f2c`; `1400` sigue sin curar):

```text
$ uv run sifen explain 1400
NOT_CURATED · 1400 (2026-10-18 · prod · eje: procesamiento [supuesto A2])
  Estado      NOT_CURATED: no curado: vigencia no resuelta; se listan las menciones en raw/ sin inferir la regla
  Aviso       vigencia no resuelta: una mención posterior puede modificar o eliminar la regla
  Menciones   3 en raw/, por fecha de producción del documento (la más reciente primero; nunca por número de NT):
              1. NT_026 rev 5ed252f14427 · p. 1 PDF · producción 2025-06-16
                 «…ción E E020 Grupo de informaciones de Compras Públicas es obligatorio 1400 El grupo de informaciones de Compras Públicas es obligatorio para tip…»
              2. MT_V150 rev 976cd88c05c3 · p. 148 impresa / 149 PDF · sin fecha de producción
                 «…2 1399 Campos que componen la Factura Electrónica FE (E010-E099) E020 1400 E025 1449 Campos de informaciones de Compras Públicas (E020-E029) E30…»
              3. MT_V150 rev 976cd88c05c3 · p. 168 impresa / 169 PDF · sin fecha de producción
                 «…n E 78 E020 Grupo de informaciones de Compras Públicas es obligatorio 1400 El grupo de informaciones de Compras Públicas es obligatorio para tip…»
  Avisos      fuentes verificadas el 2026-10-17: una NT posterior podría regir (NT 25 y 27 rigieron el día de su subida)
  Fuentes     verificadas el 2026-10-17 (hace 1 días)
  KB          e7d0f2c · corpus MT_V150 + NT_001–NT_027 + CHECKSUM_MT + NORMA_DECRETO_872_2023 + XSD_DIR + XSD_RAR · curado: 32 documentos (dates_only 24, pilot 8) · 10 campos · 12 validaciones
```

Un rechazo con XML (el XML, fuera del repo, no se modifica y sale enmascarado):

```bash
uv run sifen explain 1321 --xml C:/sifen-privado/xml/de.xml --response C:/sifen-privado/xml/respuesta.xml
uv run sifen explain 1321 --xml /ruta/de.xml --processed-at 2025-01-02 --env prod
```

El resultado es `TRUE` (la regla se viola), `FALSE` o `UNKNOWN` según la formalización y la versión vigente en **ambas** fechas. Si emisión y procesamiento caen a ambos lados de un cambio, el estado es `undetermined` (`axis_split`). Ejemplo del diseño: un DE emitido el 30/12/2024 a un receptor innominado por 10.000.000 PYG y procesado el 02/01/2025: con la fecha de emisión aplica NT 21 («mayor a 35.000.000») y no viola; con la de procesamiento aplica NT 24 («mayor a 7.000.000») y viola `1321`.

### Salida JSON

`--json` imprime la resolución como un objeto JSON, pensado para scripts y agentes (la CLI con `--json` más `CLAUDE.md` es la integración con Claude Code). Campos principales: `key`, `at`, `env`, `axis`, `state`, `reasons`, la versión elegida, `interval`, `source`, `history`, `upcoming`, `pending_effects`, `open_issues`, `mentions` (solo `not_curated`), `warnings`, `sources_checked_at`, `kb_snapshot`, el bloque `xsd` y `processing_date_source`. El contrato exacto es el modelo `Resolution` de `src/sifen_kb/model.py`; una prueba (`test_explain_json_snapshot`) protege su formato de cambios involuntarios.

## `sifen status`

Resume qué sabe y qué no sabe la KB: horizonte de fuentes (fecha del último `source check` limpio), cambios sin registrar, revisiones sin curar, efectos pendientes, Issues bloqueantes, cobertura (`coverage_from` y alcance curado) y supuestos sin verificar. Es la primera consulta ante la duda de si la KB está al día.

## Comandos de mantenimiento

| Comando | Qué hace |
|---|---|
| `sifen source check [--scope …] [--offline]` | Compara el hash de las URL conocidas y de los listados del portal de DNIT (NT, directorio XSD, Manual, tablas) y registra el chequeo en el manifiesto. No descarga fuentes a `sources/`. Con `--offline` solo verifica el repositorio. Si no hay nada sin registrar, avanza el horizonte. |
| `sifen source add --doc <DocId> --url <url>` | **Acción humana.** Descarga desde un dominio de DNIT permitido (`www.dnit.gov.py`, `ekuatia.set.gov.py`, `www.set.gov.py`), calcula `sha256` y `md5`, copia a `sources/<DocId>/<sha12>.<ext>` y agrega la revisión a `sources.manifest.yaml` (solo se le agrega). Con `--file RUTA --note TEXTO` registra una copia local que conserva la empresa (`origin: offline`, la nota es obligatoria). |
| `sifen extract [--doc <DocId>] [--check]` | Genera `raw/` (texto por página, índice y celdas de tablas) de forma determinista. Con `--check` regenera en memoria y compara byte a byte con `raw/`; así se detecta una edición a mano o un cambio del extractor. |
| `sifen draft <DocId>` | Copia desde las celdas de la tabla de fechas de la NT su `document_date` y su calendario por ambiente a `kb/documents/<DocId>.yaml`. Con `--update-revision` mueve `current_revision` a la última revisión del manifiesto y copia sus fechas. |
| `sifen draft <DocId>#<n>` | Crea la versión nueva de la entidad a la que apunta el efecto, copiando los literales de las celdas de `raw/` y heredando de la predecesora temporal las columnas que la NT no trae. Con `--baseline FILA` y la clave de la entidad (p. ej. `val:DE:D208c`) crea la entidad con su versión base copiada de esa fila del MT (p. ej. `raw:MT_V150@976cd88c05c3:p167:D208c`). En cualquier forma, `--dry-run` muestra lo que se escribiría («se escribiría»), sin escribir. |
| `sifen check [--json] [--report]` | Esquema, formato, integridad, evidencia y cobertura (subconjunto rápido de las pruebas). Devuelve **todos** los hallazgos. Con `--report`, informe de revisión del PR: por entidad, versión anterior/nueva y diff, fechas, Issues y pasado. |
| `sifen fmt [--check]` | Escribe los archivos de `kb/` (y el manifiesto) en formato canónico. Con `--check` no escribe y falla si alguno no lo es. |

Los literales y las fechas solo los copia `sifen draft`. El flujo completo y la revisión humana están en [`curacion.md`](curacion.md).

## Códigos y estados al leer una respuesta

1. Mira `state` y `reasons`. Si no es `in_force`, dilo antes de nada.
2. Si es `not_curated`, la vigencia **no está resuelta**: usa las menciones como pista, no como regla.
3. Cita el documento oficial (documento, revisión `sha12`, página impresa y PDF). La autoridad es DNIT, no "la KB".
4. Transmite `warnings`, `pending_effects`, `open_issues` y el horizonte de fuentes.
5. No presentes una versión no vigente como vigente. El número de NT no ordena el tiempo.

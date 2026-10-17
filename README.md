# sifen-kb

Base de conocimiento técnica, versionada y verificable de **SIFEN** (facturación electrónica de Paraguay, e-Kuatia): qué regla de validación rige en cada **fecha** y en cada **ambiente** (test o producción), con la cita literal del documento oficial de DNIT que la respalda.

> **Estado: alfa.** El corpus oficial ya está registrado y el extractor genera `raw/`; el dominio piloto (receptor e identidad) se está curando. Algunos comandos de la CLI todavía no están completos. Lo que ves en este README sobre su salida es ilustrativo hasta que se pegue una salida real (ver los marcadores `SALIDA-REAL`).

## El problema

Para saber si un documento electrónico (DE) debía ser aceptado o rechazado con el código `1321` no basta con abrir el Manual Técnico:

- **El Manual Técnico base no es la regla vigente.** El Manual v150 trae el umbral de `D208c` en 60.000.000 guaraníes; la Nota Técnica 21 lo bajó a 35.000.000 y la Nota Técnica 24, a 7.000.000. La respuesta correcta depende de la fecha.
- **Cada Nota Técnica (NT) tiene sus propias fechas, y distintas por ambiente.** Test y producción no cambian el mismo día (NT 23: 30/08/2024 en test y 27/09/2024 en producción). Las NT 001–012 no declaran vigencia. La numeración no ordena el tiempo.
- **DNIT cambia los archivos in situ.** Vuelve a subir una NT con otra marca de agua o con otro contenido, y modifica los XSD sin cambiar el nombre, el namespace ni la versión. Lo único que lo delata es el hash.
- **Los identificadores no son únicos.** `D208` es a la vez un campo y una validación; un mismo código puede estar en dos validaciones; una NT reasigna códigos.

Un asistente (o una persona) que contesta de memoria, o que busca por similitud de texto entre NT casi idénticas, entrega con seguridad una regla que ya no rige. Este proyecto existe para que no lo haga.

## Qué hace

Resuelve una consulta puntual a partir de fuentes con hash, evidencia literal y versiones materializadas:

```text
sifen explain 1321 --at 2025-01-10 --env prod
```

Salida **ilustrativa** (tomada del diseño, `docs/arquitectura.md` §O; los marcadores `<n>` y `<sha12>` se completan con datos reales):

```text
val:DE:D208c · código 1321 · R · IN_FORCE (prod · eje: procesamiento [supuesto A2])
  Versión     NT_024#1 · desde 2025-01-01 (declarada en NT 24, rev <sha12>) · hasta: abierta
  Literal     «…es mayor o igual a 7.000.000 (F023 >= 7.000.000 o F014 >= 7.000.000)»  NT 24 p.<n>
  Historia    MT v150 (base, ≥60 M) → NT 21 (2024-01-01, ≥35 M) → NT 24 (2025-01-01, ≥7 M)
  Violación   [interpretación, parcial] (not exists(D011) or D011 != 13) and exists(D208) and D208 == 5 and (…)
  Campos      D208 iTipIDRec (D3/D200, N 1, 0-1) · D011 iTipTra · F014 dTotGralOpe · F023 dTotalGs
  XSD         instantánea 2026-10-17, posterior a la fecha consultada: referencia, no evidencia de 2025
  Avisos      ISS-0005 gap: la prosa asocia F023/F014 a la moneda (D015); se formalizó el paréntesis
  Fuentes     verificadas el 2026-10-17 (hace 0 días)
  KB          kb-2026.11.xx · corpus MT_V150 + NT_001–NT_027 · curado: receptor/identidad
```

Salida real (se pegará aquí cuando el comando esté completo):

<!-- SALIDA-REAL -->

La respuesta nunca es solo "vigente" o "no vigente": incluye el **estado** y los **motivos**, el intervalo derivado, la cita (documento, revisión por hash y página), la historia, los avisos y el **horizonte de fuentes** (la fecha del último chequeo limpio del portal de DNIT). Si lo consultado todavía no está curado, responde `not_curated` con las menciones literales ordenadas por fecha de vigencia, sin inferir la regla:

<!-- SALIDA-REAL -->

La guía completa de la CLI está en [`docs/uso.md`](docs/uso.md).

## Principios

1. **Un solo canónico editable.** `kb/` (YAML restringido, un archivo por entidad). Todo lo demás es evidencia inmutable (`sources/`, `raw/`) o artefacto generado (`build/`). Dos lugares donde "vive la regla" son el origen de los errores silenciosos.
2. **Evidencia literal verificada contra el PDF.** Los literales (mensaje, observación, longitud, fechas) los copia una herramienta desde las celdas de `raw/`; un test exige igualdad con la celda citada. Ni una persona ni un modelo de lenguaje los teclean. La interpretación (condición formalizada, clasificación de un efecto) va aparte, marcada como tal y revisada por una persona.
3. **Versiones materializadas, no parches.** Las NT reproducen la fila completa, sin "antes/después". Cada cambio es una versión nueva completa de la entidad; lo que declara la NT (verbo, alcance) es una aserción que un test verifica contra el diff.
4. **El tiempo se deriva, no se almacena.** El inicio y el fin de cada versión salen del calendario por ambiente que declara cada documento. Git es el tiempo de transacción: `git checkout kb-<fecha>` responde qué decía la KB en esa release.
5. **Estados honestos.** Cuando la KB no sabe, lo dice (tabla siguiente) en lugar de contestar "vigente" con información incompleta.
6. **Las fuentes nunca se alteran.** `sources/` solo recibe adiciones, nombradas por hash; `sifen source add` solo descarga de dominios de DNIT. La autoridad es DNIT, nunca "la KB".
7. **La IA propone, una persona aprueba.** Se automatiza detectar, descargar, hashear, extraer y verificar; todo lo que decide contenido normativo (fechas, destinos, versiones, merge) lo decide una persona.

### Estados de una respuesta

| Estado | Significado |
|---|---|
| `in_force` | La versión curada rige en esa fecha y ambiente. |
| `removed` | La validación existió y fue eliminada (versión lápida: conserva su código). |
| `not_yet_existing` | Todavía no existía en esa fecha y ambiente. |
| `undetermined` | No se puede afirmar: hay un efecto pendiente, un Issue bloqueante, una revisión nueva sin curar, falta la fecha de procesamiento o se superó el horizonte de fuentes. El campo `reasons` dice cuál. |
| `outside_coverage` | La fecha es anterior a `coverage_from` (la KB no garantiza respuestas temporales antes). Muestra la mejor versión como referencia. |
| `not_curated` | La entidad no está curada. Solo se listan sus menciones en `raw/`, con el aviso de que la vigencia no está resuelta. |

## Instalación

Requisitos: [`git`](https://git-scm.com/) y [`uv`](https://docs.astral.sh/uv/). El intérprete (CPython 3.14) lo gestiona `uv`; no hace falta tenerlo instalado.

```bash
git clone https://github.com/NetseWin/sifen-kb.git
cd sifen-kb
uv sync            # descarga Python 3.14 (solo gestionado por uv) e instala las dependencias del lock
uv run sifen --version
```

- **Linux y macOS:** lo anterior alcanza.
- **Windows:** se recomienda **WSL2** (Ubuntu) con el repositorio dentro del sistema de archivos de Linux y **fuera de OneDrive** (bloqueos de archivos, marcadores de posición y rutas largas). El CI corre en Ubuntu; la CLI fuerza UTF-8 con fin de línea LF en la salida y se prueba simulando la codificación cp1252 de Windows.
- `uv sync --locked` falla si `uv.lock` no corresponde a `pyproject.toml`; es lo que usa el CI.

## Uso rápido

```bash
uv run sifen explain 1321 --at 2025-01-10 --env prod   # un código de rechazo en una fecha y ambiente
uv run sifen explain D208c --history                   # toda la historia con sus fuentes
uv run sifen explain iTipIDRec --json                  # contrato JSON estable (lo usan scripts y agentes)
uv run sifen explain NT_024                            # un documento: revisiones, calendario y efectos
uv run sifen status                                    # horizonte de fuentes, pendientes, Issues, cobertura
```

Con un XML real de un DE (siempre **fuera del repositorio**, en solo lectura y con los datos personales enmascarados):

```bash
uv run sifen explain 1321 --xml RUTA.xml --response RUTA_respuesta.xml
```

Opciones, estados, motivos y ejemplos: [`docs/uso.md`](docs/uso.md).

## Cómo funciona

```text
 Portal DNIT (PDF · XSD · RAR · XLSX)
      │  sifen source check: hash de las URL conocidas → horizonte de fuentes
      ▼
 sources/<doc>/<sha12>.<ext> + sources.manifest.yaml      evidencia binaria: inmutable, solo adiciones
      │  sifen extract
      ▼
 raw/<doc>/<sha12>/ pages/ · index.json · tables.jsonl    evidencia textual: generada, verificada en CI
      │  sifen draft (copia literales y fechas) + curación asistida (efectos, formalización, Issues)
      ▼
 kb/                                                      único canónico editable (YAML, 1 archivo = 1 entidad)
      │  sifen check · pytest: evidencia · integridad · golden temporal · alcance del PR
      ▼
 resolvedor temporal (entidad, fecha, ambiente) ──► sifen explain ──► texto o JSON ──► persona · Claude Code · scripts
```

Ante una Nota Técnica nueva o re-subida el flujo es: `sifen source check` → `sifen source add` → `sifen extract` → `sifen draft` → PR de conocimiento con informe → revisión humana → merge y tag `kb-AAAA.MM.DD`. Los pasos de detectar, descargar, extraer y verificar no usan un modelo de lenguaje. Ver [`docs/curacion.md`](docs/curacion.md).

El extractor de PDF (`src/sifen_kb/pdf/`) integra el código de **`pdf_to_md`**, un proyecto previo del mismo autor bajo licencia MIT: lee el árbol de etiquetas del PDF, reconstruye tablas que cruzan páginas y detecta las filas eliminadas que DNIT marca en rojo. Con él, 6 085 de 6 085 celdas críticas del Manual Técnico quedaron verificadas por dos métodos independientes.

El diseño completo, con sus decisiones y los riesgos considerados, está en [`docs/arquitectura.md`](docs/arquitectura.md); la investigación de respaldo, en [`docs/investigacion/`](docs/investigacion/).

## Estructura del repositorio

```text
sources/                  binarios oficiales de DNIT, nombrados por hash; solo se agregan (sifen source add)
sources.manifest.yaml     revisiones (sha256, md5, URL, nombre, fecha de subida) y chequeos; solo se le agrega
raw/                      texto y celdas extraídos (generado por sifen extract; nadie lo edita a mano)
extraction/fixes.yaml     única vía para corregir defectos conocidos de extracción
kb/                       el canónico: documents/ fields/ validations/ issues/ y _meta.yaml
cases/                    casos observados y sanitizados; no son normativos
curation/                 prompts/ (instrucciones de curación) y runs/ (bitácora generada por hooks)
src/sifen_kb/             librería y CLI (model, yamlio, normalize, sources, extract, pdf/, temporal, dsl…)
tests/                    unit/, evidence/, integrity/, golden/ (casos temporales), fixtures/
docs/                     arquitectura, guía de uso, guía de curación, investigación
.claude/settings.json     permisos (deny) y hooks para sesiones de Claude Code
.github/                  CI, release, plantillas de PR e Issues
build/                    artefactos generados (no versionado)
```

## Alcance actual y limitaciones

- **Corpus registrado** (consulta del portal el 2026-10-17): Manual Técnico v150 y su listado de checksums MD5, Notas Técnicas 001–027, Decreto 872/2023, el RAR oficial de XSD y una instantánea de los 47 XSD publicados.
- **MVP: un dominio piloto, receptor e identidad** (campos `C002`, `D011`, `D015`, `D201`, `D202`, `D208`, `D209`, `D210`, `F014`, `F023` y sus validaciones `D208`–`D210b`). El resto del DE (tablas completas del Manual, condición de operación, eventos, servicios web, codificaciones) está en el roadmap de `docs/arquitectura.md` §U. Fuera del piloto, `explain` responde `not_curated` con las menciones, no con una regla.
- **Cobertura temporal.** Las respuestas temporales se garantizan desde `coverage_from` (propuesta: 2023-06-17, la primera NT con calendario). Antes de esa fecha, `outside_coverage`. Las NT 001–012 no declaran vigencia: se ordenan por la fecha del documento y el inicio se marca como aproximado.
- **Eje de fecha.** `--at` significa fecha de **procesamiento** (supuesto A2, pendiente de confirmar con DNIT). Con un XML se resuelven la fecha de emisión y la de procesamiento.
- **Horizonte de fuentes.** El chequeo del portal es manual en el MVP. Si pasó el horizonte, la respuesta lo dice y, vencida la gracia, queda `undetermined`: una NT posterior podría regir.
- **XSD.** DNIT no publica historial: la instantánea solo es evidencia de estructura desde su fecha de obtención; para fechas anteriores es una referencia y no cambia el estado de la regla.
- **Interpretación.** Las condiciones formalizadas indican su nivel (`full`, `partial`, `none`) y sus huecos; no sustituyen el literal oficial.
- **Fuera del alcance:** generar o firmar XML, enviar a SIFEN, evaluar reglas no formalizadas, interfaz web, bases vectoriales. El servidor MCP llega en la Fase 4, si se cumplen las condiciones de `docs/arquitectura.md` §P.
- **No es asesoramiento legal ni tributario.** Ver [`NOTICE`](NOTICE).

## Uso con Claude Code y otros agentes

El repositorio está preparado para que un agente consulte la KB sin responder de memoria:

- [`CLAUDE.md`](CLAUDE.md) fija ocho reglas: ejecutar primero `uv run sifen explain <término> --json`, empezar por `state` y `reasons`, citar el documento oficial, transmitir avisos y horizonte, y no leer XML reales ni certificados.
- `.claude/settings.json` aplica controles que no dependen de que el agente obedezca: `permissions.deny` impide editar `sources/`, `raw/`, `kb/_meta.yaml` o las propias reglas, leer certificados, hacer `git push`/`merge` o registrar fuentes; los hooks de `SessionStart` y `PostToolUse` arman la bitácora `curation/runs/<sesión>.yaml`.
- Para curar, el agente lee primero [`curation/prompts/curar_entidad.md`](curation/prompts/curar_entidad.md). Un agente puede redactar efectos, formalizaciones e Issues; nunca copia literales ni fechas (lo hace `sifen draft`) ni hace merge.
- Cualquier otro agente puede usar el contrato JSON de `sifen explain --json`.

## Cómo contribuir

Hay dos tipos de PR y no se mezclan: **conocimiento** (`kb/`, `tests/golden/`, `cases/`, `curation/`) y **código** (todo lo demás); el check `pr-scope` del CI lo exige. También son útiles los avisos de una NT nueva o re-subida y los casos de rechazo observados y sanitizados (nunca XML reales). Lee [`CONTRIBUTING.md`](CONTRIBUTING.md) y [`SECURITY.md`](SECURITY.md).

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

## Licencia y aviso

El código y la documentación propia se publican bajo licencia [MIT](LICENSE), © 2026 Hugo Maldonado.

Los documentos de `sources/` son documentos públicos oficiales de DNIT, se redistribuyen sin modificación con fines de trazabilidad y **no** están cubiertos por la licencia MIT; su autoridad es DNIT. El texto de `raw/` es una extracción automática de esos documentos. Este proyecto no está afiliado a DNIT y no constituye asesoramiento legal ni tributario. Detalle en [`NOTICE`](NOTICE).

---

## Summary (English)

**sifen-kb** is a versioned, verifiable technical knowledge base for **SIFEN**, Paraguay's electronic invoicing system. The base Technical Manual is not the rule currently in force: each Technical Note (NT) changes rules on its own dates, with different dates for the test and production environments, and the tax authority (DNIT) re-uploads NT files and edits XSD schemas in place. A rule such as validation code `1321` (threshold 60,000,000 in the Manual, 35,000,000 in NT 21, 7,000,000 in NT 24) therefore depends on the date and environment.

`sifen explain 1321 --at 2025-01-10 --env prod` resolves the rule from official sources identified by hash, literal evidence copied by tooling and checked against the PDF cells, and fully materialized versions. Answers carry an honest state (`in_force`, `removed`, `not_yet_existing`, `undetermined`, `outside_coverage`, `not_curated`), reasons, citations (document, revision hash, page) and the date up to which sources were last checked. There is a single editable canonical form (restricted YAML in `kb/`); AI proposes, a human approves, and mechanical controls (permission denies, hooks, tests, a `pr-scope` CI check) enforce it.

Install with `git clone`, `uv sync` (uv manages Python 3.14); Linux, macOS and Windows via WSL2. Current scope (alpha): a pilot domain (receiver/identity); the rest of the electronic document is on the roadmap. The PDF extractor integrates code from the author's earlier MIT-licensed project `pdf_to_md`. Code and own documentation are MIT-licensed; the official DNIT documents under `sources/` are not covered by that license, belong to DNIT, and are redistributed unmodified for traceability. This project is not affiliated with DNIT and is not legal or tax advice. Docs are in Spanish; see `docs/arquitectura.md` for the full design.

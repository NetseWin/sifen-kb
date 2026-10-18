# Guía de curación

Cómo curar una entidad (un campo o una validación) o una Nota Técnica (NT) en `sifen-kb`, paso a paso. Se apoya en `docs/arquitectura.md` (§D.3 pipeline, §F modelo, §J estrategia con modelos de lenguaje) y en las instrucciones para el agente, [`curation/prompts/curar_entidad.md`](../curation/prompts/curar_entidad.md). Para el proceso de revisión del PR, ver [`CONTRIBUTING.md`](../CONTRIBUTING.md); para la CLI, [`uso.md`](uso.md).

## Principios que no se negocian

1. **Quien decide es una persona.** Un modelo de lenguaje (Claude) puede redactar la parte interpretativa, pero fechas, destinos, clasificación, versiones, resolución de Issues y todo merge los decide y revisa una persona.
2. **Lo literal lo copia una herramienta.** Mensajes, observaciones, longitudes, ocurrencias y fechas llegan a `kb/` con `sifen draft`, desde las celdas de `raw/`. Un test exige igualdad (tras `normalize_text`) con el literal efectivo de la celda citada (sin el texto en rojo). Nadie los teclea, ni siquiera para "arreglar" un literal que parezca erróneo.
3. **Cada cambio es una versión nueva completa.** Las NT reproducen la fila entera, sin "antes/después". El color de resaltado se lee con la leyenda del MT (rojo = eliminado, verde = agregado, amarillo = modificado) y siempre junto con el verbo del encabezado: la acción la decide quien cura, y si el color la contradice hace falta un Issue (ver «Color y verbo»). Lo que declara la NT (verbo, alcance) es una **aserción** que un test compara con el diff.
4. **Historia *append-only*.** Nunca se borra una versión, un efecto ni una fila golden. Una eliminación es una **lápida** que conserva el código; corregir el pasado exige un Issue.
5. **Lo dudoso es un Issue, no una decisión.** Contradicciones entre fuentes, posibles reemplazos no declarados, ambigüedades y prórrogas se registran; las bloqueantes vuelven `undetermined` a las entidades afectadas dentro de su ventana.
6. **Un PR de conocimiento no toca código.** El check `pr-scope` lo exige.

## Antes de empezar

```bash
git switch -c curacion/nt-028            # rama de trabajo (nunca main)
uv sync
uv run sifen status                      # horizonte, pendientes, revisiones sin curar, Issues bloqueantes
```

Si usas Claude Code, el repositorio ya trae `.claude/settings.json` (permisos y hooks) y `CLAUDE.md`. Los hooks arman la bitácora `curation/runs/<sesión>.yaml`: no la edites. Pide al agente que empiece por `curation/prompts/curar_entidad.md`.

## Curar una NT nueva o una re-subida

Es el pipeline de §D.3. Los pasos 1–3 los hace una persona o la herramienta; en los pasos 4–5 el modelo puede asistir; el 6 es automático y el 7–8, de una persona.

### 1. Detectar

```bash
uv run sifen source check
```

Compara el hash de las URL conocidas y de los listados del portal de DNIT y registra el chequeo. Si hay enlaces nuevos o hashes distintos, quedan como "sin registrar" y el horizonte de fuentes **deja de avanzar**: pasada la gracia, las respuestas de la KB pasan a `undetermined` (`beyond_horizon`).

### 2. Registrar (acción humana)

```bash
uv run sifen source add --doc NT_028 --url <url-oficial-del-PDF>
```

Descarga solo desde un dominio de DNIT permitido, calcula `sha256` y `md5`, copia a `sources/NT_028/<sha12>.pdf` y agrega la revisión a `sources.manifest.yaml`. Revisa en el diff la URL y el hash registrados: por ahí entraría una fuente equivocada. Desde este momento toda entidad que el documento menciona responde `undetermined` con `revision_not_curated`. Una re-subida es el mismo comando con el mismo `--doc`: crea otro archivo; nunca se reemplaza el anterior. Las sesiones de Claude no pueden ejecutar este comando.

### 3. Extraer

```bash
uv run sifen extract
git diff --stat raw/                     # qué páginas y filas cambiaron
```

La extracción es determinista; el diff de Git sobre `raw/` ya muestra qué cambió. Si el extractor se equivoca en una celda, no la edites: propone una entrada justificada en `extraction/fixes.yaml` (PR revisado).

### 4. Calendario y efectos

```bash
uv run sifen draft NT_028
```

Copia `document_date` y el calendario por ambiente (`schedule.test` y `schedule.prod`) desde las celdas de la tabla de fechas de la NT a `kb/documents/NT_028.yaml`. **Las fechas se revisan siempre contra el PDF renderizado**: la columna correcta, el ambiente correcto y las erratas (hay NT con el año equivocado en la fecha del documento). Una fecha "a definir" queda como `value: null`: versión prospectiva, nunca vigente.

Después se escriben los **efectos** de la NT en el mismo archivo, uno por cada cambio (cada fila o párrafo "se modifica / se agrega / se elimina / se excluye"):

```yaml
effects:
  - id: NT_028#1
    verb_literal: se modifica
    action: modify
    target: val:DE:D208c
    declared_scope: row
    evidence:
      - raw:NT_028@<sha12>:p3:D208c
    disposition: pending
    interpretation:
      by: llm
      run: <id de la sesión>
```

(Ejemplo de forma, no de contenido: el verbo, el alcance y las referencias salen de la NT.) Reglas:

- `verb_literal` es el verbo del encabezado, tal cual. `action` es `add`, `modify` o `remove` (una exclusión es `modify` solo si el texto restringe el alcance; si elimina la validación, `remove`).
- `declared_scope` lo declara la NT: "se modifica … en la Longitud" es `[length]`; si reproduce la fila entera, `row`, y toda columna que cambió (salvo la observación) va en `acknowledged_changes`.
- `target` es la entidad afectada; si la fila citada trae ID, debe coincidir (un test lo verifica). `null` solo con `disposition`.
- `disposition: pending` mientras no se haya curado; `not_modeled` (con `note` obligatoria) para menciones que el MVP no modela.
- Toda mención del vocabulario curado (IDs, códigos, `xml_name`) en la NT debe quedar reconocida por algún efecto; el guardián de cobertura lo comprueba. Una mención **dentro de una fila que ya cita un efecto aplicado o `pending`** cuenta como reconocida (la observación de D208c nombra D011, D208, F014 y F023 sin modificarlos); las menciones en prosa o en filas no citadas necesitan su propio efecto (`not_modeled` con nota si el MVP no las modela).

Este PR **puede mergearse antes de curar** las versiones: desde ese momento, toda consulta afectada muestra el efecto pendiente (`pending_effect`).

### 5. Curar las versiones

```bash
uv run sifen draft NT_028#1
```

Crea la versión nueva de la entidad apuntada con los literales copiados de las celdas de `raw/` y hereda de la **predecesora temporal en producción** (`based_on`) las columnas que la fila de la NT no trae. `--dry-run` muestra el resultado sin escribir.

Si la entidad todavía no existe en `kb/`, primero se crea su **versión base** desde la fila del Manual Técnico (la línea base de `kb/_meta.yaml`):

```bash
uv run sifen draft val:DE:D208c --baseline raw:MT_V150@976cd88c05c3:p167:D208c
```

El literal que se copia es `RawRow.effective_literal`: la celda sin el texto en rojo, en el MT **y en las NT** (decisiones 2 y 3 del usuario, 2026-10-17: en NT 21 y 24 el rojo también es contenido eliminado, así que D208c rige «mayor a» 35.000.000 / 7.000.000, sin la excepción D011≠13). `draft` avisa qué tramos quitó, para contrastarlos con el PDF; la celda completa (`rendered_literal`) queda en `raw/`. Una lápida copia la predecesora y su fila (entera en rojo) se compara por lo visible.

**Color y verbo (regla «mixta», decisión del usuario del 2026-10-17).** `draft` avisa y `sifen check` (comprobación `marcado`) exige un Issue que nombre el efecto como sujeto (`affects: [{subject: NT_0xx#n}]`) cuando el marcado de la fila contradice el efecto:

- el color contradice la **acción curada** (una fila entera en verde curada como `modify`, una entera en rojo que no es `remove`), el marcado no permite reconstruir el contenido efectivo de forma unívoca (el rojo vacía una celda de una fila que se conserva; la celda ID es un alta o una baja y otras celdas tienen otro color) o un `modify` no cambia el contenido efectivo respecto de la predecesora ⇒ Issue **bloqueante** (abierto, con una ventana que contenga el inicio del efecto en cada ambiente) o resuelto por una persona;
- el color coincide con la acción pero no con el **verbo literal** del encabezado (NT 23: altas en verde bajo «se modifica la siguiente validación») ⇒ Issue **de trazabilidad**, no bloqueante.

Nada de esto va en `extraction/fixes.yaml` (reservado a defectos técnicos de extracción).

Lo que hay que completar a mano, y que es **interpretación**:

- **`condition`** de una validación: `expr` en el DSL (polaridad fija: verdadera cuando la validación se **viola**; `exists()` para campos opcionales; `and`/`or`/`not` en minúsculas), `level` (`full`, `partial`, `none`) y, si no es `full`, `gaps` con lo que no captura. Las constantes deben estar en el literal (`7000000` ↔ `7.000.000`).
- **`enumeration`** de un campo, si la observación enumera valores con su etiqueta.
- Quitar `disposition: pending` del efecto: queda aplicado cuando una versión lo cita (`introduced_by`).

Cada afirmación interpretada lleva `interpretation: {by: llm, run: <sesión>}` (o `by: human` si la escribe una persona sin un modelo). Casos especiales:

| Caso | Tratamiento |
|---|---|
| "Se elimina" | Versión lápida (`kind: tombstone`): copia los literales de la predecesora, **conserva el código** y cita la fila que elimina. |
| Regla nueva con otro ID que parece equivalente a una anterior | Entidad nueva más un Issue `undeclared_change` **bloqueante** sobre la regla anterior desde el inicio de la NT en cada ambiente. No se fusionan sin declaración de DNIT. |
| Prórroga (re-subida con otra fecha, o comunicado) | **No** crea versión nueva: cambió cuándo empieza, no la regla. Se edita el `schedule` con la celda de la revisión nueva, se actualiza `current_revision` y se agrega un Issue `temporal` (resuelto) con ambas fechas. |
| Re-subida que cambia filas sin cambiar fechas | Versión nueva con `from_revision` en el efecto; su inicio es desconocido dentro de una ventana, que cubre un Issue `temporal` bloqueante. Nunca retroactivo sin evidencia. |
| Dos efectos con el mismo inicio sobre la misma entidad | Una sola versión con `introduced_by: [efecto1, efecto2]`. Dos versiones **distintas** el mismo día son un error de datos. |
| Test ≠ producción | Es normal (NT 23: 30/08 y 27/09/2024). No uses la fecha de producción como sustituto de una fecha de test ausente: queda `test_date_missing`. |
| Conflicto o ambigüedad | Issue (`source_conflict`, `ambiguity`, `erratum`…) con su ventana; `blocking` solo si debe volver `undetermined` a las entidades afectadas. |
| Error de curación en una versión pasada | Se corrige en el lugar con un Issue `curation_error` cuyo `corrects` lista el atributo (por ejemplo `val:DE:D208c@NT_021#1.observation`). Nunca se borra. |

Nuevos Issues: `kb/issues/ISS-NNNN.yaml` (siguiente número libre), con `kind`, `affects` (sujeto, ambiente, `since`/`until`), `statement`, `evidence`, `blocking`, `policy`, `status`.

### 6. Verificar

```bash
uv run sifen fmt && uv run sifen check && uv run pytest -q
```

Verifica el formato canónico, la integridad (referencias, biyección efecto↔versión, `based_on`, unicidad de inicios), la evidencia (literal = celda, fila = entidad, fechas por encabezado, constantes en el literal, citas en la página), la cobertura, el golden temporal y que el pasado esté justificado. Corrige **tu cambio**; no relajes un test. Agrega en `tests/golden/temporal.yaml` una fila el día anterior y otra el día de cada frontera nueva, en cada ambiente donde las fechas difieran.

Comprueba el alcance del PR como en el CI: `uv run python -m sifen_kb.prscope origin/main`.

### 7. Revisión humana

El PR de conocimiento se acompaña de un **informe**: por entidad, versión anterior y nueva con su diff; fechas por ambiente; Issues nuevos; cambios al pasado; pendientes que quedan. La persona que revisa —en una sesión distinta y posterior a la curación— usa la checklist de [`CONTRIBUTING.md`](../CONTRIBUTING.md) y de la plantilla de PR: fechas contra el PDF renderizado, alcance declarado, Issues, cambios al pasado.

### 8. Merge y tag

Merge a `main` (protegido) con el trailer `Reviewed-by:` en el mensaje. El workflow `release` crea el tag anotado `kb-AAAA.MM.DD` y adjunta `sources.manifest.yaml` solo si el último commit que tocó `kb/` lleva el trailer.

## Curar una entidad sin una NT nueva

Para ampliar el alcance curado (pasar una validación de `not_curated` a curada):

1. `uv run sifen explain <código o ID> --json` en modo índice lista todas las menciones en `raw/`, de la más reciente a la más antigua por fecha de producción del documento (nunca por número de NT). Esa lista es el inventario: la fila del Manual Técnico (línea base) y cada NT que la cambia, elimina o menciona.
2. Verifica que cada documento mencionado tenga su ficha y calendario en `kb/documents/` (`sifen draft <DocId>` si falta).
3. Registra un efecto por cada NT que modifica o elimina la entidad (o `not_modeled` con `note` si la mención no se modela), y sigue desde el paso 5: versiones con `sifen draft`, interpretación, Issues, golden y verificación.
4. Una entidad queda curada cuando todas sus menciones están reconocidas por un efecto y cada versión cita su fila.

## Qué hace (y qué no) Claude en una sesión de curación

| Tarea | Quién |
|---|---|
| Chequear el portal, descargar y registrar fuentes, extraer | Herramienta; `source add` lo lanza una persona. Claude no. |
| Calendario y literales de una versión | Herramienta (`sifen draft`). |
| Efectos: verbo, acción, alcance, destino | Claude propone; una persona revisa. |
| Formalización de la condición, enumeraciones | Claude propone (es interpretación); una persona revisa. |
| Conflictos, reemplazos no declarados, errores de curación | Claude redacta el Issue; decide una persona. |
| Merge de contenido normativo | Solo una persona (trailer `Reviewed-by:`). |

Los controles no dependen de que el agente obedezca: `permissions.deny` (no puede editar `sources/`, `raw/`, `kb/_meta.yaml`, `.claude/` ni `CLAUDE.md`; no puede hacer `git push`, `git merge`, `gh pr merge`, `gh api` ni `sifen source add`; no lee certificados), los hooks que registran la sesión, las pruebas de evidencia, `pr-scope` y la protección de `main`. Un archivo editado en una sesión de Claude no puede declarar `by: human` para una interpretación nueva (`test_llm_runs_cover_outputs`). Bash sigue siendo una vía no cubierta del todo por las reglas de permisos; por eso las sesiones de curación no deben tener credenciales de push ni acceso a certificados.

### Registrar a posteriori lo que el hook no capturó (backfill)

Si una sesión editó archivos con herramientas que no disparan los hooks (por ejemplo, herramientas MCP), la bitácora quedó incompleta y `sifen check` falla (`corridas_llm`). Es legítimo registrar esas salidas a posteriori, pero de forma **explícita y visible**: no edites `curation/runs/<sesión>.yaml` a mano; usa el modo `Backfill` con un motivo que explique por qué se registró retrospectivamente:

```bash
echo '{"session_id": "<sesión>", "cwd": "'"$PWD"'", "paths": ["kb/..."], "reason": "por qué se registró retrospectivamente"}' \
  | uv run python -m sifen_kb.hooklog Backfill
```

La corrida debe existir ya (el backfill nunca crea su encabezado) y cada salida queda con `source: backfill`, el motivo y el instante del registro: quien revisa el diff ve que es un registro retrospectivo y por qué, y `sifen check` lo informa en un hallazgo `info` por corrida. Un archivo ya registrado por un hook no se toca (su entrada es la evidencia del hecho); uno ya registrado con backfill se actualiza. Si una ruta no es registrable (fuera del repo, en `curation/runs/` o `.git/`, inexistente), no se registra ninguna y el comando termina con error.

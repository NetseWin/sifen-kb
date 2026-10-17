# Cómo contribuir

Gracias por querer mejorar `sifen-kb`. Este documento explica los tipos de PR, el flujo ante una Nota Técnica (NT) nueva, qué revisa una persona antes de aprobar un cambio de conocimiento y las convenciones del repositorio. El diseño que respalda estas reglas está en [`docs/arquitectura.md`](docs/arquitectura.md) (§D.3, §J, §K y §L); la guía paso a paso de curación, en [`docs/curacion.md`](docs/curacion.md).

Antes de empezar:

- Lee el [`README.md`](README.md) y el [`NOTICE`](NOTICE): los documentos de `sources/` son de DNIT y **no** están bajo la licencia MIT.
- **Nunca** subas XML reales, respuestas de SIFEN, certificados, claves ni contraseñas. Ver [`SECURITY.md`](SECURITY.md).
- Para un error o una duda, abre un Issue con las plantillas de `.github/ISSUE_TEMPLATE/`.

## Dos tipos de PR, y no se mezclan

| Tipo | Qué toca | Ejemplos |
|---|---|---|
| **Conocimiento** | `kb/**`, `tests/golden/**`, `cases/**`, `curation/**` | Curar una entidad, registrar efectos de una NT, abrir un Issue, agregar una fila golden, agregar un caso observado y sanitizado, ajustar el prompt de curación |
| **Código** | Todo lo demás con efecto sobre el comportamiento: `src/**`, el resto de `tests/**`, `.github/**`, `.claude/**`, `CLAUDE.md`, `pyproject.toml`, `uv.lock` | Resolvedor, extractor, CLI, pruebas, CI, permisos |
| Neutro (va con cualquiera) | `docs/**`, los `*.md` de la raíz, `LICENSE`, `NOTICE`, `sources/**`, `sources.manifest.yaml`, `raw/**`, `extraction/**` | Documentación, una fuente nueva registrada con `sifen source add`, `raw/` regenerado |

**Por qué no se mezclan.** Un PR de curación que también tocara el código podría, aunque fuera sin querer, desactivar o relajar la prueba que lo detectaría (por ejemplo, la que exige que un literal sea igual a su celda). Y un PR de código no debe cambiar lo que la KB responde. Para que la revisión de cada tipo sea acotada y verificable, el check `pr-scope` del CI **falla** si un PR mezcla conocimiento con código. Un archivo no previsto en las listas se trata como código.

El check también falla si:

- `sources/` recibe algo distinto de **adiciones** (una fuente oficial nunca se modifica, se borra ni se mueve; una re-subida de DNIT es un archivo nuevo);
- se agrega un `*.p12`, `*.pfx`, `*.key`, `*.pem` o `*.jks`.

**Excepción `extractor-recopy`.** Si un cambio del extractor (`src/sifen_kb/extract.py` o `src/sifen_kb/pdf/**`) regenera `raw/` y obliga a volver a copiar con `sifen draft` literales ya curados, el PR puede incluir esos cambios en `kb/`. Para ello el título del PR debe contener la etiqueta `extractor-recopy`; el único código admitido es el del extractor y sus pruebas, y el único conocimiento admitido está bajo `kb/`. El check lo reporta y la revisión humana confirma que en `kb/` solo cambian literales vueltos a copiar. Se puede probar localmente:

```bash
PR_TITLE="extractor-recopy: columnas partidas" uv run python -m sifen_kb.prscope origin/main
```

## Flujo ante una NT nueva o una re-subida

Es el pipeline de `docs/arquitectura.md` §D.3. Cada paso dice quién lo hace.

1. **Detectar** (herramienta). `uv run sifen source check` compara el hash de las URL conocidas y de los listados del portal de DNIT y registra el chequeo. Si no queda nada sin registrar, avanza el horizonte de fuentes.
2. **Registrar** (acción humana, sin modelo de lenguaje). `uv run sifen source add --doc <DocId> --url <url>` descarga desde un dominio de DNIT permitido, calcula `sha256` y `md5`, copia el archivo a `sources/` y agrega la revisión a `sources.manifest.yaml`. Desde ese momento, toda entidad que el documento menciona responde `undetermined` (`revision_not_curated`) hasta que se cure. Este comando lo ejecuta una persona; las sesiones de Claude Code lo tienen denegado.
3. **Extraer** (herramienta). `uv run sifen extract`. El diff de Git sobre `raw/` ya muestra qué páginas y qué filas cambiaron.
4. **Calendario y efectos.** `uv run sifen draft <DocId>` copia la fecha del documento y el calendario por ambiente desde las celdas de la tabla de fechas. Quien cura (persona o Claude) escribe los **efectos**: verbo literal, acción, alcance declarado y evidencia. **Un revisor humano revisa siempre las fechas.** Este PR puede mergearse antes de curar: desde ese momento, toda consulta afectada muestra el pendiente.
5. **Curar.** `uv run sifen draft <DocId>#<n>` crea la versión nueva de la entidad copiando las celdas de `raw/` y heredando de la predecesora temporal lo que la fila de la NT no trae. Quien cura clasifica, formaliza la condición y abre Issues ante reemplazos no declarados, conflictos o ambigüedades.
6. **Verificar.** `uv run sifen fmt && uv run sifen check && uv run pytest -q` (ver la sección siguiente).
7. **Revisión humana** del PR de conocimiento con la lista de la sección siguiente.
8. **Merge y tag.** Merge a `main` con el trailer `Reviewed-by:`; después, el workflow `release` crea el tag anotado `kb-AAAA.MM.DD`, solo si el último commit que tocó `kb/` lleva ese trailer.

Los pasos 1–3, 6 y 8 no usan un modelo de lenguaje. En los pasos 4 y 5 un modelo puede clasificar y formalizar, pero **todo lo literal lo copia la herramienta** y lo verifica una prueba. Una re-subida sigue el mismo camino.

## Checklist de revisión humana de un PR de conocimiento

Quien revise lo hace **en una sesión distinta y posterior a la curación**, con la plantilla de PR (`.github/pull_request_template.md`):

- [ ] **Fechas contra el PDF renderizado.** Abre el PDF de `sources/` y compara, para cada ambiente (test y producción), la fecha de la tabla con la de `kb/documents/<DocId>.yaml`. No basta con el literal copiado: confirma que la columna es la del ambiente correcto y que la fecha del documento no es una errata.
- [ ] **Alcance declarado.** El `declared_scope` de cada efecto coincide con lo que dice la NT ("se modifica … en la Longitud" → `[length]`); si es la fila entera (`row`), todo lo que cambió además de la observación figura en `acknowledged_changes`. Ningún cambio de severidad, código o mensaje pasa sin reconocerse.
- [ ] **Destino y clasificación.** Cada efecto apunta a la entidad correcta (la clave de fila de la celda citada es el ID de la entidad), con la acción correcta (`add`, `modify`, `remove`; una eliminación es una lápida que conserva el código).
- [ ] **Issues.** Los reemplazos no declarados, los conflictos entre fuentes, las ambigüedades y las prórrogas tienen su Issue, con su ventana y si es bloqueante. Nada dudoso se resolvió en silencio; lo dudoso está en `open_questions`.
- [ ] **Interpretación.** Las condiciones formalizadas indican `level` y `gaps`; las constantes están en el literal; la polaridad es "se viola cuando".
- [ ] **Cambios al pasado.** El informe del PR enumera aparte los cambios a versiones ya existentes. Todo cambio al pasado tiene un Issue `curation_error`, `erratum` o `temporal` que lo declara; no se borró ninguna versión, efecto ni fila golden.
- [ ] **Golden.** Cada frontera temporal nueva tiene una fila el día anterior y otra el día del cambio, en cada ambiente donde las fechas difieran.
- [ ] **El PR es solo de conocimiento** (`pr-scope` en verde) y no se editaron `sources/`, `raw/` ni `kb/_meta.yaml` a mano.
- [ ] **Sin datos sensibles** en casos ni en Issues (nada de RUC, cédulas, CDC reales ni XML).

## Cómo correr las pruebas y los linters

```bash
uv sync                                    # una vez (Python 3.14 gestionado por uv)
uv run pytest -q                           # todas las pruebas
uv run pytest -q tests/unit/test_prscope.py  # un archivo
uv run ruff check .                        # lint
uv run ruff format --check .               # formato (sin --check, reformatea)
uv run sifen fmt --check                   # kb/ está en formato canónico (sin --check, lo reescribe)
uv run sifen extract --check               # raw/ regenerado == raw/ versionado, byte a byte
uv run sifen check                         # esquema, formato, integridad, evidencia y cobertura (rápido)
uv run python -m sifen_kb.prscope origin/main   # alcance del PR, como en el CI
```

El CI ejecuta lo anterior con `uv sync --locked`, más `gitleaks`. `test_past_changes_justified` compara contra la base de `main`, por eso el CI hace el checkout con historial completo (`fetch-depth: 0`); si lo corres localmente, asegúrate de tener `origin/main`.

No agregues dependencias sin discutirlo antes en un Issue: el diseño limita deliberadamente las de ejecución (pydantic, pyyaml, xmlschema). Quien las agrega debe actualizar `uv.lock`, y eso es un PR de código.

## Convenciones

- **YAML canónico.** Todo archivo de `kb/` (y el manifiesto) debe ser idéntico a lo que produce `uv run sifen fmt`: sin comentarios, sin anchors ni alias, sin claves duplicadas, literales en bloque `|-`, todo escalar como texto (los códigos como `1321` o `0160` y las fechas llegan como `str`; Pydantic las tipa). `sifen fmt --check` falla ante un comentario, un truncamiento o un formato no canónico. Lo que importa va en `note`, `gaps` u `open_questions`.
- **Literales solo con `sifen draft`.** Mensajes, observaciones, longitudes, ocurrencias y fechas se copian desde las celdas de `raw/` con `sifen draft`; nunca se teclean ni se parafrasean, ni siquiera "para corregir un error evidente". Un defecto de extracción se corrige solo con una entrada justificada en `extraction/fixes.yaml` (PR revisado).
- **Un solo canónico.** No agregues otra representación de una regla (JSON, Markdown, tablas) que se pueda editar. Lo generado va a `build/` y no se versiona.
- **Historia *append-only*.** Se agregan versiones, efectos e Issues; no se borran. Una eliminación de DNIT es una lápida; una corrección del pasado exige un Issue.
- **Código.** Python 3.14, `ruff` (línea de 110 caracteres), tipos y módulos pequeños. Toda escritura de archivos con `encoding="utf-8", newline="\n"`; la salida de la CLI es UTF-8 con LF. Nunca `eval` ni `yaml.load` sin el `KBLoader`.
- **Idioma.** Documentación y mensajes de usuario en español con ortografía correcta (tildes, eñe); los identificadores técnicos en su forma original (`iTipIDRec`, `D208c`, `val:DE:D208c`).
- **Commits.** Mensajes en español con prefijo de tipo (`feat`, `fix`, `docs`, `test`, `chore`, `style`) y alcance opcional, por ejemplo `feat(sources): …`. Un commit, un cambio.
- **Trailer `Reviewed-by:`.** Todo merge de un PR de conocimiento a `main` lleva en el mensaje del commit de merge (o de *squash*) una línea de la forma:

  ```text
  Reviewed-by: Nombre Apellido <correo@ejemplo.com>
  ```

  La escribe la persona que revisó, no quien curó ni el agente. El workflow `release` solo crea el tag `kb-AAAA.MM.DD` si el último commit de `main` que tocó `kb/` la lleva. Con una sola persona en el proyecto, el protocolo es: revisión en una sesión distinta y posterior a la curación, con la checklist anterior, y el trailer en el merge. Con dos personas, la aprobación del PR y los CODEOWNERS pasan a ser obligatorios.
- **`main` protegido.** PR obligatorio, CI en verde, sin *force-push* ni borrado y sin excepciones para administradores. Nadie hace `push` directo a `main`.

## Sesiones con Claude Code

Si curas con Claude Code, el repositorio ya trae [`CLAUDE.md`](CLAUDE.md), `.claude/settings.json` y el prompt [`curation/prompts/curar_entidad.md`](curation/prompts/curar_entidad.md). Los permisos impiden que el agente edite evidencia o metadatos, registre fuentes, haga `push` o `merge`, o lea certificados; los hooks registran la sesión en `curation/runs/`. Un archivo editado en una sesión de Claude no puede declarar `by: human` para una interpretación nueva. Esos controles no sustituyen la revisión humana.

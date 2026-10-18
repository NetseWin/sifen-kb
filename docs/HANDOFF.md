# Traspaso de desarrollo — sifen-kb

Estado al **2026-10-18** (último commit de esta etapa: ver `git log`). Este documento es para quien **continúe
el desarrollo** (persona o sesión de Claude). Para *usar* la KB, ver `README.md` y `docs/uso.md`.

Léelo entero antes de tocar nada. El diseño está cerrado: **no rediseñar**; implementar lo que falta según
`docs/arquitectura.md` y las decisiones de la sección 2.

## ▶ Retomar aquí (actualizado el 2026-10-18, al cerrar el paso B)

- **Paso B (curación): hecho, verificado y commiteado** en `kb/piloto-receptor`: `7ba7fdb` (aprobado por el
  usuario; `sifen check` 0 errores, `pytest -q` 1833 passed / 1 skipped previsto).
- **Publicado (2026-10-18):** `https://github.com/NetseWin/sifen-kb` (público; solo merge commit; `main` protegida:
  PR obligatorio, check `checks` en verde, sin force-push ni borrado, también para administradores). PR #1
  (`feat/literal-efectivo`) y PR #2 (`feat/bitacora-procedencia`) integrados con merge commit (`aa76b37`,
  `c8a6bca`); CI en verde. **PR #3** (`kb/piloto-receptor`, conocimiento) abierto: **lo revisa y mergea el
  usuario** (merge commit, `Reviewed-by:`). Después siguen los próximos pasos reales de la sección 5: T.8,
  revisión humana contra los PDF renderizados, merge del PR #3, follow-ups de código y primera release.
- **Autonomía (decisión del usuario, 2026-10-18):** la sesión decide sola lo técnico y de proceso (ramas,
  rebases, verificaciones, bitácoras, docs, commits de trabajo en ramas de feature) y consulta solo lo normativo
  de SIFEN, push/merge/PR/publicación, lo destructivo o irreversible, credenciales, cambios de alcance o de
  diseño y bloqueos reales.
- Contexto del paso B: Re-materializadas con `sifen draft` las 8
  versiones con literal efectivo (D208 @NT_002#1/@NT_023#1, D210 @NT_002#2/@NT_023#2, F023 @NT_008#1, D208c
  @NT_021#1/@NT_024#1, 1314 @NT_023#4) y rehechas sus interpretaciones; ISS-0014 nuevo (trazabilidad
  NT_023#5–#7); ISS-0010 e ISS-0012 resueltos (la cláusula D011≠13 en rojo la traza solo ISS-0011); golden
  actualizado (1314 desde NT 23 `in_force`, filas `diff` e ISS-0014, sin `id` duplicados). Detalle:
  `docs/traspaso-curacion-piloto.md` §1, §3 (decisiones 13–15) y §4 «Paso B»; informe:
  `docs/informe-revision-piloto.md`.
- **Bitácora (decisión 1b′):** la sesión editó con herramientas MCP, que no disparan `PostToolUse`. El PR de
  código `feat/bitacora-procedencia` (`6e0c377`, worktree `../sifen-kb-bitacora`, aprobado y commiteado) agrega
  `source: hook|backfill` por salida y el modo manual `python -m sifen_kb.hooklog Backfill`. El bridge abrió 3
  sesiones de Claude Code; cada archivo se registró como `backfill` en la de su última edición real: 15 salidas
  en `ce4ca541`, 1 en `6b58d45f` (golden) y 3 en `6767ad7f` (`HANDOFF.md`, traspaso, ISS-0012). El informe no se
  registró (procedencia mixta, worker + MCP; nota en su cabecera). Las tres bitácoras entran en el commit.
- **`kb/piloto-receptor`** rebasada sobre `feat/bitacora-procedencia` (stash con OK del usuario, sin conflictos):
  `16d6e87` (`_meta.yaml`), `e9ff1e0` (curación previa al literal efectivo), `8465490` (prompt y traspaso), sobre
  `6e0c377` ← `215175e` ← `0685ce4`. Cierre: `git diff --check`, ruff y `sifen fmt --check` OK; `sifen check`
  0 errores (8 informativos); `pytest -q` 1833 passed, 1 skipped (previsto); `explain` focalizados como se
  esperaba; anexo del informe regenerado con `sifen check --report`.
- **Integración:** las ramas estaban apiladas en línea sobre `main`, así que no se rebaseó nada (`pr-scope`
  compara contra el ancestro común) y cada PR entra con merge commit: los hashes citados en `kb/` y `docs/`
  siguen existiendo en `main`. No usar squash ni «rebase and merge» (desactivados en el repo).
- **Follow-up (PR de código independiente, NO en el paso B):** ampliar el matcher del hook `PostToolUse` y los
  `deny` `Edit(...)` de `.claude/settings.json` a las herramientas MCP de escritura (p. ej.
  `mcp__.*__(edit|write)`), con tests de `hooklog`.
- **Paso A (código): hecho y commiteado** en `feat/literal-efectivo` (worktree `../sifen-kb-literal-efectivo`):
  `0685ce4` literal efectivo + comprobación `marcado`; `215175e` C002 documentado por MT/NT frente al XSD.
- **Pendiente de decidir con el usuario:** `cut_kb` conserva Issues posteriores al corte (un Issue no tiene fecha
  propia). El `NOTICE` ya está decidido (2026-10-18, opción 1a: publicar tal cual; sección 2).
- Reglas de trabajo con este usuario: commits de trabajo en ramas de feature sin pedir permiso (autonomía de
  arriba); nunca push, merge ni `git clean` sin su OK; `git stash` solo para preservar trabajo, con respaldo previo; preguntas de decisión como texto numerado (1a, 2b…). Mapa de
  documentos: sección 8.

---

## 1. Qué es, dónde está y en qué etapa

- **Qué es:** base de conocimiento técnica de SIFEN (facturación electrónica de Paraguay) que responde qué regla
  rige en una fecha y ambiente, con evidencia literal verificada contra los PDF oficiales de DNIT.
- **Diseño (fuente de verdad del diseño):** `docs/arquitectura.md` (secciones A–V + «Decisión recomendada»).
  Investigación de respaldo en `docs/investigacion/` (`sifen.md` hechos de DNIT verificados, `pdf.md`,
  `stack.md`, `priorart.md`).
- **Repo local:** `/home/soporte/proyectos/sifen-kb` en WSL2 Ubuntu 26.04 (usuario `soporte`).
  Desde Windows: `\\wsl.localhost\Ubuntu\home\soporte\proyectos\sifen-kb`.
- **GitHub:** publicado el 2026-10-18 en `https://github.com/NetseWin/sifen-kb` (**público**; ver «Retomar aquí»).
- **Etapa:** construyendo el **MVP = Fases 0–1** del roadmap (`docs/arquitectura.md` §S, §T, §U) en el dominio
  piloto **receptor/identidad** (D208c / código 1321 y afines).

## 2. Decisiones tomadas con el usuario (no reabrir sin preguntarle)

| Tema | Decisión |
|---|---|
| Licencia del código | **MIT** (`LICENSE`, Copyright 2026 Hugo Maldonado). |
| Documentos DNIT en el repo público | **Sí**, PDF/XSD oficiales en `sources/` y su texto extraído en `raw/`, con aviso en `NOTICE`. |
| Revisión del contenido normativo | **El usuario revisa y mergea** el PR de conocimiento (`kb/`, `tests/golden/`, `cases/`, `curation/`). Claude puede mergear código e infraestructura. |
| Valores por defecto (§V) | Aceptados todos: `coverage_from = 2023-06-17`; línea base = MT publicado (sha256 `976cd88c…`, con Issue porque su MD5 no coincide con el listado oficial); gracia del horizonte 7 días; piloto receptor/identidad; repo público `NetseWin/sifen-kb`; documentación en español. |
| Extractor PDF | **Integrar el extractor del proyecto privado del usuario `~/proyectos/pdf_to_md`** (árbol de etiquetas; 6 085/6 085 celdas críticas verificadas) bajo MIT. Hecho: `src/sifen_kb/pdf/` (origen: commit `8603b5b`). |
| Nombre | Repo `sifen-kb`, paquete `sifen_kb`, CLI `sifen`. |
| Estilo de trabajo | Si algo depende del usuario, **preguntarle**; no tomar decisiones que no corresponden. |

**Decidido (2026-10-18, opción 1a: publicar tal cual):** `NOTICE` declara que la *estructura e interpretación* de
`kb/` están bajo MIT y que los *literales copiados de DNIT* quedan fuera de la licencia. *(Estado histórico
superado: esta nota figuraba como «pendiente de confirmar con el usuario»; ya no lo está.)*

## 3. Entorno y comandos

- Herramientas (en `~/.local/bin`): **uv 0.12.10**, Python **3.14.7** gestionado por uv (`.python-version`),
  **gitleaks 8.30.1**. `sudo` pide contraseña: no se usó apt (no hizo falta).
- Comandos habituales (desde la raíz del repo):

  ```bash
  uv sync                       # instala runtime + grupos dev e ingest
  uv run pytest -q              # ~6 min: la extracción sobre PDF reales es lo lento
  uv run pytest -q tests/unit   # rápido
  uv run ruff check . && uv run ruff format --check .
  uv run sifen extract --check  # raw/ regenerado == versionado (byte a byte, ~45 s)
  uv run sifen --help
  ```

- **Mejor forma de continuar con Claude Code:** abrirlo **dentro de WSL** con cwd = el repo. Así se cargan
  `CLAUDE.md`, `.claude/settings.json` (deny + hooks de bitácora) y las rutas son nativas.
- Si se trabaja desde Claude Code en **Windows** (como en esta etapa), los comandos van así (el `--exec` es
  obligatorio; sin él se pierden las variables `$x`; `exec </dev/null` evita que algo consuma stdin):

  ```bash
  MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu --exec bash -lc 'exec </dev/null; cd ~/proyectos/sifen-kb && export PATH=$HOME/.local/bin:$PATH && uv run pytest -q tests/unit'
  ```

  y los archivos se leen/escriben por la ruta UNC `\\wsl.localhost\Ubuntu\home\soporte\proyectos\sifen-kb\…`.
- **GitHub:** WSL tiene `gh` nativo (`/usr/bin/gh`, 2.46.0) autenticado como **NetseWin** (protocolo https;
  scopes `gist`, `read:org`, `repo` y `workflow`). El repo tiene `origin` = `https://github.com/NetseWin/sifen-kb.git`
  y un credential helper **local al repo** (`credential.https://github.com.helper = !/usr/bin/gh auth
  git-credential`); la configuración global de git no se tocó. (Hasta el 2026-10-18 solo había `gh` de Windows,
  sin el scope `workflow`.)
- Identidad git de este repo (config local, decisión del usuario 2026-10-18): `Hugo Maldonado
  <92177318+NetseWin@users.noreply.github.com>`. La global de WSL sigue con el email personal: no commitear con
  ella. Antes de publicar se reescribió toda la historia con el noreply (ver «Historial reescrito» en la sección 6). Los commits llevan el trailer
  `Co-Authored-By: Claude …`.
- `.codegraph/` (índice local de CodeGraph) está en `.gitignore`.

## 4. Estado por componente

Suite al cierre del paso B (rama `kb/piloto-receptor`): **1833 passed, 1 skipped** (el previsto:
`tests/unit/test_explain.py:929`). `ruff check` y
`ruff format --check` limpios. `sifen extract --check` en verde.

| Componente | Archivos | Estado | Notas |
|---|---|---|---|
| Contratos base | `model.py`, `normalize.py`, `yamlio.py`, `load.py`, `cli.py` | ✅ | Modelos de §F; YAML restringido (`KBLoader`: todo escalar es `str`); `KB` con índices derivados y `reindex()`; CLI argparse con 8 comandos cableados. |
| Fuentes | `sources.py`, `sources.manifest.yaml`, `sources/` | ✅ | 32 revisiones: MT_V150, NT_001–027, CHECKSUM_MT, NORMA_DECRETO_872_2023, XSD_RAR, XSD_DIR (47 XSD en `sources/XSD_DIR/2026-10-17/`). Un `source check` limpio (horizonte 2026-10-17). 44 tests. |
| Evidencia `raw/` | `extract.py`, `extract_tables.py`, `extract_ledger.py`, `rawio.py`, `pdf/**`, `extraction/fixes.yaml` | ✅ | `raw/` completo: 30 documentos, 302 páginas, 1 180 filas (509 campos y 445 validaciones del MT; fila `fechas` de NT 013–027), libro de cambios NT→MT en `raw/_ledger/changes.jsonl` (211). 326 tests vendorizados en `tests/extraction/`. Tests nuevos hechos y en verde: `test_golden_piloto.py`, `test_raw_contract.py`, `test_extract_determinism.py` y unitarios de `apply_fixes`/`parse_fixes`/`RawRow.current`. |
| DSL de condiciones | `dsl.py` | ✅ | `parse`/`evaluate` (Kleene)/`fields`/`constants`/`unparse`/`literal_contains_constant`. Sin `eval`. 232 tests. |
| Resolvedor temporal | `temporal.py`, `mentions.py` | ✅ | `resolve`, `resolve_xml_axes`, `timeline`, `cut_kb`, `diff_versions`, `chosen_version`, `index_answer`. Fixture `tests/fixtures/kb_hyp{,_rev2}` (generada por `make_kb_hyp.py`), `golden_hyp.yaml`, Hypothesis. 94 tests. |
| XSD / XML | `xsd.py` | ✅ | Carga 100 % offline, `XsdIndex.lookup/check_occurrence`, `validate_xml`, `read_values`, fechas de emisión/procesamiento, `mask`, `PII_ELEMENTS`, `snapshot_from_manifest`. Fixtures en `tests/fixtures/xml/` (ver su README). 136 tests. |
| Claude Code / CI / docs | `CLAUDE.md`, `.claude/settings.json`, `hooklog.py`, `prscope.py`, `.github/`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`, `docs/uso.md`, `docs/curacion.md`, `curation/prompts/curar_entidad.md` | ✅ | 138 tests (hooklog + prscope). Sintaxis de permisos/hooks verificada contra code.claude.com. `actionlint` limpio. |
| **Consulta** | `explain.py` | ✅ | `sifen explain` y `sifen status` (commit `d2eef71`). Enumeración documentada por MT/NT frente a la aceptada por el XSD (`xsd.enumeration`, decisión 8) y fecha de NT 001–012 como cita: `215175e`. |
| **Integridad y formato** | `integrity.py` | ✅ | `sifen check` (29 comprobaciones, `--report`) y `sifen fmt` (commits `0a0e9ca`, `08cd5f7`). `literales` contra `effective_literal` y comprobación `marcado` (regla «mixta»): `0685ce4`. |
| **Borrador desde celdas** | `draft.py` | ✅ | `sifen draft <DocId>`, `<EffectId>`, `<clave> --baseline <RowRef>` (commit `2ebf82a`). Copia `effective_literal`, avisa tramos quitados y conflictos del marcado; `--dry-run` corregido: `0685ce4`. |
| **Conocimiento curado** | `kb/`, `tests/golden/temporal.yaml` | 🟡 paso B commiteado, PR #3 abierto | Rama `kb/piloto-receptor` (paso B en `7ba7fdb`, sobre `6e0c377`). Bitácora resuelta con `backfill`; `sifen check` 0 errores; CI del PR #3 en verde. Falta el merge, que hace el usuario. Ver «Retomar aquí» y `docs/traspaso-curacion-piloto.md` §4. Va en un PR aparte que revisa el usuario. |

## 5. Próximos pasos, en orden

a) **Cierre documental** de esta etapa: dejar `docs/` (este archivo, `docs/traspaso-curacion-piloto.md` y
   `docs/informe-revision-piloto.md`) coherente con el estado real (PR #1/#2 integrados, paso B hecho y
   verificado, PR #3 abierto). Es esta revisión misma.
b) **T.8 — evaluación ciega** (plantilla en `docs/evaluacion.md`): el usuario escribe las 15 preguntas y su
   clave de respuestas **antes** de ver salidas de `sifen explain`. La plantilla ya está corregida (la trampa
   «D208b después de NT 23» espera `removed`, `introduced_by: NT_010#6` e ISS-0002 como Issue no
   bloqueante/aviso). **No ejecutar todavía la evaluación.**
c) **Revisión humana del PR #3** contra los PDF renderizados: checklist **sin marcar** en
   `docs/informe-revision-piloto.md` §11 (trabajo del usuario).
d) **Merge del PR #3** por el usuario (merge commit con trailer `Reviewed-by:`; sin squash ni «rebase and
   merge», desactivados en el repo).
e) **Follow-ups de código** (PR de código independiente):
   - ampliar el matcher del hook `PostToolUse` y los `deny` `Edit(...)` de `.claude/settings.json` a las
     herramientas MCP de escritura (p. ej. `mcp__.*__(edit|write)`), con tests de `hooklog`;
   - `cut_kb` conserva Issues posteriores al corte (un Issue no tiene fecha propia): requiere una decisión del
     usuario sobre qué significa «posterior».
f) **Primera release:** tras el merge del #3, `release.yml` (manual) crea el tag `kb-AAAA.MM.DD` y la release
   con el manifiesto.

### Estado histórico (plan original de §5) — se conserva por trazabilidad; todo está hecho, salvo lo indicado

1. Tests nuevos del extractor (`tests/extraction/test_golden_piloto.py`, `test_raw_contract.py`,
   `test_extract_determinism.py` y unitarios de `apply_fixes`/`parse_fixes`/`RawRow.current`): **hechos y en
   verde** (qué fija cada uno se ve en el propio test; la especificación original era: filas del MT, contrato
   de `raw/` y determinismo de la extracción).
2. `integrity.py` + `draft.py` (+ `normalize.parse_date_literal` con fechas en palabras y `dd-mm-aaaa`):
   **hechos** (`cmd_fmt`, `cmd_check` con las comprobaciones de §K.3/§K.4 y `--report`, `cmd_draft`).
3. `explain.py` (+ `cmd_status`, `--json`, `--xml`, `--history`): **hecho** (commit `d2eef71`).
4. Curación del piloto: **hecha** (paso B, `7ba7fdb`; PR #3).
5. `tzdata; sys_platform == 'win32'` en `pyproject.toml` (para Windows): **hecho**.
6. Reemplazar los marcadores `<!-- SALIDA-REAL -->` (README y `docs/uso.md`) por salidas reales de
   `sifen explain`: **hecho** en el cierre documental del PR #3 (salidas reales de `explain 1321` y `explain 1400`
   ejecutadas contra un checkout limpio de `e7d0f2c`).
7. Definition of Done (`docs/arquitectura.md` §T): plantillas listas en `docs/evaluacion.md`; T.8 pasa al paso
   b) de arriba, T.11 y T.12 los completa el usuario (T.12 después del merge).
8. Publicación en GitHub: **hecha** (repo público `NetseWin/sifen-kb`, `main` protegida, PR #1 y #2 integrados
   con merge commit); la release (tag `kb-AAAA.MM.DD`) queda en el paso f).

## 6. Hallazgos que conviene no redescubrir

**Portal DNIT:** Liferay; archivos en `/documents/<grupo>/<carpeta>/<título>/<uuid>?t=<ms>`; `?t=` es epoch en
milisegundos (UTC) = **subida**, no publicación ni vigencia; títulos con `+` por espacio; `www.set.gov.py`
redirige a `www.dnit.gov.py`; `dnit.gov.py` sin `www` no resuelve; índice XSD de `ekuatia.set.gov.py` en
ISO-8859-1. `XSD_RAR` («Estructura_DE xsd.rar») contiene un XML, no XSD. El Decreto 872/2023 está en
`/web/e-kuatia/decretos` (25 MB; extracción geométrica con ruido, sin tablas).

**Extracción:** texto por página = texto de la IR antes de unir tablas (`verify.ir_page_text`): incluye texto
tachado/rojo y encabezados repetidos, excluye lo que está fuera del árbol de etiquetas (pie del MT). Página
impresa del MT desde el pie «septiembre de 2019 NNN» (PDF 1, 62, 113, 118, 146, 160, 194 no tienen pie →
`null`). Marcas: `changes` por atributo, `row_change` por fila, `marks` con posiciones; `RawRow.current(attr)`
quita lo tachado. El `note_info` vendorizado pierde la fecha de producción de NT 021/024 (rótulo en dos
renglones): la fila `fechas` propia lo resuelve. NT_023 escribe las fechas **en palabras**.

**Resolvedor temporal** (interpretaciones de ambigüedades de §G, documentadas en `temporal.py`):
`test_date_missing` aplica desde `min(document_date, inicio en prod)`; un pendiente sin fecha bloquea si su
documento ya existía y siempre figura en `upcoming`; `from_revision` → `max(fecha declarada, portal_t)`; sin
ningún chequeo limpio → siempre `beyond_horizon`; dos versiones con el mismo inicio → `TemporalDataError`;
`axis_split` también cuando un veredicto es `None` y el otro `bool`; `cut_kb` no reconstruye calendarios
anteriores a una prórroga.

**XSD:** todas las rutas del piloto verificadas (p. ej. `iTipIDRec` = `/rDE/DE/gDatGralOpe/gDatRec/iTipIDRec`,
`dTotGralOpe`/`dTotalGs` bajo `gTotSub`, `iTipTra`/`cMoneOpe` bajo `gOpeCom`). `fecUTC` exige desplazamiento
(`AAAA-MM-DDThh:mm:ss±hh:mm`); `dFeEmiDE` no lleva zona. `rProtDe` solo se alcanza vía `rRetEnviDe`
(`WS_SiRecepDE_v150.xsd`), por eso `load_schema` carga dos entradas. `gOblAfe`: manual 0-11 vs XSD 0-12
(Issue `source_conflict` ya previsto).

**DSL:** números del texto fuente a `Decimal` (sin float); `exists()` nunca es UNKNOWN; con tipo "N" un valor
no numérico da UNKNOWN; `literal_contains_constant` usa convención es-PY (punto = miles, coma = decimal).

**Historial reescrito (2026-10-18, antes de publicar):** los 26 commits se reescribieron con el email noreply
(autor y committer; nombre y fechas intactos) y se remapearon las citas a commits en `kb/` y `docs/`
(`e9b482c→0685ce4`, `30d4c99→215175e`, `b036909→6e0c377`, `401dac1→7ba7fdb`, `8ec4d04→d2eef71`…; mapa completo
en `.git/noreply-rewrite/map.tsv`, respaldo en `.git/backup-pre-noreply.bundle`, ambos solo locales). Las citas a
commits que ya no estaban en la historia antes de reescribir (`5d41560`, `1d42499` y los `base_commit`
`926f1eb…`/`8e86a454…` de las bitácoras) se dejaron como estaban: no tienen un equivalente exacto. El remapeo
cambió mecánicamente `ISS-0009.yaml` y el traspaso después de su `backfill`: sus `sha256` en las bitácoras
`ce4ca541` y `6767ad7f` son los del contenido anterior al remapeo. Este archivo se volvió a registrar después
(último registro: commit `59c83c3`); las correcciones documentales de la revisión del PR #3 (HANDOFF, traspaso e
informe) no se registraron: son solo docs, sin interpretación `by: llm`, y la bitácora no se tocó en esa revisión.

**Arnés sin herramientas nativas:** si la sesión corre en un arnés que edita con herramientas MCP
(p. ej. Pi: `mcp__custom-tools__edit`/`write`), ni el hook `PostToolUse` (matcher `Edit|Write|MultiEdit`) ni los
`deny` `Edit(...)` de `.claude/settings.json` las alcanzan: la bitácora queda sin `outputs` y `sifen check`
(`corridas_llm`) falla. Le pasó a la sesión `ce4ca541` del paso B (2026-10-18).

**Hooks/permisos de Claude Code:** `Edit(ruta)` cubre todas las herramientas de escritura; rutas con `/` =
relativas a la raíz del proyecto; las reglas `Bash(...)` no son un límite de seguridad (la protección real es
la rama protegida y no darle credenciales de push a la sesión). La carpeta de XML reales se bloquea en
`.claude/settings.local.json` (ver `SECURITY.md`).

## 7. Cómo trabajar con subagentes (lecciones de esta etapa)

- Un agente por conjunto de archivos; los compartidos (`model`, `normalize`, `yamlio`, `load`, `cli`) los
  cambia solo el coordinador.
- No correr `ruff format` sobre todo el repo mientras otros agentes trabajan, ni `uv add`/`uv lock` en paralelo.
- `ruff format` formateaba los bloques de Python de los Markdown: por eso `docs` y `*.md` están excluidos.
- El 2026-10-17 hubo un 429 «session limit» con 5 agentes en paralelo; con 3–4 funcionó.
- Modelos usados: Opus para resolvedor temporal, integración del extractor y curación; Sonnet para fuentes,
  DSL, XSD, documentación y CLI.
- Un subagente de curación con permiso solo sobre `kb/` y `tests/golden/` no puede integrar su traspaso en
  `docs/` ni dejarlo en el scratchpad (`/tmp`, se pierde al reiniciar): dárselo como entregable o permitirle
  escribir en `docs/`.

## 8. Mapa de documentos (para qué sirve cada uno)

| Documento | Para qué sirve | ¿Quién lo edita? |
|---|---|---|
| `docs/HANDOFF.md` | Este archivo: punto de entrada para continuar el desarrollo (estado, decisiones, próximos pasos). | Quien cierra una etapa |
| `docs/traspaso-curacion-piloto.md` | Detalle del paso 4: estado de la curación del piloto, las decisiones 1–15 del usuario sobre ella, el paso A y el paso B (ambos hechos). **Leer después de este archivo.** | Sesión de curación |
| `docs/informe-revision-piloto.md` | Informe para la revisión humana del PR de conocimiento (por entidad, fechas, Issues, discrepancias diseño↔evidencia, checklist contra el PDF, salida de `sifen check --report`). Va en la descripción del PR. | Sesión de curación; se regenera con `sifen check --report` |
| `docs/arquitectura.md` | Diseño cerrado (secciones A–V): modelo, temporalidad, tests, MVP, Definition of Done. Fuente de verdad del diseño. | Solo con decisión del usuario |
| `docs/curacion.md` | Guía humana de curación (pipeline de §D.3, casos especiales). | Con cambios de diseño |
| `docs/uso.md`, `README.md` | Cómo usar la KB y la CLI. | Desarrollo |
| `docs/evaluacion.md` | Plantillas de T.8 (evaluación ciega), T.11 (costo) y T.12 (cronometraje) que completa el usuario. | Usuario |
| `docs/investigacion/*.md` | Investigación de respaldo: `sifen.md` (hechos de DNIT, inventario de NT §1.4), `pdf.md`, `stack.md`, `priorart.md`. Algunos datos los corrigió la curación (ver el traspaso, §5). | Referencia |
| `CLAUDE.md` | Reglas para Claude al consultar la KB (siempre `sifen explain`, nunca de memoria). | Protegido |
| `curation/prompts/curar_entidad.md` | Reglas que sigue Claude al curar (los hooks lo hashean al iniciar sesión). | Entre sesiones, nunca durante una curación |
| `curation/runs/<sesión>.yaml` | Bitácora de cada sesión de curación (la escriben los hooks). | Nadie a mano |
| `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`, `LICENSE` | Proceso de PR y revisión, seguridad (XML reales, certificados), avisos y licencia. | Desarrollo / usuario |
| `sources/`, `sources.manifest.yaml` | PDF y XSD oficiales con su hash; manifiesto append-only. | Solo `sifen source add`/`check` (persona) |
| `raw/` | Texto por página y celdas extraídas de cada fuente; `raw/_ledger/changes.jsonl` = libro de cambios NT↔MT deducido (guía, no afirmación normativa). | Solo `sifen extract` |
| `extraction/fixes.yaml` | Correcciones de defectos técnicos de extracción (no semántica). | PR revisado |
| `kb/_meta.yaml` | Línea base, `coverage_from`, gracia del horizonte, supuestos A1/A2. | Solo el usuario |
| `kb/documents/`, `kb/fields/`, `kb/validations/`, `kb/issues/` | Conocimiento canónico (fichas, versiones, efectos, Issues). Literales y fechas solo con `sifen draft`. | PR de conocimiento |
| `tests/golden/temporal.yaml` | Golden temporal de la KB real (formato en la cabecera de `tests/fixtures/golden_hyp.yaml`). | PR de conocimiento; nunca borrar filas |
| `tests/fixtures/kb_hyp*/`, `tests/fixtures/golden_hyp.yaml` | KB hipotética [HIP] del escenario de §G.5 (la genera `make_kb_hyp.py`). | Desarrollo |

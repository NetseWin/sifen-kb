# Traspaso de desarrollo — sifen-kb

Estado al **2026-10-17** (último commit de esta etapa: ver `git log`). Este documento es para quien **continúe
el desarrollo** (persona o sesión de Claude). Para *usar* la KB, ver `README.md` y `docs/uso.md`.

Léelo entero antes de tocar nada. El diseño está cerrado: **no rediseñar**; implementar lo que falta según
`docs/arquitectura.md` y las decisiones de la sección 2.

## ▶ Retomar aquí (actualizado el 2026-10-17, al cerrar la sesión del paso A)

- **Siguiente: paso B (curación) en una sesión NUEVA** de Claude Code abierta en el repo (WSL), en la rama
  `kb/piloto-receptor`. Debe ser nueva porque `curation/prompts/curar_entidad.md` cambió y el hook
  `SessionStart` hashea el prompt al arrancar (decisión del usuario). Instrucciones paso a paso, literales
  efectivos esperados e Issues: **`docs/traspaso-curacion-piloto.md` §4 «Paso B»** (leer antes sus §1 y §3:
  decisiones 1–12 del usuario, no reabrirlas).
- **Paso A (código): hecho y commiteado** en `feat/literal-efectivo` (rama desde `main`, worktree
  `../sifen-kb-literal-efectivo`): `0685ce4` literal efectivo (`rendered_literal`/`effective_literal`, rojo =
  eliminado en MT y NT) + comprobación `marcado` (regla «mixta»); `215175e` `explain`/XSD: C002 documentado por
  MT/NT frente a aceptado por el XSD. Suite completa 1690 passed, 2 skipped; `pr-scope` OK. **Sin push ni merge**
  (los decide el usuario; repo aún no publicado).
- **`kb/piloto-receptor`**: commits `5d41560` (`_meta.yaml`) y `1d42499` (curación del piloto, estado previo al
  literal efectivo), rebasados sobre `feat/literal-efectivo`. Sin commitear: `curar_entidad.md`, este archivo y
  el traspaso. `sifen check` da hoy **11 errores esperados** (8 `literales` + 3 `marcado`): son el trabajo del
  paso B. Tests rápidos en verde (1181 passed, 1 skipped previsto).
- **Orden de los PR:** primero `feat/literal-efectivo` → `main` (código); después rebasar `kb/piloto-receptor`
  sobre `main` y abrir el PR de conocimiento (lo revisa y mergea el usuario; informe:
  `docs/informe-revision-piloto.md`, que se actualiza al cerrar el paso B).
- **Pendiente de decidir con el usuario:** `cut_kb` conserva Issues posteriores al corte (un Issue no tiene fecha
  propia); ISS-0012 ¿se resuelve con «mayor a»? (lo pregunta el paso B); `NOTICE` (sección 2).
- Reglas de trabajo con este usuario: commits solo con su OK explícito; nunca push, merge, `git clean` ni
  `git stash`; preguntas de decisión como texto numerado (1a, 2b…). Mapa de documentos: sección 8.

---

## 1. Qué es, dónde está y en qué etapa

- **Qué es:** base de conocimiento técnica de SIFEN (facturación electrónica de Paraguay) que responde qué regla
  rige en una fecha y ambiente, con evidencia literal verificada contra los PDF oficiales de DNIT.
- **Diseño (fuente de verdad del diseño):** `docs/arquitectura.md` (secciones A–V + «Decisión recomendada»).
  Investigación de respaldo en `docs/investigacion/` (`sifen.md` hechos de DNIT verificados, `pdf.md`,
  `stack.md`, `priorart.md`).
- **Repo local:** `/home/soporte/proyectos/sifen-kb` en WSL2 Ubuntu 26.04 (usuario `soporte`).
  Desde Windows: `\\wsl.localhost\Ubuntu\home\soporte\proyectos\sifen-kb`.
- **GitHub:** **todavía no publicado.** Destino acordado: `https://github.com/NetseWin/sifen-kb`, **público**.
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

**Pendiente de confirmar con el usuario:** `NOTICE` declara que la *estructura e interpretación* de `kb/` están
bajo MIT y que los *literales copiados de DNIT* quedan fuera de la licencia. Preguntarle si está de acuerdo.

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
- **GitHub:** el `gh` de Windows (`/mnt/c/Users/hugo.maldonado/scoop/shims/gh.exe`) está autenticado como
  **NetseWin** con scopes `repo`, `gist`, `read:org`. **Falta el scope `workflow`** (sin él no se puede empujar
  `.github/workflows/`): el usuario debe ejecutar `gh auth refresh -h github.com -s workflow` (abre el
  navegador). En WSL no hay `gh` ni credenciales: para `git push` desde WSL, configurar un helper **local al
  repo**: `git config credential.helper '!/mnt/c/Users/hugo.maldonado/scoop/shims/gh.exe auth git-credential'`.
- Identidad git (global en WSL): `Hugo Maldonado <92177318+NetseWin@users.noreply.github.com>`. Los commits llevan el trailer
  `Co-Authored-By: Claude …`.
- `.codegraph/` (índice local de CodeGraph) está en `.gitignore`.

## 4. Estado por componente

Suite al cierre del paso A (rama `feat/literal-efectivo`, sin `kb/`): **1690 passed, 2 skipped** (los 2 son el golden real, que en esa rama no existe; en `kb/piloto-receptor` corre). `ruff check` y
`ruff format --check` limpios. `sifen extract --check` en verde.

| Componente | Archivos | Estado | Notas |
|---|---|---|---|
| Contratos base | `model.py`, `normalize.py`, `yamlio.py`, `load.py`, `cli.py` | ✅ | Modelos de §F; YAML restringido (`KBLoader`: todo escalar es `str`); `KB` con índices derivados y `reindex()`; CLI argparse con 8 comandos cableados. |
| Fuentes | `sources.py`, `sources.manifest.yaml`, `sources/` | ✅ | 32 revisiones: MT_V150, NT_001–027, CHECKSUM_MT, NORMA_DECRETO_872_2023, XSD_RAR, XSD_DIR (47 XSD en `sources/XSD_DIR/2026-10-17/`). Un `source check` limpio (horizonte 2026-10-17). 44 tests. |
| Evidencia `raw/` | `extract.py`, `extract_tables.py`, `extract_ledger.py`, `rawio.py`, `pdf/**`, `extraction/fixes.yaml` | ✅ código / ⚠️ tests | `raw/` completo: 30 documentos, 302 páginas, 1 180 filas (509 campos y 445 validaciones del MT; fila `fechas` de NT 013–027), libro de cambios NT→MT en `raw/_ledger/changes.jsonl` (211). 326 tests vendorizados en `tests/extraction/`. **Faltan** los tests nuevos (sección 5, paso 1). |
| DSL de condiciones | `dsl.py` | ✅ | `parse`/`evaluate` (Kleene)/`fields`/`constants`/`unparse`/`literal_contains_constant`. Sin `eval`. 232 tests. |
| Resolvedor temporal | `temporal.py`, `mentions.py` | ✅ | `resolve`, `resolve_xml_axes`, `timeline`, `cut_kb`, `diff_versions`, `chosen_version`, `index_answer`. Fixture `tests/fixtures/kb_hyp{,_rev2}` (generada por `make_kb_hyp.py`), `golden_hyp.yaml`, Hypothesis. 94 tests. |
| XSD / XML | `xsd.py` | ✅ | Carga 100 % offline, `XsdIndex.lookup/check_occurrence`, `validate_xml`, `read_values`, fechas de emisión/procesamiento, `mask`, `PII_ELEMENTS`, `snapshot_from_manifest`. Fixtures en `tests/fixtures/xml/` (ver su README). 136 tests. |
| Claude Code / CI / docs | `CLAUDE.md`, `.claude/settings.json`, `hooklog.py`, `prscope.py`, `.github/`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `NOTICE`, `docs/uso.md`, `docs/curacion.md`, `curation/prompts/curar_entidad.md` | ✅ | 138 tests (hooklog + prscope). Sintaxis de permisos/hooks verificada contra code.claude.com. `actionlint` limpio. |
| **Consulta** | `explain.py` | ✅ | `sifen explain` y `sifen status` (commit `d2eef71`). Enumeración documentada por MT/NT frente a la aceptada por el XSD (`xsd.enumeration`, decisión 8) y fecha de NT 001–012 como cita: `215175e`. |
| **Integridad y formato** | `integrity.py` | ✅ | `sifen check` (29 comprobaciones, `--report`) y `sifen fmt` (commits `0a0e9ca`, `08cd5f7`). `literales` contra `effective_literal` y comprobación `marcado` (regla «mixta»): `0685ce4`. |
| **Borrador desde celdas** | `draft.py` | ✅ | `sifen draft <DocId>`, `<EffectId>`, `<clave> --baseline <RowRef>` (commit `2ebf82a`). Copia `effective_literal`, avisa tramos quitados y conflictos del marcado; `--dry-run` corregido: `0685ce4`. |
| **Conocimiento curado** | `kb/`, `tests/golden/temporal.yaml` | 🟡 commiteado, falta el paso B | Rama `kb/piloto-receptor` (`1d42499`). Ver «Retomar aquí» y `docs/traspaso-curacion-piloto.md` §4. Va en un PR aparte que revisa el usuario. |

## 5. Próximos pasos, en orden

1. **Tests nuevos del extractor** (`tests/extraction/`):
   - `test_golden_piloto.py`: filas del MT (validaciones D208–D210a; campos D201, D202, D208, D209, D210, D011,
     D015, C002, F014, F023), D208c en NT_021 (35.000.000) y NT_024 (7.000.000), fechas de NT_021, NT_023 y
     NT_024. Verificar contra el PDF, no contra la memoria.
   - `test_raw_contract.py`: campos obligatorios de cada fila (`rawio`), cada ref resuelve a una sola fila,
     sha256/chars de `index.json` coinciden con `pNNN.txt`, el texto de cada celda está en su página normalizada.
   - `test_extract_determinism.py`: dos corridas con distinto `PYTHONHASHSEED` → mismos bytes; extracción por
     tramos == corrida única.
   - Unitarios de `apply_fixes`, `parse_fixes`, `RawRow.current`.
2. **`integrity.py` + `draft.py`** (núcleo de la garantía de evidencia):
   - `cmd_fmt` (`--check`): canonicidad de `kb/**/*.yaml` y del manifiesto (`yamlio.is_canonical`).
   - `cmd_check` (`--json`): errores de carga + todas las comprobaciones de §K.3 y §K.4 como funciones
     reutilizables por los tests: hash de fuentes (`sources.verify_sources`), literales == celda normalizada,
     fila citada == ID de la entidad (y celda de código == `code`), destino de efectos == ID de la fila,
     citas de prosa contenidas en la página, fechas == celda del encabezado correcto y `value == parse(literal)`,
     constantes del DSL ⊂ literal (`dsl.literal_contains_constant`), etiquetas de enumeración ⊂ observaciones,
     **guardián de cobertura** (toda mención del vocabulario del piloto en las 27 NT reconocida por un efecto;
     usar también `raw/_ledger/changes.jsonl` como oráculo), biyección efecto↔versión, `based_on` = predecesora
     temporal, diff ⊆ `declared_scope` (+ `acknowledged_changes`), cambio interpretado ⇒ cambió el literal,
     inicio único por ambiente, integridad referencial temporal, colisiones de código declaradas, fechas sanas
     (test ≤ prod; > 90 días doc→test exige Issue `erratum`), pasado justificado contra `main`
     (`test_past_changes_justified`), corridas LLM que cubren las salidas, casos sanitizados.
     Opcional útil: `--report` con el informe del PR (§D.3 paso 7).
   - `cmd_draft`: `<DocId>` → copia `document_date`/`change_period`/`schedule` desde la fila `fechas` de
     `raw/` (CellRef `raw:NT_024@sha12:pN:fechas#test`); `<EffectId>` → crea la versión nueva copiando las celdas
     de la fila citada por el efecto y heredando de `based_on` las columnas que la NT no reproduce.
   - **Antes:** `normalize.parse_date_literal` debe aceptar fechas en palabras («30 de agosto de 2024»,
     «27 de setiembre de 2024», «del») y `dd-mm-aaaa` (NT_001). Afecta NT 013–018, 020, 022, 023. Ajustar el
     validador de `DateStatement` y sus tests.
3. **`explain.py`** según su docstring y el informe de cierre (resumen): resolver el término (código con
   lápidas vía `kb.code_index()`, ID → campo y/o validación, `xml_name`, DocId, clave completa; si no está
   curado, modo índice `not_curated` con `mentions.find_mentions` y el aviso obligatorio), salida de texto como
   §O (estado no vigente primero), `--history` con `temporal.diff_versions`, `--json` (contrato del docstring;
   `xsd` = dump de `XsdCheck`), `--xml` (solo lectura, prohibido con `--at`, fechas de `dFeEmiDE` y de
   `--response`/`--processed-at`, `xsd.read_values` con mapeo ID → (xml_name, padre real del XSD),
   `dsl.evaluate` dentro de `temporal.resolve_xml_axes`, PII enmascarada, el CDC es el atributo `DE/@Id` y
   también se enmascara, aviso «SIFEN informa el primer error…»), `cmd_status` y errores (término desconocido
   → exit 2; `kb.errors` → exit 1; `TemporalDataError` → exit 1). Tests: los de §K.1 (`test_cli_output_utf8_piped`)
   y §K.7 (`test_explain_json_snapshot`) más los de la especificación. `--at` por defecto = hoy en
   America/Asuncion (fallback UTC-03:00).
4. **Curación del piloto (PR de conocimiento, lo revisa el usuario):**
   - `kb/_meta.yaml` (línea base MT_V150 `976cd88c…`, `coverage_from` 2023-06-17, gracia 7, eje `processing`,
     supuestos A1 y A2 `unverified`).
   - `kb/documents/`: una ficha por fuente (32), calendario de NT 013–027 con `sifen draft <DocId>`;
     efectos completos solo en las NT que tocan el piloto (según el inventario/libro de cambios: 1, 2, 8, 10, 21,
     23, 24…), el resto `curation_scope: dates_only`.
   - Campos DE (10): C002, D011, D015, D201, D202, D208, D209, D210, F014, F023.
   - Validaciones DE (12): D208 (1310), D208a, D208b (1319), D208c (1321), D208d (1322, lápida NT 2), D208e
     (1331), D208f (1333), D208g (1335), D209a (1313), D210 (1314), D210a (1323, lápida NT 2), D210b (1334).
   - Issues ISS-0001…0006 (lista en `docs/arquitectura.md` §S).
   - `tests/golden/temporal.yaml` real (filas de §G.5 y §K.5; regla día anterior/día del cambio por ambiente).
   - Seguir `curation/prompts/curar_entidad.md`; literales y fechas SOLO con `sifen draft`; interpretaciones
     con `Interpretation(by: llm, run: …)`. La bitácora `curation/runs/` la arman los hooks si la curación corre en
     una sesión de Claude Code abierta en el repo (WSL). Si no, registrar la corrida de forma explícita y decirlo.
5. **Dependencia menor:** `tzdata; sys_platform == 'win32'` en `pyproject.toml` (sin ella, en Windows la fecha
   de Paraguay usa UTC-03:00 fijo: puede errar en el invierno de 2024 y antes).
6. **README:** reemplazar los marcadores `<!-- SALIDA-REAL -->` (README y `docs/uso.md`) por salidas reales de
   `sifen explain` una vez implementado.
7. **Verificar la Definition of Done** (`docs/arquitectura.md` §T). Lo que depende del usuario: T.8 evaluación
   ciega (él escribe 15 preguntas y su clave de respuestas **antes** de ver salidas), T.11 umbral de costo de
   curación por NT, T.12 cronometraje de tres rechazos. Preparar plantillas y pedírselo.
8. **Publicar en GitHub** (pedir al usuario el scope `workflow` antes):
   1. `gh repo create NetseWin/sifen-kb --public --source . --remote origin` (descripción y topics).
   2. Push de `main` con código, infraestructura, `sources/` y `raw/` (sin `kb/`): CI debe quedar verde.
   3. Protección de `main`: PR obligatorio, CI verde, sin force-push, sin bypass de administradores.
   4. Rama + PR de conocimiento (`kb/`, `tests/golden/`, `curation/`) con el informe de revisión → lo revisa y
      mergea el usuario con trailer `Reviewed-by:`.
   5. Tras el merge, `release.yml` (manual) crea el tag `kb-AAAA.MM.DD` y la release con el manifiesto.

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
| `docs/traspaso-curacion-piloto.md` | Detalle del paso 4: estado de la curación del piloto, las decisiones 1–12 del usuario sobre ella, el paso A (hecho) y el paso B pendiente. **Leer después de este archivo.** | Sesión de curación |
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

# Traspaso: curación del piloto receptor/identidad (§5 paso 4 de docs/HANDOFF.md)

Estado al 2026-10-17 (actualizado al cerrar la sesión del paso A). Es el detalle del paso 4 de `docs/HANDOFF.md` (que remite aquí desde «Retomar aquí»): estado de la curación, las decisiones del usuario sobre ella y los pasos siguientes, en orden. Lo escribió la sesión de curación; el informe para la revisión humana del PR está en `docs/informe-revision-piloto.md`.

## 1. Dónde estamos

**Actualizado al cerrar la sesión del paso A (2026-10-17, sesión `d700f0c7`).**

- **Paso A (código) hecho** en la rama `feat/literal-efectivo` (desde `main`, en el worktree `../sifen-kb-literal-efectivo`): commits `0685ce4` (literal efectivo y comprobación `marcado`) y `215175e` (C002: enumeración MT/NT frente a XSD). Suite completa en esa rama: 1690 passed, 2 skipped (el golden real, que no existe en `main`); `pr-scope` contra `main`: OK (código + neutro). **Sin push ni merge: lo decide el usuario.**
- **`kb/piloto-receptor` commiteada y rebasada** sobre `feat/literal-efectivo` (con el OK del usuario): `5d41560` (`_meta.yaml`) y `1d42499` (curación del piloto, estado previo al literal efectivo). El PR de conocimiento solo pasará `pr-scope` cuando `feat/literal-efectivo` esté mergeada en `main` (entonces se rebasa sobre `main`).
- Sin commitear en `kb/piloto-receptor`: `curation/prompts/curar_entidad.md` (regla 9 y paso 4 del procedimiento: color con verbo, literal efectivo, Issues del marcado), este traspaso y `docs/HANDOFF.md`. El prompt se cambió **entre sesiones**: la sesión del paso B debe ser NUEVA para que su `SessionStart` hashee el prompt nuevo (decisión del usuario).
- `uv run sifen check` en `kb/piloto-receptor` da hoy **11 errores, todos esperados** (el trabajo del paso B): 8 de `literales` (las versiones de §4 paso B.1) y 3 de `marcado` (`color_verbo` en NT_023#5, #6 y #7). `uv run pytest -q tests/unit tests/test_golden_temporal.py tests/extraction/test_golden_piloto.py` → 1181 passed, 1 skipped (previsto).
- Informe para la revisión humana: `docs/informe-revision-piloto.md` (todavía describe el estado previo al literal efectivo: se actualiza al cerrar el paso B).

## 2. Qué contiene la KB

- 32 fichas en `kb/documents/` (fechas copiadas por `sifen draft`). `curation_scope: pilot`: MT_V150, NT 1, 2, 8, 10, 21, 23, 24. El resto `dates_only` (incluidas NT 3, 6, 7, 12, 14, 20, 26, 27, que solo tienen efectos `not_modeled` de menciones).
- 10 campos (C002, D011, D015, D201, D202, D208, D209, D210, F014, F023) y 12 validaciones (D208, D208a–g, D209a, D210, D210a, D210b) con versión base del MT (`sifen draft <clave> --baseline raw:MT_V150@976cd88c05c3:p<N>:<ID>`), versiones por NT y lápidas (D208d y D210a por NT 2; D208b por NT 10).
- Issues ISS-0001…ISS-0013 (`kb/issues/`). Bloqueantes hoy: ISS-0003 (D208/1310 desde NT 23) e ISS-0010 (D210/1314 desde NT 23, transitorio, ver §4).
- `tests/golden/temporal.yaml`: 88 filas reales (G.5 1–6, 15–17, 20; K.5 corregido por la evidencia; fronteras día anterior/día del cambio por ambiente; oráculo «watermark»; `1400` → `not_curated`).

## 3. Decisiones del usuario (2026-10-17) — no reabrir sin preguntarle

1. **D208b / NT 10**: NT 10 elimina D208b (lápida NT_010#6, inicio aproximado). ISS-0002 (D208f ≈ D208b) **no bloqueante**; D208f es entidad independiente; no fusionar historiales. ISS-0008 resuelto. **Aplicado.**
2. **Color en las NT**: rojo = contenido eliminado, verde = agregado, amarillo = modificado, aplicado junto con el verbo del encabezado y el contexto; si las señales se contradicen o no permiten reconstruir el contenido efectivo, Issue bloqueante. Separar `rendered_literal` (celda completa visible, con su marcado) de `effective_literal` (derivado de forma determinista aplicando el marcado). Es semántica de diseño: **no** va en `extraction/fixes.yaml` (reservado a defectos técnicos de extracción). **Código hecho (paso A); falta re-materializar los datos (paso B).**
3. **D208c / NT 21 y NT 24**: el rojo también es eliminación. Regla efectiva: NT 21 «mayor a 35.000.000», NT 24 «mayor a 7.000.000», sin la excepción D011≠13. ISS-0011 e ISS-0012 no bloqueantes (trazabilidad). No dejar D208c `undetermined`; la consulta a DNIT puede seguir en paralelo y una respuesta oficial contraria se registra con trazabilidad. **Código hecho (paso A); re-materializar en el paso B.**
4. **ISS-0010 / 1314**: deja de ser bloqueante cuando se reconstruya el `effective_literal` de NT_023#4 (sin la excepción B2F); puede resolverse. **Hoy sigue bloqueante a propósito**, como estado transitorio, porque la versión materializada todavía muestra la celda completa.
5. **curation_scope**: `dates_only` para NT cuyo único contenido curado son menciones `not_modeled` fuera del piloto; `pilot` solo si se curaron cambios reales a entidades del piloto. **Aplicado.**
6. **«Efectos completos»** = completos respecto del alcance: efectos sobre entidades del piloto + menciones externas necesarias para cobertura, desambiguación o dependencia. No registrar exhaustivamente cambios ajenos (E711, H018…). **Aplicado (no hay que hacer nada).**
7. **Marca de agua de NT 21**: solo oráculo golden «watermark» (fin derivado de NT_021#1 = 2025-01-01); no `superseded_by`, no crear `VisualRef`. **Aplicado.**
8. **C002 / ISS-0013**: `source_conflict` no bloqueante. Mantener separadas la semántica documental (MT/NT: 1–8) y la aceptación estructural del XSD (instantánea por hash: 1, 4–7, 9, 10); no consolidar, no inventar etiquetas para 9 y 10. **Datos y código aplicados (paso A): `explain C002` muestra ambas dimensiones, `xsd.status: mismatch` con ISS-0013.**

### Decisiones del usuario en la sesión del paso A (2026-10-17) — tampoco reabrir

9. **Regla «mixta» del marcado** (concreta la decisión 2): color ≠ acción curada, o contenido efectivo no reconstruible de forma unívoca (incluye `modify` sin cambio efectivo) ⇒ Issue **bloqueante**; color ≠ verbo literal del encabezado pero = acción curada ⇒ Issue **no bloqueante de trazabilidad**. NT 23 #5–#7 (D208f/1333, D210b/1334, D208g/1335, filas en verde bajo «se modifica la siguiente validación»): siguen `in_force` y se registra el Issue no bloqueante.
10. **Cobertura del Issue**: un Issue cubre un conflicto del marcado solo si nombra el **efecto** en `affects` (`subject: NT_023#5`…); uno que solo nombra la entidad (ISS-0002, ISS-0004) no cuenta.
11. **Sin normalización manual del literal efectivo**: el espacio antes de la coma que deja quitar el rojo en D210 @NT_023#4 («…(D201=2) , el número…») se conserva; una normalización futura sería una operación explícita y separada.
12. **Ramas y commits**: código en `feat/literal-efectivo` (worktree), conocimiento en `kb/piloto-receptor`; `curar_entidad.md` va en la rama kb (pr-scope lo clasifica como conocimiento); todo commit con OK explícito del usuario; nunca push ni merge.

## 4. Próximos pasos (en orden)

### Paso A — Código: HECHO (2026-10-17, commits `0685ce4` y `215175e` en `feat/literal-efectivo`)

- `rawio`: `rendered_literal` / `effective_literal` (reemplazan a `RawRow.literal`), `removed_spans`, `color_signal`, `verb_actions`, `marking_conflicts` (decisiones 9–10).
- `draft`: copia `effective_literal` y avisa los tramos quitados; la lápida se compara por lo visible; avisa los conflictos del marcado; `--dry-run` dice «se escribiría».
- `integrity`: `literales` contra `effective_literal`; comprobación nueva `marcado` (Issue bloqueante abierto con ventana que contenga el inicio del efecto en cada ambiente, o resuelto; de trazabilidad: cualquiera que nombre el efecto).
- `explain`/`xsd`/`model`: `XsdCheck.enumeration` (documentado por MT/NT frente a aceptado por la instantánea; C002 → `mismatch` con ISS-0013, sin etiquetas para 9 y 10); la fecha de NT 001–012 sale como cita.
- `tests/test_golden_temporal.py`: la completitud exige filas en los bordes de las ventanas de Issues bloqueantes abiertos (el golden real ya cumple).
- Docs: `arquitectura.md` §I.4, §F.2; `curacion.md`; `investigacion/sifen.md` §5 (corrección); `uso.md`. `curar_entidad.md`: en la rama kb (ver §1).
- **Pendiente (decisión de diseño, fuera del paso A):** `cut_kb` conserva Issues posteriores al corte; un Issue no tiene fecha propia, así que hay que decidir con el usuario qué significa «posterior».

### Paso B — Re-materializar la KB con el literal efectivo (sesión de curación NUEVA, rama `kb/piloto-receptor`)

El código del paso A ya está en la rama (rebase hecho). Abrir una sesión nueva de Claude Code en el repo (WSL) para que el hook registre el prompt nuevo; leer `CLAUDE.md`, `curation/prompts/curar_entidad.md`, este traspaso y `docs/HANDOFF.md`.

1. **Re-materializar** (literales solo con `sifen draft`). `uv run sifen check` lista las 8 versiones. `draft NT_0xx#n` no hace nada si una versión ya cita el efecto, así que primero hay que quitar esas versiones. Opción recomendada: quitar del archivo de la entidad las versiones afectadas **y las posteriores de esa entidad** (la línea base y sus interpretaciones se conservan) y repetir `uv run sifen draft <efecto>` en orden cronológico. Alternativa del traspaso original: borrar el archivo y repetir `--baseline` + cada efecto (obliga a rehacer también las interpretaciones de la línea base). En ambos casos `main` no tiene `kb/`: no hay «pasado» que justificar. Literales efectivos esperados (verificados en `raw/` con el código nuevo):
   - field:DE:D208 @NT_002#1: «Obligatorio si D201 = 2 y D202 ≠ 4 1= Cédula paraguaya …» (sin «No informar si D201 = 1 o D202=4»); @NT_023#1: «Obligatorio si D201 = 2 No informar si D201 = 1 1= Cédula paraguaya … 6=Tarjeta Diplomática de exoneración fiscal 9= Otro». Rehacer `enumeration` (+ `enumeration_interpretation`) y `open_questions`.
   - field:DE:D210 @NT_002#2: «Obligatorio si D201 = 2 y D202 ≠ 4 En caso de DE innominado, completar con 0 (cero)»; @NT_023#2: «Obligatorio si D201 = 2 No informar si D201 = 1 En caso de DE innominado, completar con 0 (cero)». Revisar `open_questions`.
   - field:DE:F023 @NT_008#1: sin «Cuando C002=4 corresponde a F014».
   - val:DE:D210 @NT_023#4: «Si la naturaleza del receptor es NO contribuyente (D201=2) , el número de documento de identidad debe ser informado» (espacio antes de la coma: se conserva, decisión 11). Condición `D201 == 2 and not exists(D210)`; revisar `open_questions`.
   - val:DE:D208c @NT_021#1 y @NT_024#1: «El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando … es mayor a 35.000.000 (F023 > 35000000 o F014 > 35000000)» / «… mayor a 7.000.000 (F023 > 7.000.000 o F014 > 7.000.000)». Condición `exists(D208) and D208 == 5 and ((exists(F023) and F023 > U) or (exists(F014) and F014 > U))` con U = 35000000 / 7000000. El paréntesis «(D208≠5)» **sigue** en el literal efectivo: la polaridad mixta y ISS-0005 se mantienen en `gaps`. Rehacer `legal_basis` (cita de prosa verificada) si se quitó la versión.
   - Lápidas (D208b, D208d, D210a) y altas (D208e, D208f, D208g, D210b): `check` no las marca en `literales`; no deberían cambiar.
2. **Issues**:
   - Nuevo Issue **no bloqueante** (p. ej. ISS-0014, `ambiguity`) con `affects` NT_023#5, NT_023#6 y NT_023#7 (decisiones 9–10): NT 23 §2.1 dice «se modifica la siguiente validación» y las filas D208f, D210b y D208g están enteras en verde (altas); se curan como `add`. Evidencia: las tres filas. Con eso `marcado` queda en 0 errores.
   - ISS-0010: resolver (decisión 4) cuando NT_023#4 tenga el literal efectivo; quitar el bloqueo.
   - ISS-0009: pasa a trazabilidad o se resuelve. ISS-0011: queda no bloqueante (trazabilidad). ISS-0012: con «mayor a» desaparece la divergencia con el Decreto («supere») en el umbral y en la excepción D011 → **preguntar al usuario** si se resuelve. ISS-0003 sigue (D208g ≈ D208).
3. **Golden**: las filas de val:DE:D210 desde NT 23 (`tests/golden/temporal.yaml`, «ISS-0010 bloquea desde NT 23») pasan de `undetermined` a `in_force` (lo prevé la decisión 4; el golden aún no está en `main`, así que no es un cambio al pasado; dejar constancia en el informe). Agregar filas que fijen el literal/condición nuevos de D208c si el formato lo permite. La completitud ahora también exige filas en los bordes de ventanas de Issues bloqueantes.
4. **Verificar**: `uv run sifen fmt && uv run sifen check && uv run pytest -q` (suite completa, ~6 min), y `explain 1321 --at 2025-01-10`, `explain D208 --at 2024-09-15 --env test|prod`, `explain 1322 --at 2025-03-01`, `explain D208b --at 2024-09-27` (debe dar `removed`), `explain 1314 --at 2024-10-01`, `explain C002`, `sifen status`.
5. **Informe y traspaso**: actualizar `docs/informe-revision-piloto.md` (literales efectivos, Issues nuevos y resueltos, golden, salida de `sifen check --report`) y `docs/HANDOFF.md` («Retomar aquí»). Pedir OK al usuario antes de cada commit. El PR de conocimiento lo revisa y mergea el usuario con `Reviewed-by:` (antes debe estar `feat/literal-efectivo` en `main` y la rama rebasada sobre `main`).

### Paso C — Lo que sigue de docs/HANDOFF.md §5

Pasos 5–8 sin cambios: `tzdata` para Windows, salidas reales en README/docs/uso.md, Definition of Done (§T; T.8, T.11, T.12 dependen del usuario), publicación en GitHub.

## 5. Hallazgos que conviene no redescubrir

- El MT V150 publicado ya trae «6=Tarjeta Diplomática de exoneración fiscal» en D208 (en verde, p. 71/72); NT 2 también. NT 23 no agrega el valor 6: cambia «No informar si D201 = 1 o D202=4» → «No informar si D201 = 1».
- Las NT 2, 8, 10 y 23 colorean con la leyenda del MT. En NT 21/24 la «E» de «El Tipo» en amarillo delata que la cláusula roja previa se elimina.
- NT 10 §2.1 elimina D208b (fila entera en rojo, idéntica al MT); D208e es la «nueva».
- NT 23 §2.1 dice «se modifica» para D208f, D210b y D208g, que son altas (filas en verde).
- La marca de agua de NT 21 es gráfica: no está en el texto del PDF (pypdfium2) ni en `raw/`.
- Decreto 872/2023 (`raw/NORMA_DECRETO_872_2023`, p. 10–11 PDF): art. 6 num. 1 (B2B, B2F, B2G deben identificar al receptor; NT 23 lo cita) y num. 2 («supere» 35 M desde 2024, 7 M desde 2025).
- XSD `tiTiDE` = «1|[4-7]|9|10»; `tiTipDocRec` = «[1-6]|9»; ocurrencias de los 10 campos coinciden con el MT.
- El guardián de cobertura reconoce por (documento, término): basta un efecto sobre la entidad del término en ese documento; las menciones dentro de filas citadas por efectos aplicados/pending quedan reconocidas. Un efecto con destino no curado es error (`referencias`), así que las menciones se reconocen con `not_modeled` dirigidos a la entidad del piloto mencionada.
- En NT 2 las filas eliminadas de D208d y D210a tienen la «R» de la severidad sin color (`row_change` null): `color_signal` toma la fila como baja porque la celda `id` está entera en rojo y ninguna otra celda tiene otro color.
- Para renderizar una página del PDF y mirarla: `uv run python <script> sources/<Doc>/<sha12>.pdf <página> salida.png` con pypdfium2 (`pdf[p-1].render(scale=1.5).to_pil().save(...)`), y abrir el PNG con Read.
- Los hooks solo registran Edit/Write en `curation/runs/`; los archivos que reescriben `sifen draft`/`sifen fmt` quedan con sha256 viejo en `outputs` (no se compara). Todo archivo con `by: llm` debe haberse editado al menos una vez con Edit/Write en la sesión.

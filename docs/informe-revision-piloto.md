# Informe para la revisión humana — PR de conocimiento «piloto receptor/identidad»

- Rama: `kb/piloto-receptor` (sin commitear). Corridas LLM: `curation/runs/a067d55b-d757-498d-a601-f946db1a3acc.yaml` (curación original) y, del paso B (2026-10-18), `ce4ca541-bb4f-49d4-8e9f-5430b10e6d63.yaml`, `6b58d45f-98a7-4353-8d45-d1b664f31286.yaml` y `6767ad7f-b35b-4bcd-a3a7-d670f1b45845.yaml`. Las arman los hooks; los archivos que escribieron `sifen draft` y `sifen fmt` por Bash no actualizan su sha256 en `outputs`. En la corrida original todo archivo con `by: llm` fue editado al menos una vez con Edit/Write y figura ahí; en las del paso B los hooks no registraron nada (no ven las herramientas MCP con las que se editó) y las salidas se registraron a posteriori como `source: backfill` (§1.1, §12.8 y la nota siguiente).
- **Bitácora del paso B (procedencia).** La sesión de Pi del paso B corrió a través de `claude-bridge`, que abrió tres sesiones de Claude Code: `ce4ca541` (14:51–15:34 UTC), `6b58d45f` (desde 18:31 UTC) y `6767ad7f` (desde 19:08 UTC). Editó con herramientas MCP (`mcp__custom-tools__edit`/`write`), que no disparan el hook `PostToolUse`, así que las salidas se registraron a posteriori con `hooklog Backfill` (6e0c377): cada entrada lleva `source: backfill`, el motivo y la hora real del registro. Cada archivo se atribuyó a la sesión de su última edición real (según los transcripts, sin contar la reproducción del historial con que arranca cada sesión nueva): las 8 fichas con `by: llm`, ISS-0003/0005/0009/0010/0011/0014 y `D208g.yaml` a `ce4ca541`; el golden a `6b58d45f`; `docs/HANDOFF.md`, el traspaso e ISS-0012 a `6767ad7f`. La última reescritura de «Retomar aquí» en `docs/HANDOFF.md` se hizo con un script Python ejecutado por `mcp__custom-tools__bash` (no con `edit`/`write`); su entrada en la bitácora `6767ad7f` lleva un motivo propio que lo dice. `kb/fields/DE/D210.yaml` y `F023.yaml` solo los escribió `sifen draft` y no se registran.
- **Historial reescrito antes de publicar (2026-10-18).** Todos los commits se reescribieron con el email noreply del autor y se remapearon las citas a commits (por ejemplo `e9b482c` → `0685ce4` en ISS-0009). Ese remapeo cambió mecánicamente `kb/issues/ISS-0009.yaml` y el traspaso después de su registro `backfill`: el `sha256` que guardan las bitácoras `ce4ca541` y `6767ad7f` para esas dos rutas es el del contenido anterior al remapeo (`docs/HANDOFF.md`, editado otra vez después, se volvió a registrar con su contenido final) (`corridas_llm` no compara el `sha256`, por diseño). Los `base_commit` `926f1eb…` de las tres bitácoras del paso B apuntan a un commit que ya no estaba en la historia antes de reescribir (rebase previo) y se conservan tal como los escribió el hook.
- **Este informe no se registra en ninguna corrida.** Su contenido lo escribió principalmente un worker (subagente `gentle-ai-worker`, sin sesión de Claude Code propia) y después tuvo ajustes desde la sesión Pi/MCP (`6b58d45f`, `6767ad7f`) y el anexo regenerado por `sifen check --report`. Como su sha256 final no puede atribuirse honestamente a una sola corrida de Claude Code, no se le hizo backfill, y tampoco se inventó una corrida para el worker.
- Alcance del diff: `kb/documents/` (32 fichas), `kb/fields/DE/` (10), `kb/validations/DE/` (12), `kb/issues/` (14), `tests/golden/temporal.yaml` (nuevo). `kb/_meta.yaml` no se tocó.
- Literales y fechas: todos copiados por `sifen draft` (`<DocId>`, `<clave> --baseline <RowRef>`, `NT_0xx#n`). Lo tecleado a mano es solo interpretación (efectos, `condition`, `enumeration`, `subject_field`, `legal_basis.citation`, `open_questions`, Issues), siempre con `interpretation: {by: llm, run: a067d55b-… | ce4ca541-…}` donde el modelo lo admite.
- **Las fechas y el alcance deben contrastarse con el PDF renderizado** (ver la checklist al final). `draft` copia; no decide.

## 0. Actualización tras las decisiones del usuario (2026-10-17)

Las decisiones del usuario sobre las 8 preguntas están en `docs/traspaso-curacion-piloto.md`, §3. Aplicado en la KB:
- ISS-0002 pasa a no bloqueante (D208b sigue `removed` después de NT 23; D208f independiente); ISS-0008 resuelto (NT 10 elimina D208b, aceptado).
- NT 3, 6, 7, 12, 14, 20, 26 y 27 vuelven a `curation_scope: dates_only` (solo menciones `not_modeled`).
- Golden: D208b `removed` el 2024-08-30 (test) y el 2024-09-27 (prod); ISS-0002 en lugar de ISS-0008 en `open_issues`.
- ISS-0009, ISS-0010 e ISS-0011: su `policy` registra la decisión «rojo = eliminado» y que las versiones afectadas esperan el `effective_literal` (cambio de código). ISS-0010 queda bloqueante solo como estado transitorio (superado en el paso B: resuelto).

Pendiente entonces (requería código, fuera de este PR): `effective_literal` en rawio/draft/integrity y re-materializar NT_002#1/#2, NT_008#1, NT_021#1, NT_023#1/#2/#4 y NT_024#1; mostrar en `explain` las dos dimensiones MT/XSD de C002. **Hecho**: el código está en `feat/literal-efectivo` (commits `0685ce4` y `215175e`, ya en la historia de esta rama) y los datos se re-materializaron en el paso B (abajo).

### Actualización paso B (2026-10-18)

Corrida de curación `curation/runs/ce4ca541-bb4f-49d4-8e9f-5430b10e6d63.yaml`. La KB se re-materializó con el literal efectivo (rojo = contenido eliminado; decisiones 2, 3, 4, 9, 10 y 11 de `docs/traspaso-curacion-piloto.md` §3):

- **Versiones re-materializadas con `sifen draft`** (literales copiados, no tecleados): field:DE:D208 @NT_002#1 y @NT_023#1; field:DE:D210 @NT_002#2 y @NT_023#2; field:DE:F023 @NT_008#1; val:DE:D208c @NT_021#1 y @NT_024#1; val:DE:D210 @NT_023#4. Procedimiento: se quitaron esas versiones (y las posteriores de la misma entidad) y se repitió `sifen draft <efecto>` en orden cronológico; las líneas base no se tocaron. `main` no tiene `kb/`: no hay «pasado» que justificar.
- **Interpretaciones rehechas**: enumeración de D208 (los mismos 7 valores); D208c `exists(D208) and D208 == 5 and ((exists(F023) and F023 > U) or (exists(F014) and F014 > U))` con U = 35000000 / 7000000 (level partial; gaps: ISS-0005 y polaridad mixta) y `legal_basis` re-agregado; D210 (1314) @NT_023#4 `D201 == 2 and not exists(D210)` (level full). Notas de efecto de NT_002, NT_008, NT_021, NT_023 y NT_024 actualizadas.
- **Issues**: nuevo ISS-0014 (ambigüedad, no bloqueante, afecta a NT_023#5, #6 y #7); ISS-0010 **resuelto** (decisión 4; 1314 `in_force` desde NT 23); ISS-0009 sigue abierto no bloqueante como trazabilidad; ISS-0011 abierto no bloqueante (`policy`: aplicado); ISS-0003 con enunciado actualizado (el campo D208 ahora dice «Obligatorio si D201 = 2»), sigue bloqueante; ISS-0005 menciona «>» desde NT 21; ISS-0012 **resuelto** (decisión del usuario 2026-10-18: con el literal efectivo no queda diferencia con el Decreto; la cláusula D011≠13 en rojo la traza solo ISS-0011).
- **Golden**: las filas de val:DE:D210 del inicio de NT 23 pasaron de `undetermined`/`blocking_issue` a `in_force` (decisión 4; el golden no está en `main`, así que no es un cambio al pasado: §6) y se agregaron filas `diff` e ISS-0014 (§10).
- **Verificación**: `uv run pytest -q tests/test_golden_temporal.py` → 154 passed; `uv run sifen check` → 0 errores de `literales` y `marcado` (3 informativos `color_verbo` cubiertos por ISS-0014), y, tras el backfill y la integración de 6e0c377, también 0 errores de `corridas_llm` (§1.1, §13). Los `explain` de §13 dan lo esperado.

Lo que sigue (secciones 1–13) describe el estado actual, incluidos los cambios de este paso B.

## 1. Resumen de lo que hay que decidir (lo más importante primero)

1. **`corridas_llm`: resuelto con backfill explícito (antes, 16 errores en `sifen check`).** La sesión del paso B editó las fichas con herramientas MCP (`mcp__custom-tools__edit`/`write`), no con Edit/Write de Claude Code: el hook `PostToolUse` (matcher `Edit|Write|MultiEdit`) no registró `outputs` en `curation/runs/ce4ca541-….yaml` (`outputs: []`) y la comprobación de la corrida falla (§12.8, §13; detalle en `docs/traspaso-curacion-piloto.md` §4, B.6). **Decisión del usuario (2026-10-18): opción 1b′.** Un registro retrospectivo hecho con el mecanismo actual sería indistinguible de eventos nativos (la bitácora no tiene campo de origen), así que primero va un PR de código independiente (`feat/bitacora-procedencia`) que agrega a cada salida un origen explícito (`hook`/`backfill`, con motivo y fecha del registro) y un modo `Backfill` en `hooklog`; después la corrida `ce4ca541` se registra como `backfill`, visible en la propia bitácora. Ampliar el matcher y los `deny` a las herramientas MCP queda para otro PR de código. **Hecho:** `feat/bitacora-procedencia` commiteado (`6e0c377`) e integrado en esta rama (rebase); 19 salidas `source: backfill` en las tres corridas del paso B (15 en `ce4ca541`, 1 en `6b58d45f`, 3 en `6767ad7f`; atribución en la nota de procedencia de la cabecera); `sifen check` → 0 errores. El informe no se registró (procedencia mixta).
2. **ISS-0012 (D208c/1321): resuelto** (decisión del usuario 2026-10-18). Con el literal efectivo (decisión 3), NT 21 y NT 24 dicen «mayor a» (equivalente al «supere» del Decreto 872/2023) y tampoco conservan la excepción D011 = 13: no queda una diferencia material propia. La cláusula D011≠13 que sigue en rojo en el literal visible depende de la lectura del color y la traza solo ISS-0011.
3. **ISS-0002 (D208b/D208f)** quedó no bloqueante con la decisión 1 (NT 10 elimina D208b; D208f es entidad independiente). No exige decisión salvo resolverlo.

Ya decidido por el usuario y aplicado (no reabrir; `docs/traspaso-curacion-piloto.md` §3, decisiones 1–12):

- NT 10 elimina D208b (1319) (decisión 1; ISS-0008 resuelto, ISS-0002 no bloqueante).
- Rojo = eliminado, verde = agregado, amarillo = modificado; `rendered_literal` separado de `effective_literal` (decisión 2): las versiones de NT 2, 8 y 23 (campos) y de NT 21, 23 y 24 (D208c, D210) se re-materializaron con el literal efectivo (§0, paso B).
- D208c (1321): «mayor a» 35.000.000 / 7.000.000, sin la excepción D011 = 13 (decisión 3); ISS-0011 queda como trazabilidad.
- 1314 `in_force` desde NT 23 sin la excepción B2F; ISS-0010 resuelto (decisión 4).
- `curation_scope`: `pilot` solo con efectos sobre entidades del piloto (decisión 5): MT_V150 y NT 1, 2, 8, 10, 21, 23, 24 (§3).
- NT 23 #5–#7 (D208f, D210b, D208g) se curan como `add` y se registra ISS-0014 no bloqueante (decisiones 9 y 10).
- Sin normalizar el literal efectivo: el espacio antes de la coma en D210 @NT_023#4 se conserva (decisión 11).

Verificado, sin decisión pendiente: el valor 6 de D208 ya está en el MT V150 y en NT 2 (NT 23 no lo agrega) y la marca de agua de NT 21 es gráfica, por lo que no hay `superseded_by` citable (§9).

## 2. Entidades: versiones, diff y fuente

Página MT: impresa / PDF. Revisiones: MT_V150 `976cd88c05c3`, NT_001 `4c47b667084d`, NT_002 `6aaf4a8f4797`, NT_008 `2b1c2f0b25e9`, NT_010 `d261165c512c`, NT_021 `1e716577d874`, NT_023 `9cb063673358`, NT_024 `ccc2d1550e92`. Inicio «~» = aproximado (NT sin calendario: fecha del documento, anterior a `coverage_from`, supuesto A1).

### Campos

| Clave | Versiones (inicio test / prod) | Diff contra la predecesora | Fuente |
|---|---|---|---|
| field:DE:C002 `iTiDE` | línea base | — (enumeración 1–8 interpretada) | MT p. 63/64 |
| field:DE:D011 `iTipTra` | línea base | — (enumeración 1–13) | MT p. 66/67 |
| field:DE:D015 `cMoneOpe` | línea base | — | MT p. 67/68 |
| field:DE:D201 `iNatRec` | línea base | — (enumeración 1–2) | MT p. 71/72 |
| field:DE:D202 `iTiOpe` | línea base | — (enumeración 1–4) | MT p. 71/72 |
| field:DE:D208 `iTipIDRec` | línea base → NT_002#1 (~2020-07-16 / ~2020-07-16) → NT_023#1 (2024-08-30 / 2024-09-27) | Literal efectivo (paso B). NT_002#1: quita en rojo «No informar si D201 = 1 o D202=4» («Obligatorio si D201 = 2 y D202 ≠ 4 1= Cédula paraguaya …»). NT_023#1: quita «y D202 ≠ 4» (en rojo) y agrega «No informar si D201 = 1» («Obligatorio si D201 = 2 No informar si D201 = 1 …»). Enumeración 1,2,3,4,5,**6**,9 en las tres versiones (sin cambios) | MT p. 71/72; NT_002 p. 1; NT_023 p. 1 |
| field:DE:D209 `dDTipIDRec` | línea base | — (sin enumeración propia: la lista de descripciones es la tabla de D209a) | MT p. 72/73 |
| field:DE:D210 `dNumIDRec` | línea base → NT_002#2 (~2020-07-16) → NT_023#2 (2024-08-30 / 2024-09-27) | Literal efectivo (paso B). NT_002#2: quita en rojo «No informar si D201 = 1 o D202=4». NT_023#2: quita «y D202 ≠ 4» y agrega «No informar si D201 = 1» («Obligatorio si D201 = 2 No informar si D201 = 1 En caso de DE innominado, completar con 0 (cero)») | MT p. 72/73; NT_002 p. 1; NT_023 p. 1 |
| field:DE:F014 `dTotGralOpe` | línea base → NT_001#1 (~2019-10-14) | `observations` «F008 - F013 + F025» → «F008-F013+F025» (solo espacios) | MT p. 104/105; NT_001 p. 2 |
| field:DE:F023 `dTotalGs` | línea base → NT_008#1 (~2021-09-21) | Literal efectivo: quita en rojo «Cuando C002=4 corresponde a F014» (Histórico: «se elimina la diferencia … Autofactura campo F023») | MT p. 106/107; NT_008 p. 1 |

### Validaciones

| Clave (código) | Versiones (inicio test / prod) | Diff / condición formalizada (polaridad: verdadera = se VIOLA) | Fuente |
|---|---|---|---|
| val:DE:D208 (1310) | línea base | `D201 == 2 and D202 != 4 and not exists(D208)` (full). Bloqueada por ISS-0003 desde NT 23 | MT p. 166/167 |
| val:DE:D208a (1311) | línea base | `D201 == 1 and exists(D208)` (full) | MT p. 166/167 |
| val:DE:D208b (1319) | línea base → **lápida NT_010#6** (~2022-02-04) | `exists(D208) and D208 == 5 and D202 != 2` (full; heredada por la lápida). ISS-0008 (interpretación), ISS-0002 (no bloqueante desde la decisión 1) | MT p. 166/167; NT_010 p. 3 |
| val:DE:D208c (1321) | línea base → NT_021#1 (2024-01-01 / 2024-01-01) → NT_024#1 (2025-01-01 / 2025-01-01) | Literal efectivo (paso B). `observation`: umbral 60.000.000 → «mayor a» 35.000.000 → «mayor a» 7.000.000 (y «el Tipo» → «El Tipo»); se quitan en rojo «Si el Tipo de transacción es distinto a Muestras médicas (D011≠13),», «o igual» y el «=» de los dos «>=» (decisión 3). Condición `exists(D208) and D208 == 5 and ((exists(F023) and F023 > U) or (exists(F014) and F014 > U))` con U = 35000000 / 7000000 (partial; gaps: ISS-0005, polaridad mixta; ISS-0011 como trazabilidad). La línea base conserva «mayor o igual» y la guarda `(not exists(D011) or D011 != 13)`. `legal_basis`: NT 21 «Decreto 872/2023, art. 6»; NT 24 «…, numeral 2, inciso ii)» (citas verificadas en la página) | MT p. 166/167; NT_021 p. 1; NT_024 p. 1 |
| val:DE:D208d (1322) | línea base → lápida NT_002#3 (~2020-07-16) | `(D201 == 1 or D202 == 4) and exists(D208)` (full) | MT p. 166/167; NT_002 p. 1 |
| val:DE:D208e (1331) | alta NT_010#7 (~2022-02-04) → NT_023#3 (2024-08-30 / 2024-09-27) | `C002 in (5, 6) and exists(D208) and D208 == 5` → `C002 in (5, 6, 7) and …` (observación agrega Nota de Remisión) | NT_010 p. 3; NT_023 p. 2 |
| val:DE:D208f (1333) | alta NT_023#5 (2024-08-30 / 2024-09-27) | `exists(D208) and D208 == 5 and D202 != 2` (full; texto idéntico a D208b) | NT_023 p. 2 |
| val:DE:D208g (1335) | alta NT_023#7 (2024-08-30 / 2024-09-27) | `D201 == 2 and not exists(D208)` (full) | NT_023 p. 2 |
| val:DE:D209a (1313) | línea base | level none (exige tabla código→descripción; fuera del DSL) | MT p. 167/168 |
| val:DE:D210 (1314) | línea base → NT_023#4 (2024-08-30 / 2024-09-27) | Literal efectivo (paso B): quita en rojo «y el tipo de operación es diferente a B2F (D202≠4)» («Si la naturaleza del receptor es NO contribuyente (D201=2) , el número…»; el espacio antes de la coma se conserva, decisión 11); condición `D201 == 2 and not exists(D210)` (full). ISS-0010 resuelto (decisión 4) | MT p. 167/168; NT_023 p. 2 |
| val:DE:D210a (1323) | línea base → lápida NT_002#4 (~2020-07-16) | `(D201 == 1 or D202 == 4) and exists(D210)` (full). ISS-0004 | MT p. 167/168; NT_002 p. 1 |
| val:DE:D210b (1334) | alta NT_023#6 (2024-08-30 / 2024-09-27) | `D201 == 1 and exists(D210)` (full). ISS-0004 | NT_023 p. 2 |

`subject_field`: D208, D208a–g → field:DE:D208; D209a → field:DE:D209; D210, D210a, D210b → field:DE:D210.

## 3. Efectos por NT

Aplicados (citados por una versión): NT_001#1, NT_002#1–4, NT_008#1, NT_010#6–7, NT_021#1, NT_023#1–7, NT_024#1.

`not_modeled` (mención del vocabulario del piloto fuera de una fila citada; `declared_scope: []`, nota «Mención, no cambio»): NT_001#2 (C002 en la validación F014/2365), NT_003#1–2 (D202 en D219/D223), NT_006#1 (C002 en D011a/1216), NT_007#1 (C002 en B006; NT sin encabezado con verbo: el verbo se tomó del Histórico), NT_010#1–5 (D011 en D012; C002 en E980 y en la validación D202/1300; D201 y D202 en D202/1300), NT_012#1–2 (C002 y D015 en D022/1213), NT_014#1–6 (iNatRec, iTiOpe, iTipIDRec, dDTipIDRec, dNumIDRec del evento de Nominación y D208 en GENFE002e/4469), NT_020#1 (D202 en D202b/1332), NT_023#8 (C002 en H001/2400 y H018a/2444), NT_026#1–3 (D202 en E704, E705, E020 y en las validaciones excluidas 1400, 1401, 1800, 1801), NT_027#1–2 (iTipIDRec y dDTipIDRec de GENFE010/011).

`declared_scope`: `row` en todos los aplicados salvo NT_001#1 y NT_008#1 (`[observations]`: los encabezados hablan de «fórmulas»). Ningún efecto necesitó `acknowledged_changes` (solo cambian observaciones).

Acciones que no salen literalmente del verbo: NT_023#5, #6, #7 tienen el encabezado «se modifica la siguiente validación» pero D208f, D210b y D208g no existen antes (filas enteras en verde = altas): se modelan como `add` y se registra ISS-0014 (no bloqueante; color = acción curada ≠ verbo literal, decisiones 9–10). NT_010#6/#7 reparten el verbo compuesto «se modifican y elimina … y se agrega nueva validación» (ISS-0008).

`curation_scope: pilot` solo en MT_V150 y en las NT con efectos sobre entidades del piloto (1, 2, 8, 10, 21, 23, 24): 8 fichas. Las otras 24 quedan `dates_only`, incluidas NT 3, 6, 7, 12, 14, 20, 26 y 27, cuyo único contenido curado son menciones `not_modeled` (decisión 5 del usuario; en la revisión anterior estaban en `pilot`).

No se registraron efectos para los cambios de esas NT a entidades fuera del piloto (E711, H018, D202/1300, D220, etc.): el guardián no los exige y el modelo no admite efectos `pending`/`not_modeled` con destino a una entidad no curada (`referencias`). Si «efectos completos» debe incluir esas filas, la alternativa es `not_modeled` con `target: null`.

## 4. Fechas por ambiente tal como las copió `sifen draft`

NT con calendario (celda `raw:NT_0xx@<rev>:p1:fechas#test|prod`):

| NT | Fecha del documento | Test | Producción | Revisión | Alcance |
|---|---|---|---|---|---|
| NT_013 | «20/03/2023» → 2023-03-20 | «21 de Abril del 2023» → 2023-04-21 | «17 de Junio del 2023» → 2023-06-17 | 5e9e85ec22f1 | dates_only |
| NT_014 | «20/03/2023» → 2023-03-20 | «31 de Mayo del 2023» → 2023-05-31 | «08 de Agosto del 2023» → 2023-08-08 | 5320a52a9152 | pilot |
| NT_015 | «14/08/2023» → 2023-08-14 | «21 de Agosto del 2023» → 2023-08-21 | «21 de Septiembre del 2023» → 2023-09-21 | d41ae8e7d1fd | dates_only |
| NT_016 | «14/08/2023» → 2023-08-14 | «25 de Agosto del 2023» → 2023-08-25 | «22 de Septiembre del 2023» → 2023-09-22 | 6406e5e6cd4f | dates_only |
| NT_017 | «14/08/2023» → 2023-08-14 | «24 de Agosto del 2023» → 2023-08-24 | «25 de Agosto del 2023» → 2023-08-25 | 21112d7c0a1a | dates_only |
| NT_018 | «17/11/2023» → 2023-11-17 | «01 de diciembre de 2023» → 2023-12-01 | «08 de enero de 2024» → 2024-01-08 | 96079a30c8c1 | dates_only |
| NT_019 | «17/11/2023» → 2023-11-17 | «15/12/2023» → 2023-12-15 | «31/01/2024» → 2024-01-31 | c3fcd3bd96d0 | dates_only |
| NT_020 | «17/11/2023» → 2023-11-17 | «15 de diciembre de 2023» → 2023-12-15 | «31 de enero del 2024» → 2024-01-31 | 0d877d1fb16a | pilot |
| NT_021 | «29/12/2023» → 2023-12-29 | «01/01/2024» → 2024-01-01 | «01/01/2024» → 2024-01-01 | 1e716577d874 | pilot |
| NT_022 | «09/02/2024» → 2024-02-09 | «09 de febrero de 2024» → 2024-02-09 | «09 de febrero de 2024» → 2024-02-09 | 269840094089 | dates_only |
| NT_023 | «27/08/2024» → 2024-08-27 | «30 de agosto de 2024» → 2024-08-30 | «27 de setiembre de 2024» → 2024-09-27 | 9cb063673358 | pilot |
| NT_024 | «17/12/2024» → 2024-12-17 | «01/01/2025» → 2025-01-01 | «01/01/2025» → 2025-01-01 | ccc2d1550e92 | pilot |
| NT_025 | «23/04/2024» → 2024-04-23 (errata, ISS-0007) | «28/04/2025» → 2025-04-28 | «28/04/2025» → 2025-04-28 | 3950e171f161 | dates_only |
| NT_026 | «06/06/2025» → 2025-06-06 | «09/06/2025» → 2025-06-09 | «16/06/2025» → 2025-06-16 | 5ed252f14427 | pilot |
| NT_027 | «09/03/2026» → 2026-03-09 | «09/03/2026» → 2026-03-09 | «09/03/2026» → 2026-03-09 | 3ff6fbbf9f54 | pilot |

NT sin calendario (PageRef con la frase «Fecha: …» / «Cambios desde …» de la página 1):

| NT | Fecha del documento | Período de cambios | Revisión |
|---|---|---|---|
| NT_001 | «14-10-2019» → 2019-10-14 | «10-09-2019» → 2019-09-10 – «14-10-2019» → 2019-10-14 | 4c47b667084d |
| NT_002 | «16/07/2020» → 2020-07-16 | «14/10/2019» → 2019-10-14 – «16/07/2020» → 2020-07-16 | 6aaf4a8f4797 |
| NT_003 | «18/11/2020» → 2020-11-18 | «15/11/2020» – «15/11/2020» | 3d27fa591b59 |
| NT_004 | «29/12/2020» → 2020-12-29 | «29/12/2020» – «29/12/2020» | 185619ec4bad |
| NT_005 | «09/02/2021» → 2021-02-09 | «09/02/2021» – «09/02/2021» | 6889f1fc4f2e |
| NT_006 | «25/03/2021» → 2021-03-25 | — («Cambios desde la fecha: 25/03/2021», una sola fecha: draft deja null) | 44db68fbdcc1 |
| NT_007 | «01/02/2022» → 2022-02-01 | «01/02/2022» – «01/02/2022» | ad25333d61ec |
| NT_008 | «21/09/2021» → 2021-09-21 | «16/09/2021» – «21/09/2021» | 2b1c2f0b25e9 |
| NT_009 | «09/09/2021» → 2021-09-09 | «08/09/2021» – «09/09/2021» | bc6a85c1e77e |
| NT_010 | «04/02/2022» → 2022-02-04 | «01/02/2021» – «04/02/2022» | d261165c512c |
| NT_011 | «20/10/2022» → 2022-10-20 | «23/09/2022» – «20/10/2022» | 6abf95164f4e |
| NT_012 | «21/02/2023» → 2023-02-21 | — (la NT no lo declara) | 3f9243e48a0a |

MT_V150, CHECKSUM_MT, NORMA_DECRETO_872_2023, XSD_DIR (cdd1f03f1d29) y XSD_RAR (6df48074babb): ficha mínima sin fechas. Todas las fechas coinciden con el inventario de `docs/investigacion/sifen.md` §1.4.

## 5. Issues nuevos

| Issue | Tipo | Bloqueante | Sujeto y ventana | Resumen |
|---|---|---|---|---|
| ISS-0001 | source_conflict | no | MT_V150 | MD5 del MT publicado (f48d7c82…) ≠ certificado (25EB165A…); cita verificada en CHECKSUM_MT p. 1 |
| ISS-0002 | undeclared_change | no | val:DE:D208b desde 2024-08-30 (test) / 2024-09-27 (prod) | D208f (1333) reproduce D208b (1319). Con la evidencia de NT 10 sería una reintroducción. No bloqueante desde la decisión 1 (NT 10 elimina D208b; D208f es entidad independiente) |
| ISS-0003 | undeclared_change | **sí** | val:DE:D208 desde 2024-08-30 (test) / 2024-09-27 (prod) | D208g (1335) = D208 (1310) sin excepción B2F; con el literal efectivo el campo D208 dice «Obligatorio si D201 = 2», coherente con D208g pero no con el texto de 1310 (enunciado actualizado en el paso B). Sigue bloqueante |
| ISS-0004 | undeclared_change | no | val:DE:D210a, val:DE:D210b | D210b (1334) ≈ D210a (1323, eliminada por NT 2) sin B2F |
| ISS-0005 | ambiguity | no | val:DE:D208c | Prosa por moneda frente al paréntesis (F023/F014); desde NT 21, con «>» (literal efectivo) |
| ISS-0006 | temporal | no | NT_013 (prod) | Producción 21/05/2023 según fuente secundaria (Roshka) frente a 17/06/2023 del PDF; la fuente secundaria no es `stated_in` |
| ISS-0007 | erratum | no | NT_025 | «Fecha: 23/04/2024» con vigencias y Histórico de 2025 (lo exige `fechas_sanas`) |
| ISS-0008 | ambiguity | no | val:DE:D208b, val:DE:D208f | NT 10 §2.1: la eliminación de D208b es interpretación (verbo compuesto) |
| ISS-0009 | ambiguity | no | field:DE:D208, D210, F023 | Rojo = eliminado en NT 2, NT 8 y NT 23 (campos): aplicado en el paso B (literal efectivo). Queda como trazabilidad de que las NT no declaran la leyenda del MT |
| ISS-0010 | ambiguity | resuelto | val:DE:D210 desde 2024-08-30 (test) / 2024-09-27 (prod) | NT 23 «se modifica» D210 (1314) quitando en rojo la excepción B2F. **Resuelto** (decisión 4): NT_023#4 con literal efectivo y condición `D201 == 2 and not exists(D210)`; 1314 `in_force` desde NT 23 |
| ISS-0011 | ambiguity | no | val:DE:D208c desde 2024-01-01 | Rojo de NT 21/24 en D208c: aplicado como eliminación (decisión 3, «mayor a» sin excepción D011). Trazabilidad de que las NT no reproducen la leyenda del MT (`policy`: aplicado) |
| ISS-0012 | source_conflict | no | val:DE:D208c desde 2024-01-01 | Decreto 872/2023 art. 6 num. 2 «supere» (leído en su literal, p. 11 PDF) frente a NT 21/24. **Resuelto** (decisión del usuario 2026-10-18): con el literal efectivo, «mayor a» equivale a «supere» y no queda la excepción D011 = 13; la cláusula en rojo la traza solo ISS-0011 (§1) |
| ISS-0013 | source_conflict | no | field:DE:C002 | XSD `tiTiDE` = «1\|[4-7]\|9\|10» frente a MT 1–8; el XSD no tiene texto en raw/ (referencia solo en el enunciado) |
| ISS-0014 | ambiguity | no | NT_023#5, NT_023#6, NT_023#7 | D208f (1333), D210b (1334) y D208g (1335): filas enteras en verde (altas) bajo el encabezado «se modifica la siguiente validación». Color = acción curada ≠ verbo literal (decisiones 9–10): se curan como `add` y queda constancia de trazabilidad. Nuevo en el paso B |

## 6. Cambios al pasado

Ninguno: es el primer PR de conocimiento (la base `main` d2eef71d1974 no tiene `kb/` ni golden; `sifen check` lo informa como «no hay pasado que comparar»). La re-materialización del literal efectivo (paso B) no cambia nada del pasado: `main` no tiene `kb/`, así que no hay versiones previas que reescribir.

Golden: las filas de `val:DE:D210` del inicio de NT 23 (2024-08-30 test, 2024-09-27 prod) pasaron de `undetermined`/`blocking_issue` a `in_force` al resolver ISS-0010 (decisión 4). Es un cambio de una expectativa del golden, no del pasado: `tests/golden/temporal.yaml` tampoco está en `main`. Se deja constancia aquí por transparencia con la revisión.

## 7. Efectos pendientes que quedan

Ninguno (`sifen status`: «ningún efecto pendiente»). Revisiones sin curar: ninguna (las 32 tienen ficha con su revisión vigente).

## 8. open_questions (avisos `needs_review`)

- field:DE:D208 @NT_023#1: la observación exige D208 para todo receptor no contribuyente (D201 = 2), como D208g (1335), mientras la validación D208 (1310) sigue diciendo «y D202≠4» y NT 23 no la menciona: no se sabe si el servidor devuelve 1310, 1335 o ambos (ISS-0003).
- val:DE:D208f @NT_023#5: ¿reintroduce D208b? (ISS-0002, ISS-0008)
- val:DE:D208g @NT_023#7: ¿reemplaza a D208 sin la excepción B2F? (ISS-0003, ISS-0009)
- val:DE:D210b @NT_023#6: ¿reintroduce D210a sin B2F? (ISS-0004)

Quitaron en el paso B: field:DE:D208 @NT_002#1, field:DE:D210 @NT_002#2 y @NT_023#2 (la duda del rojo se resolvió con el literal efectivo; ISS-0009 queda como trazabilidad) y val:DE:D210 @NT_023#4 (ISS-0010 resuelto).

## 9. Discrepancias entre el diseño y la evidencia

1. **Valor 6 de D208.** §G.3 («NT 23 agrega el valor 6 a field:DE:D208»; ejemplo XSD «acepta hoy el 6 que agregó NT 23»), §K.5 (golden `enum_excludes: "6"` en prod 2024-09-15), §S («test ≠ producción (D208 valor 6 …)», «ampliación de enumeración (D208)») y `docs/investigacion/sifen.md` §1.4/§4: el MT V150 publicado ya trae «6=Tarjeta Diplomática de exoneración fiscal» (en verde, p. 71/72) y NT 2 (2020) lo reproduce en negro. NT 23 cambia en D208 «No informar si D201 = 1 o D202=4» → «No informar si D201 = 1» (y marca en rojo «y D202 ≠ 4»). Golden: `enum_includes: "6"` en test y en prod.
2. **D208b (1319) eliminada por NT 10** (encabezado «se modifican y elimina … y se agrega nueva validación»; fila D208b idéntica al MT y en rojo). El diseño (§G.3, §S ISS-0002, §K.5 fila «D208b 2024-09-26 → in_force») la supone vigente hasta NT 23. Golden: `removed` en todo el intervalo (2024-08-30 test; 2024-09-26 y 2024-09-27 prod), con ISS-0002 como aviso no bloqueante.
3. **Semántica del color en las NT.** §I.4, `docs/curacion.md` y la investigación (§5) dan por verificado que en NT 21/24 el rojo marca texto vigente. En NT 2, 8, 10 y 23 el color sigue la leyenda del MT (verde = agregado, amarillo = modificado, rojo = eliminado) y en NT 21/24 la «E» de «El Tipo» está en amarillo (mayúscula donde empezaría la oración si se quita la cláusula roja). El Decreto 872/2023 (art. 6 num. 2) dice «supere» y no exceptúa muestras médicas. La KB aplica desde el paso B el literal efectivo (rojo = eliminado, decisión 2) y deja la lectura como trazabilidad en ISS-0009/0011 (ISS-0010 e ISS-0012 resueltos, §1).
4. **NT 23 y D210 (1314).** El diseño la lista como modificada; la fila reproducida es idéntica al MT salvo el tramo en rojo, que el literal efectivo elimina (paso B). ISS-0010 quedó resuelto (decisión 4).
5. **NT 23 «se modifica» para D208f, D210b, D208g**, que son altas (filas en verde): `action: add` por interpretación (lo anticipaba el encargo).
6. **Marca de agua de NT 21.** §G.3/§F.1 prevén `superseded_by` con un PageRef «VER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025»; la marca es gráfica (no está en el texto del PDF: comprobado con pypdfium2) y `citas` exige que la cita esté en la página de `raw/`. No se agregó; el oráculo queda como fila golden (`interval_to: 2025-01-01`).
7. **Menciones fuera de lo previsto.** Además de iTipIDRec en NT 14/27, el guardián exigió efectos `not_modeled` en NT 1, 3, 6, 7, 10, 12, 14 (GENFE002e menciona D208=5), 20, 23 y 26 (C002, D011, D015, D201, D202, D209, D210 en filas ajenas al piloto).
8. **NT 1 y NT 8**: NT 1 modifica F014 (solo espaciado de la fórmula); NT 8 reproduce F023 idéntico al MT salvo el tramo en rojo, que el literal efectivo elimina (ISS-0009).
9. **Decreto 872/2023 leído**: numeral 2 «supere» (antes [P]) y numeral 1 (B2B, B2F y B2G deben identificar al receptor; NT 23 lo cita para D208/D210). Habilitó ISS-0012, resuelto en el paso B (§1).
10. **XSD**: `tiTiDE` «1|[4-7]|9|10» frente a C002 1–8 (ISS-0013). `tiTipDocRec` «[1-6]|9» coincide con la enumeración de D208; ocurrencias de los 10 campos: match.
11. **§G.5 fila 18** (frontera 6.999.999/7.000.000 con `--xml`): el formato golden no la expresa (el veredicto por versión lo declara la fila; no evalúa el DSL sobre valores del XML). Se incluyeron G5-16 y G5-17 (ejes emisión/procesamiento) sobre la KB real.
12. Ninguna NT menciona la validación D209 (1312, en rojo en el MT): no hizo falta tratarla.

## 10. Golden `tests/golden/temporal.yaml`

97 filas (todas pasan: `uv run pytest -q tests/test_golden_temporal.py` → 154 passed; `test_golden_real_completeness` en verde, con fronteras de versiones y bordes de las ventanas de Issues bloqueantes abiertos): cobertura (2023-06-16/17), horizonte (2026-10-24/25), G5-01 a G5-06, G5-15, G5-16, G5-17, G5-20, oráculo de la marca de agua, filas de §K.5 corregidas por la evidencia (D208 valor 6, D208b, D208d `removed` en 2025, D208e con test ≠ prod), día anterior/día del cambio por ambiente para cada versión de las 22 entidades (incluidos los inicios aproximados anteriores a la cobertura) y para las ventanas de ISS-0002 e ISS-0003 (la de ISS-0010 desaparece al resolverlo), `1400` → `not_curated` con NT_026 como primera mención, y `1323` → `removed` con ISS-0004.

Paso B (literal efectivo): las filas de `val:DE:D210` del inicio de NT 23 (2024-08-30 test, 2024-09-27 prod) pasaron de `undetermined`/`blocking_issue` a `in_force` (ISS-0010 resuelto; §6) y se agregaron 9 filas. Seis `diff`, que fijan qué campos cambió cada versión (`changed: […]`), porque el formato no admite fijar el texto literal ni las condiciones: `d208-nt02-diff`, `d208-nt23-diff`, `d210-nt02-diff`, `d210-nt23-diff` (field:DE:D210), `f023-nt08-diff` y `val-d210-nt23-diff` (val:DE:D210; se renombró porque compartía `id` con la del campo, sin cambiar su contenido). Tres `iss14-…` (`d208f`, `d210b`, `d208g`), que fijan ISS-0014 como aviso sin bloquear. Los comentarios de D208c reflejan «> 35 M / > 7 M».

## 11. Checklist para quien revisa (contra el PDF renderizado)

Fechas
- [ ] NT 13–27: test y producción de la tabla de §4 contra la página 1 de cada PDF (columna y ambiente correctos). En especial NT 13 (prod 17/06/2023, ISS-0006), NT 18 (01/12/2023 y 08/01/2024), NT 23 (en palabras: 30 de agosto y 27 de setiembre de 2024), NT 25 (errata «23/04/2024», ISS-0007).
- [ ] NT 1–12: «Fecha:» y «Cambios desde …» (NT 6 con una sola fecha → `change_period` null; NT 12 sin período).

Acciones y alcance
- [ ] NT 10 p. 3 (§2.1): ¿acepta que «elimina» corresponde a D208b (NT_010#6, ISS-0008)? (ISS-0002 no bloqueante desde la decisión 1; ¿se resuelve?)
- [ ] NT 23 p. 2: D208f, D210b, D208g como `add` pese a «se modifica» (ISS-0014).
- [ ] NT_001#1 y NT_008#1 con `declared_scope: [observations]` («fórmulas»); el resto `row`.
- [ ] Efectos `not_modeled` (§3): cada nota dice qué fila menciona qué término.

Color y literales (renderizar y mirar)
- [ ] NT 2 p. 1: rojo en «No informar si D201 = 1 o D202=4» (D208, D210) y en D208d/D210a (ISS-0009).
- [ ] NT 8 p. 1: rojo en «Cuando C002=4 corresponde a F014» (ISS-0009).
- [ ] NT 23 p. 1–2: rojo «y D202 ≠ 4», verde «No informar si D201 = 1», rojo en D210 (1314) (ISS-0009; ISS-0010 resuelto).
- [ ] NT 21 p. 1 y NT 24 p. 1: rojo en la cláusula D011≠13, «o igual» y «=»; «E» en amarillo (ISS-0011, aplicado como eliminación). ¿Se consulta a DNIT?
- [ ] MT p. 71/72: «6=Tarjeta Diplomática …» y «9= Otro» en verde.
- [ ] **Tramos en rojo que el literal efectivo quita**: contra el PDF renderizado, comprobar que cada tramo borrado coincide con lo resaltado en rojo — NT 2 (D208, D210), NT 8 (F023), NT 23 (D208, D210 y la validación 1314), NT 21 y NT 24 (D208c) — y que lo que queda es continuo (el espacio antes de la coma en 1314 se conserva, decisión 11).

Condiciones y enumeraciones
- [ ] Polaridad y guardas de las 12 condiciones (§2), en particular D208c (partial: paréntesis, polaridad mixta; sin la guarda D011 desde NT 21), D210 (full: `D201 == 2 and not exists(D210)`) y D209a (none).
- [ ] Etiquetas de enumeración (C002 incluye «(Futuro)»; D202 omite la aclaración de B2F).
- [ ] `legal_basis` de D208c (NT 21 y NT 24).

Issues
- [ ] Bloqueante: solo ISS-0003 (ventanas por ambiente). ISS-0002, ISS-0011 e ISS-0014 no bloqueantes; ISS-0010 e ISS-0012 resueltos.
- [ ] Nuevos no previstos por el diseño: ISS-0007 a ISS-0014.
- [ ] Bitácora (§1): la corrida `ce4ca541` debe figurar con salidas `source: backfill` y su motivo (PR 1b′), no como eventos del hook.

Otros
- [ ] `curation_scope: dates_only` en las NT con solo efectos `not_modeled` (decisión 5): `pilot` queda en MT_V150 y NT 1, 2, 8, 10, 21, 23, 24.
- [ ] Sin `superseded_by` en NT_021 (marca de agua no textual).

## 12. Defectos de código o de diseño detectados (no se corrigieron en este PR)

1. `sifen draft <DocId> --dry-run` imprime «kb/documents/NT_023.yaml: escrito» aunque no escribe (mensaje engañoso; comprobado: no creó el archivo).
2. `Supersession.stated_in` solo admite PageRef y `citas` exige la cita en el texto de `raw/`: una marca de agua gráfica (NT 21) no se puede citar, así que `superseded_by` y el oráculo `reemplazo` no son aplicables a la KB real.
3. `sifen explain NT_0xx` (texto) muestra el `stated_in` PageRef de la fecha del documento como un dict de Python («(informativa; {'doc': 'NT_010', …})»). Cosmético.
4. `test_golden_real_completeness` solo exigía fronteras de versiones; **corregido en el paso A** (`feat/literal-efectivo`): la completitud ahora exige también los bordes de las ventanas de los Issues bloqueantes abiertos (`boundary_gaps`, `tests/test_golden_temporal.py`).
5. `cut_kb` conserva Issues cuya ventana empieza después del corte (en G5-06 aparecen ISS-0011/0012 en una KB cortada al 2023-12-20). No afecta estados.
6. Los hooks solo registran Edit/Write: los archivos que reescriben `sifen draft` y `sifen fmt` (Bash) quedan con un sha256 desactualizado en `outputs` (`corridas_llm` no lo compara, por diseño).
7. Diseño: la regla «en una NT se copia la celda completa» hacía que varias versiones (NT 2, NT 8, NT 23/D210) no reflejaran el cambio que la NT declara (ISS-0009/0010). **Superado** en el paso A/paso B con la separación `rendered_literal` / `effective_literal` (decisión 2; `extraction/fixes.yaml` no se usa para esto): el literal efectivo se deriva aplicando el marcado. Sigue abierto el criterio de lectura del color (las NT no declaran la leyenda del MT): ISS-0009 queda como trazabilidad.
8. **`corridas_llm` (resuelto con backfill, §1.1).** La sesión del paso B editó las fichas con herramientas MCP (`mcp__custom-tools__edit`/`write`), no con Edit/Write de Claude Code, y el hook `PostToolUse` (matcher `Edit|Write|MultiEdit`) no registró esos archivos: `curation/runs/ce4ca541-….yaml` quedó con `outputs: []` y `sifen check` reportaba 16 errores de `corridas_llm`. Se resolvió con el soporte de procedencia de 6e0c377 y un registro `backfill` visible en cada bitácora (§1.1). Sigue pendiente, en otro PR de código, ampliar el matcher y los `deny` a las herramientas MCP.

## 13. Verificación

Paso B (2026-10-18), sobre el estado re-materializado:

Cierre (2026-10-18, después del backfill y del rebase sobre `feat/bitacora-procedencia`):

- `uv run sifen check --report` → **OK**: 0 errores, 0 avisos, 8 informativos (`fuentes` 1; `marcado` 3 `color_verbo`, cubiertos por ISS-0014; `corridas_llm` 3, uno por corrida con salidas `backfill` y su motivo; `pasado` 1). Salida completa en el anexo.
- `git diff --check`, `ruff check .`, `ruff format --check .` y `sifen fmt --check` → OK. Golden sin `id` duplicados. Las 10 bitácoras de `curation/runs/` son válidas con el código integrado.
- `uv run pytest -q` (suite completa) → **1833 passed, 1 skipped** (el previsto: `test_explain.py:929`, «1321 ya está curado»).
- `uv run pytest -q tests/test_golden_temporal.py` → 154 passed.
- `explain 1321 --at 2025-01-10` → in_force NT_024#1 («… es mayor a 7.000.000 (F023 > 7.000.000 o F014 > 7.000.000)»), base legal citada (Decreto 872/2023, art. 6, numeral 2, inciso ii)), ISS-0005 e ISS-0011 como avisos (ISS-0012 resuelto ya no aparece).
- `explain D208 --at 2024-09-15 --env test` → campo: NT_023#1 («Obligatorio si D201 = 2 No informar si D201 = 1 …», valor 6 presente); validación 1310: undetermined (ISS-0003).
- `explain D208 --at 2024-09-15 --env prod` → campo: NT_002#1 (sin «No informar …»), próximo NT_023#1 desde 2024-09-27; validación 1310: in_force (línea base).
- `explain 1322 --at 2025-03-01` → removed (lápida NT_002#3, inicio aproximado).
- `explain D208b --at 2024-09-27` → removed (lápida NT_010#6).
- `explain 1314 --at 2024-10-01` → in_force NT_023#4 (literal sin la excepción B2F; `D201 == 2 and not exists(D210)`).
- `explain C002` → `xsd.status: mismatch` con ISS-0013 (documentado por MT/NT 1–8 frente a aceptado por la instantánea 1, 4–7, 9, 10).
- `sifen status` → 32 documentos curados (24 dates_only, 8 pilot), 10 campos, 12 validaciones, sin pendientes, 1 Issue bloqueante (ISS-0003).

Antes del rebase, la suite completa daba 1787 passed, 1 skipped (`docs/traspaso-curacion-piloto.md` §4, B.4); la diferencia son los 46 tests de 6e0c377. La verificación previa (estado anterior al literal efectivo) fue: `sifen fmt` → OK (69 archivos, 0 no canónicos); `pytest -q --ignore=tests/extraction` → 1049 passed, 1 skipped; `pytest -q tests/extraction` → 705 passed; `pytest -q tests/unit tests/test_golden_temporal.py tests/extraction/test_golden_piloto.py` → 1157 passed, 1 skipped (`test_explain.py:845`, skip previsto por el propio test).

## Anexo: salida de `uv run sifen check --report`

```
sifen check: 29 comprobaciones sobre /home/soporte/proyectos/sifen-kb
[fuentes] 1 info
  INFO   sources.manifest.yaml: horizonte de fuentes: 2026-10-17
[marcado] 3 info
  INFO   kb/documents/NT_023.yaml: NT_023#5 (color_verbo): raw:NT_023@9cb063673358:p2:D208f: el marcado (added) indica `add`, como la acción curada, y el verbo del encabezado «se modifica la siguiente validación» no lo nombra; cubierto por ISS-0014
  INFO   kb/documents/NT_023.yaml: NT_023#6 (color_verbo): raw:NT_023@9cb063673358:p2:D210b: el marcado (added) indica `add`, como la acción curada, y el verbo del encabezado «se modifica la siguiente validación» no lo nombra; cubierto por ISS-0014
  INFO   kb/documents/NT_023.yaml: NT_023#7 (color_verbo): raw:NT_023@9cb063673358:p2:D208g: el marcado (added) indica `add`, como la acción curada, y el verbo del encabezado «se modifica la siguiente validación» no lo nombra; cubierto por ISS-0014
[corridas_llm] 3 info
  INFO   curation/runs/6767ad7f-b35b-4bcd-a3a7-d670f1b45845.yaml: 3 outputs registrados retroactivamente (backfill): docs/HANDOFF.md (Sesión en arnés Pi: docs/HANDOFF.md fue editado mediante herramientas MCP (mcp__custom-tools__edit y mcp__custom-tools__bash), que no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); docs/traspaso-curacion-piloto.md (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0012.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18)
  INFO   curation/runs/6b58d45f-98a7-4353-8d45-d1b664f31286.yaml: 1 output registrado retroactivamente (backfill): tests/golden/temporal.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18)
  INFO   curation/runs/ce4ca541-bb4f-49d4-8e9f-5430b10e6d63.yaml: 15 outputs registrados retroactivamente (backfill): kb/fields/DE/D208.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/validations/DE/D208c.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/validations/DE/D210.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_002.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_008.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_021.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_023.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_024.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0003.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0005.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0009.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0010.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0011.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0014.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/validations/DE/D208g.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18)
[pasado] 1 info
  INFO   kb: la base main (d2eef71d1974) no tiene kb/ ni golden: no hay pasado que comparar
Resumen: 0 error(es), 0 aviso(s), 8 informativo(s) → OK

# Informe de revisión de la KB — base main (d2eef71d1974)

## Entidades
### field:DE:C002 (kb/fields/DE/C002.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### field:DE:D011 (kb/fields/DE/D011.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### field:DE:D015 (kb/fields/DE/D015.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### field:DE:D201 (kb/fields/DE/D201.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### field:DE:D202 (kb/fields/DE/D202.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### field:DE:D208 (kb/fields/DE/D208.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_002#1 · content · nueva · based_on baseline · test 2020-07-16 (approx) · prod 2020-07-16 (approx)
  - diff contra based_on baseline: enumeration_interpretation, observations
    - enumeration_interpretation: {"by": "llm", "note": "El valor 6 ya figura en el MT V150 publicado (resaltado en verde = agregado en la leyenda del MT).", "run": "a067d55b-d757-498d-a601-f946db1a3acc"} → {"by": "llm", "note": "Lista de valores idéntica a la de la línea base: NT 2 no agrega ni quita valores. El cambio está en la condición: el tramo en rojo «No informar si D201 = 1 o D202=4» se elimina (rojo = contenido eliminado, decisión del usuario 2026-10-17), en la misma NT que elimina D208d (13…
    - observations: "Obligatorio si D201 = 2 y D202 ≠ 4 No informar si D201 = 1 o D202=4 1= Cédula paraguaya 2= Pasaporte 3= Cédula extranjera 4= Carnet de residencia 5= Innominado 6=Tarjeta Diplomática de exoneración fiscal 9= Otro" → "Obligatorio si D201 = 2 y D202 ≠ 4 1= Cédula paraguaya 2= Pasaporte 3= Cédula extranjera 4= Carnet de residencia 5= Innominado 6=Tarjeta Diplomática de exoneración fiscal 9= Otro"
- Versión NT_023#1 · content · nueva · based_on NT_002#1 · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - diff contra based_on NT_002#1: enumeration_interpretation, observations
    - enumeration_interpretation: {"by": "llm", "note": "Lista de valores idéntica a la de la línea base: NT 2 no agrega ni quita valores. El cambio está en la condición: el tramo en rojo «No informar si D201 = 1 o D202=4» se elimina (rojo = contenido eliminado, decisión del usuario 2026-10-17), en la misma NT que elimina D208d (13… → {"by": "llm", "note": "Lista de valores idéntica a la del MT V150 y de NT 2: NT 23 no agrega ni quita valores. El cambio está en la condición: se elimina «y D202 ≠ 4» (en rojo) y se agrega «No informar si D201 = 1».", "run": "ce4ca541-bb4f-49d4-8e9f-5430b10e6d63"}
    - observations: "Obligatorio si D201 = 2 y D202 ≠ 4 1= Cédula paraguaya 2= Pasaporte 3= Cédula extranjera 4= Carnet de residencia 5= Innominado 6=Tarjeta Diplomática de exoneración fiscal 9= Otro" → "Obligatorio si D201 = 2 No informar si D201 = 1 1= Cédula paraguaya 2= Pasaporte 3= Cédula extranjera 4= Carnet de residencia 5= Innominado 6=Tarjeta Diplomática de exoneración fiscal 9= Otro"
  - open_questions: Desde NT 23 la observación del campo exige D208 para todo receptor no contribuyente (D201 = 2), como D208g (1335), mientras la validación D208 (1310) sigue diciendo «y D202≠4» y NT 23 no la menciona: no se sabe si el servidor devuelve 1310, 1335 o ambos (ISS-0003).
### field:DE:D209 (kb/fields/DE/D209.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### field:DE:D210 (kb/fields/DE/D210.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_002#2 · content · nueva · based_on baseline · test 2020-07-16 (approx) · prod 2020-07-16 (approx)
  - diff contra based_on baseline: observations
    - observations: "Obligatorio si D201 = 2 y D202 ≠ 4 No informar si D201 = 1 o D202=4 En caso de DE innominado, completar con 0 (cero)" → "Obligatorio si D201 = 2 y D202 ≠ 4 En caso de DE innominado, completar con 0 (cero)"
- Versión NT_023#2 · content · nueva · based_on NT_002#2 · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - diff contra based_on NT_002#2: observations
    - observations: "Obligatorio si D201 = 2 y D202 ≠ 4 En caso de DE innominado, completar con 0 (cero)" → "Obligatorio si D201 = 2 No informar si D201 = 1 En caso de DE innominado, completar con 0 (cero)"
### field:DE:F014 (kb/fields/DE/F014.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_001#1 · content · nueva · based_on baseline · test 2019-10-14 (approx) · prod 2019-10-14 (approx)
  - diff contra based_on baseline: observations
    - observations: "Corresponde al cálculo aritmético F008 - F013 + F025" → "Corresponde al cálculo aritmético F008-F013+F025"
### field:DE:F023 (kb/fields/DE/F023.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_008#1 · content · nueva · based_on baseline · test 2021-09-21 (approx) · prod 2021-09-21 (approx)
  - diff contra based_on baseline: observations
    - observations: "Si D015 ≠ PYG y D017 = 1, corresponde al cálculo aritmético: F014 * D018 Si D015 ≠ PYG y D017 = 2, corresponde a la suma de todas las ocurrencias de EA009 Este campo no debe existir si D015=PYG No informar si D015 = PYG Cuando C002=4 corresponde a F014" → "Si D015 ≠ PYG y D017 = 1, corresponde al cálculo aritmético: F014 * D018 Si D015 ≠ PYG y D017 = 2, corresponde a la suma de todas las ocurrencias de EA009 Este campo no debe existir si D015=PYG No informar si D015 = PYG"
### val:DE:D208 (kb/validations/DE/D208.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### val:DE:D208a (kb/validations/DE/D208a.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### val:DE:D208b (kb/validations/DE/D208b.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_010#6 · tombstone · nueva · based_on baseline · test 2022-02-04 (approx) · prod 2022-02-04 (approx)
  - diff contra based_on baseline: sin cambios de contenido
### val:DE:D208c (kb/validations/DE/D208c.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_021#1 · content · nueva · based_on baseline · test 2024-01-01 (stated) · prod 2024-01-01 (stated)
  - diff contra based_on baseline: condition, legal_basis, observation
    - condition: {"expr": "(not exists(D011) or D011 != 13) and exists(D208) and D208 == 5 and ((exists(F023) and F023 >= 60000000) or (exists(F014) and F014 >= 60000000))", "gaps": "Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 >= 60.000.000 y… → {"expr": "exists(D208) and D208 == 5 and ((exists(F023) and F023 > 35000000) or (exists(F014) and F014 > 35000000))", "gaps": "Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 > 35.000.000 y F023 <= 35.000.000, el paréntesis viola…
    - legal_basis: [] → [{"citation": "Decreto 872/2023, art. 6", "stated_in": {"doc": "NT_021", "page_pdf": 1, "page_printed": null, "quote": "Conforme a lo dispuesto en el Artículo N° 6 del Decreto N° 872/2023", "rev": "1e716577d874"}}]
    - observation: "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), el Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es … → "El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es mayor a 35.000.000 (F023 > 35000000 o F014 > 35000000)"
- Versión NT_024#1 · content · nueva · based_on NT_021#1 · test 2025-01-01 (stated) · prod 2025-01-01 (stated)
  - diff contra based_on NT_021#1: condition, legal_basis, observation
    - condition: {"expr": "exists(D208) and D208 == 5 and ((exists(F023) and F023 > 35000000) or (exists(F014) and F014 > 35000000))", "gaps": "Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 > 35.000.000 y F023 <= 35.000.000, el paréntesis viola… → {"expr": "exists(D208) and D208 == 5 and ((exists(F023) and F023 > 7000000) or (exists(F014) and F014 > 7000000))", "gaps": "Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 > 7.000.000 y F023 <= 7.000.000, el paréntesis viola y l…
    - legal_basis: [{"citation": "Decreto 872/2023, art. 6", "stated_in": {"doc": "NT_021", "page_pdf": 1, "page_printed": null, "quote": "Conforme a lo dispuesto en el Artículo N° 6 del Decreto N° 872/2023", "rev": "1e716577d874"}}] → [{"citation": "Decreto 872/2023, art. 6, numeral 2, inciso ii)", "stated_in": {"doc": "NT_024", "page_pdf": 1, "page_printed": null, "quote": "Conforme a lo dispuesto en el inciso ii), Numeral 2 del Artículo N° 6 del Decreto N° 872/2023.", "rev": "ccc2d1550e92"}}]
    - observation: "El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es mayor a 35.000.000 (F023 > 35000000 o F014 > 35000000)" → "El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es mayor a 7.000.000 (F023 > 7.000.000 o F014 > 7.000.000)"
### val:DE:D208d (kb/validations/DE/D208d.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_002#3 · tombstone · nueva · based_on baseline · test 2020-07-16 (approx) · prod 2020-07-16 (approx)
  - diff contra based_on baseline: sin cambios de contenido
### val:DE:D208e (kb/validations/DE/D208e.yaml) — nueva
- Versión NT_010#7 · content · nueva · based_on baseline · test 2022-02-04 (approx) · prod 2022-02-04 (approx)
- Versión NT_023#3 · content · nueva · based_on NT_010#7 · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - diff contra based_on NT_010#7: condition, observation
    - condition: {"expr": "C002 in (5, 6) and exists(D208) and D208 == 5", "gaps": "Polaridad mixta: «(D208 ≠ 5)» es la restricción que debe cumplirse, no el disparador; la condición de violación es D208 = 5. D208 ausente no viola.", "interpretation": {"by": "llm", "note": null, "run": "a067d55b-d757-498d-a601-f946… → {"expr": "C002 in (5, 6, 7) and exists(D208) and D208 == 5", "gaps": "Polaridad mixta: «(D208 ≠ 5)» es la restricción que debe cumplirse, no el disparador; la condición de violación es D208 = 5. D208 ausente no viola.", "interpretation": {"by": "llm", "note": null, "run": "a067d55b-d757-498d-a601-f…
    - observation: "Si el tipo de documento electrónico es Nota de Crédito (C002 = 5) o Nota de Débito (C002 = 6), el tipo de documento de identidad del receptor no puede ser INNOMINADO (D208 ≠ 5)" → "Si el tipo de documento electrónico seleccionado es igual a Nota de Crédito, Nota de Débito o Nota de Remisión Electrónica (C002 = 5, 6, 7), el tipo de documento de identidad del receptor no puede ser INNOMINADO (D208 ≠ 5)"
### val:DE:D208f (kb/validations/DE/D208f.yaml) — nueva
- Versión NT_023#5 · content · nueva · based_on baseline · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - open_questions: ¿D208f (1333) reintroduce con otro ID y código la regla de D208b (1319), eliminada por NT 10 según NT_010#6? DNIT no lo declara (ISS-0002, ISS-0008).
### val:DE:D208g (kb/validations/DE/D208g.yaml) — nueva
- Versión NT_023#7 · content · nueva · based_on baseline · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - open_questions: ¿D208g (1335) reemplaza a D208 (1310) sin la excepción B2F? DNIT no lo declara; en la misma NT la observación del campo D208 pasa a «Obligatorio si D201 = 2» (literal efectivo, sin «y D202 ≠ 4»), coherente con D208g, pero 1310 no se menciona (ISS-0003, ISS-0009).
### val:DE:D209a (kb/validations/DE/D209a.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
### val:DE:D210 (kb/validations/DE/D210.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_023#4 · content · nueva · based_on baseline · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - diff contra based_on baseline: condition, observation
    - condition: {"expr": "D201 == 2 and D202 != 4 and not exists(D210)", "gaps": null, "interpretation": {"by": "llm", "note": "Se viola cuando el receptor es no contribuyente, la operación no es B2F y D210 no se informa. D201 y D202 son obligatorios (1-1): se leen sin guarda.", "run": "a067d55b-d757-498d-a601-f94… → {"expr": "D201 == 2 and not exists(D210)", "gaps": null, "interpretation": {"by": "llm", "note": "Se viola cuando el receptor es no contribuyente y D210 no se informa, también en operaciones B2F: NT 23 quita en rojo «y el tipo de operación es diferente a B2F (D202≠4)» (rojo = contenido eliminado, d…
    - observation: "Si la naturaleza del receptor es NO contribuyente (D201=2) y el tipo de operación es diferente a B2F (D202≠4), el número de documento de identidad debe ser informado" → "Si la naturaleza del receptor es NO contribuyente (D201=2) , el número de documento de identidad debe ser informado"
### val:DE:D210a (kb/validations/DE/D210a.yaml) — nueva
- Versión baseline · content · nueva · based_on — · test línea base (baseline) · prod línea base (baseline)
- Versión NT_002#4 · tombstone · nueva · based_on baseline · test 2020-07-16 (approx) · prod 2020-07-16 (approx)
  - diff contra based_on baseline: sin cambios de contenido
### val:DE:D210b (kb/validations/DE/D210b.yaml) — nueva
- Versión NT_023#6 · content · nueva · based_on baseline · test 2024-08-30 (stated) · prod 2024-09-27 (stated)
  - open_questions: ¿D210b (1334) reintroduce con otro ID y código la regla de D210a (1323), eliminada por NT 2, sin la condición B2F? DNIT no lo declara (ISS-0004).

## Calendarios (documentos nuevos o con fechas cambiadas)
- CHECKSUM_MT (nuevo): sin fechas
- MT_V150 (nuevo): sin fechas
- NORMA_DECRETO_872_2023 (nuevo): sin fechas
- NT_001 (nuevo): document_date '14-10-2019' → 2019-10-14 (PageRef); change_period[0] '10-09-2019' → 2019-09-10 (PageRef); change_period[1] '14-10-2019' → 2019-10-14 (PageRef)
- NT_002 (nuevo): document_date '16/07/2020' → 2020-07-16 (PageRef); change_period[0] '14/10/2019' → 2019-10-14 (PageRef); change_period[1] '16/07/2020' → 2020-07-16 (PageRef)
- NT_003 (nuevo): document_date '18/11/2020' → 2020-11-18 (PageRef); change_period[0] '15/11/2020' → 2020-11-15 (PageRef); change_period[1] '15/11/2020' → 2020-11-15 (PageRef)
- NT_004 (nuevo): document_date '29/12/2020' → 2020-12-29 (PageRef); change_period[0] '29/12/2020' → 2020-12-29 (PageRef); change_period[1] '29/12/2020' → 2020-12-29 (PageRef)
- NT_005 (nuevo): document_date '09/02/2021' → 2021-02-09 (PageRef); change_period[0] '09/02/2021' → 2021-02-09 (PageRef); change_period[1] '09/02/2021' → 2021-02-09 (PageRef)
- NT_006 (nuevo): document_date '25/03/2021' → 2021-03-25 (PageRef)
- NT_007 (nuevo): document_date '01/02/2022' → 2022-02-01 (PageRef); change_period[0] '01/02/2022' → 2022-02-01 (PageRef); change_period[1] '01/02/2022' → 2022-02-01 (PageRef)
- NT_008 (nuevo): document_date '21/09/2021' → 2021-09-21 (PageRef); change_period[0] '16/09/2021' → 2021-09-16 (PageRef); change_period[1] '21/09/2021' → 2021-09-21 (PageRef)
- NT_009 (nuevo): document_date '09/09/2021' → 2021-09-09 (PageRef); change_period[0] '08/09/2021' → 2021-09-08 (PageRef); change_period[1] '09/09/2021' → 2021-09-09 (PageRef)
- NT_010 (nuevo): document_date '04/02/2022' → 2022-02-04 (PageRef); change_period[0] '01/02/2021' → 2021-02-01 (PageRef); change_period[1] '04/02/2022' → 2022-02-04 (PageRef)
- NT_011 (nuevo): document_date '20/10/2022' → 2022-10-20 (PageRef); change_period[0] '23/09/2022' → 2022-09-23 (PageRef); change_period[1] '20/10/2022' → 2022-10-20 (PageRef)
- NT_012 (nuevo): document_date '21/02/2023' → 2023-02-21 (PageRef)
- NT_013 (nuevo): document_date '20/03/2023' → 2023-03-20 (raw:NT_013@5e9e85ec22f1:p1:fechas#fecha); schedule.test '21 de Abril del 2023' → 2023-04-21 (raw:NT_013@5e9e85ec22f1:p1:fechas#test); schedule.prod '17 de Junio del 2023' → 2023-06-17 (raw:NT_013@5e9e85ec22f1:p1:fechas#prod)
- NT_014 (nuevo): document_date '20/03/2023' → 2023-03-20 (raw:NT_014@5320a52a9152:p1:fechas#fecha); schedule.test '31 de Mayo del 2023' → 2023-05-31 (raw:NT_014@5320a52a9152:p1:fechas#test); schedule.prod '08 de Agosto del 2023' → 2023-08-08 (raw:NT_014@5320a52a9152:p1:fechas#prod)
- NT_015 (nuevo): document_date '14/08/2023' → 2023-08-14 (raw:NT_015@d41ae8e7d1fd:p1:fechas#fecha); schedule.test '21 de Agosto del 2023' → 2023-08-21 (raw:NT_015@d41ae8e7d1fd:p1:fechas#test); schedule.prod '21 de Septiembre del 2023' → 2023-09-21 (raw:NT_015@d41ae8e7d1fd:p1:fechas#prod)
- NT_016 (nuevo): document_date '14/08/2023' → 2023-08-14 (raw:NT_016@6406e5e6cd4f:p1:fechas#fecha); schedule.test '25 de Agosto del 2023' → 2023-08-25 (raw:NT_016@6406e5e6cd4f:p1:fechas#test); schedule.prod '22 de Septiembre del 2023' → 2023-09-22 (raw:NT_016@6406e5e6cd4f:p1:fechas#prod)
- NT_017 (nuevo): document_date '14/08/2023' → 2023-08-14 (raw:NT_017@21112d7c0a1a:p1:fechas#fecha); schedule.test '24 de Agosto del 2023' → 2023-08-24 (raw:NT_017@21112d7c0a1a:p1:fechas#test); schedule.prod '25 de Agosto del 2023' → 2023-08-25 (raw:NT_017@21112d7c0a1a:p1:fechas#prod)
- NT_018 (nuevo): document_date '17/11/2023' → 2023-11-17 (raw:NT_018@96079a30c8c1:p1:fechas#fecha); schedule.test '01 de diciembre de 2023' → 2023-12-01 (raw:NT_018@96079a30c8c1:p1:fechas#test); schedule.prod '08 de enero de 2024' → 2024-01-08 (raw:NT_018@96079a30c8c1:p1:fechas#prod)
- NT_019 (nuevo): document_date '17/11/2023' → 2023-11-17 (raw:NT_019@c3fcd3bd96d0:p1:fechas#fecha); schedule.test '15/12/2023' → 2023-12-15 (raw:NT_019@c3fcd3bd96d0:p1:fechas#test); schedule.prod '31/01/2024' → 2024-01-31 (raw:NT_019@c3fcd3bd96d0:p1:fechas#prod)
- NT_020 (nuevo): document_date '17/11/2023' → 2023-11-17 (raw:NT_020@0d877d1fb16a:p1:fechas#fecha); schedule.test '15 de diciembre de 2023' → 2023-12-15 (raw:NT_020@0d877d1fb16a:p1:fechas#test); schedule.prod '31 de enero del 2024' → 2024-01-31 (raw:NT_020@0d877d1fb16a:p1:fechas#prod)
- NT_021 (nuevo): document_date '29/12/2023' → 2023-12-29 (raw:NT_021@1e716577d874:p1:fechas#fecha); schedule.test '01/01/2024' → 2024-01-01 (raw:NT_021@1e716577d874:p1:fechas#test); schedule.prod '01/01/2024' → 2024-01-01 (raw:NT_021@1e716577d874:p1:fechas#prod)
- NT_022 (nuevo): document_date '09/02/2024' → 2024-02-09 (raw:NT_022@269840094089:p1:fechas#fecha); schedule.test '09 de febrero de 2024' → 2024-02-09 (raw:NT_022@269840094089:p1:fechas#test); schedule.prod '09 de febrero de 2024' → 2024-02-09 (raw:NT_022@269840094089:p1:fechas#prod)
- NT_023 (nuevo): document_date '27/08/2024' → 2024-08-27 (raw:NT_023@9cb063673358:p1:fechas#fecha); schedule.test '30 de agosto de 2024' → 2024-08-30 (raw:NT_023@9cb063673358:p1:fechas#test); schedule.prod '27 de setiembre de 2024' → 2024-09-27 (raw:NT_023@9cb063673358:p1:fechas#prod)
- NT_024 (nuevo): document_date '17/12/2024' → 2024-12-17 (raw:NT_024@ccc2d1550e92:p1:fechas#fecha); schedule.test '01/01/2025' → 2025-01-01 (raw:NT_024@ccc2d1550e92:p1:fechas#test); schedule.prod '01/01/2025' → 2025-01-01 (raw:NT_024@ccc2d1550e92:p1:fechas#prod)
- NT_025 (nuevo): document_date '23/04/2024' → 2024-04-23 (raw:NT_025@3950e171f161:p1:fechas#fecha); schedule.test '28/04/2025' → 2025-04-28 (raw:NT_025@3950e171f161:p1:fechas#test); schedule.prod '28/04/2025' → 2025-04-28 (raw:NT_025@3950e171f161:p1:fechas#prod)
- NT_026 (nuevo): document_date '06/06/2025' → 2025-06-06 (raw:NT_026@5ed252f14427:p1:fechas#fecha); schedule.test '09/06/2025' → 2025-06-09 (raw:NT_026@5ed252f14427:p1:fechas#test); schedule.prod '16/06/2025' → 2025-06-16 (raw:NT_026@5ed252f14427:p1:fechas#prod)
- NT_027 (nuevo): document_date '09/03/2026' → 2026-03-09 (raw:NT_027@3ff6fbbf9f54:p1:fechas#fecha); schedule.test '09/03/2026' → 2026-03-09 (raw:NT_027@3ff6fbbf9f54:p1:fechas#test); schedule.prod '09/03/2026' → 2026-03-09 (raw:NT_027@3ff6fbbf9f54:p1:fechas#prod)
- XSD_DIR (nuevo): sin fechas
- XSD_RAR (nuevo): sin fechas

## Issues nuevos
- ISS-0001 (source_conflict, open): 'El «Listado Checksum MD5» oficial de DNIT certifica MT_E_Kuatia_V150_10_09_2019.pdf con MD5 25EB165A8506EFA3A255B863ABCCAE95. El binario publicado hoy en el portal («Manual Técnico Versión 150.pdf», registrado en sources.manifest.yaml) tiene MD5 f48d7c820a14723ec14e66bfcb02e0df (sha256 976cd88c05c…
- ISS-0002 (undeclared_change, open): 'NT 23 agrega D208f (1333) con el mismo mensaje y la misma observación que D208b (1319) («El Tipo de documento de identidad del receptor no puede ser innominado (D208=5), cuando el tipo de operación es distinto a B2C (D202 ≠ 2)»). NT 10 ya había eliminado D208b (NT_010#6, ISS-0008), de modo que D20…
- ISS-0003 (undeclared_change, bloqueante, open): 'NT 23 agrega D208g (1335, «El tipo de documento de identidad del receptor es requerido»: obligatorio si D201=2) sin mencionar D208 (1310, «Es obligatorio informar el tipo de documento de identidad del receptor»: obligatorio si D201=2 y D202≠4). Es la misma obligación sin la excepción B2F, con otro…
- ISS-0004 (undeclared_change, open): 'NT 2 elimina D210a (1323, «El número de documento de identidad del receptor no es requerido»: contribuyente o B2F). NT 23 agrega D210b (1334) con el mismo mensaje y la observación sin la parte B2F («Si la naturaleza del receptor es contribuyente (D201=1) el número de documento de identidad no debe…
- ISS-0005 (ambiguity, open): 'La observación de D208c (1321) asocia en prosa el monto a la moneda («el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG)», es decir F023 con moneda extranjera y F014 con PYG, según D015), pero el paréntesis fo…
- ISS-0006 (temporal, open): 'El PDF oficial vigente de NT 13 (revisión 5e9e85ec22f1) declara producción el 17/06/2023 (test 21/04/2023). Una fuente secundaria no oficial (README de la librería rshk-jsifenlib de Roshka) documenta para NT 13 «21/04/2023 desarrollo y 21/05/2023 producción»: posible prórroga in situ en una revisi…
- ISS-0007 (erratum, open): 'NT 25 dice «Fecha: 23/04/2024», pero sus fechas de puesta a disposición son 28/04/2025 (test y producción) y su Histórico del Documento registra elaboración y revisión el 23/04/2025: probable errata de año en la fecha del documento (370 días entre la fecha impresa y la de test).'
- ISS-0008 (ambiguity, resolved): 'NT 10 §2.1 («se modifican y elimina las siguientes validaciones y se agrega nueva validación») reproduce cuatro filas sin decir qué verbo corresponde a cada una: D202 (1300), D220 (1325), D208b (1319) y D208e (1331). La curación (NT_010#6) interpreta que D208b es la eliminada: D208e es la única qu…
- ISS-0009 (ambiguity, open): 'Las NT no declaran la leyenda de colores del MT, pero en varias el texto resaltado en rojo dentro de una fila «modificada» marca texto eliminado (como en la leyenda del MT): (1) NT 2, campos D208 y D210: «No informar si D201 = 1 o D202=4» en rojo, en la misma NT que elimina D208d (1322) y D210a (1…
- ISS-0010 (ambiguity, bloqueante, resolved): 'NT 23 §2.1 dice «se modifica la siguiente validación» y reproduce D210 (1314) con mensaje y observación idénticos a los del MT V150: el literal no muestra ningún cambio. El único cambio visible en el PDF es el resaltado rojo de «y el tipo de operación es diferente a B2F (D202≠4)». Si el rojo marca…
- ISS-0011 (ambiguity, open): 'En la fila D208c (1321) de NT 21 y de NT 24 están resaltados en rojo «Si el Tipo de transacción es distinto a Muestras médicas (D011≠13),», «o igual» y el «=» de los dos «>=», y en amarillo la «E» de «El Tipo» (en el MT V150 es «el», en minúscula) y los montos. La curación inicial tomó todo el tex…
- ISS-0012 (source_conflict, resolved): 'Obligación legal frente a regla técnica. El Decreto 872/2023, art. 6, numeral 2 (leído en su literal) obliga a identificar al cliente en operaciones B2C «cuando la operación supere» 35.000.000 desde el 1° de enero de 2024 y 7.000.000 desde el 1° de enero de 2025, sin excepción por tipo de transacc…
- ISS-0013 (source_conflict, open): 'La instantánea XSD del 2026-10-17 (XSD_DIR rev cdd1f03f1d29, DE_Types_v150.xsd, tipo tiTiDE del elemento iTiDE) restringe C002 con el patrón «1|[4-7]|9|10», mientras el MT V150 enumera 1 a 8 (2, 3 y 8 marcados «(Futuro)») y ninguna NT del corpus agrega los valores 9 y 10 ni modifica C002. El XSD n…
- ISS-0014 (ambiguity, open): 'NT 23 §2.1 encabeza con «se modifica la siguiente validación» tres filas que no existen en el MT V150 ni en ninguna NT anterior y que están enteras en verde (agregado según la leyenda del MT): D208f (1333), D210b (1334) y D208g (1335). El color coincide con la acción curada (`add`) pero no con el …

## Cambios al pasado
- [INFO] kb: la base main (d2eef71d1974) no tiene kb/ ni golden: no hay pasado que comparar

## Bitácora de curación (corridas LLM)
- [INFO] curation/runs/6767ad7f-b35b-4bcd-a3a7-d670f1b45845.yaml: 3 outputs registrados retroactivamente (backfill): docs/HANDOFF.md (Sesión en arnés Pi: docs/HANDOFF.md fue editado mediante herramientas MCP (mcp__custom-tools__edit y mcp__custom-tools__bash), que no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); docs/traspaso-curacion-piloto.md (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0012.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18)
- [INFO] curation/runs/6b58d45f-98a7-4353-8d45-d1b664f31286.yaml: 1 output registrado retroactivamente (backfill): tests/golden/temporal.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18)
- [INFO] curation/runs/ce4ca541-bb4f-49d4-8e9f-5430b10e6d63.yaml: 15 outputs registrados retroactivamente (backfill): kb/fields/DE/D208.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/validations/DE/D208c.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/validations/DE/D210.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_002.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_008.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_021.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_023.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/documents/NT_024.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0003.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0005.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0009.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0010.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0011.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/issues/ISS-0014.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18); kb/validations/DE/D208g.yaml (Sesión en arnés Pi: las ediciones con herramientas MCP (mcp__custom-tools__edit/write) no dispararon el hook PostToolUse; registro retrospectivo del 2026-10-18)

## Pendientes
(ninguno)

Resultado de `sifen check`: 0 error(es), 0 aviso(s).
```

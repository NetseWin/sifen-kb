# Traspaso: curación del piloto receptor/identidad (§5 paso 4 de docs/HANDOFF.md)

Estado al 2026-10-17. Es el detalle del paso 4 de `docs/HANDOFF.md` (que remite aquí desde «Retomar aquí»): estado de la curación, las decisiones del usuario sobre ella y los pasos siguientes, en orden. Lo escribió la sesión de curación; el informe para la revisión humana del PR está en `docs/informe-revision-piloto.md`.

## 1. Dónde estamos

- Rama `kb/piloto-receptor` (no `main`). **Nada commiteado** de la curación: `kb/documents/`, `kb/fields/`, `kb/validations/`, `kb/issues/` y `tests/golden/temporal.yaml` están sin seguimiento; `curation/runs/a067d55b-d757-498d-a601-f946db1a3acc.yaml` está modificado (bitácora de hooks de esta sesión: no editar a mano).
- Verificación al cierre: `uv run sifen fmt` OK · `uv run sifen check` 0 errores · `uv run pytest -q tests/unit tests/test_golden_temporal.py tests/extraction/test_golden_piloto.py` → 1157 passed, 1 skipped (skip previsto en `test_explain.py:845`). Suite completa: 1049 + 705 passed.
- Informe para la revisión humana (detalle por entidad, fechas, Issues, discrepancias, checklist, salida de `sifen check --report`): `docs/informe-revision-piloto.md` (su texto va en la descripción del PR de conocimiento). Ojo: describe el estado de la KB; la sección 0 resume qué cambió tras las decisiones del usuario.

## 2. Qué contiene la KB

- 32 fichas en `kb/documents/` (fechas copiadas por `sifen draft`). `curation_scope: pilot`: MT_V150, NT 1, 2, 8, 10, 21, 23, 24. El resto `dates_only` (incluidas NT 3, 6, 7, 12, 14, 20, 26, 27, que solo tienen efectos `not_modeled` de menciones).
- 10 campos (C002, D011, D015, D201, D202, D208, D209, D210, F014, F023) y 12 validaciones (D208, D208a–g, D209a, D210, D210a, D210b) con versión base del MT (`sifen draft <clave> --baseline raw:MT_V150@976cd88c05c3:p<N>:<ID>`), versiones por NT y lápidas (D208d y D210a por NT 2; D208b por NT 10).
- Issues ISS-0001…ISS-0013 (`kb/issues/`). Bloqueantes hoy: ISS-0003 (D208/1310 desde NT 23) e ISS-0010 (D210/1314 desde NT 23, transitorio, ver §4).
- `tests/golden/temporal.yaml`: 88 filas reales (G.5 1–6, 15–17, 20; K.5 corregido por la evidencia; fronteras día anterior/día del cambio por ambiente; oráculo «watermark»; `1400` → `not_curated`).

## 3. Decisiones del usuario (2026-10-17) — no reabrir sin preguntarle

1. **D208b / NT 10**: NT 10 elimina D208b (lápida NT_010#6, inicio aproximado). ISS-0002 (D208f ≈ D208b) **no bloqueante**; D208f es entidad independiente; no fusionar historiales. ISS-0008 resuelto. **Aplicado.**
2. **Color en las NT**: rojo = contenido eliminado, verde = agregado, amarillo = modificado, aplicado junto con el verbo del encabezado y el contexto; si las señales se contradicen o no permiten reconstruir el contenido efectivo, Issue bloqueante. Separar `rendered_literal` (celda completa visible, con su marcado) de `effective_literal` (derivado de forma determinista aplicando el marcado). Es semántica de diseño: **no** va en `extraction/fixes.yaml` (reservado a defectos técnicos de extracción). **Pendiente: requiere cambio de código (ver §4).**
3. **D208c / NT 21 y NT 24**: el rojo también es eliminación. Regla efectiva: NT 21 «mayor a 35.000.000», NT 24 «mayor a 7.000.000», sin la excepción D011≠13. ISS-0011 e ISS-0012 no bloqueantes (trazabilidad). No dejar D208c `undetermined`; la consulta a DNIT puede seguir en paralelo y una respuesta oficial contraria se registra con trazabilidad. **Pendiente del mismo cambio de código.**
4. **ISS-0010 / 1314**: deja de ser bloqueante cuando se reconstruya el `effective_literal` de NT_023#4 (sin la excepción B2F); puede resolverse. **Hoy sigue bloqueante a propósito**, como estado transitorio, porque la versión materializada todavía muestra la celda completa.
5. **curation_scope**: `dates_only` para NT cuyo único contenido curado son menciones `not_modeled` fuera del piloto; `pilot` solo si se curaron cambios reales a entidades del piloto. **Aplicado.**
6. **«Efectos completos»** = completos respecto del alcance: efectos sobre entidades del piloto + menciones externas necesarias para cobertura, desambiguación o dependencia. No registrar exhaustivamente cambios ajenos (E711, H018…). **Aplicado (no hay que hacer nada).**
7. **Marca de agua de NT 21**: solo oráculo golden «watermark» (fin derivado de NT_021#1 = 2025-01-01); no `superseded_by`, no crear `VisualRef`. **Aplicado.**
8. **C002 / ISS-0013**: `source_conflict` no bloqueante. Mantener separadas la semántica documental (MT/NT: 1–8) y la aceptación estructural del XSD (instantánea por hash: 1, 4–7, 9, 10); no consolidar, no inventar etiquetas para 9 y 10. **Datos aplicados; la salida de `explain` todavía no muestra ambas dimensiones (pendiente de código, ver §4).**

## 4. Próximos pasos (en orden)

### Paso A — Código (PR de código, no de conocimiento; lo puede hacer y mergear Claude según docs/HANDOFF.md §2)

1. **`effective_literal` en `src/sifen_kb/rawio.py`**: hoy `RawRow.literal(attr)` devuelve `current(attr)` (sin lo tachado/rojo) solo para el MT (`COLOR_LEGEND_DOC`) y la celda completa para las NT. Implementar:
   - `rendered_literal(attr)` = `cells[attr]` (todo lo visible) y `effective_literal(attr)` = aplicar el marcado de `marks` (quitar los tramos `deleted`, conservar `added`/`modified`), para el MT y para las NT.
   - Detección de contradicciones (para exigir Issue bloqueante, no para decidir): p. ej. fila con tramos `deleted` cuyo efecto es `add`; efecto `modify` cuyo `effective_literal` es igual al de la predecesora; fila entera en rojo con un efecto que no es `remove`; resultado vacío.
2. **`src/sifen_kb/draft.py`**: copiar `effective_literal` (decisión 8 del docstring hoy dice lo contrario); avisar con los tramos quitados.
3. **`src/sifen_kb/integrity.py`** (`literales`): comparar contra `effective_literal`; nueva comprobación de contradicciones del punto 1 (exige Issue bloqueante que cubra la entidad).
4. **Tests**: `tests/unit/test_rawio_literal.py` (hoy afirma que en una NT se copia la celda completa) y `tests/unit/test_draft.py`, más los nuevos de contradicción. No relajar tests: cambiarlos porque cambió la regla, con la decisión citada.
5. **Docs**: `docs/arquitectura.md` §I.4 y §F.2 (literal), `docs/curacion.md` y `curation/prompts/curar_entidad.md` (regla 9 y «El literal que se copia es RawRow.literal…»), `docs/investigacion/sifen.md` §5 (hoy dice que en NT 21/24 el rojo es vigente). Ojo: `curar_entidad.md` lo hashean los hooks al iniciar sesión; cambiarlo entre sesiones, no durante una curación.
6. **(Decisión 8)** `explain`/`xsd.py`: mostrar para campos con enumeración «documentado por MT/NT» frente a «aceptado por la instantánea XSD» y `status: mismatch` con su Issue (hoy `XsdCheck` solo compara ocurrencia y da `match` para C002).
7. Defectos menores detectados: `sifen draft --dry-run` imprime «escrito» sin escribir; `sifen explain NT_0xx` muestra el PageRef de la fecha como dict de Python; `test_golden_real_completeness` no exige filas en ventanas de Issues bloqueantes; `cut_kb` conserva Issues posteriores al corte.

### Paso B — Re-materializar la KB con el nuevo literal (sesión de curación, rama `kb/piloto-receptor`)

Con el código del paso A en la rama base:

1. `uv run sifen check` mostrará las versiones cuyo literal ya no coincide. Re-materializar con la herramienta (nunca a mano). Como `draft NT_0xx#n` es idempotente si la versión ya existe, puede hacer falta regenerar la entidad (borrar el archivo de la entidad y repetir `--baseline` + `draft` de cada efecto en orden cronológico; no hay `main` con `kb/`, así que no hay «pasado» que justificar todavía). Afectadas:
   - field:DE:D208 y field:DE:D210 @NT_002#1/#2 (sin «No informar si D201 = 1 o D202=4») y @NT_023#1/#2 (sin «y D202 ≠ 4»; queda «Obligatorio si D201 = 2 No informar si D201 = 1 …»).
   - field:DE:F023 @NT_008#1 (sin «Cuando C002=4 corresponde a F014»).
   - val:DE:D210 @NT_023#4 (sin «y el tipo de operación es diferente a B2F (D202≠4)»): condición `D201 == 2 and not exists(D210)`.
   - val:DE:D208c @NT_021#1 y @NT_024#1 (sin la cláusula D011≠13, sin «o igual», «>» en lugar de «>=»): condición `exists(D208) and D208 == 5 and ((exists(F023) and F023 > U) or (exists(F014) and F014 > U))` con U = 35000000 / 7000000; revisar `gaps` (ISS-0005 sigue; la polaridad mixta del paréntesis «(D208≠5)» desaparece si ese tramo también se elimina: verificar qué queda).
   - Lápidas (D208b, D208d, D210a) y altas en verde (D208e, D208f, D208g, D210b): no deberían cambiar; confirmarlo.
2. Interpretación: reformular `condition` donde cambió la observación; quitar o actualizar `open_questions` de D208/D210 (campos) y de D210 @NT_023#4; enumeraciones de D208 no cambian (revisar `enumeration_interpretation`).
3. Issues: resolver ISS-0010 (y quitar su bloqueo); revisar ISS-0009 (pasa a trazabilidad o se resuelve); ISS-0011 queda no bloqueante de trazabilidad; ISS-0012: con «mayor a» la divergencia con el Decreto («supere») desaparece en el umbral y en la excepción D011: revisar si se resuelve (pregunta para el usuario); ISS-0003 sigue (D208g ≈ D208).
4. Golden: actualizar las filas de D210 (1314) desde NT 23 (de `undetermined` a `in_force`), agregar filas que fijen el nuevo literal/condición de D208c si el formato lo permite, y volver a correr la completitud.
5. Verificar: `uv run sifen fmt && uv run sifen check && uv run pytest -q tests/unit tests/test_golden_temporal.py tests/extraction/test_golden_piloto.py`, y `explain 1321 --at 2025-01-10`, `explain D208 --at 2024-09-15 --env test|prod`, `explain 1322 --at 2025-03-01`, `explain D208b --at 2024-09-27` (debe dar `removed`), `explain 1314 --at 2024-10-01`, `sifen status`.
6. Actualizar el informe de revisión y abrir el PR de conocimiento (lo revisa y mergea el usuario con `Reviewed-by:`; Claude no hace push ni merge).

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
- Para renderizar una página del PDF y mirarla: `uv run python <script> sources/<Doc>/<sha12>.pdf <página> salida.png` con pypdfium2 (`pdf[p-1].render(scale=1.5).to_pil().save(...)`), y abrir el PNG con Read.
- Los hooks solo registran Edit/Write en `curation/runs/`; los archivos que reescriben `sifen draft`/`sifen fmt` quedan con sha256 viejo en `outputs` (no se compara). Todo archivo con `by: llm` debe haberse editado al menos una vez con Edit/Write en la sesión.

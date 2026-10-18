# Evaluación del MVP — plantillas para el usuario

Tres ítems de la Definition of Done (`docs/arquitectura.md` §T) **no los puede cumplir Claude**: dependen de
quien usa la KB. Este documento trae una plantilla para cada uno.

| Ítem | Qué decides o haces tú | Cuándo |
|---|---|---|
| T.8 Evaluación ciega | Escribir 15 preguntas y su clave de respuestas **antes** de ver salidas de `sifen explain` | Antes de mergear el PR de conocimiento |
| T.11 Costo de curación | Fijar el tiempo máximo aceptable de curación por NT | El diseño lo pedía antes de curar (Fase 0); **no se hizo a tiempo**: fijarlo ahora, antes de decidir si se escala más allá del piloto (ver la nota de T.11) |
| T.12 Valor | Cronometrar tres rechazos del dominio piloto, con la KB y con el flujo manual | Después del merge |

---

## T.8 — Evaluación ciega

**Regla de oro:** la clave de respuestas se guarda **fuera del repositorio** (por ejemplo en
`C:\sifen-privado\evaluacion\clave.md` o en una nota personal) hasta que termine la evaluación. Si está en el
repo, la sesión de Claude que responde podría leerla y la evaluación deja de ser ciega.

### Procedimiento

1. Copia la tabla de abajo a un archivo **fuera del repo** y complétala sin ejecutar `sifen explain`.
   Puedes usar los PDF de `sources/` y tu experiencia; no uses salidas de la KB.
2. Diez preguntas normales de troubleshooting del dominio receptor/identidad (D208, D208a–g, D209a, D210,
   D210a, D210b; códigos 1310–1335) y **cinco trampas**, una de cada tipo:
   - un código **fuera del piloto** → se espera `not_curated`;
   - **D208b después de NT 23** (desde 2024-09-27 en producción) → `removed` (`introduced_by: NT_010#6`), con
     ISS-0002 como Issue no bloqueante/aviso;
   - una fecha **anterior a la cobertura** (antes de 2023-06-17) → `outside_coverage`;
   - un XML con **emisión y procesamiento a ambos lados de un cambio** (p. ej. emitido el 2024-12-30 y
     procesado el 2025-01-02) → `undetermined` (`axis_split`);
   - **D208d en 2025** → `removed`, con aviso de inicio aproximado.
3. Se abre una sesión **limpia** de Claude Code en el repo. Le pasas solo la pregunta; responde usando la CLI.
4. Comparas con tu clave. Una respuesta es correcta si coinciden **estado, `introduced_by`, documento y
   página**, y además transmite los avisos esperados.
5. Umbral: **≥ 14/15**, **cero** reglas históricas presentadas como vigentes y **cero** `in_force` donde
   correspondía otro estado. Se guarda la transcripción.

### Plantilla de la clave (fuera del repo)

| # | Pregunta (tal como se la harás a Claude) | ¿Trampa? | Estado esperado | `introduced_by` | Documento y página (impresa/PDF) | Avisos esperados |
|---|---|---|---|---|---|---|
| 1 |  | no |  |  |  |  |
| 2 |  | no |  |  |  |  |
| 3 |  | no |  |  |  |  |
| 4 |  | no |  |  |  |  |
| 5 |  | no |  |  |  |  |
| 6 |  | no |  |  |  |  |
| 7 |  | no |  |  |  |  |
| 8 |  | no |  |  |  |  |
| 9 |  | no |  |  |  |  |
| 10 |  | no |  |  |  |  |
| 11 |  | sí: fuera del piloto | `not_curated` | — |  | «vigencia no resuelta…» |
| 12 |  | sí: D208b tras NT 23 | `removed` | `NT_010#6` |  | ISS-0002 como Issue no bloqueante/aviso |
| 13 |  | sí: antes de la cobertura | `outside_coverage` |  |  | muestra la mejor versión solo como referencia |
| 14 |  | sí: emisión ≠ procesamiento | `undetermined` (`axis_split`) |  |  | «SIFEN informa el primer error…» |
| 15 |  | sí: D208d en 2025 | `removed` |  |  | inicio aproximado |

### Registro del resultado (este sí puede ir al repo después de la evaluación)

| # | Correcta (sí/no) | Qué falló |
|---|---|---|
| 1–15 |  |  |

Total: __/15 · Reglas históricas presentadas como vigentes: __ · `in_force` indebidos: __ · Transcripción: ____

---

## T.11 — Umbral de costo de curación por NT

La arquitectura (§U, regla de recorte) pide fijar **antes de curar** cuánto tiempo de revisión humana por NT
es aceptable. Si al cerrar la Fase 1 el costo real lo supera, la KB **no escala** al DE completo: se congela como
índice de menciones + calendarios + entidades curadas por demanda.

> **Nota de trazabilidad (2026-10-18).** El umbral **no se fijó antes de curar el piloto**, como pedía el diseño:
> el piloto receptor/identidad ya está curado y este campo sigue vacío. No se reconstruye retroactivamente como
> si se hubiera decidido antes. Queda como decisión **pendiente del usuario**, que debe tomarse **ahora**, antes
> de decidir si la KB escala más allá del piloto. El costo real del piloto se puede medir y comparar con ese
> umbral, pero el umbral elegido ahora es una decisión **posterior** al piloto y así debe constar cuando se
> registre.

- Umbral elegido: **____ minutos de revisión humana por NT** (sugerencia para empezar: 30–60 min para una NT
  de 1–5 páginas).
- Qué se mide: tiempo tuyo revisando el PR de cada NT del piloto (fechas contra el PDF, alcance declarado,
  Issues, cambios al pasado). No cuenta el tiempo de Claude.

| NT | Minutos de revisión | Observaciones |
|---|---|---|
| NT_002 |  |  |
| NT_010 |  |  |
| NT_021 |  |  |
| NT_023 |  |  |
| NT_024 |  |  |

---

## T.12 — Cronometraje de tres rechazos

Tres rechazos reales del dominio piloto (o reproducidos en el ambiente de **test** si no hay reales),
resueltos dos veces: con el flujo manual actual y con la KB. La KB debe ser más rápida en los tres.
**No pegues XML reales en el repo ni en la conversación**: guárdalos en la carpeta privada (ver `SECURITY.md`).

| # | Código | Fecha de procesamiento | Ambiente | Minutos con flujo manual | Minutos con la KB | ¿Diagnóstico coincide? |
|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |
| 3 |  |  |  |  |  |  |

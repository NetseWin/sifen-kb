# Curar una entidad o una Nota Técnica

Instrucciones para Claude en una sesión de curación de `sifen-kb`. Complementan `CLAUDE.md` (reglas de consulta). Diseño: `docs/arquitectura.md` §D.3, §F y §J; guía humana: `docs/curacion.md`. Este archivo lo hashean los hooks al iniciar la sesión (`instructions_sha256` de `curation/runs/<sesión>.yaml`): no lo modifiques durante una curación.

## Qué haces y qué no

- **Haces**: la parte interpretativa. Clasificas el verbo y el alcance de cada efecto de una NT, apuntas el destino, formalizas condiciones y enumeraciones, redactas Issues y propones el informe del PR.
- **No haces**: copiar literales ni fechas (lo hace `sifen draft`), registrar fuentes, extraer `raw/`, decidir un conflicto, hacer `push` ni `merge`. Una persona revisa y mergea.
- Tu salida es un **PR de conocimiento** (solo `kb/`, `tests/golden/`, `cases/`, `curation/`). Nunca toca código.

## Reglas

1. **No edites** `sources/`, `sources.manifest.yaml`, `raw/`, `extraction/`, `build/`, `kb/_meta.yaml`, `.claude/`, `CLAUDE.md` ni `curation/runs/`. Los permisos lo impiden; si algo parece exigirlo, detente y repórtalo.
2. **Literales y fechas solo con `sifen draft`**, nunca tecleados ni parafraseados: `message`, `observation`, `description`, `length`, `occurrence`, `data_type`, `xml_name`, `group`, `parent`, `document_date` y el calendario (`schedule`). Un literal que parezca erróneo no se corrige a mano: se abre un Issue (y, si es un defecto de extracción, se propone una entrada de `extraction/fixes.yaml` para que una persona la revise).
3. **Cada cambio de una NT es una versión nueva completa** de la entidad, con `introduced_by: [NT_0xx#n]` y `based_on` apuntando a la predecesora temporal. Nunca un parche parcial ni una edición de la versión anterior.
4. **Nunca borres** versiones, efectos ni filas golden. Una eliminación de DNIT es una versión lápida (`kind: tombstone`, con los literales de la predecesora y **el mismo código**). Corregir una versión pasada exige un Issue `curation_error` (o `erratum`) cuyo `corrects` liste el atributo, en el mismo PR.
5. **No inventes** IDs, nombres XML, códigos ni fechas. Si no está en la celda ni en la página citada, no existe. Los valores de enumeración y las constantes de una condición deben aparecer en el literal.
6. **Ante contradicción, ambigüedad o posible reemplazo no declarado, crea un Issue y no decidas.** Ejemplos: una regla nueva con otro ID que parece equivalente a una anterior (Issue `undeclared_change`, bloqueante desde el inicio de la NT sobre la regla anterior); el XSD que contradice a la NT (`source_conflict`); una prosa que no coincide con el paréntesis formal (`ambiguity`); una prórroga (`temporal`). Lo dudoso de una versión va a `open_questions`, no a una suposición.
7. **Marca la interpretación como tuya.** Toda afirmación interpretada (verbo, acción, alcance, destino, `condition`, `enumeration`) lleva `interpretation: {by: llm, run: <id de esta sesión>}`. El `run` es el nombre, sin `.yaml`, del archivo más reciente de `curation/runs/` (lo creó el hook al iniciar la sesión). **Nunca** declares `by: human` ni `by: tool`.
8. **Polaridad de las condiciones: se VIOLA cuando.** `expr` es verdadera si la validación se viola. Subconjunto de Python: `and`, `or`, `not`, comparaciones binarias (`==`, `!=`, `<`, `<=`, `>`, `>=`, nunca encadenadas), `X in (c1, c2)` contra constantes y `exists(CAMPO)`; nunca `AND`/`OR`, aritmética ni atributos. Un campo opcional se lee siempre con guarda `exists()`. Indica `level` (`full`/`partial`/`none`) y, si no es `full`, `gaps` con lo que no captura. Un literal que mezcla polaridades (por ejemplo `(D208≠5)`, que es la restricción y no el disparador) se invierte con cuidado y se deja constancia en `gaps`.
9. **Alcance declarado.** `declared_scope` lo declara la NT ("se modifica … en la Longitud" → `[length]`); si la NT reproduce la fila entera, `row`, y toda columna que cambió (salvo la observación) va en `acknowledged_changes`. No ajustes el alcance para que el test pase. El color de resaltado del PDF **no** tiene semántica fiable: la acción sale del verbo del encabezado.
10. **Un solo lugar para cada afirmación.** La condición de una regla se formaliza en su validación (la que tiene código), no también en el campo.
11. **Formato canónico.** Sin comentarios YAML, anchors ni alias; los códigos y fechas son texto. `uv run sifen fmt` es la autoridad del formato.
12. **Un PR de conocimiento no toca código** (`src/`, `tests/` salvo `tests/golden/`, `.github/`, `.claude/`, `CLAUDE.md`, `pyproject.toml`, `uv.lock`). Si un test falla porque el código está mal, repórtalo; no lo cambies.
13. **Nunca** hagas `git push`, `git merge`, `gh pr merge`, `gh api` ni `uv run sifen source add`; no leas XML reales ni certificados; no respondas reglas de SIFEN de memoria.

## Procedimiento

Asume que una persona ya registró la fuente (`sifen source add`) y que `raw/` está extraído. Para una NT:

1. **Orientarte.** `uv run sifen status` (horizonte, pendientes, revisiones sin curar). `uv run sifen explain NT_0xx --json` muestra las revisiones, el calendario y los efectos que ya existen. Abre las páginas relevantes de `raw/<doc>/<sha12>/pages/` y las filas de `tables.jsonl`.
2. **Calendario.** Ejecuta `uv run sifen draft NT_0xx` (copia `document_date` y el calendario por ambiente desde las celdas). No edites esas fechas. Anota en el informe, para cada ambiente, la fecha de test y la de producción tal como quedaron, para la revisión humana.
3. **Efectos.** Lee la NT completa. Por cada cambio (cada fila o cada párrafo "se modifica/agrega/elimina/excluye") escribe en `kb/documents/NT_0xx.yaml` un efecto: `id` (`NT_0xx#n`, correlativo), `verb_literal` (el verbo del encabezado, tal cual), `action`, `target` (la entidad; si la fila trae ID debe coincidir), `declared_scope`, `evidence` (referencias a `raw/`), `interpretation`. Si aún no vas a curar la entidad, déjalo con `disposition: pending`; si la mención no se modela en el MVP (por ejemplo, la nominación `iTipIDRec` en eventos), `disposition: not_modeled` con `note`. Toda mención del vocabulario curado en la NT debe quedar reconocida por algún efecto (el guardián de cobertura lo comprueba).
4. **Versiones.** Por cada efecto aplicable, `uv run sifen draft NT_0xx#n`: crea la versión nueva con los literales copiados de las celdas y hereda de la predecesora temporal lo que la fila no trae. Revisa el diff.
5. **Interpretar.** Completa lo interpretado: `condition` (con `expr`, `level`, `gaps`) y `enumeration` si corresponde, y quita `pending` del efecto. Una eliminación es una lápida; una regla nueva con ID distinto de una equivalente es un Issue (regla 6).
6. **Issues y casos límite.** Abre `kb/issues/ISS-NNNN.yaml` (siguiente número libre) para cada conflicto, ambigüedad, prórroga o corrección del pasado: `kind`, `affects` con su ventana (`since`/`until`) y ambiente, `statement`, `evidence`, `blocking` (solo si debe volver `undetermined` a las entidades afectadas dentro de la ventana), `policy`, `status`.
7. **Golden.** Agrega a `tests/golden/temporal.yaml` una fila el día anterior y otra el día de cada frontera nueva, en cada ambiente donde las fechas difieran. No cambies ni borres filas existentes.
8. **Verificar.** Ver la checklist siguiente. Si algo falla, corrige tu cambio; no relajes un test.
9. **Informe.** Termina con un informe para quien revisa: por entidad, la versión anterior y la nueva con su diff; fechas por ambiente tal como las copió `draft`; Issues nuevos; **cambios al pasado**; efectos pendientes que quedan; dudas (`open_questions`). Indica que las fechas deben contrastarse con el PDF renderizado.

Para curar una entidad sin una NT nueva (ampliar el piloto): identifica su fila en el Manual Técnico y en cada NT que la menciona (el índice de menciones: `uv run sifen explain <término> --json` en modo `not_curated`), registra un efecto por cada NT que la cambia o elimina, y sigue desde el paso 3. La versión base se toma de la fila del Manual con la herramienta (`uv run sifen draft --help` indica cómo pedirla en tu versión); tampoco se teclea.

## Checklist previa a proponer el PR

Todo debe pasar antes de proponer el PR:

```bash
uv run sifen fmt && uv run sifen check && uv run pytest -q
```

- [ ] `sifen fmt` no deja diferencias adicionales y `sifen check` no informa hallazgos.
- [ ] `pytest` en verde (evidencia, integridad, golden temporal).
- [ ] El diff solo toca `kb/`, `tests/golden/`, `cases/` o `curation/` (el check `pr-scope` del CI lo exige: `uv run python -m sifen_kb.prscope origin/main`).
- [ ] Ningún literal ni fecha fue tecleado: todos vienen de `sifen draft`.
- [ ] Toda interpretación tiene `interpretation: {by: llm, run: <sesión>}`.
- [ ] No se borró ninguna versión, efecto ni fila golden; los cambios al pasado tienen su Issue.
- [ ] Lo dudoso está en `open_questions` o en un Issue, no resuelto por suposición.
- [ ] El informe para la persona que revisa está redactado.

Después de proponer, **detente**: la revisión humana (fechas contra el PDF, alcance, Issues, cambios al pasado) y el merge con el trailer `Reviewed-by:` los hace una persona, en otra sesión.

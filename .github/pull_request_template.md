<!--
Un PR es de CONOCIMIENTO o de CÓDIGO, nunca de ambos (el check `pr-scope` lo exige).
Conocimiento: kb/, tests/golden/, cases/, curation/. Código: todo lo demás con efecto sobre el comportamiento
(src/, el resto de tests/, .github/, .claude/, CLAUDE.md, pyproject.toml, uv.lock).
Excepción: si cambias el extractor y vuelves a copiar literales en kb/, pon la etiqueta `extractor-recopy` en el título.
NO subas XML reales, certificados, claves ni datos personales (ver SECURITY.md).
-->

## Tipo de PR

- [ ] **Conocimiento** (kb/, tests/golden/, cases/, curation/)
- [ ] **Código** (src/, tests/, CI, configuración)
- [ ] Solo documentación o fuentes (docs/, README, sources/, raw/)

## Qué cambia y por qué

<!-- Una o dos frases. Para una NT: número, revisión (sha12) y qué entidades toca. -->

## Verificación local

- [ ] `uv run sifen fmt && uv run sifen check && uv run pytest -q`
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run python -m sifen_kb.prscope origin/main` (alcance del PR)
- [ ] Si toqué `raw/` o el extractor: `uv run sifen extract --check`

## Checklist de revisión de conocimiento

Solo para PR de conocimiento. Lo completa **la persona que revisa**, en una sesión distinta y posterior a la curación.

- [ ] **Fechas contra el PDF renderizado**: la fecha de test y la de producción de cada documento coinciden con la tabla del PDF de `sources/` (columna y ambiente correctos; sin erratas de año).
- [ ] **Alcance declarado**: `declared_scope` de cada efecto coincide con lo que dice la NT; con alcance `row`, todo cambio distinto de la observación figura en `acknowledged_changes` (severidad, código y mensaje incluidos).
- [ ] **Destino y acción** de cada efecto correctos (fila = entidad; las eliminaciones son lápidas que conservan el código).
- [ ] **Issues**: los conflictos, reemplazos no declarados, ambigüedades y prórrogas tienen su Issue, con ventana y `blocking` justificados; lo dudoso está en `open_questions`.
- [ ] **Interpretación**: las condiciones indican `level` y `gaps`; la polaridad es "se viola cuando"; las constantes están en el literal.
- [ ] **Cambios al pasado**: el informe los enumera aparte y cada uno tiene su Issue `curation_error`, `erratum` o `temporal`; no se borró ninguna versión, efecto ni fila golden.
- [ ] **Golden**: cada frontera temporal nueva tiene una fila el día anterior y otra el día del cambio, en cada ambiente donde las fechas difieran.
- [ ] Los literales y las fechas vienen de `sifen draft` (no se teclearon) y no se editaron `sources/`, `raw/` ni `kb/_meta.yaml` a mano.
- [ ] Sin datos sensibles (RUC, cédulas, CDC reales, XML) en casos ni en Issues.

### Informe de curación

<!-- Pega aquí el informe: por entidad, versión anterior y nueva con su diff; fechas por ambiente; Issues nuevos;
     cambios al pasado; pendientes que quedan. Si la sesión fue con Claude Code, indica el archivo de curation/runs/. -->

## Checklist de código

Solo para PR de código.

- [ ] Hay pruebas nuevas o actualizadas para el cambio.
- [ ] No cambia lo que la KB responde (no toca `kb/`), salvo la excepción `extractor-recopy`.
- [ ] Sin dependencias nuevas, o están justificadas en un Issue y `uv.lock` está actualizado.
- [ ] La escritura de archivos usa `encoding="utf-8", newline="\n"`.

## Merge

Un merge de conocimiento a `main` lleva en el mensaje del commit el trailer de quien revisó:

```text
Reviewed-by: Nombre Apellido <correo@ejemplo.com>
```

Sin ese trailer, el workflow `release` no crea el tag `kb-AAAA.MM.DD`.

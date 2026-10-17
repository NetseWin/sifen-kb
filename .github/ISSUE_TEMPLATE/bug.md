---
name: Error o regla incorrecta
about: Un error del código, o una regla, fecha o cita de la KB que no coincide con el documento oficial de DNIT
title: "[bug] "
labels: bug
---

<!--
No pegues XML reales, RUC, cédulas, CDC reales, certificados ni claves. Si el caso viene de un rechazo real,
descríbelo con valores sintéticos. Para una vulnerabilidad usa el aviso privado de seguridad (ver SECURITY.md).
-->

## Tipo

- [ ] Error del código o de la CLI
- [ ] Una respuesta de la KB no coincide con el documento oficial (regla, fecha, ambiente, cita)
- [ ] Un literal no es igual a la celda del PDF (posible error de extracción)
- [ ] Otro:

## Qué esperabas y qué obtuviste

## Cómo reproducirlo

Comando exacto y su salida (con `--json` si aplica):

```text
uv run sifen explain <término> --at AAAA-MM-DD --env prod
```

## Evidencia oficial

Documento (por ejemplo `NT_024` o `MT_V150`), revisión (sha12 que muestra `explain`), página impresa y PDF, y el texto o la fecha que, según el PDF, es la correcta. Si no puedes citarlo, descríbelo igualmente.

## Entorno

- Commit o tag de la KB (`git describe --tags --always`):
- Salida de `uv run sifen status` (horizonte de fuentes, pendientes):
- Sistema operativo (Linux, macOS, Windows/WSL2):

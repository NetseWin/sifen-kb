# SIFEN KB — reglas para Claude

Base de conocimiento de SIFEN (Paraguay): qué regla rige en cada fecha y ambiente, con evidencia de los documentos oficiales de DNIT. Diseño en `docs/arquitectura.md`; uso de la CLI en `docs/uso.md`.

1. Ante cualquier código, validación, campo, `xml_name` o documento (`NT_0xx`) de SIFEN, ejecuta primero
   `uv run sifen explain <término> --json [--at AAAA-MM-DD] [--env prod|test]`. No respondas reglas SIFEN de memoria.
2. Para un rechazo con XML usa `--xml RUTA` y pide la respuesta de SIFEN (`--response RUTA`) o su fecha de
   procesamiento (`--processed-at`). Nunca abras un XML real con Read, cat, grep ni otra herramienta.
3. Empieza por `state` y `reasons`. Si no es `in_force`, dilo antes que nada. Si es `not_curated`, di que la
   vigencia no está resuelta y muestra las menciones sin inferir la regla.
4. Cita el documento oficial (documento, revisión sha12, página impresa y PDF). La autoridad es DNIT, nunca "la KB".
5. Transmite `warnings`, `pending_effects`, `open_issues` y la fecha del horizonte de fuentes tal cual.
6. Nunca presentes una versión no vigente como vigente. El número de NT no ordena el tiempo.
7. Nunca leas ni pidas certificados (.p12/.pfx/.key/.pem), contraseñas ni el CSC de producción.
8. Para curar, lee primero `curation/prompts/curar_entidad.md`. No hagas push, merge ni `uv run sifen source add`.

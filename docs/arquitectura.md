# SIFEN KB — Análisis crítico y arquitectura definitiva

Antes de opinar contrasté el pedido con lo que DNIT publica hoy (2026-10-17): el portal e-Kuatia (documentación técnica, tablas y codificaciones, FAQ), el Manual Técnico v150 (217 páginas), **las 27 Notas Técnicas (NT 001–027), leídas una por una**, el directorio de 47 XSD en `ekuatia.set.gov.py/sifen/xsd/` y las guías de 2024 y 2026. También verifiqué licencias y versiones de las herramientas en PyPI y en sus repositorios, y probé en este Windows cómo se comporta PyYAML y si FTS5 está disponible. Conclusión de entrada: **el ejemplo del pedido es real** (D208c, código 1321: umbral de 60.000.000 en el MT, 35.000.000 en NT 21 y 7.000.000 en NT 24), pero varios supuestos estructurales no lo son: DNIT vuelve a subir NT y XSD in situ, los IDs y los códigos no son únicos, la severidad cambia, test y producción tienen fechas distintas y algunas NT rigen el mismo día en que se suben. Esta versión sintetiza dos propuestas independientes —una orientada a MVP y otra a rigor regulatorio—, decide explícitamente dónde divergían (C.3) e incorpora tres revisiones adversariales (temporalidad, pragmatismo y completitud/IA/seguridad). Al final hay un registro de lo verificado y de lo pendiente.

Convención: **[V]** verificado en fuente oficial de DNIT · **[P]** probable (fuente secundaria o inferencia fuerte; nunca se usa como hecho) · **[VERIFICAR-DNIT]** debe confirmarse antes de fijarlo en la KB · **[HIP]** dato hipotético, solo para tests · **[verificar]** detalle de una herramienta externa (sintaxis, plan, API) a confirmar en la versión instalada.

---

## A. Veredicto general

**Parcialmente correcta.** La dirección y el diagnóstico central son acertados (el manual base no es la regla vigente; hace falta historia), y los principios también: Git, `sources/` inmutable, evidencia separada de interpretación, la IA propone y el humano aprueba, sin infraestructura pesada, piloto primero, casos separados de la normativa y MCP después. Los conservo todos. Lo que está mal, por gravedad:

1. **Demasiadas representaciones editables** (`curated/`, `rules/*.json`, `patches/` y luego SQLite). Con cuatro lugares donde puede vivir "la regla", R5 no es un riesgo: está garantizado por diseño. Debe haber **un solo canónico editable**; lo demás es evidencia inmutable o artefacto generado.
2. **El modelo temporal descansa en supuestos falsos** [V]: test y producción tienen fechas distintas (NT 23: 30/08 frente a 27/09/2024); NT 001–012 no declaran vigencia; la numeración no es cronológica (NT 9 es del 09/09/2021, NT 8 del 21/09/2021 y NT 7 del 01/02/2022); NT 21 se volvió a subir con una marca de agua que remite a NT 24, y NT 18 se volvió a subir en junio de 2024 (si cambió el contenido no se sabe); NT 25 y NT 27 rigieron el mismo día en que se subieron y NT 22 se subió 26 días **después** de su vigencia; el MD5 del Manual publicado (`f48d7c82…`) no coincide con el certificado (`25EB165A…`); los XSD se modifican in situ sin cambiar nombre, namespace ni `dVerFor`.
3. **El "patch" como instrucción ejecutable.** Las NT no publican deltas: reproducen la fila completa, sin "antes/después", y el color de resaltado no tiene semántica fiable [V]. Reproducir deltas es frágil ante el orden y ante una base equivocada, y oculta R3. Lo robusto es **materializar versiones completas** y usar lo que declara la NT como **aserción verificable**.
4. **La identidad de las entidades es incorrecta** [V]: "D208" es campo y validación (código 1310); `iTipIDRec` es D208 en el DE y GENFE010 en la nominación; GDE008 tiene dos códigos (4006/4069) y el 2419 lo usan H002c y H005a; el grupo es D3 con padre D200, no "D".
5. **No existe una precedencia global**: el XSD contradice a las NT (`gOblAfe`: `maxOccurs=12` frente a `0-11`; `dSisFact`: requerido frente a eliminado por NT 10) [V]. La autoridad depende de la dimensión y los conflictos son datos, no fallos.
6. **Markdown como RAW y como capa curada**: el primero pierde celdas, página y filas partidas; el segundo no se valida sin otro parser.
7. **Faltan el estado "pendiente" y el horizonte de conocimiento**: lo más peligroso es una KB que sabe que hay una NT sin curar —o que no revisa el portal desde hace semanas— y responde igual con seguridad (R8, R9).
8. **Secuencia y tamaño invertidos**: empieza por lo más caro y menos verificable (convertir 217 páginas con ML), suma tecnología que todavía no aporta (Marker/MinerU, Typer, Rich, httpx, orjson, lxml, SQLite temprano) y no da valor hasta haber curado todo. Un índice de menciones ordenado por fecha de vigencia ya ayuda el primer día.

**Tesis.** Para que "Analiza el rechazo 1321" funcione con fuentes trazables y vigencia correcta hacen falta cinco cosas: (1) fuentes inmutables por hash y un horizonte de chequeo explícito; (2) evidencia determinista (texto por página más las celdas de las filas del piloto y de las tablas de fechas); (3) un canónico YAML por entidad, con versiones materializadas y literales ligados mecánicamente a celdas concretas; (4) un resolvedor temporal determinista por fecha y ambiente, con estados honestos (incluidos "no curado" y "más allá del horizonte"); (5) tests que impidan mergear una cita inventada, una fila de otra entidad, un cambio no declarado, una NT ignorada o un pasado alterado sin justificación.

---

## B. Decisiones con las que estoy de acuerdo

| Decisión | Veredicto | Razón |
|---|---|---|
| Git como registro | De acuerdo | Es el **tiempo de transacción**: `git checkout kb-<fecha> && sifen explain 1321 --at 2025-01-10` responde "qué decía la KB en esa release" sin bitemporalidad (válido desde el primer tag real). Requiere un archivo por entidad, `main` protegido y tags anotados. |
| `sources/` nunca lo modifica una IA | De acuerdo, reforzado | Con mecanismos (test de sha256, `deny`, `source add` solo desde dominios DNIT, `.gitattributes`) y guardando **todas** las revisiones: DNIT vuelve a subir archivos [V]. |
| Separar evidencia de interpretación | De acuerdo: es el principio rector | Bajado a nivel de atributo: literal (copiado por herramienta y verificado contra una celda) frente a formalización (revisada). |
| IA propone, humano revisa, tests validan, Git registra | De acuerdo | El humano decide el merge, las fechas, los destinos y los conflictos; los pasos mecánicos no lo necesitan (tabla única en J). |
| Sin vector/graph DB, microservicios, Kafka, UI ni agentes autónomos | De acuerdo | 28 documentos y 47 XSD consultados por identificadores exactos. |
| Python, uv, Pydantic, pytest | De acuerdo | Con 3.14 fijo y `uv sync --locked` (E). |
| Piloto antes de procesar todo | De acuerdo, más estrecho | Un dominio, sin sondas, precedido por un índice de menciones que ya sirve para cualquier código (S). |
| Casos separados de la normativa | De acuerdo | Son evidencia observada del servidor: abren un Issue, nunca editan una regla. Los sintéticos no cuentan como casos. |
| MCP y RAG fuera de la primera versión | De acuerdo | P y Q. |
| No aplicar OCR indiscriminadamente | De acuerdo | El MT es digital, con fuentes embebidas y etiquetado (`StructTreeRoot`) [V]. |
| CLAUDE.md corto | De acuerdo, con un añadido | Ocho reglas de consulta; las de curación van en el prompt de curación. Cada regla importante tiene detrás un test, un `deny` o la protección de rama. |
| Precedencia por dimensión (la autocrítica del propio pedido) | De acuerdo | Concretada en D.5. |
| Estados discretos en lugar de `confidence` | De acuerdo | Se calculan; no se escriben a mano. |
| Separar versión de software y snapshot de conocimiento | De acuerdo, simplificado | En el MVP basta un eje: el tag `kb-AAAA.MM.DD` con el manifiesto de fuentes (C.2, n.º 26). |
| La IA no actualiza la regla vigente sin revisión | De acuerdo | Ni ahora ni después: se automatizan la detección y el borrador, nunca el merge de contenido normativo. |
| SQLite derivado; Hypothesis | De acuerdo, acotados | SQLite nunca canónico ni versionado (Fase 3); Hypothesis solo en el resolvedor. |
| Reconstruir con `git clone` + `uv sync` | De acuerdo, con matiz | Lo reproducible es la extracción y la verificación; el borrador del LLM, una vez revisado, **es** el canónico y no se regenera. |

---

## C. Decisiones que cambiaría

### C.1 Cambios

| Propuesta actual | Tu propuesta | Por qué |
|---|---|---|
| `raw/` = PDF → Markdown | Texto por página + **celdas en JSONL** (filas del piloto y tablas de fechas) con página PDF e impresa, hash y texto normalizado; Markdown solo como vista | Markdown pierde celdas multilínea, filas partidas y procedencia. Las NT citan la página impresa (D208c: 166 impresa / 167 PDF) [V]. |
| `curated/` Markdown + `rules/*.json` | **Un único canónico**: `kb/` en YAML restringido, un archivo por entidad, validado por Pydantic | Elimina R5 por construcción; `git log` útil por regla; un Markdown no se valida con un esquema. |
| `patches/` con `action: override` | **Versiones materializadas** + **efectos declarativos** por documento (verbo literal, acción, alcance declarado, cambios reconocidos) usados como aserción | Las NT reproducen la fila completa [V]. Se revisa el estado resultante y un test exige que el diff caiga dentro de lo declarado (anti-R3). |
| `effective_date` (+ `publication_date`) | **Calendario por ambiente** (test, prod) con literal y celda de origen; `document_date` y subida al portal solo informativas; **horizonte de fuentes** | NT 13+ separan test y producción; NT 001–012 no tienen fechas; NT 22 se subió después de su vigencia; NT 25 tiene una errata de año [V]. Sin horizonte, la KB afirma vigencia sobre fechas que no puede conocer. |
| Orden por número de NT | Orden por fecha del ambiente consultado | La numeración no es cronológica [V]. |
| `overridden_by`, `active`, `effective_to` almacenados | Derivados en la consulta | Lo almacenado se vuelve falso cuando pasa una fecha futura y permite huecos y solapes. |
| `source: "MT_v150"` | Evidencia por **contenido**: documento, **revisión por sha256**, página, clave de fila y atributo (`raw:NT_024@<sha12>:p2:D208c#observation`) | "v150" no es un binario único: el MD5 publicado no coincide con el certificado [V]. Una referencia por posición se rompe con cualquier cambio del extractor. |
| Códigos únicos; `get-validation` devuelve una | Índice código → validaciones **N:M, temporal y con lápidas**, derivado; colisiones conocidas declaradas como Issue | 2419 → H002c y H005a; GDE008 → 4006/4069; NT 18 reasignó 4313–4323 [V]. Un código eliminado debe seguir respondiendo `removed`. |
| `group: "D"`, `xml_name` como identidad | Clave `contexto:ID` con espacios `field:`/`val:`; `group: D3`, `parent: D200`; `xml_name` como atributo | Colisión campo/validación D208; `iTipIDRec` en DE y en nominación [V]. |
| Condición como texto, AST o ambas | **Literal oficial** (evidencia) + **DSL textual** con polaridad fija "se viola cuando", ausencia explícita con `exists()` y nivel `full/partial/none`; el AST se deriva | Una sola representación editable. La NT mezcla polaridades: `(D208≠5)` es la restricción, no el disparador [V]. |
| `confidence: high/review` | Estados calculados + **Issues** como datos (`blocking` con ventana) | "MT = XSD ⇒ verified" da falsos positivos: ambos tienen erratas [V]. |
| Precedencia global | Autoridad por dimensión + Issue visible (D.5) | Una precedencia global resolvería `gOblAfe` y `dSisFact` en silencio. |
| Severidad fija | Severidad por versión | GED003/4253: AO en el MT → R en NT 19 [V]. |
| `sources/` = un PDF por NT; detector de NT nuevas | N revisiones por hash (PDF, XSD, RAR, XLSX) en `sources.manifest.yaml`; `source check` mínimo desde el MVP que vigila también re-subidas, el directorio XSD y la página de tablas | NT 21 "+30.12.24", NT 18 "-+Junio"; los XSD cambian in situ y todos devuelven el mismo `Last-Modified`; el XLSX geográfico cambió sin NT [V]. |
| Marker / Docling / MinerU; lxml; Typer + Rich; httpx, orjson; Python 3.13+ | pdfplumber (+ pypdfium2); xmlschema; argparse; `urllib` y `json` de la stdlib; **3.14 fijo** | El problema PDF es reconstruir celdas de forma auditable, no layout ni OCR (I); el resto, en E. |
| SQLite desde el inicio; CLI de 9 comandos; pipeline de 15 pasos | SQLite derivado desde la Fase 3; `explain` + `status` + seis de mantenimiento (O); 8 pasos (D.3) | Unas 25 entidades caben en memoria; `explain` cubre `get-field`, `get-validation`, `rule --at`, `diff` y `source`; el "diff semántico" es determinista. |
| 2–3 dominios piloto | **1 dominio** (receptor/identidad), sin sondas, precedido por un **índice de menciones** (entregable 0) | El dominio ejercita casi todos los patrones temporales reales; el índice da valor para cualquier código antes de curar (S). |
| "KB 2026.10.17" + `effective_state: NT027` | Tag `kb-AAAA.MM.DD` con manifiesto de fuentes, horizonte, pendientes e Issues bloqueantes | "Estado NT027" sugiere que todo está curado y que el número ordena el tiempo; ninguna de las dos cosas es cierta. |
| Salida `Status: ACTIVE` | `in_force / removed / not_yet_existing / undetermined / outside_coverage / not_curated` + motivos (`reasons`) + avisos obligatorios | "ACTIVE" con información incompleta es el modo de falla más peligroso (R9). |
| `test_validation_codes_are_unique_when_expected` | `test_code_collisions_declared`: N:M solo si hay un Issue `code_collision` | La unicidad no es la norma en SIFEN [V]. |
| Caso `gPaConEIni = 700000` | `gPaConEIni` (E605) es un **grupo** (G, 0-999); el monto está en `dMonTiPag` (E608); las reglas son E605a/E605b con `dMonEnt` (E645), código 1551 [V] | El ejemplo del propio pedido muestra R2: una interpretación plausible e incorrecta. |
| D208c "relacionado" con D201 y D202 | D208c usa D011, D208, F014 y F023 (y la moneda, D015, por interpretación); D201/D202 se relacionan por la obligatoriedad de D208 y por D208b/D208f [V] | Las relaciones se derivan de las condiciones; no se enumeran a mano. |

### C.2 Posición sobre las 30 decisiones abiertas (§37)

| # | Decisión | Posición |
|---|---|---|
| 1 | Marker / Docling / MinerU | Ninguna en el núcleo: pdfplumber (+ pypdfium2) o el árbol de etiquetas. Marker: pesos con licencia comercial por encima de USD 5 M de ingresos o de financiación. MinerU: ya no es AGPL, pero tiene licencia propia con umbrales y terminación automática, y fusiona tablas de forma opaca. PyMuPDF: AGPL. Docling: solo si el sondeo de la Fase 0 encuentra una NT escaneada. |
| 2 | Python | Sí, 3.14 fijo. |
| 3 | uv | Sí: lock versionado, `--locked` en CI, `only-managed` (iguala también SQLite: 3.50 frente a 3.53 medido). |
| 4 | Pydantic | Sí: `extra="forbid"`, `frozen`, IDs `str` con patrón (nunca `int \| str`), uniones discriminadas; integridad entre archivos en un pase aparte. |
| 5 | lxml | No; xmlschema. lxml no tiene caso de uso (la firma XMLDSig está fuera del alcance). |
| 6 | Typer | No; argparse. Rich tampoco. |
| 7 | JSON / YAML / SQLite | YAML restringido canónico; texto y JSONL en `raw/`; JSON exportado en la Fase 2 y SQLite en la 3, ambos generados. Plan B: JSON canónico. |
| 8 | Fuente de verdad | `kb/*.yaml`, un archivo por entidad (H). |
| 9 | Reglas | `Validation` con versiones: literales + `Formalization`; sin entidad `Rule` (F.2). |
| 10 | Overrides | Efectos declarativos como aserción; nada se reproduce sobre la base. |
| 11 | Temporalidad | Calendario por ambiente con procedencia por celda; inicio y fin derivados; lápidas; prospectivas; `coverage_from`; horizonte de fuentes; Git como tiempo de transacción (G). |
| 12 | Provenance | Por clase de afirmación (F.2); nunca por atributo escrita a mano. |
| 13 | Qué genera el LLM | Efectos (acción, alcance, destino si la fila no trae ID), formalizaciones, enumeraciones, borradores de Issues y de casos, diagnósticos desde la CLI. |
| 14 | Qué nunca modifica | `sources/`, `sources.manifest.yaml`, `raw/`, `extraction/`, `build/`, `kb/_meta.yaml`, `.claude/`, `CLAUDE.md`, literales y fechas; nunca registra fuentes, nunca borra versiones ni filas golden, nunca mergea. |
| 15 | Repositorio | D.2: sin `curated/`, `rules/`, `patches/`, `schemas/`, `examples/` ni `scripts/`. |
| 16 | Tests | K: evidencia, integridad y golden temporal primero. |
| 17 | CI | Un workflow, un job Linux; la corrida en Windows se registra localmente (L). |
| 18 | MCP | Fase 4: consumidor que no sea Claude Code + contrato estable dos ciclos de NT. |
| 19 | FTS | Fase 3 (DE completo), FTS5 derivado. |
| 20 | Embeddings: cuándo | No antes de cientos de casos y de que FTS5 falle en una evaluación medida. |
| 21 | Embeddings: ¿alguna vez? | Nunca para resolver reglas; quizá para casos parecidos. |
| 22 | Casos reales | Sanitizados, `origin: observed`, con `emitted_at`, `processed_at`, `env` y `kb_snapshot`; si contradicen la KB, abren un Issue. |
| 23 | Actualización DNIT | `source check` mínimo (manual) desde el MVP, que fija el horizonte; programado y con apertura de *issue* en la Fase 2. Primero `revision_not_curated`/`pending`, después curación. |
| 24 | Automatización | Sin humano: detectar, descargar, hashear, extraer, diff e informe. Con humano: todo lo que decide contenido normativo (J). |
| 25 | Human-in-the-loop | Fechas, destinos y clasificación, versiones, resolución de Issues y todo merge de contenido normativo. |
| 26 | Versionado | MVP: un eje, tag `kb-AAAA.MM.DD` con manifiesto de fuentes. `schema_version` cuando haya un consumidor externo del JSON (Fase 4); SemVer solo si se publica el paquete. |
| 27 | Seguridad | Sin XML reales en el repo ni en la conversación; carpeta única con `deny`; PII enmascarada; gitleaks; bloqueo de certificados por extensión y por `deny`; repo privado (M). |
| 28 | Reproducibilidad | `raw/` determinista, verificado byte a byte en CI; artefactos del LLM versionados y auditados por corrida (hooks) y PR. |
| 29 | Observabilidad | Informe de `sifen check`, `sifen status` (horizonte, pendientes, Issues) y logs de CI; sin dashboards. |
| 30 | Escalabilidad | El cuello es la curación humana; no generalizar sin un segundo dominio real (N); regla de recorte en U. |

### C.3 Divergencias entre las dos propuestas evaluadas y cómo las resolví

| Tema | MVP-first | Rigor regulatorio | Decisión y razón |
|---|---|---|---|
| Extracción PDF en el MVP | Solo texto por página (pypdfium2); Claude cura mirando la página; tablas en Fase 3 | pdfplumber + pypdfium2 + árbol de etiquetas + batería completa desde el inicio | Texto por página de **todo** el corpus con **un** motor (lo decide el spike) + **celdas solo de las filas del piloto y de las tablas de fechas**. Control cruzado entre motores y batería completa en la Fase 3: en el piloto el oráculo independiente son las *golden pages* transcritas a mano. "La cita está en la página" no detecta un literal **truncado**; "literal = celda" sí, y en una decena de páginas es barato. |
| Quién copia los literales | El LLM, con test de contención | Una herramienta | Herramienta (`sifen draft`) para toda celda, **fechas incluidas**; el LLM solo cita prosa, verificada y revisada. Un LLM que teclea literales es el vector principal de R2 y R10. |
| Piloto | Receptor/identidad, corpus completo, guardián en 27 NT | D3 completo + sondas GENFE010/011 y GED003; 8 NT | Receptor/identidad + corpus completo + guardián, **sin sondas**: la colisión de contexto ya la ejercita el guardián (NT 14 y 27 mencionan `iTipIDRec`) y la severidad versionada es el mismo mecanismo que el umbral (unitario sobre [HIP]). GENFE010 y GED003 abren la Fase 2. |
| SQLite / FTS5 | Fase 3 | v1 (= DE completo); `kb.sqlite` desde el MVP | Fase 3, siempre derivado: ambas solo necesitan FTS con el DE completo. |
| Estados | `active/removed/not_yet_existing/before_baseline` + avisos | `in_force/removed/not_yet_existing/undetermined/outside_coverage` | Los cinco + `not_curated`, con `reasons` explícitos: un pendiente, un Issue bloqueante, una revisión sin curar o el horizonte cambian el **estado**, no una nota al pie (R9). |
| NT 001–012 | Inicio aproximado = fecha del documento | `coverage_from` + supuesto A1 | Ambas: la fecha del documento ordena lo previo a la cobertura (NT 2 y NT 10 tocan el mismo dominio), con el período "Cambios desde X al Y" como rango de incertidumbre; antes de `coverage_from`, `outside_coverage`. |
| Qué cambió la NT | `changed` por versión = diff | `declared_scope` en el efecto ⊇ diff | `declared_scope` (lo declara la NT: es evidencia) + `acknowledged_changes` cuando el alcance es la fila entera + diff en el informe del PR; `changed` sería un derivado que el curador podría "ajustar". |
| Prórrogas | `date_history` | Historia desde las revisiones | Ninguna de las dos como campo: la prórroga es una **revisión nueva** (que deja la entidad `undetermined` hasta curarla) + la edición del `schedule` + un Issue `temporal` que registra ambas fechas. La fecha anterior queda en Git y en el Issue. |
| Eje temporal con `--xml` | No lo trata | `--processed-at` y ambas fechas | Ambas fechas; la de procesamiento sale de la respuesta de SIFEN (`dFecProc`) o de `--processed-at`; si falta y hay un cambio entre emisión y hoy, `undetermined`. |
| CLI | 5 (`explain`) | ~13 (`show`, `code`, `history`, `doc`, `status`…) | `explain` (código, ID, `xml_name` o documento) + `status` + seis de mantenimiento: un punto de entrada para Claude; `status` ataca R1 y R9. |
| Tipado y CI | basedpyright en Fase 2; job Ubuntu | basedpyright ya; dos jobs | MVP-first: un job Linux; basedpyright y la matriz Windows en la Fase 2. La codificación de Windows se prueba en Linux simulando cp1252, y la DoD exige el log de una corrida local en Windows. |
| Sanitizador | Enmascarar la salida | `sanitize` en el MVP | Enmascarar en el MVP; `sanitize` (con DV y CDC) en Fase 2, con casos reales. |
| Pasado inmutable | Golden + revisión | `timeline-diff main..HEAD` | Historia *append-only* precisa: borrar nunca; editar el pasado solo con un Issue `curation_error`/`erratum` que lo declare. `timeline-diff` en Fase 2. |
| Atestación de revisión | `reviewer` en la corrida | `reviewed_by` + test | El merge humano a `main` protegido. Con una persona: revisión en otra sesión y trailer `Reviewed-by:` que el CI exige para crear el tag. Un campo YAML lo puede rellenar el propio agente. |

---

## D. Arquitectura que implementaría

### D.1 Diagrama

```
 Portal DNIT (PDF · XSD · RAR · XLSX)
      │  sifen source check: hash de las URL conocidas y de los listados → HORIZONTE de fuentes
      │  (MVP: manual · Fase 2: semanal y programado)
      ▼
 sifen source add (humano) ─► sources/<doc>/<sha12>.<ext> + sources.manifest.yaml   EVIDENCIA BINARIA: inmutable,
      │   solo dominios DNIT; la herramienta descarga y hashea                       solo la escribe la herramienta
      ▼
 sifen extract ───► raw/<doc>/<sha12>/ pages/pNNN.txt · index.json · tables.jsonl   EVIDENCIA TEXTUAL: generada,
      │             (texto: un motor · celdas: pdfplumber · extraction/fixes.yaml)    versionada, verificada en CI
      ▼
 sifen draft ─────► kb/   ÚNICO CANÓNICO EDITABLE (YAML restringido, 1 archivo = 1 entidad)
      │   <DocId>: calendario copiado de la tabla de fechas · <EffectId>: versión copiada de las celdas
      │   + Claude: efectos, clasificación, formalización, Issues (bitácora por hooks en curation/runs/)
      │   + humano: revisa el PR → merge a main protegido → tag kb-AAAA.MM.DD
      ▼
 sifen check / pytest: evidencia · integridad · golden temporal · XSD offline · pasado justificado · alcance del PR
      ▼
 librería sifen_kb (load → index → resolve → explain) ──► CLI (texto | --json) ──► Claude Code · humano · scripts
      ▲                          ▲
 cases/ (sanitizados,       XML real FUERA del repo, en una carpeta única
 no normativos)             (--xml + --response | --processed-at; solo lectura; PII enmascarada)

 Entidad no curada: explain responde not_curated con sus menciones en raw/ (entregable 0)
 Fase 2: build/ (JSON, JSON Schema, vistas) · Fase 3: build/kb.sqlite con FTS5 · Fase 4: MCP read-only sobre la librería
```

### D.2 Repositorio

```
C:\dev\sifen-kb\                    # FUERA de OneDrive: bloqueos de archivos, placeholders y rutas largas
├─ sources/                         # binarios oficiales; solo se AGREGAN (sifen source add)
│  ├─ MT_V150/976cd88c05c3.pdf      # nombre = sha12 del contenido
│  ├─ NT_021/<sha12>.pdf            # cada re-subida es otro archivo; nunca se reemplaza
│  └─ XSD_DIR/<fecha>/…             # instantánea de los 47 XSD; carpeta nueva solo si cambia algún hash
├─ sources.manifest.yaml            # revisiones (sha256, md5, url, nombre, ?t=, retrieved_at) y chequeos; append-only
├─ raw/                             # GENERADO por `sifen extract`; versionado; nadie lo edita a mano
│  └─ <doc>/<sha12>/pages/p001.txt … index.json tables.jsonl
├─ extraction/fixes.yaml            # ÚNICA vía para corregir defectos de extracción (justificada, revisada)
├─ kb/                              # ÚNICO CANÓNICO
│  ├─ _meta.yaml                    # baseline, coverage_from, horizon_grace_days, eje de fecha, supuestos A1/A2
│  ├─ documents/ MT_V150.yaml NT_001.yaml … NT_027.yaml XSD_DIR.yaml NORMA_DECRETO_872_2023.yaml …
│  ├─ fields/DE/D208.yaml …
│  ├─ validations/DE/D208c.yaml …
│  └─ issues/ISS-0001.yaml …
├─ cases/2026/2026-10-02-<slug>.md  # Markdown + frontmatter; sanitizado; origin: observed; NO normativo
├─ curation/ prompts/curar_entidad.md runs/<sesión>.yaml   # instrucciones versionadas + bitácora (hooks)
├─ src/sifen_kb/                    # model, yamlio, normalize, sources, extract, load, integrity, temporal, dsl, xsd, explain, cli, hooklog
├─ tests/ unit/ evidence/ integrity/ golden/temporal.yaml golden/pages/ fixtures/{xml,kb_hyp,cases}/ allowlist_pii.yaml
├─ build/                           # gitignored (Fase 2: JSON, JSON Schema, vistas · Fase 3: SQLite)
├─ .claude/settings.json            # deny + hooks (J)
├─ .github/ workflows/ci.yml CODEOWNERS
├─ CLAUDE.md README.md pyproject.toml uv.lock .python-version .gitignore
└─ .gitattributes                   # sources/** -text · *.pdf *.rar *.xlsx binary · raw/** text eol=lf · * text=auto eol=lf
```

Se eliminan `curated/` y `rules/` (fundidos en `kb/`), `patches/` (no hay deltas ejecutables), `schemas/` como capa (los XSD son fuentes), `examples/` (los XML oficiales son fuentes y los sintéticos son *fixtures*) y `scripts/` (los scripts sueltos se pudren: pasan a subcomandos). El manifiesto vive fuera de `sources/` para que el revisor vea en el diff del PR la URL y el sha256 registrados, que es por donde entraría una fuente errónea. El `.gitattributes` no es cosmético: con `core.autocrlf` Git convierte LF en CRLF y cambia el sha256 de un XSD entre Windows y Linux; los XSD conservan el diff de texto (un cambio in situ se ve en el PR) y los PDF, RAR y XLSX se tratan como binarios.

### D.3 Pipeline ante una NT nueva o una re-subida (8 pasos)

1. **Detectar.** `sifen source check` compara el hash de todas las URL conocidas y de los listados (NT, directorio XSD, tablas) y registra el chequeo; si no hay cambios sin registrar, avanza el horizonte. MVP: lo lanza una persona; Fase 2: semanal y programado, abre un *issue*.
2. **Registrar.** `sifen source add --doc <DocId> --url <url>` (acción humana): la herramienta descarga desde un dominio DNIT permitido, calcula sha256 y md5, copia a `sources/` y agrega la revisión al manifiesto. Desde ese momento, toda entidad mencionada por ese documento responde `undetermined` (`revision_not_curated`) hasta que se cure. Sin LLM.
3. **Extraer.** `sifen extract`: el diff de Git sobre `raw/` ya muestra qué páginas y qué filas cambiaron.
4. **Calendario y efectos.** `sifen draft <DocId>` copia `document_date` y el calendario desde las celdas de la tabla de fechas. Claude escribe los efectos (verbo literal, acción, alcance, evidencia); el destino de una fila con ID lo verifica un test. El humano revisa **siempre** las fechas. Este PR puede mergearse antes de curar: desde ese momento, toda consulta afectada muestra el pendiente. (El generador del esqueleto de efectos a partir de los encabezados con verbo llega en la Fase 2.)
5. **Curar.** `sifen draft NT_028#n` crea la versión nueva copiando las celdas de `raw/` y heredando de la predecesora temporal las columnas que la fila de la NT no trae. Claude clasifica, formaliza la condición y abre Issues ante reemplazos no declarados. La bitácora de la sesión la registran los hooks en `curation/runs/`.
6. **Verificar.** `sifen check` + `pytest`: literales = celdas, fila = entidad, diff ⊆ alcance declarado, guardián de cobertura, golden, XSD, pasado justificado, alcance del PR.
7. **Revisión humana** del PR, con un informe generado: por entidad, versión anterior y nueva con su diff, fechas por ambiente, Issues nuevos, cambios al pasado y pendientes que quedan.
8. **Merge y tag** `kb-AAAA.MM.DD` (el CI exige el trailer `Reviewed-by:`).

Los pasos 1–3 y 6–8 no usan LLM; en los pasos 4 y 5 Claude clasifica y formaliza, y la herramienta copia y verifica todo lo literal. El "diff semántico" y el "reporte" del pipeline original son salidas deterministas del paso 6. Una re-subida sigue el mismo camino; en el MVP toda revisión nueva se cura (aunque sea solo para actualizar `current_revision`); la clasificación automática `identical_text`/`furniture_only`/`dates_changed`/`rows_changed` llega en la Fase 2.

### D.4 Componentes (un único paquete Python)

| Módulo | Responsabilidad |
|---|---|
| `model` | Modelos Pydantic (F). |
| `yamlio` | `KBLoader` (todo escalar es `str` salvo `true`/`false`/`null`; error ante claves duplicadas, anchors y alias) y `fmt` (volcado canónico con `\|-` para literales). |
| `normalize` | `normalize_text()`: la única normalización de texto (H), usada por `extract` y por todas las comparaciones. |
| `sources` | Hashes, manifiesto *append-only*, `source add` con lista permitida de dominios, `source check`, horizonte. |
| `extract` | Texto por página, celdas (pdfplumber), *stitching* mínimo registrado, `extraction/fixes.yaml`, `index.json` con página impresa. |
| `load` / `integrity` | Carga de `kb/` e índices (clave → entidad, código → validaciones con lápidas, `xml_name` → campos, documento → efectos); pase de integridad que devuelve **todos** los hallazgos. |
| `temporal` | Resolvedor `(clave, fecha, ambiente) → Resolution`. Puro, unas decenas de líneas, probado con golden e Hypothesis. |
| `dsl` | Parser con lista blanca de `ast` → IR; evaluador trivalente (Kleene). Nunca `eval`. |
| `xsd` | xmlschema offline (`allow="sandbox"`, `defuse="always"`, `uri_mapper` para las inclusiones por URL HTTPS absoluta [V]); ocurrencias; validación con ruta; marca de anacronismo. |
| `explain` | API de consulta estable (modo resuelto y modo índice): la usan la CLI y, en el futuro, el MCP. |
| `cli` | argparse, delgado; reconfigura stdout/stderr a UTF-8 con LF. |
| `hooklog` | Lo invocan los hooks de Claude Code para armar `curation/runs/` (J). |

### D.5 Autoridad por dimensión (reemplaza la precedencia global)

| Dimensión | Autoridad | Si discrepan |
|---|---|---|
| Estructura que el servidor valida por esquema (errores tipo 0160) | Instantánea XSD por hash, **evidencia solo desde su `retrieved_at`** (DNIT no publica historial [V]); para fechas anteriores es una referencia anacrónica que no cambia el estado. Toda comparación KB ↔ XSD usa la versión vigente en producción en esa fecha. | Issue `source_conflict` (p. ej. `gOblAfe` 12 frente a 0-11) |
| Regla de negocio: condición, código, mensaje, severidad | Versión materializada vigente (MT + NT) por fecha y ambiente | Issue `observed_vs_documented` si un caso o el Prevalidador la contradicen |
| Significado y etiquetas de valores | MT/NT (el XSD suele tener solo un patrón: `tiTipDocRec = [1-6]\|9`) [V] | Issue si el rango del XSD difiere del conjunto MT/NT |
| Fechas de aplicación técnica | Tabla de fechas de la revisión curada (`current_revision`) de la NT, o el comunicado que la modifique | Revisión nueva sin curar → `undetermined`; prórroga → Issue `temporal` |
| Obligación legal | Ley, decreto o resolución, citada y **no consolidada** | Issue `source_conflict` legal frente a técnico, solo tras leer el literal (Decreto 872/2023 "supere" es hoy [P] frente a NT 24 "mayor o igual" [V]) |
| Parámetros operativos (límites, plazos de WS) | MT | Issue (lote: 10.000 KB en el MT frente a 1000 KB en la Guía 2024 [V]) |
| Comportamiento observado del servidor | Nunca normativo (`cases/`) | Issue, nunca edición de la regla |

### D.6 Fuente de verdad y formatos

| Artefacto | Formato | ¿Editable? | ¿Versionado? |
|---|---|---|---|
| Fuentes oficiales | Binario original | No (solo `source add`) | Sí |
| Manifiesto de fuentes y chequeos | YAML (`sources.manifest.yaml`) | No (solo `source add` y `source check`) | Sí, *append-only* |
| Evidencia textual | `.txt` por página + `index.json` + `tables.jsonl` (texto normalizado + `raw_text` + `fix_id`) | No (generado; correcciones solo en `extraction/fixes.yaml`) | Sí, regenerado y comparado en CI |
| Conocimiento canónico | YAML restringido, un archivo por entidad | **Sí** (borrador de herramienta/Claude + revisión humana) | Sí |
| Casos | Markdown + frontmatter YAML | Sí | Sí |
| Bitácora de curación | YAML generado por hooks | No a mano | Sí |
| Salida de consultas | Texto / JSON con contrato estable | — | No |
| Export JSON, JSON Schema y vistas (Fase 2); SQLite (Fase 3) | Generados en `build/` | No | No (se adjuntan al release) |

---

## E. Stack tecnológico (solo lo necesario)

| Componente | Tecnología | Tipo | Alternativa | Razón |
|---|---|---|---|---|
| Intérprete | CPython **3.14** gestionado por uv | runtime | 3.13 / 3.15 | 3.13 ya es *security-only*. 3.15 trae el modo UTF-8 por defecto (PEP 686), pero se adopta cuando pydantic-core, PyYAML y pypdfium2 publiquen ruedas cp315 [verificar]; el argumento de Docling y torch ya no aplica. |
| Entorno y lock | **uv** (`uv.lock`, `--locked`, `only-managed`) | herramienta | pip-tools | Lock universal con hashes; mismo intérprete y mismo SQLite en todas las máquinas. |
| Modelos | **Pydantic 2** | runtime | attrs + cattrs | Validación en la carga, uniones discriminadas, `extra="forbid"`. |
| Canónico | **PyYAML** + `KBLoader` (~30 líneas) | runtime | JSON canónico; ruamel.yaml | Con `safe_load`, `0160` se vuelve 112, `0260` 176, `NO` False y las claves duplicadas pasan sin aviso [probado localmente]. ruamel (YAML 1.2) convierte `0160` en 160: no lo resuelve. |
| XSD y XML | **xmlschema 4** | runtime | lxml | Introspección de componentes, errores con ruta, *sandbox* sin red, `defuse`. |
| Texto y celdas de PDF | **pdfplumber** (MIT) + **pypdfium2** (Apache-2.0/BSD) | grupo `ingest` | árbol de etiquetas; Camelot | pdfplumber 0.11.10 ya exige `pdfminer.six==20260107` y `pypdfium2>=5.9.0` [verificado en PyPI]: declarar pypdfium2 no agrega paquetes al lock, y se declara porque se importa (texto por página si gana el spike; PNG para la revisión visual). Un solo motor de texto en el MVP. |
| CLI, DSL, descarga, JSON, índice | **argparse**, **`ast`**, **urllib + hashlib**, **json**, **sqlite3** (Fase 3) | stdlib | Click, Lark, httpx | Cero dependencias; argparse 3.14 trae color y sugerencias. |
| Tests | **pytest** + **Hypothesis** (solo el resolvedor) | dev | — | Ver K. |
| Calidad | **ruff** (MVP) · **basedpyright** (Fase 2) | dev | mypy | ruff incluye `S506` (`yaml.load` inseguro), `DTZ` y `PLW1514` (`open()` sin `encoding`). basedpyright no descarga npm fuera del lock. |
| Secretos | **gitleaks** (binario fijado) | externo | detect-secrets (estancado desde 2024) | Más bloqueo por extensión: un `.p12` binario no lo detecta una regex. |

Dependencias del MVP: runtime **3** (pydantic, pyyaml, xmlschema); grupo `ingest` **2** declaradas (pdfplumber, pypdfium2: una sola familia en el lock); desarrollo **3** (pytest, hypothesis, ruff). Opcionales, **no ahora**: basedpyright (Fase 2), Docling (solo si el sondeo de la Fase 0 encuentra una NT escaneada), Lark (si el DSL se queda corto), SDK de MCP (Fase 4). **No entran:** lxml (sin caso de uso), Typer, Rich, httpx, orjson, Marker, MinerU, PyMuPDF, LangChain, bases vectoriales, SQLAlchemy, Jinja2 ni pandas.

---

## F. Modelo de datos

Regla de diseño: **cada concepto existe porque un caso real de SIFEN lo exige**; si no hay caso, no entra (al final de F.2 se listan los que quedaron fuera). Un caso [HIP] no cuenta como uso.

### F.1 Pseudocódigo Pydantic

```python
from datetime import date, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, StringConstraints as S

class M(BaseModel):   # extra="forbid": una clave inventada falla. Sin strip: el literal se conserva intacto.
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

# --- Identificadores (patrones a confirmar con el inventario de Fase 0) ---
CORE      = r"[A-Z][A-Z0-9_]*"            # alfabeto ÚNICO del DocId dentro de RowRef, CellRef y EffectId
Sha256    = Annotated[str, S(pattern=r"^[0-9a-f]{64}$")]
Sha12     = Annotated[str, S(pattern=r"^[0-9a-f]{12}$")]
DocId     = Annotated[str, S(pattern=r"^(MT_V150|NT_\d{3}|XSD_DIR|XSD_RAR|CHECKSUM_MT|TABLA_GEO|(GUIA|COM|NORMA)_[A-Z0-9_]+)$")]
Ctx       = Literal["DE"]                 # MVP; "EV-NOM", "EV-DES"… entran con sus entidades (Fase 2)
SifenId   = Annotated[str, S(pattern=r"^[A-Z][A-Za-z]{0,6}\d{1,3}[a-z]?$")]  # D208c, GENFE010, ASch03
SifenCode = Annotated[str, S(pattern=r"^\d{4}$")]                          # "0160", nunca 160
FieldKey  = Annotated[str, S(pattern=r"^field:[A-Z][A-Z-]*:\w+$")]         # field:DE:D208
ValKey    = Annotated[str, S(pattern=r"^val:[A-Z][A-Z-]*:\w+$")]           # val:DE:D208 (código 1310) ≠ el campo
EffectId  = Annotated[str, S(pattern=rf"^{CORE}#\d+$")]                    # NT_024#1
RowRef    = Annotated[str, S(pattern=rf"^raw:{CORE}@[0-9a-f]{{12}}:p\d+:[^:#~]+(~\d+)?$")]
CellRef   = Annotated[str, S(pattern=rf"^raw:{CORE}@[0-9a-f]{{12}}:p\d+:[^:#~]+(~\d+)?#[a-z_]+$")]
#   Por CONTENIDO, no por posición: página PDF + clave de fila (el ID; "fechas" u otra clave declarada si la fila
#   no tiene ID; ~n desambigua un ID repetido) + atributo. raw:NT_024@<sha12>:p2:D208c#observation
#   El extractor mapea encabezados a atributos con una tabla probada: «Longitud»/«Long.» → length,
#   «Ocurrencia»/«Ocu» → occurrence, «E» → severity, «…Ambiente de Test» → test, «…Producción» → prod.
CaseRef   = Annotated[str, S(pattern=r"^case:\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")]
Env       = Literal["test", "prod"]

# --- Provenance / Evidence ---
class PageRef(M):                      # cita de prosa (sin fila de tabla)
    doc: DocId
    rev: Sha12
    page_pdf: int
    page_printed: int | None           # las NT citan la impresa (D208c: 166 impresa / 167 PDF)
    quote: str                         # test: normalize_text(quote) contenida en esa página de raw/
Evidence = RowRef | CellRef | PageRef  # RowRef: los literales de la versión = las celdas de esa fila, atributo por atributo

class Interpretation(M):               # solo para afirmaciones interpretadas (nunca literales)
    by: Literal["tool", "llm", "human"]
    run: str | None                    # obligatorio si by == "llm" (validador): curation/runs/<sesión>.yaml
    note: str | None = None            # razonamiento no normativo ("D011 ausente se trata como ≠ 13")
# La atestación de revisión NO es un campo: es el merge humano a main protegido (J).

# --- sources.manifest.yaml (raíz): lo escribe SOLO la herramienta; append-only; no forma parte de kb/ ---
class SourceRevision(M):
    doc: DocId; sha256: Sha256; md5: str; size: int
    url: str                           # dominio DNIT de la lista permitida: `source add` descarga él mismo
    filename: str                      # "NT_E_KUATIA_021_MT_V150+30.12.24.pdf"
    portal_t: datetime | None          # ?t= del portal = SUBIDA; nunca publicación ni vigencia
    retrieved_at: datetime
    origin: Literal["portal", "offline"]   # offline: copia que conserva la empresa (--file, nota obligatoria)
    note: str | None = None
    # Fase 2: content_change: frozenset[Literal["identical_text", "furniture_only", "dates_changed", "rows_changed"]]

class SourceCheck(M):                  # lo escribe `sifen source check`
    at: datetime
    scope: list[Literal["nt", "xsd", "tablas", "guias"]]
    unregistered: list[str]            # URL con hash nuevo o enlaces nuevos; vacío ⇒ chequeo limpio
# Horizonte de fuentes = fecha del último chequeo limpio (DERIVADO; lo muestran explain y status).

# --- DocumentSource: documento lógico + revisión curada + calendario por ambiente ---
class DateStatement(M):                # una fecha TAL COMO la declara una fuente concreta
    value: date | None                 # None = "a definir": versión prospectiva, nunca vigente
    literal: str                       # "01/01/2025"; validador: value == parse(literal) (None si dice "a definir")
    stated_in: CellRef | PageRef       # celda de la tabla de fechas (atributo test/prod/fecha) o comunicado

class Schedule(M):                     # el ambiente lo da la ranura, no un campo
    test: DateStatement | None         # "Fecha puesta a disposición para el Ambiente de Test"
    prod: DateStatement | None         # "... de Producción"

class Supersession(M):                 # reemplazo declarado A NIVEL DE DOCUMENTO (no entre reglas)
    doc: DocId; since: date            # NT 21: "VER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025"
    stated_in: PageRef                 # oráculo: el fin derivado de lo que introdujo NT 21 debe ser `since`

class LegalRef(M):
    citation: str                      # "Decreto 872/2023, art. 6" (no se consolida ni se interpreta)
    stated_in: Evidence

class Effect(M):                       # el "patch", declarativo y NO ejecutable
    id: EffectId
    verb_literal: str                  # "se modifica", "se excluye" (encabezado, literal)
    action: Literal["add", "modify", "remove"]
    target: FieldKey | ValKey | None   # None: fuera del modelo; si la fila citada trae ID, debe coincidir (test)
    declared_scope: Literal["row"] | list[str]   # NT 23 §1.2 "se modifica … en la Longitud" → ["length"]
    acknowledged_changes: list[str] = []         # con "row": toda columna cambiada salvo la observación, reconocida
    evidence: list[Evidence]
    from_revision: Sha12 | None = None # aparece en una re-subida que no cambió las fechas (G.3)
    disposition: Literal["pending", "not_modeled"] | None = None   # None ⇒ aplicado: lo cita exactamente UNA versión
    interpretation: Interpretation     # clasificar verbo, alcance y destino ES interpretación
    note: str | None = None            # obligatoria con not_modeled

class DocumentSource(M):               # kb/documents/<DocId>.yaml
    id: DocId
    kind: Literal["manual", "technical_note", "xsd_bundle", "codelist", "checksum_list",
                  "guide", "communication", "legal"]
    number: int | None = None          # identificador; NUNCA orden temporal
    title: str
    current_revision: Sha256           # revisión curada; debe existir en el manifiesto (test)
    official_md5: str | None = None    # MT: DNIT lista 25EB165A…; el publicado es f48d7c82… → Issue
    document_date: DateStatement | None    # "Fecha:" impresa; informativa (NT 25 tiene errata de año)
    change_period: tuple[DateStatement, DateStatement] | None = None   # NT 001–011: "Cambios desde X al Y"
    schedule: Schedule | None          # None: MT y NT 001–012 (no declaran vigencia)
    superseded_by: Supersession | None = None
    effects: list[Effect] = []
    curation_scope: Literal["dates_only", "pilot", "full"]

# --- Condiciones ---
class Formalization(M):
    expr: str | None                   # subconjunto Python; polaridad FIJA: True ⇒ la validación se VIOLA
    level: Literal["full", "partial", "none"]
    gaps: str | None                   # obligatorio si level != "full": qué no captura
    interpretation: Interpretation

# --- Versiones materializadas (RuleVersion ≡ ValidationVersion) ---
class VersionBase(M):
    introduced_by: Literal["baseline"] | list[EffectId]   # 1..n efectos con el MISMO inicio por ambiente
    based_on: Literal["baseline"] | list[EffectId] | None = None   # predecesora TEMPORAL en prod (None solo en la base)
    kind: Literal["content", "tombstone"] = "content"     # tombstone: literales de la predecesora; conserva el código
    evidence: list[Evidence]                              # ≥ 1: la fila que la introduce (o la que la elimina)
    open_questions: list[str] = []                        # no vacío ⇒ aviso needs_review en toda salida

class EnumValue(M):
    code: str                          # "6"
    label: str                         # "Tarjeta Diplomática de exoneración fiscal"; test: ⊂ observations

class FieldVersion(VersionBase):       # columnas LITERALES de la tabla, copiadas por `sifen draft`
    group: str | None                  # "D3"
    parent: str | None                 # "D200"
    xml_name: str | None               # "iTipIDRec": atributo, no identidad
    description: str | None
    data_type: str | None              # Tabla B: XML, G, CG, CE…, A, N, F, B
    length: str | None                 # "1-15p(0-8)" tal cual; su parser a estructura llega en la Fase 3
    occurrence: str | None             # "0-1"; occurs se DERIVA (parser trivial m-n)
    observations: str | None           # "Obligatorio si D201 = 2 y D202 ≠ 4 …": literal; su regla vive en val:DE:D208
    enumeration: list[EnumValue] | None = None          # interpretada desde observations
    # xpath: DERIVADO de la instantánea XSD (contexto + xml_name + padre); ambigüedad ⇒ Issue

class Field(M):
    key: FieldKey
    context: Ctx
    id: SifenId
    versions: list[FieldVersion]       # orden libre: el orden temporal lo calcula el resolvedor

class ValidationVersion(VersionBase):
    code: SifenCode | None             # puede cambiar (NT 18 reasignó 4313–4323)
    severity: Literal["R", "AO", "A", "N"] | None       # por versión (GED003: AO→R); "N" existe (BC01/0260)
    message: str | None                # literal
    observation: str | None            # literal: la EVIDENCIA de la regla
    condition: Formalization | None = None              # la INTERPRETACIÓN
    legal_basis: list[LegalRef] = []

class Validation(M):                   # Rule ≡ Validation (ver F.2)
    key: ValKey
    context: Ctx
    id: SifenId
    subject_field: FieldKey | None     # D208c → field:DE:D208
    versions: list[ValidationVersion]
# Índice código → validaciones: DERIVADO, N:M, con intervalos por ambiente y CON lápidas. Buscar un código
# devuelve toda validación que alguna vez lo tuvo, resuelta en `at`, marcando si el código rige en esa fecha.

# --- Issue, Case, corrida LLM, metadatos ---
class IssueScope(M):                   # dónde y cuándo afecta
    subject: FieldKey | ValKey | EffectId | DocId
    env: Env | None = None             # None = ambos
    since: date | None = None          # ventana [since, until); None = sin límite
    until: date | None = None

class Issue(M):                        # kb/issues/ISS-NNNN.yaml
    id: Annotated[str, S(pattern=r"^ISS-\d{4}$")]
    kind: Literal["source_conflict", "undeclared_change", "ambiguity", "temporal",
                  "erratum", "observed_vs_documented", "code_collision", "curation_error"]
    affects: list[IssueScope]
    statement: str
    evidence: list[Evidence | CaseRef]
    blocking: bool                     # True ⇒ "undetermined" para sus sujetos, SOLO dentro de su ventana y ambiente
    policy: str | None                 # qué se responde mientras tanto
    corrects: list[str] = []           # curation_error/erratum: "val:DE:D208c@NT_021#1.observation" (G.3)
    status: Literal["open", "resolved"]
    resolution: str | None = None

class Case(M):                         # frontmatter de cases/AAAA/*.md; el cuerpo es narrativa
    id: str
    origin: Literal["observed", "synthetic"]   # synthetic solo en tests/fixtures/cases/; nunca cuenta como caso
    env: Env; document_type: str; kb_snapshot: str
    emitted_at: date | None            # dFeEmiDE
    processed_at: date | None          # dFecProc de la respuesta de SIFEN
    codes_received: list[SifenCode]    # NO exhaustivo: en el rechazo SIFEN informa el primer error (MT §12) [V]
    entities: list[FieldKey | ValKey]  # deben existir
    status: Literal["open", "solved", "unexplained"]
    contradicts_kb: str | None = None  # ISS-…: un caso nunca edita una regla
    sanitized: Literal[True]           # el loader rechaza un caso sin sanitizar

class FileHash(M):
    path: str; sha256: Sha256

class CurationRun(M):                  # curation/runs/<sesión>.yaml: lo arman HOOKS de Claude Code, no el agente
    session_id: str; started_at: datetime; base_commit: str
    tool: str; model: str              # "claude-code <versión>", modelo: qué expone la API de hooks [verificar]
    prompt_path: str
    instructions_sha256: Sha256        # CLAUDE.md + prompt de curación usados
    inputs: list[FileHash]; outputs: list[FileHash]

class Assumption(M):
    id: str; text: str; status: Literal["unverified", "confirmed", "refuted"]

class KBMeta(M):                       # kb/_meta.yaml (protegido: el LLM no lo edita)
    baseline: tuple[DocId, Sha256]     # MT_V150 @ 976cd88c… (Issue: MD5 ≠ certificado)
    coverage_from: date                # 2023-06-17: DECISIÓN = prod actual de NT 13 [V]; depende de A1 [VERIFICAR-DNIT]
    horizon_grace_days: int            # 7: política, no garantía (NT 25 y 27 rigieron el día de su subida)
    date_axis_default: Literal["processing", "emission"]   # processing = supuesto A2 [VERIFICAR-DNIT]
    assumptions: list[Assumption]      # A1 (NT 001–012 rigieron antes de coverage_from), A2 (eje de fecha)

# --- Salida del resolvedor (contrato de `explain --json`; no se almacena) ---
Basis = Literal["baseline", "approx", "stated"]
Boundary = tuple[date, Basis]

class XsdCheck(M):
    snapshot: Sha12; retrieved_at: date
    status: Literal["match", "mismatch", "not_checked"]
    anachronistic: bool                # at < retrieved_at: estructura posterior a la fecha consultada

class Resolution(M):
    key: FieldKey | ValKey | None      # None en modo índice
    at: date; env: Env
    axis: Literal["processing", "emission"]
    processing_date_source: Literal["response", "flag", "unknown"] | None   # solo con --xml
    state: Literal["in_force", "removed", "not_yet_existing", "undetermined",
                   "outside_coverage", "not_curated"]
    reasons: list[Literal["pending_effect", "blocking_issue", "revision_not_curated", "beyond_horizon",
                          "processing_date_unknown", "axis_split", "test_date_missing"]]
    version: FieldVersion | ValidationVersion | None
    interval: tuple[Boundary | None, Boundary | None]  # [desde, hasta) DERIVADO; None = línea base / abierto
    source: str                                        # efecto + documento + revisión sha12 + página
    history: list[tuple[str, Boundary | None]]         # cada frontera con su base (exacta o aproximada)
    upcoming: list[str]; pending_effects: list[EffectId]; open_issues: list[str]
    mentions: list[str] = []                           # solo not_curated: doc · rev · página, por fecha de prod desc.
    xsd: XsdCheck | None
    warnings: list[str]                                # no bloqueantes: inicio aproximado, horizonte en gracia, gap…
    kb_snapshot: str                                   # git describe + último documento + alcance curado
    sources_checked_at: date                           # horizonte de fuentes

# --- Event / Service / Code: definidos, NO implementados en el MVP (Fase 4) ---
class EventTypeVersion(VersionBase):   # NT 19 cambió cómo se cuentan los 45 días del receptor [V]
    actor: Literal["emisor", "receptor", "set", "automatico"]
    deadline_literal: str | None       # "48 h", "168 h", "45 días" (también depende de la plataforma)
class EventType(M):  context: str; versions: list[EventTypeVersion]

class ServiceVersion(VersionBase):     # NT 11 agregó un WS; NT 10 cambió una URL [V]
    name: str; mode: Literal["sync", "async", "query"]; path_literal: str
    limits_literal: str | None         # 10.000 KB (MT) frente a 1000 KB (Guía) ⇒ Issue
class Service(M):  key: str; versions: list[ServiceVersion]

class Code(M):      # canónico SOLO para códigos sin fila de validación: 0364, 0422 (el MT dice 0421)
    code: SifenCode
    kind: Literal["documented_outside_tables", "observed_only"]
    meaning: str
    evidence: list[Evidence | CaseRef]
```

En el MVP no existen los contextos de eventos: las menciones de `iTipIDRec` en la nominación (NT 14, NT 27) quedan reconocidas por efectos `not_modeled` con nota. `EventType`, `Service` y `Code` se implementan cuando se cure un atributo propio del evento o del servicio (plazo, URL, límite) o un código sin fila de validación.

### F.2 Decisiones del modelo

- **`Rule` no existe como entidad.** En SIFEN la regla con código **es** una fila de validación, y la obligatoriedad condicional de un campo suele tener además su validación con código (D208/1310 "Es obligatorio informar el tipo de documento de identidad del receptor" [V]): se formaliza ahí y en ningún otro lugar. Por eso `presence` no está en el MVP: formalizar la misma condición en el campo y en la validación crearía dos interpretaciones editables que pueden divergir sin que nada lo detecte (R5 en la capa interpretada). Vuelve solo para un campo cuya obligatoriedad no tenga validación con código, con `test_presence_single_formalization`. `RuleVersion` ≡ `ValidationVersion`.
- **`Override/Patch` ≡ `Effect`**, declarativo: dice qué documento afecta qué entidad, con qué verbo y alcance, y si está pendiente. La versión materializada es el resultado; el efecto es la aserción que se verifica. Que un efecto esté "aplicado" se deriva (lo cita una versión); no se almacena.
- **Las revisiones de un documento viven solo en el manifiesto**, que escribe la herramienta. `kb/documents/` guarda únicamente `current_revision`: la revisión contra la que se curó. Si el manifiesto tiene una más reciente, el resolvedor lo deriva (`revision_not_curated`); no hace falta que alguien abra un Issue a mano.
- **Los literales están dos veces (en `raw/` y en `kb/`), a propósito.** El revisor los ve en el diff del PR y Claude lee una sola ficha. No es una segunda fuente de verdad porque la copia la hace la herramienta y un test exige **igualdad** (tras `normalize_text`) con la celda del atributo citado, en la fila cuya clave es el ID de la entidad.
- **Predecesora bien definida.** La versión de la que `draft` hereda las columnas que la NT no reproduce es la predecesora **temporal en producción** (`based_on`), no la anterior en el archivo. Si se cura fuera de orden (un comunicado descubierto tarde, NT 2 después de NT 21), `check` detecta que `based_on` ya no es la predecesora y obliga a re-materializar lo heredado; ese cambio está permitido porque no altera nada que la NT haya declarado.
- **Provenance por clase de afirmación**, no por atributo:

| Clase | Ejemplo | Procedencia | Verificación automática |
|---|---|---|---|
| Literal | `message`, `observation`, `length`, `xml_name` | `RowRef` de la versión | Igualdad con la celda del atributo; clave de fila = ID de la entidad; celda de código = `code` |
| Derivada | `occurs`, `xpath`, intervalo, "aplicado" | Ninguna: función determinista, no se almacena | Unitarios; XSD |
| Interpretada | `condition`, `enumeration`, acción, alcance y destino del efecto | `Interpretation` (+ corrida) | Nombres del DSL existen; constantes ⊂ literal; etiquetas ⊂ observaciones; destino = ID de la fila |
| Temporal | calendario, `document_date`, `change_period` | `CellRef` (o `PageRef` de un comunicado) | Literal = celda; encabezado de la columna ↔ atributo (`test`/`prod`); `value == parse(literal)` |
| Cruzada | ocurrencia XSD frente al campo | Se calcula desde una instantánea con hash, contra la versión vigente en su `retrieved_at` | Todo desacuerdo tiene Issue |
| Observada | "SIFEN devolvió 1321 el 2025-01-03" | `Case` sanitizado, `origin: observed` | Si contradice la resolución, exige Issue |

**Conceptos descartados por no tener caso real hoy** (y qué los justificaría): `effective_to`/`is_current` almacenados (nunca: son derivables); un campo de fechas anteriores (`superseded`/`date_history`): la prórroga es una revisión nueva + la edición del calendario + un Issue `temporal` con ambas fechas, y el único caso real conocido —producción de NT 13 el 21/05/2023 según una fuente secundaria frente al 17/06/2023 del PDF [P]— entra como Issue, porque una fuente secundaria no puede citarse como `stated_in`; relación `replaces` entre reglas (ninguna NT declara un reemplazo **entre reglas**; D208b → D208f es una sospecha y va como Issue; la marca de agua de NT 21 es un reemplazo **de documento**, modelado como `superseded_by`); fechas por efecto (las 27 NT fechan por documento [V]; `from_revision` cubre el único caso límite); convivencia de dos versiones aceptadas (ninguna NT la usa [V]); vigencia por valor de enumeración (las NT reproducen la lista completa; sí haría falta para el XLSX geográfico); dimensión de alcance aparte (el tipo de documento ya está en la condición: D208e, `C002 = 5,6,7`); `presence` (ver arriba); `content_change` (Fase 2, en el manifiesto); `schema_version` (Fase 4); `confidence` (nunca).

---

## G. Temporalidad

### G.1 Glosario operativo de fechas (semántica cerrada)

**Tiempo válido de la KB** = el período durante el cual **el SIFEN del ambiente E aplica** esta versión. Es una definición técnica, no legal, y verificable con casos reales. Para una validación, "puesta a disposición" se interpreta como "el servidor empieza a aplicarla" [VERIFICAR-DNIT]; para un campo de "inclusión opcional" (NT 23) no implica obligación [V].

| Nombre | Significado exacto | ¿Resuelve vigencia? |
|---|---|---|
| `document_date` | La "Fecha:" impresa en la NT | No. Informativa; tiene erratas (NT 25 dice 2024 y es de 2025) [V]. Solo ordena NT sin calendario. |
| `change_period` | "Cambios desde la fecha X al Y" de NT 001–011 [V] | No. Se muestra como rango de incertidumbre del inicio aproximado (NT 10: 01/02/2021–04/02/2022, más de un año). |
| `portal_t` | Sello `?t=` del portal: subida o modificación del archivo | **Nunca.** Detecta re-subidas (NT 22 se subió 26 días después de su vigencia) [V] y acota el inicio de un efecto `from_revision`. |
| `retrieved_at` | Cuándo descargamos esa revisión | No. Auditoría; en una instantánea XSD marca desde cuándo es evidencia de estructura. |
| `schedule.test` / `schedule.prod` | "Fecha puesta a disposición para el Ambiente de Test/Producción" (NT 13+) | **Sí**: inicio de la versión en ese ambiente. |
| Horizonte de fuentes | Fecha del último `source check` limpio | Acota la respuesta: hasta `horizonte + horizon_grace_days`, aviso; después, `undetermined` (`beyond_horizon`). |
| Fecha legal | Vigencia de un decreto o resolución | No. Se muestra; las divergencias son Issues. |
| `coverage_from` | Desde cuándo la KB **garantiza** respuestas temporales. Es una **decisión de diseño**: propuesta 2023-06-17 = producción actual de NT 13 [V], la primera NT con calendario; depende de A1 (NT 001–012 ya regían antes) [VERIFICAR-DNIT] | Antes: `outside_coverage`, con la mejor versión como referencia. |
| Fecha de emisión / de procesamiento | `dFeEmiDE` del XML / `dFecProc` de la respuesta de SIFEN (elemento obligatorio de `rProtDe`, tipo `fecUTC` [V]) | Eje de la consulta (G.4). |

Reglas de cálculo: fechas de calendario de Paraguay; el cambio rige desde las 00:00 del día indicado, hora de Asunción [VERIFICAR-DNIT]; `dFecProc` se convierte a fecha local antes de resolver (formato y zona de `fecUTC` [VERIFICAR-DNIT]); intervalos semiabiertos `[desde, hasta)`; ambiente por defecto `prod`. **Se almacenan** solo las fechas declaradas, con su celda de origen. **Se derivan** el inicio de cada versión (del documento que la introdujo, según el ambiente), su fin (inicio de la siguiente en ese ambiente), el estado, el historial inverso (entidad → NT), el índice código → validaciones y el horizonte. El tiempo de transacción ("¿qué respondía la KB en la release X?") vive en Git (`git checkout kb-<fecha> && sifen explain …`, válido desde el primer tag real). No hay bitemporalidad en los datos.

### G.2 Algoritmo de resolución

```python
PRE_COVERAGE = date(1900, 1, 1)                       # documento sin fecha ni calendario: anterior a todo

def effect_start(e, env, kb) -> tuple[date | None, str]:
    doc = kb.doc_of(e)
    if doc.schedule is None:                          # MT y NT 001–012: sin calendario
        d = doc.document_date.value if doc.document_date else None
        return (d or PRE_COVERAGE, "approx")          # A1: siempre < coverage_from (test_approx_starts_before_coverage)
    st = doc.schedule.prod if env == "prod" else doc.schedule.test
    if st is None:        return (None, "missing_test" if env == "test" else "undated")   # sin respaldo silencioso
    if st.value is None:  return (None, "undated")                                        # "a definir"
    if e.from_revision:   return (kb.portal_t(e.from_revision), "stated")  # la ventana previa la bloquea un Issue (G.3)
    return (st.value, "stated")

def version_start(v, env, kb):
    if v.introduced_by == "baseline":
        return (date.min, "baseline")                 # solo para ordenar; la salida muestra "línea base", nunca 0001-01-01
    (s,) = {effect_start(kb.effect(e), env, kb) for e in v.introduced_by}   # mismo inicio o error de datos
    return s

def resolve(key, at, env, kb, axis="processing") -> Resolution:
    if not kb.is_curated(key):
        return index_answer(key, at, env, kb)         # not_curated + menciones en raw/, la más reciente primero
    starts = [(version_start(v, env, kb), v) for v in kb.versions(key)]
    tl   = sorted(((s, v) for s, v in starts if s[0] is not None), key=lambda x: x[0][0])
    pros = [(s, v) for s, v in starts if s[0] is None]            # prospectivas o sin fecha de test
    assert_unique_starts(tl)                          # dos versiones DISTINTAS el mismo día = error de datos
    past = [(s, v) for s, v in tl if s[0] <= at]      # el NÚMERO de NT no participa
    chosen = past[-1] if past else None

    pend = kb.pending_effects_on(key) + kb.pending_untargeted_mentioning(key)
    pend_now   = [e for e in pend if (d := effect_start(e, env, kb)[0]) is None or d <= at]   # sin fecha ⇒ conservador
    pend_later = [e for e in pend if e not in pend_now]

    reasons = []
    if pend_now:                                       reasons.append("pending_effect")
    if kb.blocking_issues_on(key, at, env):            reasons.append("blocking_issue")        # ventana y ambiente
    if kb.uncurated_revisions_on(key, at):             reasons.append("revision_not_curated")  # manifiesto ≠ current_revision
    if any(b == "missing_test" and kb.prod_start(v) <= at for (_, b), v in pros):
                                                       reasons.append("test_date_missing")
    if at > kb.horizon() + timedelta(kb.meta.horizon_grace_days):
                                                       reasons.append("beyond_horizon")

    if at < kb.meta.coverage_from:         state = "outside_coverage"   # muestra igual la mejor versión
    elif reasons:                          state = "undetermined"       # muestra la última curada + motivos
    elif chosen is None:                   state = "not_yet_existing"
    elif chosen[1].kind == "tombstone":    state = "removed"
    else:                                  state = "in_force"
    upcoming = [v for s, v in tl if s[0] > at] + [v for _, v in pros] + pend_later   # nada futuro queda oculto
    return Resolution(state=state, reasons=reasons, version=chosen and chosen[1],
                      interval=(boundary(chosen), next_start_after(tl, chosen)),
                      upcoming=upcoming, warnings=collect_warnings(...), ...)
```

Definiciones que el pseudocódigo deja implícitas:
- `pending_untargeted_mentioning(key)`: efectos `pending` todavía sin destino, de documentos cuyo `raw/` menciona el vocabulario de la clave (ID, código, `xml_name`).
- `uncurated_revisions_on(key, at)`: documentos con efectos sobre la clave (o cuyo `raw/` la menciona) cuya última revisión en el manifiesto difiere de `current_revision`, desde la fecha de ese documento. Un documento registrado sin ficha en `kb/documents/` es una revisión sin curar desde `coverage_from` (todavía no se conocen sus fechas: NT 22 se subió después de su vigencia), y sin `raw/` afecta a todas las claves: es el estado de una NT recién descargada, que dura hasta `sifen draft <DocId>`.
- `blocking_issues_on(key, at, env)`: Issues abiertos y bloqueantes con algún `IssueScope` cuyo sujeto es la clave, un efecto que la apunta o un documento con efectos que la apuntan, con `at` dentro de `[since, until)` y el ambiente coincidente.
- Avisos no bloqueantes (`warnings`): horizonte vencido pero dentro de la gracia, inicio aproximado (con `change_period` si existe), `gaps` de la formalización, XSD anacrónico, `open_questions`, Issues no bloqueantes y prórrogas registradas.

No existe un "pendiente siempre con calendario": NT 001–012 no tienen calendario [V] y una fecha puede ser "a definir". Un pendiente sin fecha bloquea si su documento ya existía en `at`; uno futuro o sin fecha aparece siempre en `upcoming` (propiedad de Hypothesis en K).

**Cadena de honestidad ante una NT nueva** (ningún eslabón necesita un LLM): el portal cambia → `source check` lo detecta y el horizonte deja de avanzar → pasada la gracia, `beyond_horizon` → `source add` → `revision_not_curated` para las entidades que el documento menciona → `sifen draft <DocId>` + efectos `pending` → `pending_effect` → versiones curadas → `in_force`. En cada etapa la respuesta dice exactamente lo que la KB sabe.

### G.3 Tratamiento de cada caso

| Caso | Tratamiento |
|---|---|
| Publicado el 01/03, vigente el 01/04 | `document_date` informativa; resuelve `schedule`. Entre ambas fechas, `upcoming` avisa. |
| Test ≠ producción (NT 23: 30/08 frente a 27/09/2024 [V]) | `--env test` y `--env prod` difieren entre esas fechas. Golden con datos reales. |
| Falta la fecha de test | En `--env test`, `undetermined` (`test_date_missing`) con el aviso "test sin fecha declarada". No se usa la de producción: test suele adelantarse, y usarla mostraría la regla vieja justo cuando ya rige la nueva. |
| Fecha "a definir" | `value: null`: versión prospectiva, nunca vigente, siempre en `upcoming`. |
| Prórroga (re-subida con otra fecha, o comunicado) | Revisión nueva en el manifiesto → `revision_not_curated` automático. El PR que la cura edita el `schedule` (con la celda de la revisión nueva), actualiza `current_revision` y agrega un Issue `temporal` (resuelto) con ambas fechas. **No** se crea una versión nueva de la regla: cambió cuándo empieza, no la regla. |
| Re-subida que cambia filas sin cambiar fechas (patrón real: NT 18 `-+Junio`, subida el 06/06/2024 sobre fechas de 2023; NT 14 `V150X`, 25/01/2024; si cambió su contenido, NO VERIFICADO) | Versión nueva cuyo efecto lleva `from_revision`. Su inicio es desconocido dentro de `[fecha declarada, portal_t de la revisión)`: se toma la subida como inicio y un Issue `temporal` bloqueante cubre esa ventana. Nunca se aplica retroactivamente sin evidencia. |
| Re-subida sin cambio normativo | En el MVP toda revisión nueva se cura, aunque solo sea para actualizar `current_revision`; la clasificación automática llega en la Fase 2. NT 21 solo existe hoy en su revisión de 2024: entra como revisión inicial con nota, y su marca de agua se modela como `superseded_by: {doc: NT_024, since: 2025-01-01}`, que es además un **oráculo de test**: el fin derivado de la versión de NT 21 debe ser 2025-01-01. |
| Override parcial | Versión nueva **completa**; la herramienta copia las columnas que la NT reproduce y hereda las demás de `based_on`. Test: el diff cae dentro de `declared_scope`; con alcance `row`, toda columna cambiada distinta de la observación debe figurar en `acknowledged_changes` (así se detecta un AO→R no declarado como el de GED003, o un error de copia de DNIT); un atributo interpretado (`condition`) solo puede cambiar si cambió su literal (`observation`). |
| Dos efectos con el mismo inicio sobre la misma entidad | Una sola versión con `introduced_by: [efecto1, efecto2]` y alcance efectivo = unión. Casos reales: NT 23 organiza sus cambios por columna ("en la Longitud", §1.2; "en la ocurrencia", §1.3) y NT 19 y NT 20 comparten calendario (test 15/12/2023, producción 31/01/2024) [V]. Dos versiones **distintas** el mismo día siguen siendo error. |
| Orden invertido entre ambientes | Real a nivel de documento [V]: en test NT 18 (01/12/2023) va antes que NT 21 (01/01/2024); en producción NT 21 (01/01/2024) va antes que NT 18 (08/01/2024); lo mismo NT 19/20 frente a NT 21. Hoy no tocan la misma entidad. Si ocurre, la predecesora se define por producción y `check` exige un Issue `temporal` bloqueante en test durante la ventana invertida. |
| Curación fuera de orden | `based_on` deja de ser la predecesora temporal → `check` falla y obliga a re-materializar las columnas heredadas (cambio permitido). |
| Cambio en un campo frente a su validación | Entidades y efectos distintos: NT 23 agrega el valor 6 a `field:DE:D208` y modifica `val:DE:D208e` con dos efectos [V]. |
| Eliminación ("se elimina") | Versión lápida (`kind: tombstone`): copia los literales de la predecesora, **conserva el código** y cita la fila que elimina. La clave nunca se reutiliza ni se borra, y el índice de códigos la encuentra (`explain 1322` → `removed`). |
| "Se excluye" | `verb_literal` conservado. Es `modify` de la condición solo si el texto restringe el alcance: NT 26 vuelve opcionales E020/E704/E705 "si D202=3" y excluye sus validaciones (1400/1401, 1800/1801). La exclusión de GEC002c (4004) en NT 25 es probablemente una validación del propio evento de cancelación (el código está junto a GDE008/4006 de §11.6.1): `remove`. Interpretación revisada [VERIFICAR-DNIT]. |
| ID nuevo para una regla equivalente (NT 23: D208f ≈ D208b, D208g ≈ D208) | Entidad nueva + Issue `undeclared_change` **bloqueante sobre la regla del MT** desde el inicio de NT 23 en cada ambiente → D208b y D208 quedan `undetermined`; D208f y D208g, `in_force` con aviso. D210b ≈ D210a (lápida de NT 2): Issue no bloqueante "posible reintroducción con otro ID". Nunca se fusionan sin declaración de DNIT. |
| Reintroducción tras una lápida | Solo con `action: add` y un Issue que lo justifique. |
| Corrección de DNIT sin retroactividad declarada (NT 18 corrige códigos) | Versión nueva con las fechas de la NT: refleja lo que hace el servidor desde entonces. Retroactividad solo con evidencia (Issue `erratum`). |
| Error de curación en una versión pasada | Se corrige en el lugar con un Issue `curation_error` cuyo `corrects` lista el atributo; nunca se borra una versión, un efecto ni una fila golden. Git conserva lo que la KB respondía antes, y `--history` muestra la corrección. |
| Consulta anterior a `coverage_from` | `outside_coverage`, con la mejor versión como referencia y su base (`approx`). |
| Consulta posterior al horizonte | Dentro de la gracia, el estado normal más el aviso "fuentes verificadas el X; una NT posterior podría regir (NT 25 y 27 rigieron el día de su subida)"; después, `undetermined` (`beyond_horizon`) con la mejor versión. Residual: una NT subida tarde (NT 22) puede afectar fechas anteriores al horizonte. |
| Estructura consultada antes de la primera instantánea XSD | El bloque XSD dice "instantánea posterior a la fecha consultada: referencia, no evidencia" (`anachronistic`) y **no altera el estado** de la regla de negocio. Ejemplo: `tiTipDocRec = [1-6]\|9` acepta hoy el 6 que agregó NT 23; un XML de 2024-06 con D208=6 "pasa el esquema" solo de forma anacrónica. |

### G.4 Eje temporal: ¿emisión o procesamiento?

Es el punto ciego del diseño original. Un DE puede emitirse antes de un cambio y transmitirse después: existe la validación AO por transmisión extemporánea (A004b/1005) [V]; los plazos de transmisión normal que se citan (72 h desde la firma, 120 h desde la emisión) no se localizaron en el texto oficial [VERIFICAR-DNIT]. Ejemplo: DE emitido el 30/12/2024 a un receptor innominado por 10.000.000 PYG y procesado el 02/01/2025. Con la fecha de emisión aplica NT 21 (≥ 35 M) y **no** viola; con la de procesamiento aplica NT 24 (≥ 7 M) y **viola** 1321.

Decisión: `--at` significa fecha de procesamiento (supuesto A2, declarado en `_meta.yaml`) [VERIFICAR-DNIT]. Con `--xml`, `--at` no se admite y el resolvedor corre con **ambas** fechas:
- **Emisión**: `dFeEmiDE` del XML.
- **Procesamiento**: `dFecProc` de la respuesta de SIFEN si se pasa `--response RUTA` (elemento obligatorio de `rProtDe` en `protProcesDE_v150.xsd` [V]); si no, `--processed-at AAAA-MM-DD`. Nunca "hoy" por defecto: un rechazo de 2024 evaluado con la regla de hoy da un veredicto falso. `Resolution.processing_date_source` registra el origen.
- Si falta la fecha de procesamiento y hay una frontera de versión entre la emisión y el horizonte, el estado es `undetermined` (`processing_date_unknown`) y se muestra la resolución por emisión como referencia; si no hay frontera, cualquier fecha de procesamiento cae en la misma versión y se resuelve normalmente.
- Si ambas fechas caen en versiones con veredictos distintos, `undetermined` (`axis_split`) con los dos resultados. No requiere modelado extra: es correr el resolvedor dos veces.

### G.5 Ejemplo: D208c cambia tres veces (dos cambios reales y uno [HIP]), y luego se elimina [HIP]

**Datos reales [V].** MT v150 (p. impresa 166 / PDF 167): umbral 60.000.000. NT 21 (documento 29/12/2023; test y producción 01/01/2024; re-subida el 30/12/2024 con marca de agua): 35.000.000. NT 24 (documento 17/12/2024; subida 19/12/2024; test y producción 01/01/2025): 7.000.000. NT 25–27 no tocan D208c.

```yaml
# kb/documents/NT_024.yaml  (extracto; hashes, páginas y claves de fila como marcadores)
id: NT_024
kind: technical_note
number: 24
title: Nota Técnica N° 24
current_revision: <sha256 de NT_E_KUATIA_024_MT_V150.pdf>
document_date: {value: 2024-12-17, literal: 17/12/2024, stated_in: 'raw:NT_024@<sha12>:p1:fechas#fecha'}
schedule:
  test: {value: 2025-01-01, literal: 01/01/2025, stated_in: 'raw:NT_024@<sha12>:p1:fechas#test'}
  prod: {value: 2025-01-01, literal: 01/01/2025, stated_in: 'raw:NT_024@<sha12>:p1:fechas#prod'}
effects:
  - {id: 'NT_024#1', verb_literal: <encabezado literal>, action: modify, target: 'val:DE:D208c',
     declared_scope: row, evidence: ['raw:NT_024@<sha12>:p<n>:D208c'], interpretation: {by: llm, run: <sesión>}}
curation_scope: pilot
```

```yaml
# kb/validations/DE/D208c.yaml  (literales copiados por `sifen draft`; aquí los ya verificados)
key: 'val:DE:D208c'
context: DE
id: D208c
subject_field: 'field:DE:D208'
versions:
  - {introduced_by: baseline, code: '1321', severity: R, …, evidence: ['raw:MT_V150@976cd88c05c3:p167:D208c']}   # ≥ 60.000.000
  - {introduced_by: ['NT_021#1'], based_on: baseline, code: '1321', severity: R, …, evidence: ['raw:NT_021@<sha12>:p<n>:D208c']}   # ≥ 35.000.000
  - introduced_by: ['NT_024#1']
    based_on: ['NT_021#1']
    code: '1321'
    severity: R
    message: |-
      Tipo de documento de identidad del receptor incorrecto para el total general de la operación en guaraníes
    observation: |-
      Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es mayor o igual a 7.000.000 (F023 >= 7.000.000 o F014 >= 7.000.000)
    condition:
      expr: |-
        (not exists(D011) or D011 != 13) and exists(D208) and D208 == 5 and ((exists(F023) and F023 >= 7000000) or (exists(F014) and F014 >= 7000000))
      level: partial
      gaps: |-
        Sigue el paréntesis formal. La prosa asocia F023 a moneda extranjera y F014 a PYG (D015): con moneda extranjera, F014 >= 7.000.000 y F023 < 7.000.000, el paréntesis viola y la prosa no (ISS-0005). Que D011 ausente equivalga a "≠ 13" y que D208 ausente no viole son interpretaciones.
      interpretation: {by: llm, run: <sesión>}
    legal_basis: [{citation: 'Decreto 872/2023, art. 6, numeral 2, inciso ii)', stated_in: <PageRef de la Observación de NT 24>}]
    evidence: ['raw:NT_024@<sha12>:p<n>:D208c']
```

Los comentarios `#` y los `…` son ilustrativos: en `kb/` los comentarios están prohibidos (`sifen fmt --check`) y cada versión es completa. Con el `KBLoader`, `2024-12-17` y `1321` llegan como texto y Pydantic los tipa.

**Escenario [HIP]** (vive solo en `tests/fixtures/kb_hyp/`, nunca en `kb/`; el fixture declara su propio horizonte, 2027-12-31):
- **NT_901 [HIP]**, documento 2027-01-15. Encabezado "se modifica la Observación de la siguiente validación" → `declared_scope: [observation]`. Umbral 7.000.000 → 5.000.000; mensaje, código y severidad intactos (**cambio parcial**). Revisión 1 (subida 2027-01-18): test **2027-02-01**, producción **2027-03-01**. Revisión 2 (re-subida 2027-02-20): producción **2027-04-01** (**prórroga**). El Issue `temporal` resuelto registra ambas fechas.
- **NT_902 [HIP]**, documento 2027-08-02: "se elimina la siguiente validación: D208c". Test **2027-09-01**, producción **2027-10-01** (**eliminación** con test ≠ producción).

Línea de tiempo derivada:

| Versión | Introducida por | Contenido | Producción desde | Test desde | Hasta (prod, derivado) |
|---|---|---|---|---|---|
| v0 | baseline MT v150 | ≥ 60 M | línea base | línea base | 2024-01-01 |
| v1 | NT_021#1 | ≥ 35 M | 2024-01-01 | 2024-01-01 | 2025-01-01 (= `superseded_by` de NT 21) |
| v2 | NT_024#1 | ≥ 7 M | 2025-01-01 | 2025-01-01 | 2027-04-01 [HIP] |
| v3 [HIP] | NT_901#1 | ≥ 5 M | 2027-04-01 (antes 2027-03-01) | 2027-02-01 | 2027-10-01 |
| v4 [HIP] | NT_902#1 | lápida `tombstone` | 2027-10-01 | 2027-09-01 | — |

Consultas y respuestas esperadas (cada fila es un golden de `tests/golden/temporal.yaml`). La columna KB indica la base de conocimiento: `real`, `hyp` (fixture), `hyp_rev2_pendiente` (el mismo fixture con la revisión 2 de NT_901 registrada en el manifiesto y `current_revision` todavía en la 1) o `corte:<fecha>` (la KB real sin los documentos posteriores a esa fecha ni las versiones que introducen, con el horizonte en esa fecha):

| # | Consulta | KB | Resultado esperado | Qué demuestra |
|---|---|---|---|---|
| 1 | `explain 1321 --at 2023-12-31` | real | `in_force` v0 (≥ 60 M), MT v150 p. 166/167, hasta 2024-01-01 | Base dentro de la cobertura |
| 2 | `--at 2024-01-01` | real | v1 (≥ 35 M) | Semiabierto: el día del cambio ya rige lo nuevo |
| 3 | `--at 2024-12-31` | real | v1; `upcoming`: NT 24 desde 2025-01-01 | Frontera del día anterior |
| 4 | `--at 2025-01-01` y `--at 2026-10-17` | real | v2 (≥ 7 M), NT 24, base legal citada | Vigente hoy [V] |
| 5 | `--at 2023-01-10` | real | `outside_coverage`; referencia v0 | No inventa certeza antes de 2023-06-17 |
| 6 | `--at 2024-06-01` | `corte:2023-12-20` (sin NT 21 ni posteriores) | `undetermined` (`beyond_horizon`); mejor versión v0 | Lo que una KB de entonces podía decir honestamente (réplica del tiempo de transacción) |
| 7 | `--at 2027-02-15 --env test` [HIP] | hyp | v3 (≥ 5 M) | Test ≠ producción |
| 8 | `--at 2027-02-15 --env prod` [HIP] | hyp | v2; `upcoming`: v3 desde 2027-04-01 (prorrogada; antes 2027-03-01, según ISS) | Prórroga sin versión nueva |
| 9 | `--at 2027-03-15 --env prod` [HIP] | hyp_rev2_pendiente | `undetermined` (`revision_not_curated`) | Honestidad durante la curación, sin Issue manual |
| 10 | `--at 2026-10-17 --env prod` [HIP] | hyp_rev2_pendiente | v2 `in_force` | La revisión sin curar solo bloquea desde la fecha de NT_901 (2027-01-15) |
| 11 | `--at 2027-03-15 --env prod` [HIP] | hyp | v2 | Prórroga aplicada |
| 12 | `--at 2027-09-15 --env test` [HIP] | hyp | `removed` (NT_902) | Lápida en test |
| 13 | `--at 2027-09-15 --env prod` [HIP] | hyp | v3 `in_force`; `upcoming`: eliminación 2027-10-01 | Eliminación con test ≠ producción |
| 14 | `explain 1321 --at 2027-10-05` [HIP] | hyp | `removed`: "recibir 1321 contradice la KB → registrar un caso" | El código sigue respondiendo tras eliminarse |
| 15 | `explain D208c --history` | real | MT v150 (base) → NT 21 (2024-01-01) → NT 24 (2025-01-01), con fuentes, diff de cada tramo y base de cada frontera | Historial |
| 16 | `--xml` emisión 2024-12-30, `--processed-at 2025-01-02`, D208=5, PYG, F014=10.000.000 | real | emisión → v1 → FALSE; procesamiento → v2 → TRUE; `undetermined` (`axis_split`) | G.4 |
| 17 | El mismo XML sin fecha de procesamiento | real | `undetermined` (`processing_date_unknown`); referencia: emisión → v1 → FALSE | Nunca "hoy" por defecto |
| 18 | `--xml` con F014 = 6.999.999 y 7.000.000; emisión y procesamiento 2025-03-01 | real | FALSE / TRUE | Frontera "mayor o igual" |
| 19 | Diff v2 → v3 [HIP] | hyp | Cambian `observation` y `condition` ⊆ alcance `[observation]` → pasa; si el curador también tocara `message`, **falla** | Anti-R3 |
| 20 | `explain 1321 --at 2027-01-01` | real, horizonte 2026-10-17 | `undetermined` (`beyond_horizon`); mejor versión v2 | La KB no afirma vigencia sobre fechas que no puede conocer |

Eliminación real en el mismo dominio: NT 2 (16/07/2020, sin calendario) elimina D208d (1322) y D210a (1323) [V]. `explain 1322 --at 2025-03-01` → `removed`, fuente NT 2, aviso de inicio aproximado; `--at 2020-08-01` → `outside_coverage`. Que sigan eliminadas en 2025 es una **conclusión de la curación** (NT 23 no menciona D208d ni D210a, y lo controla el guardián de cobertura), no un hecho [V] [VERIFICAR-DNIT]. `explain 1323` muestra siempre el Issue que vincula D210a con D210b (1334, NT 23), porque responder solo "eliminada" induciría a error en el troubleshooting. Y fuera del piloto, `explain 1400` → `not_curated`, con NT 26 (que la excluye) como primera mención.

---

## H. Fuente de verdad

**Un único canónico: YAML restringido en `kb/`, un archivo por entidad, validado por Pydantic.** `sources/` (con su manifiesto) es evidencia binaria; `raw/` es evidencia textual generada y verificada; JSON, Markdown y SQLite se generan en `build/` y no se versionan.

| Opción | Veredicto | Motivo |
|---|---|---|
| A: Markdown `curated/` canónico | No | No se valida con un esquema; una IA "mejora" la prosa y la regla deriva; haría falta un segundo parser para extraer datos. |
| **B: YAML canónico; Markdown, JSON y SQLite generados** | **Sí** | Revisable en un PR; legible para humanos e IA; validable; `git log --follow` por regla; literales multilínea legibles en bloque. |
| C: SQLite canónico | No | Diffs binarios, sin revisión en PR, conflictos de merge irresolubles. |
| JSON canónico | Plan B | Cero ambigüedad de tipos, pero literales con `\n` escapados y PR ilegibles. |
| TOML | No | Las tablas anidadas (versiones → condición → interpretación) confunden; el *frontmatter* de los casos seguiría siendo YAML: dos formatos. |

Condiciones no negociables para que YAML sea seguro:
1. `KBLoader`: todo escalar es `str` (salvo `true`/`false`/`null`) y Pydantic es la única autoridad de tipos; claves duplicadas, anchors y alias son error con número de línea.
2. **Una sola normalización de texto**, `normalize_text()`: NFC; se quita el guion blando (U+00AD); los saltos de línea dentro de una celda se unen con un espacio, salvo tras un "-" final, que se une sin espacio (así `1-15p(0-` + `8)` vuelve a ser `1-15p(0-8)`); espacios colapsados; `strip`. La aplica `extract` al escribir `tables.jsonl` (que conserva además `raw_text`) y la usan todas las comparaciones (celdas, citas, fechas). Sin ella, "literal = celda" fallaría siempre o se relajaría caso por caso.
3. Literales siempre en bloque `|-`, un párrafo por línea, sin cortes editoriales ni salto final. En un escalar plano, `" #"` trunca el texto en silencio; un corte "estético" a 100 caracteres rompería la igualdad. Se descartó `>-`: el plegado agrega una transformación entre el archivo y el valor. Como el texto normalizado no tiene espacios iniciales ni finales, el volcador nunca necesita cambiar a comillas.
4. Sin comentarios: lo que importa va en `note`, `gaps` u `open_questions`.
5. `sifen fmt --check` en CI: cargar y volver a volcar debe dar **el mismo archivo**. Así se detectan a la vez los comentarios, los truncamientos y el formato no canónico.

---

## I. Estrategia PDF

**Para este caso concreto:** 217 páginas digitales exportadas de Word, de una columna, etiquetadas, con tablas con bordes que cruzan páginas, y NT de 1 a 5 páginas, también de Word [V]. El problema no es el layout ni el OCR (lo que aportan Marker, MinerU o Docling), sino **reconstruir celdas de forma determinista y auditable**. Por eso:

**MVP**
1. **Texto por página de todo el corpus** (MT + 27 NT) con **un solo motor**: pypdfium2 (orden del flujo de contenido, que debería mantener contiguo el texto de una celda multilínea) o pdfplumber; lo decide el spike. Con `pdftotext -layout` los nombres XML de la tabla D3 salieron desplazados de fila, y el modo "raw" los recompuso mejor [V]. `index.json` guarda la página impresa (pie "septiembre de 2019 NNN") y el hash de cada página. Habilita el índice de menciones (entregable 0), las citas y el guardián de cobertura.
2. **Celdas solo donde se necesitan:** las filas que cura el piloto (en el MT: tablas D1/D3/F y §12.4; en las NT que lo tocan: 1, 2, 8, 10, 21, 23 y 24, según el inventario de la Fase 0) y las **tablas de fechas de NT 13–27**. Con pdfplumber (estrategia `lines`) o con el árbol de etiquetas `Table/TR/TD` del PDF: el spike decide. *Stitching* mínimo y registrado: se elimina el encabezado repetido y se une la fila de continuación (ID vacío), con las dos procedencias. Cada fila se indexa por (página, clave), que es lo que citan las referencias de `kb/`.
3. **`extraction/fixes.yaml`** es la única vía para corregir defectos reales y conocidos; `extract` las aplica y `tables.jsonl` guarda el `original` y el `fix_id`. Los defectos ya identificados (`E827` partido en `E82` + `7` en NT 20; códigos fusionados "1400 / 1401" en NT 14, 18 y 26 [V]) están fuera del piloto: entran cuando se curen esas NT.
4. **El color de resaltado no tiene semántica fiable** [V]: la acción sale del verbo del encabezado.

**Spike de Fase 0, con criterios explícitos:**
- *golden pages* transcritas a mano una vez: las páginas del piloto (unas seis a ocho) y una tabla de fechas;
- el extractor elegido debe dar **100 % de las celdas** de esas páginas, encontrar el 100 % de las citas del piloto en el texto de página y producir **los mismos hashes en Windows y en Linux**;
- si ni pdfplumber ni el árbol de etiquetas llegan al 100 %, el *fallback* es explícito: citas por página verificadas por contención más revisión visual obligatoria de la celda (PNG renderizado con pypdfium2). Nunca en silencio;
- el sondeo de páginas (capa de texto, imágenes, etiquetas) decide si alguna NT está escaneada; solo entonces entra Docling.

**Fase 3 (DE completo).** Tablas completas del MT con la batería anti-errores silenciosos: **control cruzado entre motores** (cada celda de pdfminer debe aparecer en el texto de PDFium), conservación de caracteres por página, invariantes del *stitching*, secuencia y formato de IDs, dominios por columna, conteos por grupo comprometidos en Git, parser de longitudes con su golden, cruce de facetas con el XSD, 10–20 *golden pages* y regeneración byte a byte.

**Descartados** (detalle de licencias en C.2, decisión 1): Marker (pesos con umbral de USD 5 M), MinerU (licencia propia con umbrales y terminación automática; fusión opaca), PyMuPDF (AGPL), Docling (MIT y bueno, pero ~1,3 GB más modelos, determinismo no garantizado y sin fusión nativa de tablas multipágina: solo para una NT escaneada), servicios en la nube (no reproducibles) y Markdown como RAW (pierde celdas, página y orden).

---

## J. Estrategia LLM

Una sola tabla define quién hace qué. **Sin humano** (herramienta, nunca Claude): detectar, descargar, hashear, extraer, calcular diffs, generar el informe y abrir un *issue* o un PR. **Siempre con aprobación humana**: calendario, destinos y clasificación de efectos, versiones, resolución de Issues y todo merge de contenido normativo.

| Tarea | Quién | Revisión humana | Metadata |
|---|---|---|---|
| Chequear el portal, descargar y registrar fuentes | Herramienta (`source check`, `source add`); `source add` lo lanza una persona | No (diff del manifiesto visible) | Manifiesto |
| Extraer `raw/` | Herramienta | No (diff visible; CI regenera) | `index.json` (versión del extractor) |
| Calendario de un documento | Herramienta (`sifen draft <DocId>` copia las celdas de la tabla de fechas) | **Siempre** | `CellRef` |
| Efectos: verbo, acción, alcance, destino | Claude en el MVP (generador de esqueleto en la Fase 2); el destino de una fila con ID lo verifica un test | **Sí** | `Interpretation` + corrida |
| Literales de una versión | Herramienta (`sifen draft <EffectId>`) | Sí (en el diff) | `RowRef` |
| Formalización de la condición, enumeración | Claude | **Sí: es interpretación** | `Interpretation` + corrida |
| Conflictos, reemplazos no declarados, errores de curación | Claude redacta el Issue | Decide el humano | Issue |
| Diagnosticar un rechazo | Claude, **solo a partir de `sifen explain --json`** | No es un cambio de la KB | — |
| Redactar un caso | Claude, sanitizado | Sí | Frontmatter |
| Merge de contenido normativo | Solo una persona | — | Trailer `Reviewed-by:` |

**Reproducibilidad y metadata.** Los borradores del LLM no se regeneran; revisados y mergeados, **son** el canónico. Lo reproducible es la verificación. La bitácora no la escribe el agente: hooks de Claude Code la arman en `curation/runs/<sesión>.yaml` —`SessionStart` registra sesión, fecha, commit base y hash de CLAUDE.md y del prompt; `PostToolUse` sobre `Edit`/`Write` agrega cada ruta tocada con su sha256 [verificar la API de hooks y qué datos expone en la versión instalada]—. Un validador exige `run` en toda interpretación `by: llm`, y `test_llm_runs_cover_outputs` exige que todo archivo de `kb/` con una interpretación nueva figure en las salidas de una corrida del mismo PR; un archivo editado en una sesión de Claude no puede declarar `by: human` para una interpretación nueva.

**Automatización por fases.** Fase 2: `source check` semanal que abre un *issue*, y generador del esqueleto de efectos. Fase 4: el detector abre un PR con `sources/`, `raw/` y el esqueleto. Fase 5: Claude redacta el borrador del PR; el único merge automático admitido es el de una re-subida cuyo texto extraído es **idéntico**, hecho por una cuenta bot con una excepción explícita en la regla de rama (el `deny` de push solo se relaja para esa cuenta, nunca en las sesiones de Claude).

**CLAUDE.md propuesto** (corto; las reglas de curación viven en el prompt de curación):

```markdown
# SIFEN KB — reglas para Claude

1. Ante cualquier código, validación, campo, xml_name o documento (NT_0xx) de SIFEN, ejecuta primero
   `uv run sifen explain <término> --json [--at AAAA-MM-DD] [--env prod|test]`. No respondas reglas SIFEN de memoria.
2. Para un rechazo con XML usa `--xml RUTA` y pide la respuesta de SIFEN (`--response RUTA`) o su fecha de
   procesamiento (`--processed-at`). Nunca abras un XML real con Read, cat, grep ni otra herramienta.
3. Empieza por `state` y `reasons`. Si no es `in_force`, dilo antes que nada. Si es `not_curated`, di que la
   vigencia no está resuelta y muestra las menciones sin inferir la regla.
4. Cita el documento oficial (doc, revisión sha12, página impresa/PDF). La autoridad es DNIT, nunca "la KB".
5. Transmite `warnings`, `pending_effects`, `open_issues` y la fecha del horizonte de fuentes tal cual.
6. Nunca presentes una versión no vigente como vigente. El número de NT no ordena el tiempo.
7. Nunca leas ni pidas certificados (.p12/.pfx/.key/.pem), contraseñas ni el CSC de producción.
8. Para curar, lee primero `curation/prompts/curar_entidad.md`. No hagas push, merge ni `sifen source add`.
```

`curation/prompts/curar_entidad.md` contiene las reglas de curación: no editar `sources/`, `sources.manifest.yaml`, `raw/`, `extraction/`, `build/` ni `kb/_meta.yaml`; literales y fechas solo con `sifen draft`, nunca tecleados ni parafraseados; cada cambio de una NT es una versión nueva completa con `introduced_by: [NT_0xx#n]`; nunca borrar versiones, efectos ni filas golden (una eliminación es una lápida; una corrección del pasado exige un Issue `curation_error`); no inventar IDs, nombres XML, códigos ni fechas; ante contradicción, ambigüedad o posible reemplazo no declarado, crear un Issue y no decidir; lo dudoso va a `open_questions`; antes de proponer: `uv run sifen fmt && uv run sifen check && uv run pytest -q`; un PR de conocimiento no toca código. Los controles reales son los de la tabla siguiente.

**Controles mecánicos, que no dependen de que el agente obedezca:**

| Control | Qué impide |
|---|---|
| `.claude/settings.json` con `permissions.deny`: `Edit`/`Write` sobre `sources/**`, `sources.manifest.yaml`, `raw/**`, `extraction/**`, `build/**`, `kb/_meta.yaml`, `.claude/**` y `CLAUDE.md`; `Read` sobre `**/*.p12`, `**/*.pfx`, `**/*.key`, `**/*.pem` y la carpeta de XML reales (ruta absoluta); `Bash(git push*)`, `Bash(git merge*)`, `Bash(gh pr merge*)`, `Bash(gh api*)`, `Bash(*sifen source add*)` [verificar la sintaxis, también la de rutas absolutas en Windows] | Que Claude edite evidencia, metadatos o sus propias reglas, registre fuentes, mergee o lea secretos con sus herramientas. Bash sigue siendo una vía: la cubren las filas siguientes. |
| `test_sources_hash_matches_manifest`, `extract --check` en CI; `source add` solo descarga de dominios DNIT de una lista permitida | Fuentes alteradas o inventadas, incluso por un comando Bash. |
| `test_literals_equal_raw_cells`, `test_rowref_matches_entity`, `test_quotes_in_raw_page`, `test_date_cells_match_attribute`, `test_condition_constants_in_literal` | Literales inventados, truncados o parafraseados; una fila de otra entidad (la regla de D208b asignada a D208c); fechas de test y producción intercambiadas; umbrales mal copiados (70.000.000 en vez de 7.000.000). |
| `test_past_changes_justified` (contra la base de `main`) | Borrar versiones, efectos o filas golden; editar el pasado sin un Issue que lo declare. |
| Check `pr-scope` en CI: un PR que toca `kb/`, `tests/golden/`, `cases/` o `curation/` no puede tocar `src/`, el resto de `tests/`, `.github/`, `.claude/`, `CLAUDE.md`, `pyproject.toml` ni `uv.lock`; a la inversa, un PR de código no toca `kb/`, salvo una excepción declarada: si cambia el extractor, puede regenerar `raw/` y volver a copiar con `sifen draft` los literales afectados, y el check admite en `kb/` solo esos cambios | Que un PR de curación desactive el test que lo detectaría. |
| Protección de `main`: PR obligatorio, CI en verde, sin *force-push* ni borrado, **sin bypass para administradores** ("Do not allow bypassing the above settings"). En repos privados requiere GitHub Pro, Team o superior (o el equivalente de GitLab o Azure DevOps) [verificar plan] | Que un cambio llegue a la KB sin PR ni CI. |
| Con una persona: PR sin aprobación requerida (GitHub no permite aprobar el propio), revisión en una sesión distinta y posterior a la curación, con *checklist* (fechas contra el PDF renderizado, alcance declarado, Issues, cambios al pasado), y trailer `Reviewed-by:` en el merge; el CI crea el tag `kb-AAAA.MM.DD` solo si el trailer existe. Con dos personas (condición de la Fase 3): aprobación obligatoria y CODEOWNERS sobre `kb/`, `tests/`, `src/sifen_kb/{integrity,temporal,yamlio,normalize,sources,extract}.py`, `extraction/`, `sources.manifest.yaml`, `.github/`, `.claude/`, `CLAUDE.md`, `pyproject.toml` y `uv.lock` | Que un cambio normativo llegue a una release sin revisión humana. |
| Sesiones de curación sin credenciales de push ni acceso a certificados [verificar cómo aislarlas en Windows] | Que un comando Bash eluda los `deny`. |
| gitleaks + bloqueo de extensiones en CI | Secretos y certificados en el historial. |

---

## K. Tests

La pirámide se ordena por **qué error detecta** cada capa, no por volumen. Todo corre con `pytest`; `sifen check` ejecuta el subconjunto rápido durante la curación.

**1. Unitarios (milisegundos)**
- `test_kbloader_codes_stay_strings`: `0160`, `0260`, `NO`, `on`, `1.50` y `2024-04-01` llegan como `str`.
- `test_kbloader_rejects_duplicates_anchors_aliases`: error con número de línea.
- `test_fmt_roundtrip`: un comentario o un `" #"` que trunca rompen la igualdad cargar-volcar.
- `test_normalize_idempotent` y sus casos: celda multilínea, guion blando, `1-15p(0-` + `8)`.
- `test_occurrence_parser`: `1-1`, `0-1`, `0-999`, `0-n`, `1`, `-`. `test_date_literal_parsing`: `"01/01/2025"` → 2025-01-01.
- `test_dsl_whitelist`: rechaza `__import__`, atributos, `lambda`, comprensiones, comparaciones encadenadas, nombres que no son IDs de campo y `AND` (con un mensaje que sugiere `and`).
- `test_dsl_kleene`: tablas de verdad; una lectura sin guarda de un campo ausente da UNKNOWN (independiente del orden de los operandos); con la condición de D208c, D208 ausente → FALSE gracias a `exists()`.
- Resolvedor: `test_resolver_semiopen_boundary`, `test_resolver_tombstone`, `test_resolver_prospective_in_upcoming_never_in_force`, `test_resolver_pending_without_date_is_visible`, `test_resolver_duplicate_start_is_error`, `test_resolver_test_date_missing_is_undetermined`, `test_resolver_file_order_irrelevant` (dos órdenes fijos), `test_resolver_issue_window`, `test_resolver_beyond_horizon` (aviso en la gracia, `undetermined` después), `test_resolver_revision_not_curated`, `test_resolver_processing_date_unknown`, `test_resolver_severity_versioned` (sobre [HIP]).
- `test_cli_output_utf8_piped`: ejecuta `explain 1321` en un subproceso con `PYTHONIOENCODING=cp1252` y la salida por tubería; "≠" y "≥" deben salir en UTF-8 con LF. Así el problema medido en Windows se detecta también en el CI de Linux.

**2. Propiedades con Hypothesis (solo el resolvedor; en CI con `derandomize=True`)**
Sobre historiales aleatorios con fechas por ambiente, lápidas, prospectivas, pendientes y orden de archivos barajado: como máximo una versión por fecha; el resultado solo cambia en las fronteras; el orden de los archivos no altera el resultado; tras una lápida, `removed`; **toda prospectiva y todo pendiente futuro aparecen en `upcoming` y nunca son `in_force`**. Se justifica porque el resolvedor es el único componente donde un error silencioso produce un "vigente" falso, y los errores que la revisión encontró en el pseudocódigo (pendientes sin fecha, prospectivas filtradas) son justo los que estas propiedades atrapan. El DSL se cubre con unitarios; Hypothesis vuelve para el CDC cuando llegue el sanitizador.

**3. Evidencia (anti-alucinación, anti-R6)**
- `test_sources_hash_matches_manifest`; `test_manifest_append_only`; `test_current_revision_in_manifest`; `test_raw_regenerates_identically` (CI).
- `test_golden_pages_cells`: celda a celda contra las páginas transcritas a mano.
- `test_refs_resolve_uniquely`: cada `RowRef`/`CellRef` resuelve a exactamente una fila (y una celda).
- `test_literals_equal_raw_cells` (con `normalize_text` y las correcciones de `extraction/fixes.yaml`).
- `test_rowref_matches_entity`: la clave de fila citada (tras correcciones) es el `id` del campo o de la validación, y la celda de código es igual a `code`. `test_effect_target_matches_row_id`: un efecto cuya fila trae ID apunta a esa entidad.
- `test_quotes_in_raw_page`; `test_date_cells_match_attribute`: el literal es igual a la celda citada, el encabezado de su columna corresponde al atributo (`test` → "…Ambiente de Test", `prod` → "…Producción") y `value == parse(literal)`.
- `test_condition_constants_in_literal`: `7000000` ↔ `7.000.000`; si el curador escribe 70.000.000, falla.
- `test_enum_labels_in_observations`.
- `test_coverage_guard`: el vocabulario del piloto (IDs, códigos, `xml_name`) se busca en el `raw/` de las 27 NT; toda mención debe estar reconocida por un efecto (aplicado, `pending` o `not_modeled` con nota). Caso real: NT 14 y NT 27 mencionan `iTipIDRec` en la nominación; sobre `field:DE:D208` quedan `not_modeled`.

**4. Integridad del catálogo real**
- `test_all_kb_files_validate`, `test_key_matches_path`, `test_paths_unique_case_insensitive` (Windows).
- `test_references_exist`: `subject_field`, nombres del DSL, destinos de efectos, entidades de casos, sujetos de Issues, `introduced_by`, `based_on`, `CaseRef`.
- `test_effect_version_bijection`: cada efecto sin `disposition` está en exactamente una versión; los efectos de una versión comparten inicio por ambiente; los `pending` y `not_modeled` no tienen versión.
- `test_based_on_is_temporal_predecessor`; `test_env_inversion_has_issue`.
- `test_diff_within_declared_scope` (con `acknowledged_changes` cuando el alcance es `row`) y `test_interpreted_change_requires_literal_change` (anti-R3).
- `test_unique_start_per_env`; `test_approx_starts_before_coverage` (A1: ningún inicio aproximado cae después de `coverage_from`).
- `test_temporal_referential_integrity`: en cada punto de cambio, toda validación vigente referencia campos vigentes (NT 10 eliminó `dSisFact`: nada vigente después puede usarlo).
- `test_code_collisions_declared`: el índice N:M solo admite colisiones con un Issue `code_collision`. En el piloto no hay colisiones reales, y precisamente por eso detecta una fila o un código asignados a la entidad equivocada.
- `test_dates_sane`: `test ≤ prod`; más de 90 días entre `document_date` y la fecha de test exige Issue `erratum` (así se detecta NT 25).
- `test_past_changes_justified`: contra la base de `main`, nunca se borra una entidad, versión, efecto o fila golden ni cambia `introduced_by`; modificar un atributo de una versión existente o una expectativa golden exige un Issue `curation_error`, `erratum` o `temporal` del mismo PR que lo liste en `corrects`; el informe del PR enumera aparte los "cambios al pasado".
- `test_llm_runs_cover_outputs`; `test_cases_sanitized` (M).

**5. Golden temporal declarativo** (`tests/golden/temporal.yaml`, al estilo de OpenFisca)

Formato: `{key, at, env, kb?, processed_at?, expect}`. Regla de completitud: **cada frontera de cada patrón temporal del piloto tiene una fila el día anterior y otra el día del cambio, en cada ambiente donde las fechas difieran**.

```yaml
- {key: "val:DE:D208c",  at: "2024-12-31", env: prod, expect: {state: in_force, introduced_by: ["NT_021#1"]}}
- {key: "val:DE:D208c",  at: "2025-01-01", env: prod, expect: {state: in_force, introduced_by: ["NT_024#1"]}}
- {key: "field:DE:D208", at: "2024-09-15", env: test, expect: {enum_includes: "6"}}    # NT 23 test 30/08 [V]
- {key: "field:DE:D208", at: "2024-09-15", env: prod, expect: {enum_excludes: "6"}}    # NT 23 prod 27/09 [V]
- {key: "val:DE:D208b",  at: "2024-09-26", env: prod, expect: {state: in_force}}
- {key: "val:DE:D208b",  at: "2024-09-27", env: prod, expect: {state: undetermined, reasons: [blocking_issue]}}  # ISS-0002
- {key: "val:DE:D208d",  at: "2025-03-01", env: prod, expect: {state: removed, introduced_by: ["NT_002#1"]}}    # derivada de la curación [VERIFICAR-DNIT]
- {key: "val:DE:D208c",  at: "2027-01-01", env: prod, expect: {state: undetermined, reasons: [beyond_horizon]}}
```
Incluye todas las filas de G.5, D208e (C002 = 5,6,7 por NT 23, con test ≠ producción), `test_watermark_oracle` (fin de la versión de NT 21 = `superseded_by.since` = 2025-01-01), `explain 1400` → `not_curated` con NT 26 primera, y el escenario [HIP] completo sobre `tests/fixtures/kb_hyp/` y su variante.

**6. XSD y XML (sin red)**
- `test_xsd_loads_offline`: socket bloqueado, `uri_mapper` hacia copias locales.
- `test_xml_names_exist_with_parent`, `test_xpath_unique_in_context`, `test_occurrence_vs_xsd` (contra la versión vigente en producción en el `retrieved_at` de la instantánea; todo desacuerdo con Issue). Las facetas y longitudes se comparan en la Fase 3.
- `test_xsd_anachronism_flag`: una consulta anterior a la instantánea marca el bloque XSD como anacrónico y no cambia el estado.
- `test_xml_fixture_verdicts` (todos con fecha de procesamiento explícita salvo el último): innominado PYG 7.000.000 en 2025-02 → TRUE; 6.999.999 → FALSE; 8.000.000 en 2024-06 → FALSE (umbral 35 M); moneda extranjera con F023 ≥ 7 M → TRUE; moneda extranjera con F014 ≥ 7 M y F023 < 7 M → TRUE según el paréntesis, con el *gap* visible (la prosa daría FALSE); receptor sin D208 → FALSE; emisión y procesamiento a ambos lados de 2025-01-01 → `undetermined` (`axis_split`); sin fecha de procesamiento → `undetermined` (`processing_date_unknown`).
- `test_xml_untouched`: hash del archivo antes y después; `dNumIDRec` enmascarado; aviso de "primer error" presente.
- `test_pii_elements_exist_in_xsd`: los nombres de elementos que vigila `test_cases_sanitized` existen en la instantánea.

**7. Contrato y aceptación**
- `test_explain_json_snapshot`: protege a Claude, a los scripts y al futuro MCP de cambios de formato involuntarios.
- `test_replay_nt024`, determinista: se parte de una KB fixture sin NT 24, del `raw/` de NT 24 y del efecto `NT_024#1` escrito a mano; se ejecuta `sifen draft NT_024#1`; el diff contra la versión de NT 21 debe tocar solo `observation` y `condition`, y ninguna resolución anterior al 2025-01-01 debe cambiar.
- `test_seeded_errors_detected`: en una rama de *fixtures*, cinco errores sembrados deben fallar los cinco: una cita inventada, un cambio fuera del alcance declarado, una mención no reconocida, un cambio de severidad sin reconocer con alcance `row`, y la fila de una entidad asignada a otra.

**Fuera de pytest:** la evaluación ciega (T.8) y el cronometraje (T.12). **No se hace en el MVP:** *mutation testing*, umbrales de cobertura de código, tests de CDC, control cruzado entre motores, parser de longitudes y comparación de facetas (Fase 3).

---

## L. CI/CD

Un workflow y un job Linux, en cada PR y en cada push a `main`:

```
uv sync --locked --group ingest                  # falla si el lock no corresponde
uv run ruff check . && uv run ruff format --check .
uv run sifen fmt --check                         # canónico sin comentarios ni truncamientos
uv run sifen extract --check                     # raw/ regenerado == versionado (byte a byte)
uv run pytest -q                                 # capas 1–7 (fetch-depth 0 para test_past_changes_justified)
gitleaks git --redact                            # binario fijado; reglas por defecto
pr-scope: un PR de conocimiento no toca código, CI ni configuración (J)
sources/: solo adiciones · sin *.p12 *.pfx *.key *.pem *.jks
release: tag kb-AAAA.MM.DD solo si el merge lleva Reviewed-by; adjunta sources.manifest.yaml
```

`setup-uv` con versión fija; Python según `.python-version`. Windows no corre en CI en el MVP: el desarrollador trabaja en Windows y la DoD exige adjuntar al PR el log de una corrida local completa; el riesgo medido de codificación lo cubre `test_cli_output_utf8_piped` en Linux, y el de fin de línea, `.gitattributes` y los escritores con `newline="\n"`. Requisito previo: un plan con protección de rama en repos privados (J). **No entran:** CD, contenedores, cachés de modelos, publicación de paquetes ni export JSON. **Fase 2:** matriz Windows, basedpyright, `sifen build` (`build/kb.json` y su JSON Schema, adjuntos al release) y el `source check` semanal programado que abre un *issue*. **Fase 4:** el detector abre un PR con `sources/`, `raw/` y el esqueleto. Nota: `gitleaks-action` exige licencia para cuentas de organización; por eso se usa el binario.

---

## M. Seguridad

| Clase | Ejemplos | Dónde vive |
|---|---|---|
| Pública | PDF y XSD de DNIT, la KB, CSC **de test** publicados por DNIT (`ABCD000…`, `EFGH000…`) [V], el **concepto** `dCodSeg` (parte del CDC, visible en el KuDE) | En el repo (privado igualmente) |
| Confidencial | XML reales, respuestas de SIFEN, RUC, cédulas y nombres de receptores, CDC reales, `dCodSeg` reales (junto con RUC, número y fecha reconstruyen un CDC real), montos, logs de rechazos | Fuera del repo, en una carpeta única (p. ej. `C:\sifen-privado\xml\`), fuera de OneDrive si la política lo exige |
| Secreta | Clave privada, P12/PFX y su contraseña, CSC de producción (con él se fabrican QR "auténticos" [V]), *tokens* | Nunca en el repo, ni en la conversación con Claude, ni accesible desde el perfil donde corren las sesiones de curación |

Medidas:
1. `explain --xml` abre el XML en solo lectura (`defuse="always"`, sin red), imprime solo los campos que usa la regla y enmascara la PII por defecto (`dNumIDRec` → `****567`); `--show-pii` existe solo para uso humano local. La regla se evalúa con los valores completos; Claude ve lo mínimo. La salida avisa siempre: "SIFEN informa el primer error; otras reglas pueden no haberse evaluado o informado" [V: MT §12; `gResProc` admite hasta 100 resultados].
2. **El flujo natural elude el enmascarado**: si el usuario dice "te paso el XML" y Claude lo abre con Read o `cat`, el XML completo —RUC, nombres, URL del QR con `dRucRec`/`dNumIDRec`, `X509Certificate`— va a la API y queda en las transcripciones locales. Por eso: carpeta única para XML reales; `deny` de `Read` sobre ella [verificar sintaxis de ruta absoluta]; regla 2 de CLAUDE.md; y, si la versión instalada lo permite, *sandbox* de Bash con restricción de lectura sobre esa carpeta y los certificados, exceptuando `uv run sifen` [verificar]. Riesgo residual declarado: un comando Bash no previsto todavía puede leer el archivo.
3. **Política de envío a Claude**: que Claude lea un XML real significa enviarlo a la API de Anthropic. Es una decisión de la empresa (V.2). Mientras tanto, solo la salida enmascarada.
4. **Casos**: `sanitized: true` y `origin: observed` obligatorios; los sintéticos viven en `tests/fixtures/cases/`. `test_cases_sanitized` valida **por nombre de elemento**, no por una regex de RUC con guion (el RUC viaja sin guion y con el DV en otro elemento): los valores de `dRucEm`, `dRucRec`, `dNumIDRec`, `dNomEmi`, `dNomRec`, `dDirEmi`, `dDirRec`, `dTelRec`, `dEmailRec`, `dCarQR` y `X509Certificate` deben estar en `tests/allowlist_pii.yaml` (valores sintéticos); como segunda capa, regex de RUC con o sin guion cerca de "RUC", CDC de 44 dígitos y correos. En la Fase 2, `sifen sanitize` determinista: reemplaza RUC y recalcula su DV (algoritmo módulo 11 [P], probado contra el CDC de 44 caracteres del ejemplo de QR del MT), recalcula el CDC, elimina `ds:Signature`, `gCamFuFD` y el QR (llevan el hash con CSC) y marca el XML como "ya no firmado".
5. **Secretos**: `.gitignore` y check de CI por extensión (`*.p12 *.pfx *.key *.pem *.jks`), gitleaks con reglas por defecto (la regla propia para CSC —32 alfanuméricos cerca de `IdCSC`, con lista permitida para los de test— llega con el sanitizador), `deny` de lectura en Claude Code.
6. **Entradas**: pdfminer.six 20260107, exigido por pdfplumber 0.11.10 (corrige las CVE de CMaps, presentes antes de 20251230); RAR extraídos en un directorio aislado sin ejecutar nada; CI sin secretos (no consulta servicios).
7. **Escritura determinista**: `main()` reconfigura stdout y stderr a UTF-8 con LF y todo escritor usa `encoding="utf-8", newline="\n"`; sin esto, el literal de D208c ("≠", "≥") lanza `UnicodeEncodeError` en Windows cuando la salida va por tubería, que es como la captura Claude Code (se midió cp1252 en stdout por tubería con 3.14; el error es su consecuencia directa).
8. Repositorio privado; tratamiento de datos personales a revisar con el área legal según la normativa paraguaya [VERIFICAR con legal].

---

## N. Escalabilidad

El volumen de datos es trivial (miles de registros). **Lo que escala mal es la curación humana**: la arquitectura escala si cada NT cuesta poco revisar, y por eso la Fase 1 mide ese costo contra un umbral y tiene una regla de recorte (U).

| Etapa | Alcance | Qué se agrega |
|---|---|---|
| **MVP** (Fases 0–1) | Índice de menciones y calendarios de todo el corpus (entregable 0) + receptor/identidad curado | Resolvedor, DSL escalar, evidencia por celda, horizonte, `explain`/`status` |
| **v1** (Fases 2–3) | Fase 2: segundo dominio con grupos repetidos (E6xx) y las entidades GENFE010 y GED003. Fase 3: DE completo (cap. 10 + §12.4 + 27 NT) | Fase 2: DSL con `any_item`/`sum`/`count`, sanitizador, `validate`, `timeline-diff`, `render`, `build`, `source check` programado, generador de esqueleto de efectos, clasificación de re-subidas, basedpyright, CI Windows. Fase 3: tablas completas con su batería, SQLite FTS5, `analyze`, `search` |
| **v2** (Fase 4) | Eventos, WS, codificaciones; códigos fuera de tablas (0364, 0422) y 0160, cuyo `dMsgRes` agrega una lista de errores de esquema | `EventType`, `Service`, `Code`, detector que abre PR, MCP read-only |

**No construir todavía (ni probablemente nunca):** UI web, bases vectoriales o de grafos, bitemporalidad en datos, motor de patches, auto-merge de cambios normativos, agentes autónomos, generación o firma de XML, envío a SIFEN, evaluación de reglas no formalizadas, convivencia de versiones y plataforma genérica para Genesys/Dynamics/SAP. Para esos sistemas se reutiliza la **metodología** (fuentes por hash → evidencia → canónico por entidad → versiones con citas → golden temporal), no el código; generalizar `Ctx` o las claves antes de un segundo dominio real es exactamente la sobreingeniería a evitar.

---

## O. CLI inicial

```
# Consulta
sifen explain <código|ID|xml_name|DocId> [--at AAAA-MM-DD] [--env prod|test] [--history] [--json]
sifen explain <código|ID> --xml RUTA [--response RUTA | --processed-at AAAA-MM-DD] [--env prod|test] [--json]
sifen status            # horizonte de fuentes, cambios sin registrar, revisiones sin curar, pendientes,
                        # Issues bloqueantes, cobertura y supuestos sin verificar
# Mantenimiento
sifen source check      # hash de las URL conocidas y de los listados (NT, XSD, tablas); registra el chequeo, nada más
sifen source add --doc <DocId> --url <url>      # acción humana; solo dominios DNIT; descarga, hashea y registra
sifen extract [--check]
sifen draft <DocId>|<EffectId>   # DocId: calendario desde la tabla de fechas · EffectId: versión desde las celdas
sifen check             # esquema, fmt, integridad, evidencia, cobertura (rápido)
sifen fmt [--check]
```

`explain` reemplaza `get-field` (si un ID es a la vez campo y validación, como D208, devuelve ambos etiquetados), `get-validation` (si un código mapea a varias validaciones, incluidas lápidas, las lista todas), `rule --at`, `diff` (`--history`), `source NT_024` (con un `DocId` muestra revisiones del manifiesto, calendario por ambiente, efectos y su estado) y un `analyze` acotado (`--xml`: validación XSD de la instantánea, con marca de anacronismo, y evaluación TRUE/FALSE/UNKNOWN de esa regla con ambas fechas). Con `--xml` no se admite `--at`. Si la entidad no está curada responde `not_curated` con sus menciones literales en `raw/`, ordenadas por fecha de producción del documento (nunca por número de NT), la más reciente primero, con página impresa y PDF, un extracto y el aviso obligatorio "vigencia no resuelta: una mención posterior puede modificar o eliminar la regla". `update` no existe: el flujo es `source check` → `source add` → `extract` → `draft` → PR. Se posponen `validate`, `sanitize`, `timeline-diff`, `render` y `build` (Fase 2), y `analyze` completo y `search` (Fase 3).

```
$ sifen explain 1321 --at 2025-01-10
val:DE:D208c · código 1321 · R · IN_FORCE (prod · eje: procesamiento [supuesto A2])
  Versión     NT_024#1 · desde 2025-01-01 (declarada en NT 24, rev <sha12>) · hasta: abierta
  Literal     «…es mayor o igual a 7.000.000 (F023 >= 7.000.000 o F014 >= 7.000.000)»  NT 24 p.<n>
  Historia    MT v150 (base, ≥60 M) → NT 21 (2024-01-01, ≥35 M) → NT 24 (2025-01-01, ≥7 M)
  Violación   [interpretación, parcial] (not exists(D011) or D011 != 13) and exists(D208) and D208 == 5 and (…)
  Campos      D208 iTipIDRec (D3/D200, N 1, 0-1) · D011 iTipTra · F014 dTotGralOpe · F023 dTotalGs
  XSD         instantánea 2026-10-17, posterior a la fecha consultada: referencia, no evidencia de 2025
  Avisos      ISS-0005 gap: la prosa asocia F023/F014 a la moneda (D015); se formalizó el paréntesis
  Fuentes     verificadas el 2026-10-17 (hace 0 días)
  KB          kb-2026.11.xx · corpus MT_V150 + NT_001–NT_027 · curado: receptor/identidad
```

---

## P. MCP

**Cuándo (Fase 4), solo si se cumplen tres condiciones:** existe un consumidor que **no** es Claude Code (Claude Desktop, claude.ai u otro agente sin shell; para Claude Code, la CLI con `--json` + CLAUDE.md ya cumple la función); el contrato JSON de `explain` pasó dos ciclos de NT sin cambios incompatibles; y la KB cubre más que el piloto (un MCP con 25 entidades invita a preguntas que no sabe responder).

**Cómo:** servidor stdio local, **solo lectura**, que envuelve la librería `sifen_kb.explain` (no la CLI); cada respuesta lleva `state`, `reasons`, avisos, horizonte de fuentes y `kb_snapshot`. Herramientas: `get_entity(key, at?, env?)` (resuelta en una fecha) separada de `get_history(key, env?)` para que un agente no confunda lo histórico con lo vigente; `lookup_code(code, at?, env?)` (con lápidas); `get_document(doc_id)`; `list_pending(key?)`; `list_issues(key?)`; `check_xml(code, xml, response? | processed_at?)` con el mismo enmascarado; `search(text)` cuando exista FTS5. Ninguna herramienta de escritura. Al llegar el primer consumidor externo entra también `schema_version` en el contrato.

---

## Q. RAG / embeddings

- **Ahora: no. Para resolver reglas: probablemente nunca. Para casos: posiblemente después.**
- Las consultas reales llegan con identificadores exactos (1321, D208c, `iTipIDRec`): un índice exacto gana y no confunde D208c con D208f.
- R8 es **inherente** a recuperar por similitud: los textos de NT 21 y NT 24 son casi idénticos salvo el número. La vigencia solo la decide el resolvedor. El índice de menciones de `not_curated` es recuperación sin resolución, y por eso sale siempre con estado propio y aviso obligatorio.
- FTS5 en la Fase 3 (`unicode61 remove_diacritics 2` para español; `trigram` para nombres XML), devolviendo **claves** que pasan siempre por el resolvedor.
- Embeddings solo si, con cientos de casos, FTS5 no encuentra la entidad correcta en el top 5 en más de ~20 % de una evaluación medida. Aun así solo recuperarían candidatos; la respuesta sale de `explain`.

---

## R. Riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| 1 | **La KB dice "vigente" ignorando una NT, una re-subida o un XSD cambiado in situ** | Alta | Alto | Horizonte de fuentes con `source check` desde el MVP (después de la gracia, `undetermined`); `revision_not_curated` derivado del manifiesto; efectos `pending` publicados antes de curar; guardián de cobertura; chequeo programado en la Fase 2. Residual: una NT subida después de su vigencia (NT 22, 26 días) puede afectar fechas anteriores al horizonte. |
| 2 | **Fecha o eje temporal equivocados** (NT 001–012 sin vigencia, test frente a producción, emisión frente a procesamiento, prórrogas) | Alta | Alto | Calendario por ambiente copiado de la celda y verificado por encabezado; revisión humana de toda fecha; doble resolución con XML y fecha de procesamiento tomada de la respuesta; `coverage_from`; consulta a DNIT por A1/A2. |
| 3 | **La curación no da abasto**: proyecto académico o KB obsoleta (R1, R7) | Alta | Alto | Entregable 0 con valor antes de curar; MVP cerrado; literales y fechas copiados por herramienta; costo por NT medido contra un umbral; regla de recorte (U). |
| 4 | **El LLM formaliza mal una condición** (polaridad, moneda, campo ausente) (R2) | Media-alta | Alto | Literal siempre visible; `level` y `gaps`; constantes ⊂ literal; `exists()` explícito y Kleene para lecturas sin guarda; *fixtures* de frontera; salida "posible violación según la versión X". |
| 5 | **Exceso de confianza en la salida** (R9) | Media | Alto | Seis estados con `reasons`; avisos obligatorios; horizonte visible; CLAUDE.md exige transmitirlos; evaluación ciega con clave de respuestas y preguntas trampa. |
| 6 | **Cambio parcial tratado como total o cambio no declarado** (R3) | Media | Alto | Versión completa + `declared_scope` + `acknowledged_changes` + herencia desde la predecesora temporal + campo y validación separados. |
| 7 | **Errores silenciosos de extracción** (R6) | Media | Medio (MVP) / Alto (Fase 3) | Literal = celda normalizada; fila = entidad; *golden pages*; `extract --check`; correcciones auditadas; control cruzado entre motores y batería completa en la Fase 3. |
| 8 | **Conflictos entre fuentes, o servidor real ≠ documentación, resueltos en silencio** (R4) | Alta (ya existen) | Medio | Issues de primera clase con ventana; autoridad por dimensión; `blocking` → `undetermined`; casos que contradicen la KB abren Issue. |
| 9 | **Claude o un humano corrompe el canónico** (R10) | Media | Alto | `deny`; separación de PR de conocimiento y de código; literales ligados a celdas; pasado solo con corrección declarada; rama protegida sin bypass; protocolo de una persona con `Reviewed-by`. |
| 10 | **Fuga de datos** (XML reales, CSC, certificados) | Baja-media | Alto | XML en carpeta única fuera del repo con `deny`; enmascarado; política explícita de envío a Claude; gitleaks + extensiones; tests de sanitización por elemento. |

Riesgos del pedido: R1 → #3 (y #1); R2 → #4; R3 → #6 (confirmado: las NT no muestran antes/después [V]); R4 → #8 (no es un riesgo, es una condición del dominio); R5 → **bajo por diseño** (un solo editable; la única copia, los literales, está ligada por test, y la obligatoriedad se formaliza una sola vez); R6 → #7; R7 → #3 (cero servidores y tres dependencias de runtime); R8 → **eliminado en las entidades curadas** (sin RAG); residual en el índice `not_curated`, siempre con aviso, y en una NT no registrada (#1); R9 → #5; R10 → #9.

---

## S. MVP concreto

**Objetivo único:** "Analiza el rechazo 1321" (y los demás códigos del dominio) se responde con la versión correcta para la fecha y el ambiente, la cita literal verificada (documento, revisión, página), el historial, los campos relacionados con su estado XSD y avisos honestos; opcionalmente, evaluada contra un XML sin modificarlo. Y desde el entregable 0, cualquier código fuera del dominio recibe al menos sus menciones ordenadas por vigencia, marcadas `not_curated`.

**Secuencia** (U, Fase 0): **entregable 0** (índice de menciones + calendarios) → **entregable 1** (esqueleto de punta a punta de D208c) → MVP completo.

**MVP = solo esto (lista cerrada):**
- `sources/` con su manifiesto; `source check` mínimo.
- Texto por página de todo el corpus con un solo motor; celdas solo de las filas del piloto y de las tablas de fechas.
- `kb/` con una ficha por fuente del corpus (calendario por ambiente en NT 13–27), 10 campos y 12 validaciones DE, más los Issues iniciales.
- Resolvedor; DSL (parser con lista blanca y evaluador Kleene); XSD: existencia de `xml_name` con su padre y ocurrencia.
- Los ocho comandos de O.
- Tests: unitarios (loader, normalización, resolvedor, DSL, UTF-8); Hypothesis solo del resolvedor; evidencia (hash, literal = celda, fila = entidad, citas, fechas por encabezado, constantes, cobertura); integridad; golden temporal real + el escenario [HIP] (un fixture y una variante); *fixtures* XML; contrato y aceptación.
- CI Linux de un job; `deny`, hooks de bitácora y `pr-scope`.

**Pasa explícitamente a fases posteriores:** el segundo dominio, las sondas GENFE010 y GED003 (eventos), los grupos repetidos en el DSL, el generador de esqueleto de efectos, la detección programada, la clasificación de re-subidas (`content_change`), basedpyright, la matriz Windows en CI, `sifen build` (export JSON y JSON Schema), la regla gitleaks de CSC y el sanitizador (Fase 2); las tablas completas del MT, el control cruzado entre motores, el parser de longitudes, la comparación de facetas y SQLite/FTS5 (Fase 3); WS, codificaciones, `schema_version` y MCP (Fase 4). Nada de lo recortado afecta la correctitud temporal ni la trazabilidad del piloto.

**Corpus** (completo, porque es barato y lo necesitan el índice, la cobertura y el horizonte):
- MT v150, binario publicado hoy (sha256 `976cd88c…`, 5.204.470 bytes), y el listado de checksums MD5 (`CHECKSUM_MT`; Issue `source_conflict`).
- NT 001–027, revisión actual de cada una; las anteriores si alguien de la empresa las conserva (`origin: offline`, V).
- Instantánea de los 47 XSD (`XSD_DIR`) con fecha de ingesta; el RAR oficial (`XSD_RAR`) como fuente, sin compararlo todavía (Issue abierto).
- Decreto 872/2023 (`NORMA_DECRETO_872_2023`): se registra y se lee su literal antes de abrir cualquier Issue legal.

**Curación:**
- `kb/documents/`: una ficha por fuente (MT, 27 NT, XSD, RAR, checksums, decreto); calendario por ambiente de NT 13–27 con `sifen draft <DocId>` + revisión; fecha del documento y período de cambios de NT 001–012. La tabla de NT ya verificada en la investigación sirve de control cruzado.
- Efectos completos para las NT que tocan el piloto; las demás quedan en `curation_scope: dates_only`.
- Campos DE (10): C002, D011, D015, D201, D202, D208, D209, D210, F014, F023.
- Validaciones DE (12): D208 (1310), D208a, D208b (1319), D208c (1321), D208d (1322, lápida por NT 2), D208e (1331), D208f (1333), D208g (1335), D209a (1313), D210 (1314), D210a (1323, lápida por NT 2), D210b (1334).
- Issues iniciales: ISS-0001 MD5 del MT (`source_conflict`); ISS-0002 D208b frente a D208f (`undeclared_change`, bloqueante sobre D208b desde NT 23); ISS-0003 D208 frente a D208g (ídem sobre D208); ISS-0004 D210a frente a D210b (no bloqueante); ISS-0005 D208c, prosa por moneda frente a paréntesis (`ambiguity`, no bloqueante); ISS-0006 producción de NT 13 el 21/05/2023 según fuente secundaria [P] (`temporal`, no bloqueante). "Supere" frente a "≥" solo después de leer el decreto.

**Patrones temporales reales que ejercita:** umbral que cambia dos veces con fechas declaradas (D208c); test ≠ producción (D208 valor 6 y D208e por NT 23); lápidas sin calendario (D208d, D210a); ampliación de enumeración (D208); posible reemplazo no declarado (D208f ≈ D208b, D208g ≈ D208) con bloqueo por ventana; mismo `xml_name` en otro contexto (menciones de NT 14 y 27 reconocidas por el guardián); NT re-subida con marca de agua (NT 21, oráculo); NT sin fechas (NT 2, NT 10); índice `not_curated`; horizonte. El cambio de severidad se prueba con un unitario sobre [HIP].

**Entregables:** repositorio fuera de OneDrive con CI en verde; `sources/`, manifiesto y `raw/` completos; `kb/` del piloto; librería y los ocho comandos; tests de K; `golden/temporal.yaml` con el escenario D208c (real + [HIP]); CLAUDE.md, `.claude/settings.json` (deny + hooks), `curation/prompts/curar_entidad.md` y las corridas registradas; un caso real sanitizado si existe (los sintéticos solo como *fixtures*); informe de la evaluación ciega, del cronometraje y del costo de curación por NT.

---

## T. Definition of Done del MVP

La arquitectura "funciona" si **todo** lo siguiente se cumple y lo puede verificar un tercero:

1. **Reconstrucción limpia:** `git clone` → `uv sync --locked --group ingest` → `sifen extract --check` → `pytest` pasa en el CI de Linux y en una corrida local en Windows (log adjunto al PR), con `raw/` idéntico byte a byte.
2. **Exactitud temporal:** el 100 % de las filas golden pasan. Hay una fila el día anterior y otra el día de cada frontera, en cada ambiente donde las fechas difieren, para D208c, D208/D208e (NT 23), D208d, D208b/D208f, el oráculo de la marca de agua, el horizonte y el escenario [HIP] completo.
3. **Evidencia:** 100 % de los literales del piloto iguales a su celda normalizada; 100 % de las referencias resuelven a una única fila cuya clave es el ID de la entidad; 100 % de las fechas iguales a una celda del encabezado correcto y con `value == parse(literal)`; 100 % de las constantes del DSL presentes en su literal; 100 % de celdas correctas en las *golden pages*.
4. **Cobertura:** cero menciones del vocabulario del piloto sin reconocer en las 27 NT; cero efectos `pending` y cero revisiones sin curar sobre entidades del piloto; horizonte dentro de la gracia al publicar la release.
5. **Integridad:** cero referencias huérfanas; biyección efecto ↔ versión; `based_on` = predecesora temporal; integridad referencial temporal en todos los puntos de cambio; cero colisiones de código no declaradas; todo cambio al pasado justificado por un Issue.
6. **XSD:** todos los `xml_name` del piloto existen con el padre esperado; ocurrencias coincidentes o con Issue; carga sin red; la marca de anacronismo funciona.
7. **XML:** los *fixtures* dan exactamente TRUE/FALSE/UNKNOWN/`undetermined` con el motivo esperado, incluido "sin fecha de procesamiento"; el archivo no cambia; la PII sale enmascarada y el aviso de "primer error" aparece.
8. **Utilidad (evaluación ciega):** antes de ver salidas, el usuario escribe 15 preguntas de troubleshooting —10 normales y 5 trampas— y, para cada una, la clave de respuesta: estado, `introduced_by`, documento, página y avisos esperados. Claude responde en una sesión limpia usando solo la CLI; una respuesta es correcta si coincide en los cuatro primeros y transmite los avisos. Umbral: ≥ 14/15, **cero** reglas históricas presentadas como vigentes y **cero** `in_force` donde correspondía otro estado. Trampas: código fuera del piloto (`not_curated`), D208b después de NT 23 (`undetermined`), fecha anterior a la cobertura (`outside_coverage`), emisión y procesamiento a ambos lados de un cambio (`undetermined`), D208d en 2025 (`removed` con aviso de inicio aproximado). Se guarda la transcripción.
9. **Aceptación:** `test_replay_nt024` y `test_seeded_errors_detected` (5/5) pasan.
10. **Control de Claude:** un intento de Claude de editar `sources/` o de ejecutar `sifen source add` lo bloquea el `deny`; una alteración por otra vía hace fallar el test de hash; un PR que mezcla `kb/` con `tests/` o `src/` lo rechaza `pr-scope`; ningún cambio llega a `main` sin PR, tampoco el de un administrador; un merge sin `Reviewed-by` no produce release.
11. **Costo:** el tiempo de curación por NT del piloto queda registrado y no supera el umbral que el usuario fijó en la Fase 0.
12. **Valor:** se cronometran una vez tres rechazos del dominio piloto (reales, o reproducidos en el ambiente de test si no los hay), resueltos con la KB y con el flujo manual actual; la KB es más rápida en los tres.

---

## U. Roadmap (sin estimaciones de tiempo)

**Fase 0 — Entregable 0, spikes y entregable 1.**
- Repositorio fuera de OneDrive con `.gitattributes`, CI, `deny`, hooks y `pr-scope`; plan con protección de rama confirmado.
- `source add` del corpus, de la instantánea XSD y del decreto; `source check` mínimo; sondeo de páginas (capa de texto, imágenes, etiquetas), que decide si hace falta Docling.
- **Entregable 0:** texto por página de todo el corpus (un motor), `kb/documents/*.yaml` con la ficha y el calendario de cada fuente (literales de fecha verificados por contención en la página; desde el entregable 1, por celda) y `sifen explain <término>` en modo índice + `status` con el horizonte. Para 1321 ya devuelve MT p. 166 → NT 21 (2024-01-01) → NT 24 (2025-01-01), sin DSL, sin celdas y sin XSD, marcado `not_curated`.
- Spikes: extracción (pypdfium2 frente a pdfplumber frente al árbol de etiquetas, sobre las *golden pages*) y XSD (carga sin red; nombres reales de los atributos de ocurrencia en xmlschema).
- **Entregable 1:** MT + NT 21 + NT 24 → celdas → `kb/` (tres versiones con efectos y calendario) → `sifen explain 1321 [--at] [--env] [--json]` con estado, intervalo derivado y cita verificada → filas golden 1–5 de G.5 y el oráculo de la marca de agua. `--history` y `--xml` llegan en la Fase 1.
- Se lanza la consulta a DNIT por A1/A2 (tarda); se inventarían los códigos de rechazo más frecuentes de la empresa; el usuario fija el umbral de costo por NT y el N de la Fase 3, y escribe la clave de respuestas de T.8.

**Avanza si:** el entregable 0 responde `explain 1321` con las tres menciones ordenadas por fecha de producción; el entregable 1 reproduce las filas reales 1–5 y el oráculo; el extractor da 100 % en las *golden pages* (o se adopta el *fallback* explícito); el XSD carga sin red; los hashes de `raw/` coinciden en Windows y Linux; el inventario del piloto está cerrado.

**Fase 1 — MVP (S).** **Avanza si:** la DoD se cumple al 100 %, el costo de curación por NT no supera el umbral fijado en la Fase 0 y ningún concepto del modelo quedó sin usar con datos reales (un uso [HIP] no cuenta; lo que sobró se elimina antes de escalar). **Regla de recorte:** si al cerrar la Fase 1 el costo supera el umbral, la KB se congela como entregable 0 (índice + calendarios) más entidades curadas por demanda —los códigos que realmente aparecen—, en lugar de escalar al DE completo.

**Fase 2 — Segundo dominio y operación.** Condición de operación/crédito (E6xx: `gPaConEIni` 0-999, E605a/E605b, 1551) con el caso del pedido corregido; GENFE010 (contexto `EV-NOM`) y GED003 (severidad, `EV-DES`) como primeras entidades de eventos; DSL con grupos repetidos; sanitizador y regla gitleaks de CSC; `validate`, `timeline-diff`, `render` y `build`; `source check` semanal programado que abre un *issue*; generador del esqueleto de efectos; clasificación `content_change` de re-subidas; basedpyright; CI Windows. **Avanza si:** `model.py` solo tuvo cambios aditivos; pasa una segunda evaluación ciega; una NT o re-subida (real o simulada) se procesó siguiendo solo README, CLAUDE.md y el prompt de curación, sin cambios de código.

**Fase 3 — DE completo.** Tablas completas del MT con la batería de I (control cruzado entre motores, parser de longitudes, facetas); curación por lotes; efectos de las 27 NT para todo el DE (100 % de filas cubiertas); SQLite FTS5 derivado; `analyze` y `search`; segundo revisor con criterio fiscal y CODEOWNERS obligatorios. **Avanza si:** cero `pending` en el DE; cruce XSD completo; *golden pages* al 100 %; `analyze` coincide con el Prevalidador oficial en un conjunto de XML de prueba [VERIFICAR-DNIT su uso como oráculo]; al menos N rechazos reales registrados en `cases/` y resueltos con `explain` en el último mes.

**Fase 4 — Eventos, WS, codificaciones y MCP.** `EventType`, `Service`, `Code` (0364 y 0422 como `documented_outside_tables`; 0160 con su lista de errores en `dMsgRes`); golden de los códigos reasignados por NT 18 (4313–4323 antes y después); detector que abre un PR con `sources/`, `raw/` y el esqueleto; `schema_version`; MCP si se cumplen las condiciones de P. **Avanza si:** hay un consumidor no CLI identificado y el contrato JSON no tuvo cambios incompatibles durante dos ciclos de NT.

**Fase 5 — Automatización progresiva.** Borradores de PR por Claude ante un hash nuevo (merge siempre humano); merge automático solo de re-subidas con texto idéntico, por una cuenta bot con excepción explícita; evaluación de embeddings para casos con el criterio de Q; si DNIT publica un MT consolidado, usarlo como oráculo de regresión (el estado de la KB a esa fecha debe coincidir). **Avanza si:** tres NT seguidas pasan por el flujo sin errores detectados después del merge.

---

## V. Preguntas abiertas (solo las que bloquean el inicio)

**Las decide el usuario o la empresa:**
1. **Revisor y hosting:** ¿quién aprueba los PR de `kb/` (idealmente alguien con criterio fiscal que no curó)? ¿GitHub con un plan que permita proteger ramas en repos privados (Pro, Team o superior), o GitLab/Azure DevOps? Si el equipo es una persona, ¿se acepta el protocolo de una persona de J hasta la Fase 3?
2. **Política de datos con Claude:** ¿pueden XML reales y casos con datos de clientes enviarse a la API de Anthropic? Define si `--xml` enmascara o si se prohíbe adjuntar XML.
3. **Cobertura temporal:** ¿hasta qué fecha hacia atrás se necesita diagnosticar? Propuesta: `coverage_from = 2023-06-17`. Si hace falta 2022 o antes, las NT 001–012 necesitarán fechas confirmadas.
4. **Piloto:** ¿cuáles son los 5–10 códigos de rechazo más frecuentes? Si no están en receptor/identidad, el piloto cambia de dominio y conserva D208c, D208d y D208e como canarios temporales.
5. **Línea base:** ¿se acepta el MT publicado hoy (sha256 `976cd88c…`) como base, registrando que su MD5 no coincide con el certificado? Recomendación: sí; es el único disponible por el canal oficial.
6. **Umbrales:** costo máximo de curación por NT (T.11 y regla de recorte), N de la Fase 3 y gracia del horizonte (propuesta: 7 días).

**Se preguntan a DNIT** (no bloquean: se lanzan en la Fase 0, con el valor por defecto entre paréntesis):
- ¿Las validaciones se aplican según la fecha de procesamiento o según `dFeEmiDE`? (procesamiento; con XML, ambas → `undetermined` si difieren). ¿En qué formato y zona horaria viene `dFecProc` (`fecUTC`)?
- ¿Desde cuándo rigieron en producción NT 001–012? (antes de `coverage_from`, supuesto A1). ¿Se prorrogó NT 13 del 21/05 al 17/06/2023?
- ¿"Puesta a disposición" equivale a "empieza a aplicarse" para una validación, y desde qué hora? (sí, 00:00 de Asunción).
- ¿D208b (1319) sigue vigente junto a D208f (1333)? ¿Y D208 (1310) junto a D208g (1335)? (mientras tanto, D208b y D208 `undetermined` desde NT 23). D210a es lápida de NT 2 y D210b rige desde NT 23: ¿es una reintroducción? ¿Siguen eliminadas D208d, D210a, D219 y D223 después de NT 23? (sí, por curación).
- ¿Qué significa "se excluye" en NT 25 y NT 26? (interpretación revisada caso a caso).
- ¿Qué cambió entre el MT certificado (`25EB165A…`) y el publicado (`f48d7c82…`)? ¿El servidor valida con exactamente los XSD publicados y coincide el RAR con el directorio? (Issues abiertos).
- Una vez leído el Decreto 872/2023: si dice "supere", ¿cuál aplica el servidor? (el de la NT: "mayor o igual").

---

# Decisión recomendada

- **Stack final:** CPython 3.14 gestionado por uv (`uv.lock`, `--locked`, `only-managed`). Runtime: Pydantic 2 (`extra="forbid"`, `frozen`), PyYAML con `KBLoader` restringido y xmlschema 4. Grupo `ingest`: pdfplumber + pypdfium2 (una sola familia en el lock). Stdlib: argparse, `ast`, urllib, json y sqlite3 (Fase 3). Desarrollo: pytest, Hypothesis (solo el resolvedor) y ruff; basedpyright en la Fase 2. Externo: gitleaks. **Fuera del MVP:** Docling (solo si el sondeo de la Fase 0 encuentra una NT escaneada) y lxml (sin caso de uso). **Fuera:** Typer, Rich, httpx, orjson, Marker, MinerU, PyMuPDF, LangChain y bases vectoriales.
- **Fuente canonical:** `kb/` en YAML restringido, **un archivo por entidad** (documentos con `current_revision`, calendario por ambiente y efectos; campos; validaciones; Issues con ventana). Versiones **materializadas** con `introduced_by: [efectos]` y `based_on` (predecesora temporal en producción); inicio derivado del calendario del documento por ambiente, fin derivado de la versión siguiente, nada derivable almacenado. Literales y fechas copiados por herramienta y ligados por test de igualdad a celdas citadas por contenido (`raw:DOC@sha12:pN:ID#atributo`). Efectos declarativos (pendiente, no modelado o aplicado por derivación) como aserción, nunca como patch ejecutable. Revisiones de fuentes y chequeos del portal solo en `sources.manifest.yaml`. Git como tiempo de transacción (tags `kb-AAAA.MM.DD`).
- **Parser:** texto por página de todo el corpus con un solo motor (pypdfium2 o pdfplumber; decide el spike) para el índice, las citas y la cobertura; celdas con pdfplumber o el árbol de etiquetas solo para las filas del piloto y las tablas de fechas, con `normalize_text`, *stitching* mínimo registrado y `extraction/fixes.yaml`. Control cruzado entre motores, tablas completas del MT y batería de checks en la Fase 3.
- **Persistencia:** archivos de texto en Git (binarios fuente por hash + manifiesto + `raw/` texto/JSONL + YAML canónico). Sin base de datos ni export en el MVP; JSON exportado en la Fase 2 y SQLite FTS5 derivado, no versionado, desde la Fase 3.
- **Tests:** pytest en siete capas: unitarios (loader, normalización, resolvedor, DSL Kleene, UTF-8 por tubería); Hypothesis solo del resolvedor (prospectivas y pendientes siempre visibles); evidencia (hash, `raw` regenerado, celdas = golden, literal = celda, fila = entidad, fechas por encabezado, constantes ⊂ literal, guardián de cobertura); integridad (biyección efecto-versión, predecesora temporal, diff ⊆ alcance declarado con cambios reconocidos, integridad referencial temporal, colisiones declaradas, pasado justificado); golden temporal declarativo (día anterior y día de cada frontera por ambiente; D208c real + [HIP]; horizonte; `not_curated`); XSD/XML sin red (con anacronismo y fecha de procesamiento); contrato y aceptación (replay determinista de NT 24, cinco errores sembrados). Más la evaluación ciega con clave de respuestas y el cronometraje de tres rechazos.
- **IA:** Claude Code escribe efectos, formaliza condiciones (polaridad "se viola cuando", `exists()` explícito, Kleene, `level` y `gaps`), redacta Issues y diagnostica **solo a partir de `sifen explain --json`**. Nunca teclea literales ni fechas, nunca abre XML reales, nunca registra fuentes, nunca toca `sources/`, el manifiesto, `raw/`, `extraction/`, `build/`, `_meta.yaml`, `.claude/` ni `CLAUDE.md`, nunca borra versiones ni mergea (`deny` + tests + `pr-scope` + rama protegida sin bypass + `Reviewed-by`). CLAUDE.md de 8 reglas + prompt de curación. Bitácora por hooks en `curation/runs/`.
- **MCP:** no en el MVP. En la Fase 4, stdio, read-only, sobre la librería, con `get_entity` separado de `get_history`, cuando haya un consumidor distinto de Claude Code y el contrato JSON lleve dos ciclos de NT estable.
- **RAG:** no ahora; nunca para resolver reglas. El índice de menciones de `not_curated` sale siempre con aviso. FTS5 en la Fase 3, devolviendo claves que pasan por el resolvedor. Embeddings, quizá, solo para casos y solo si FTS5 falla en una evaluación medida.
- **Primer dominio piloto:** receptor/identidad, sin sondas: campos C002, D011, D015, D201, D202, D208, D209, D210, F014, F023; validaciones D208, D208a–g, D209a, D210, D210a, D210b (códigos 1310–1335, incluidas las lápidas 1322/1323). Corpus completo (MT v150 + checksums + NT 001–027 con calendario + instantánea de 47 XSD + RAR + Decreto 872/2023). GENFE010 y GED003 abren la Fase 2. Se reemplaza por los códigos más frecuentes de la empresa si la Fase 0 muestra otro dominio, conservando D208c/D208d/D208e como canarios.
- **Primer entregable:** dos pasos. **Entregable 0:** `source add` del corpus + texto por página + `kb/documents/*.yaml` con el calendario por ambiente + `sifen explain <código|ID|xml_name>` en modo índice (estado `not_curated`, menciones ordenadas por fecha de producción con página impresa y PDF, aviso "vigencia no resuelta: una mención posterior puede modificar o eliminar la regla") + `status` con el horizonte; para 1321 devuelve MT p. 166 → NT 21 (2024-01-01) → NT 24 (2025-01-01). **Entregable 1:** el esqueleto de punta a punta de D208c: MT v150 + NT 21 + NT 24 → celdas en `raw/` → `kb/` (tres versiones con efectos y calendario) → `uv run sifen explain 1321 [--at] [--env] [--json]` con estado, intervalo derivado, cita verificada (documento, revisión, página impresa y PDF) e historia 60 M → 35 M (2024-01-01) → 7 M (2025-01-01) → golden de las filas reales 1–5 de G.5 y el oráculo de la marca de agua de NT 21; pasando en Linux (CI) y en Windows (local), junto con los spikes de extracción y XSD y la consulta a DNIT por A1 y A2. `--history` y `--xml` llegan en la Fase 1.

---

## Anexo: Registro de verificación

**Verificado en fuentes oficiales de DNIT** (investigación del 2026-10-17; página principal: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica):
- D208c/1321, severidad R, umbrales 60 M (MT p. impresa 166 / PDF 167) → 35 M (NT 21, 01/01/2024) → 7 M (NT 24, 01/01/2025), y su texto literal; NT 25–27 no lo tocan.
- Inventario de las 27 NT: fecha del documento, fechas de test y producción (NT 13–27), `?t=` de subida; numeración no cronológica (NT 7/8/9); NT 001–011 con "Cambios desde X al Y" y NT 012 solo con "Fecha"; errata de año de NT 25; NT 22 subida después de su vigencia; NT 25 y NT 27 vigentes el día de su subida.
- Re-subidas: NT 21 con marca de agua "VER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025"; NT 18 `-+Junio` (creación 06/06/2024; si cambió su contenido, no verificado); NT 14 `V150X`.
- MD5 del MT publicado (`f48d7c82…`) distinto del certificado (`25EB165A…`): listado de checksums en el portal.
- XSD (https://ekuatia.set.gov.py/sifen/xsd/): 47 archivos; cambios in situ (`dBasExe`, `gOblAfe`, `dCodConDncp`, `dRucFus`); inclusiones por URL HTTPS absoluta; conflictos `gOblAfe` y `dSisFact`; `tiTipDocRec = [1-6]|9`. Revisado de nuevo para este documento: `protProcesDE_v150.xsd` declara en `rProtDe` el elemento obligatorio `dFecProc` (tipo `fecUTC`) y `gResProc` con `maxOccurs="100"`.
- Identidad y códigos: colisión campo/validación D208 (1310); GDE008 con 4006/4069; 2419 en H002c y H005a; NT 18 reasigna GET022–GET030 a 4325–4335; GED003/4253 AO → R en NT 19; NT 2 elimina D208d/D210a; NT 23 agrega D208f, D210b y D208g y el valor 6 de D208; NT 26 excluye 1400/1401 y 1800/1801; NT 25 excluye GEC002c (4004).
- En el rechazo se informa el primer error (MT §12); CSC de test públicos (Guía de Pruebas 2026); códigos 0364 y 0422 y límite de lote de 1000 KB (Guía de Mejores Prácticas 2024); color de resaltado sin leyenda; FAQ: v150 es la versión vigente del MT.

**Queda [VERIFICAR-DNIT]:** vigencia de NT 001–012 (A1); eje emisión/procesamiento (A2); hora de inicio y equivalencia "puesta a disposición" = aplicación; formato y zona de `fecUTC`; D208b frente a D208f y D208 frente a D208g; permanencia de las eliminaciones de NT 2/NT 3 tras NT 23; significado de "se excluye" (NT 25, NT 26); diferencia entre los dos binarios del MT; RAR frente al directorio XSD y XSD que usa el servidor; literal del Decreto 872/2023 ("supere" [P]); prórroga de NT 13 [P, README de Roshka]; plazos de 72 h y 120 h de la FAQ [P]; cadenas exactas de `dEstRes`; otros canales oficiales de NT o prórrogas; el Prevalidador como oráculo; algoritmo del DV módulo 11 y longitudes del CDC [P, librería TIPS-SA].

**Fuentes externas clave:**
- Licencias y versiones (PyPI y repositorios): pdfplumber 0.11.10, MIT, dependencias `pdfminer.six==20260107` y `pypdfium2>=5.9.0` (verificado para este documento en https://pypi.org/pypi/pdfplumber/0.11.10/json); pypdfium2, Apache-2.0/BSD-3; pdfminer.six, MIT (CVE-2025-64512 y CVE-2025-70559 corregidas desde 20251230); Docling, MIT, con modelos Heron apache-2.0; Marker, pesos OpenRAIL-M modificados con umbral de USD 5 M (https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE); MinerU, licencia propia desde 3.1.0; PyMuPDF, AGPL-3.0 o comercial.
- Stack: estado de versiones de Python (https://www.python.org/downloads/); uv (https://docs.astral.sh/uv/); conversión de Pydantic (https://pydantic.dev/docs/validation/latest/concepts/conversion_table/); xmlschema (https://xmlschema.readthedocs.io/); notas de Typer; httpx en PyPI; basedpyright; gitleaks y la licencia de `gitleaks-action` para organizaciones (https://github.com/gitleaks/gitleaks-action); PEP 686 (UTF-8 por defecto en 3.15).
- Plataforma: ramas protegidas de GitHub y opción "Do not allow bypassing the above settings"; en repos privados requieren GitHub Pro, Team o Enterprise (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
- Pruebas locales en este Windows: PyYAML `safe_load` (`0160` → 112, `NO` → False, duplicados sin aviso), prototipos de `KBLoader` y del DSL, FTS5 en los intérpretes instalados y cp1252 en stdout por tubería.
- Antecedentes de diseño: OpenFisca (parámetros con vigencia y tests temporales en YAML), legislation.gov.uk/Akoma Ntoso (consolidación *point-in-time*), OSV y STIX (lápidas e IDs que no cambian de significado).

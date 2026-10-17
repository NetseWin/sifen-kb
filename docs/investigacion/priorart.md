# Prior art: temporalidad y consolidación de reglas regulatorias (insumo para la KB SIFEN)

- Fecha de la investigación: 2026-10-17.
- Alcance: extraer **patrones concretos y advertencias** de informática jurídica, modelos temporales, publicación de especificaciones de facturación electrónica en otros países y proyectos "docs-as-data". El objetivo **no** es recomendar adoptar estándares pesados.
- Método: lectura de especificaciones oficiales (OASIS, legislation.gov.uk, NIST, Peppol, DNIT) y de fuentes secundarias (blogs de proveedores, foros). Cada afirmación lleva su nivel de verificación cuando no proviene de una fuente primaria.
- Convención: los identificadores SIFEN que aparecen en los ejemplos (D208c, 1321, NT024…) vienen del pedido del usuario y son **ilustrativos**. No se verificaron contra DNIT.

---

## 0. Resumen ejecutivo (lo que sí conviene llevarse)

1. **El problema ya tiene una solución conocida en informática jurídica:** guardar **versiones consolidadas materializadas** y, aparte, un **registro de efectos** (qué documento modifica qué, cómo y desde cuándo) con un estado *aplicado / pendiente / no aplica*. Así trabaja legislation.gov.uk. Akoma Ntoso y ELI formalizan lo mismo. **No hace falta adoptar ninguno de esos estándares:** alcanza con copiar 6 u 8 conceptos.
2. **La fecha de vigencia pertenece al efecto (lo que dice la NT), no a la versión.** El inicio de una versión se *deriva* del efecto que la creó. El fin se deriva del inicio de la versión siguiente: no se almacena `effective_to`, igual que en los parámetros de OpenFisca.
3. **Las fechas también cambian y necesitan su propia procedencia.** Brasil posterga regularmente la entrada en producción de las NT (por ejemplo, la NT 2025.002 v1.52 pasó de homologación 05/10/2026 a 26/10/2026, según una fuente secundaria). México prorrogó varias veces la convivencia CFDI 3.3/4.0. Una fecha de vigencia sin fuente es un riesgo.
4. **Tiempo válido en los datos y tiempo de transacción en Git.** No conviene construir tablas bitemporales: Fowler advierte que la bitemporalidad "complica significativamente" un sistema. Git responde a la pregunta "¿qué decía la KB el día X?" siempre que haya disciplina: un archivo por entidad, `main` protegido, tags anotados por release y nada de reescribir historia.
5. **Patch frente a versión materializada:** la opción robusta es **materializar la versión completa** de cada regla y usar el "patch" solo como **aserción verificable**. Esa aserción es la lista de atributos declarados como modificados más las citas literales *old/new*, como en `textualMod` de Akoma Ntoso o en la operación `test` de JSON Patch. No se usa como instrucción ejecutable que se reproduce encima de la base. Esto ataca directamente el riesgo R3 (que una modificación parcial reemplace la regla completa).
6. **La severidad cambia con el tiempo y es atributo de la versión, no de la regla.** Peppol introduce reglas como *warning* y las pasa a *fatal* en la release siguiente. SUNAT migró códigos de "observación" a "error" por fases, con excepciones por tipo de comprobante y por canal (OSE/SEE). Brasil vuelve "obrigatórias" reglas ya existentes.
7. **Los IDs no se reutilizan, se reemplazan.** DIAN eliminó FAD09c en el anexo 1.9 y creó FAD09e con otra semántica. Hace falta una relación mínima `replaces/replaced_by`; Sigma y MITRE ATT&CK ofrecen vocabulario probado. No hay que forzar "versiones" de una regla que la autoridad trata como nueva.
8. **La "regla vigente" depende del ambiente, no solo de la fecha.** Brasil publica fechas distintas para *homologação* y *produção*, e incluso reglas que rigen primero en producción, como la rejeição 1115. Para SIFEN, el tiempo válido debería definirse como **"desde cuándo el SIFEN aplica la validación en el ambiente X"**. Esa definición es verificable y distinta de la obligación legal: la DIAN aclara que las reglas de validación no modifican la obligación legal.
9. **Las consolidaciones oficiales periódicas son un oráculo de pruebas.** El MOC 7.0 de Brasil consolidó las NT publicadas hasta octubre de 2020 y se publicó con un MD5 por anexo. Si DNIT reemite un manual consolidado, el estado resuelto de la KB a esa fecha debe coincidir con él. Es el mejor test de regresión posible.
10. **El prior art open source de e-invoicing casi no modela historia.** nfelib solo conserva el último esquema de cada versión mayor y deja la historia en un CHANGELOG. ACBr reimplementa reglas de negocio localmente y genera **rechazos falsos** cuando una NT elimina o cambia una regla. La lección: toda validación local debe declarar la fecha de corte de la KB y nunca presentarse como autoridad.

---

## 1. Informática jurídica: consolidación "point-in-time"

### 1.1 Akoma Ntoso / LegalDocML (OASIS)

Conceptos relevantes, verificados en la especificación OASIS AKN 1.0, Part 2:

- **FRBR Work / Expression / Manifestation.**
  - El *Work* es la norma abstracta.
  - Una *Expression* es una versión concreta, en un idioma y en un punto del tiempo.
  - La *Manifestation* es el formato (PDF, XML…).
  - Laws.Africa lo implementa con URIs simples: `/akn/za/act/1998/55` para el work y `/akn/za/act/1998/55/eng@2014-01-17` para la expresión a esa fecha. Si se pide el work sin fecha, devuelve la última expresión aplicable.
- **`activeModifications` / `passiveModifications`** (dentro de `meta/analysis`). El documento que modifica declara modificaciones *activas*; el documento modificado registra las *pasivas*. Se registran ambos lados.
- **`textualMod`**: atributo `type` obligatorio con los valores `repeal`, `substitution`, `insertion`, `replacement`, `renumbering`, `split`, `join`.
  - Hijos: `source` (de dónde viene), `destination` (qué afecta), `force`, `efficacy`, `application`, `duration`, `condition`, `previous`, `old` y `new` (el texto anterior y el nuevo).
  - Atributos: `period` y los flags `incomplete` y `exclusion`.
  - Existen además `meaningMod`, `scopeMod` y `forceMod`: modificaciones que **no** cambian el texto sino el significado, el alcance o la vigencia.
- **Tiempo:**
  - `lifecycle` contiene `eventRef`, cada uno con fecha, tipo y documento que lo generó.
  - `timeInterval` no usa fechas literales: sus `start`/`end` **referencian eventos**.
  - Los intervalos se agrupan en `temporalGroup` y los elementos versionados apuntan a ellos con `@period`.
  - Distingue entre periodo de **fuerza** (*force*), de **eficacia** (*efficacy*) y de **aplicación** (*application*).

**Conceptos simples reutilizables sin adoptar AKN:**

| Concepto AKN | Versión mínima para SIFEN |
|---|---|
| Work vs Expression@fecha | `Rule` (identidad estable, p.ej. D208c) vs `RuleVersion` (contenido válido desde una fecha). |
| active/passive modifications | La NT declara efectos (lado activo, canónico). El índice inverso "regla → NT que la modificaron" **se genera**, no se escribe a mano (evita R5). |
| `textualMod/@type` | Vocabulario cerrado y pequeño: `add`, `modify`, `remove`, `replace` (y quizá `renumber`). `split`/`join` solo si aparecen en las NT reales. |
| `old` / `new` | Citas literales del texto anterior y del nuevo, tal como aparecen en la NT. Sirven de **aserción verificable** contra `raw/`. |
| `meaningMod`/`scopeMod` | Algunas NT no cambian la regla sino su alcance (tipo de documento, ambiente). Conviene que el efecto pueda ser de alcance, no solo de contenido. |
| `incomplete` | Flag honesto: "este efecto está registrado pero no se modeló completamente", equivalente a `needs_review`. |
| eventos con documento generador | Toda fecha referencia el documento que la estableció. Esa es la procedencia de la fecha. |
| force / efficacy / application | Ver la advertencia de 1.6: definir **una** semántica propia para SIFEN y, a lo sumo, dos fechas por ambiente. |

**Qué NO adoptar:** XML AKN, naming convention completa, `temporalGroup` con referencias indirectas ni FRBR Manifestation. Para un corpus de un manual y unas decenas de NT, esa indirección es costo sin beneficio.

### 1.2 legislation.gov.uk (UK National Archives)

Es el precedente operativo más cercano a lo que pide el usuario. Fuente: su página de ayuda.

- **Original vs Revised.**
  - *Original* es el texto tal como se promulgó.
  - *Revised* incorpora las enmiendas posteriores.
  - Existe una **fecha base** (1 de febrero de 1991 para la mayoría): antes de ella no hay historia revisada. El equivalente SIFEN es "MT v150 = baseline; no se reconstruyen versiones anteriores".
- **Point in time / Timeline of changes.** Cada versión tiene *start date* ("la fecha más temprana en que tuvo efecto, en cualquier medida o para cualquier propósito") y *stop date* (cuando la sucede otra versión o deja de tener efecto).
- **Prospective.** Es una versión **sin fecha de inicio**, creada por una enmienda que todavía no entró en vigor. Patrón SIFEN: una NT publicada con fecha de producción "a definir" se modela como versión *prospectiva* con `from: null`. No se inventa una fecha.
- **Effects y su estado de aplicación.** Un *effect* es cualquier impacto de una disposición sobre otra.
  - La tabla "Changes to legislation" lista los efectos con la columna "Changes applied to text": `Yes` / `Not yet` / `N/A (see note)`.
  - Cuando hay efectos pendientes, se avisa **en la propia disposición afectada**.
  - El sitio reconoce un desfase: los efectos se registran 4 a 8 semanas después de recibir la norma y el texto revisado se actualiza dentro de los 3 meses de la entrada en vigor.
- **Anotaciones tipadas.** *F-notes* son enmiendas textuales con su fuente. *C-notes* son cambios de significado o alcance sin cambio textual. *I-notes* son información de entrada en vigor. *P-notes* son normas de aplicación, típicamente las órdenes de entrada en vigor.
- **Extent.** Es una dimensión de aplicabilidad (Inglaterra, Gales, Escocia, Irlanda del Norte) **ortogonal al tiempo**: puede haber versiones distintas de la misma disposición por extensión.

**Conceptos reutilizables (los más valiosos de toda la investigación):**

1. **Registro de efectos con estado `applied | pending | not_applicable`.** Una NT puede estar ingerida en `sources/` sin que sus efectos estén curados. La CLI debe poder decir: "D208c: regla según NT021; **hay 1 efecto pendiente de NT027 que afecta esta regla**". Esto mitiga R8 y R9 (falsa seguridad ante información incompleta).
2. **Aviso de efectos pendientes en la entidad afectada**, no solo en un listado global.
3. **Versión prospectiva sin fecha.**
4. **Dimensión de aplicabilidad separada del tiempo.** En SIFEN, el candidato natural es el **ambiente** (test/producción) y quizás el **tipo de documento**. No hay que modelar más dimensiones hasta que aparezcan en las NT reales.
5. **Fecha base explícita** y documentada.

### 1.3 ELI (European Legislation Identifier)

En la ontología ELI 2.0, `LegalExpression` tiene propiedades opcionales:

- de fecha: `date_publication`, `first_date_entry_in_force`, `date_no_longer_in_force`, `date_applicability` (0..n) y `version_date`;
- de estado y versión: `in_force` y `version`;
- de relación, cada una con su inversa: `amends/amended_by`, `changes/changed_by`, `consolidates/consolidated_by`, `repeals/repealed_by`, `corrects/corrected_by` y `commences/commenced_by`.

**Reutilizable:**

- **Separar publicación, entrada en vigor y aplicación.** Es exactamente el caso del usuario: "publicado el 01/03, vigente el 01/04".
- **`commences/commenced_by`.** Un documento puede fijar la fecha de inicio de otro, como una orden de entrada en vigor. En SIFEN puede pasar que una resolución o un comunicado de DNIT fije o posponga la fecha de una NT. Esto se resuelve con "la fecha tiene su propia fuente" (§2.5).
- **`corrects/corrected_by`.** Una fe de erratas no es una enmienda: corrige retroactivamente desde el origen. En la KB conviene modelarla como **edición de la versión afectada**, con procedencia, y no como una versión nueva con fecha posterior.

**Qué NO adoptar:** RDF/ontologías ni URIs ELI. Solo el vocabulario.

### 1.4 EUR-Lex: la consolidación no es normativa

EUR-Lex declara que el texto consolidado es "una herramienta de documentación" **sin efecto jurídico**. La fecha del encabezado indica cuándo se vuelve aplicable la última enmienda incluida, no cuándo se hizo la consolidación.

**Lección para SIFEN:** la KB consolidada es un **producto editorial**. Toda respuesta debe citar el documento fuente (MT v150, NT_0xx) como autoridad, nunca "la KB". Esto debería ser una regla de CLAUDE.md y un campo obligatorio en la salida de la CLI y del MCP.

### 1.5 LegalRuleML: advertencia terminológica

LegalRuleML habla de estados como "is applicable", "is in force" y "has efficacy". Sin embargo, existe un *issue* abierto en OASIS que reconoce que esos conceptos **no están definidos formalmente** ni en la documentación ni en una ontología. La literatura los usa de forma inconsistente.

**Lección:** no importar "vigencia/eficacia/aplicación" como si fueran conceptos estándar. Hay que definir en un glosario de la KB **qué significa exactamente cada fecha**, con semántica operativa y verificable (§2.6).

---

## 2. Modelos temporales

### 2.1 Tiempo válido vs tiempo de transacción (bitemporalidad)

Fowler, en *Bitemporal History*, distingue *actual time* (cuándo algo fue verdad en el mundo) de *record time* (cuándo lo supimos). Los nombres clásicos son *valid time* y *transaction time*. La pregunta típica es "¿qué creíamos el 25/03 sobre el 25/02?". También advierte:

- que la bitemporalidad "complica un sistema de manera bastante significativa" y que muchas veces es mejor evitarla;
- que el soporte en bases de datos es de nicho;
- que los usuarios tienen dificultad para aceptar que la historia "cambia".

**Aplicado a la KB SIFEN:**

| Eje | Pregunta | Dónde vive |
|---|---|---|
| Tiempo válido | "¿Qué regla aplicaba SIFEN en producción el 10/01/2025?" | En los **datos**: fechas de los efectos y versiones derivadas. |
| Tiempo de transacción | "¿Qué respondía la KB el 01/12/2024, antes de curar la NT027?" | En **Git**: tags de release y log por archivo. |

Ambos ejes son necesarios, porque un troubleshooting de un rechazo pasado puede depender de qué sabíamos entonces. Pero **no** hace falta implementarlos juntos en un modelo bitemporal. Un `git checkout kb-2024.12.01 && sifen rule D208c --at 2025-01-10` responde a la pregunta bitemporal completa sin código especial.

### 2.2 SCD tipo 2 (Slowly Changing Dimension)

Es el patrón clásico de data warehousing: una fila por versión con `valid_from`, `valid_to` e `is_current`.

**Qué tomar:**

- Una entidad estable (`Rule`) y N versiones (`RuleVersion`).
- **Intervalos semiabiertos** `[from, to)`.

**Qué NO tomar, porque son fuentes de inconsistencia:**

- **`valid_to` almacenado.** Se deriva del `from` de la versión siguiente, como en OpenFisca, donde un valor rige "desde su fecha hasta la siguiente entrada". Almacenarlo permite huecos y solapes.
- **`is_current` almacenado.** Se calcula para la fecha de consulta. Si se guarda, queda obsoleto cuando pasa una fecha de vigencia futura sin que nadie toque el archivo.

**Eliminación:** se registra con una **versión lápida** (`status: removed`), no borrando la regla.

- OpenFisca usa un valor nulo para cortar un parámetro (inferido de la documentación, no confirmado para YAML).
- OSV usa `withdrawn`: los registros retirados se excluyen de las búsquedas pero siguen recuperables por ID.
- MITRE ATT&CK distingue entre *revoked* (reemplazado por otro objeto, con una relación `revoked-by`) y *deprecated* (retirado sin reemplazo).

**Invariantes testeables** (tomados de SCD2 y OpenFisca):

- Para cada (regla, ambiente) no hay dos versiones con el mismo `from`.
- Las versiones están ordenadas y la primera es la base (`from: null` = "desde la fecha base").
- Para cualquier fecha, la consulta devuelve **exactamente 0 o 1** versiones. Si la regla está eliminada devuelve una lápida, nunca "nada" silencioso.
- Una versión prospectiva (sin fecha) nunca es "vigente" para ninguna fecha. Se informa aparte.

### 2.3 Event sourcing vs snapshots materializados

En el paralelo directo, las NT son *eventos* y la regla vigente es `fold(base, NTs ordenadas)`. Es elegante, pero tiene problemas concretos para este dominio:

- **Eventos que modifican eventos.** Brasil reemite la misma NT en versiones v1.00, v1.10… v1.52, y algunas solo cambian fechas o corrigen reglas de versiones anteriores. En event sourcing eso exige eventos de compensación o reescribir el log.
- **Orden de aplicación ambiguo.** No queda claro si se ordena por publicación o por vigencia. Una NT posterior puede tener vigencia anterior a otra, y las postergaciones reordenan.
- **Errores silenciosos de replay.** Un efecto mal curado contamina todas las versiones posteriores sin que nadie lo vea, porque nadie revisa el resultado sino el delta.
- **Revisión humana difícil.** El revisor aprueba deltas, no el estado resultante.

**Conclusión:** para la KB, el log de eventos ya existe y es doble: el registro de efectos (dominio) y Git (edición). El **estado se materializa** por versión. No hace falta un event store, coherente con la sección 30 del pedido ("event sourcing innecesario").

### 2.4 Git como tiempo de transacción: cómo hacerlo bien

Git sirve como tiempo de transacción **solo con disciplina**:

| Problema | Mitigación |
|---|---|
| `author date` y `committer date` son arbitrarios (se pueden fijar con variables de entorno) y el rebase los reescribe. | Usar como tiempo de transacción el **merge a `main` protegido** (sin force-push) y **tags anotados** por release de KB. No usar fechas de commit sueltas como evidencia. |
| Archivos monolíticos (`validations.json` con todo) vuelven inútil `git log` por regla. | **Un archivo por entidad** (p.ej. `rules/validations/D208c.yaml`). Así `git log --follow` sobre ese archivo es el historial de transacción de la regla. |
| Campos `updated_at` / `last_modified` escritos a mano duplican Git y divergen. | No guardarlos en los datos. Lo que sí es dato es `last_reviewed_at` / `reviewed_by`, porque es una atestación humana y no tiempo de transacción. |
| "¿Qué respondía la KB en la fecha X?" | Tags `kb-AAAA.MM.DD`, y el artefacto generado (SQLite/JSON) incluye el ID del snapshot. |

### 2.5 Las fechas tienen historia: postergaciones y procedencia de la fecha

Evidencia de que las fechas de vigencia cambian después de publicadas:

- **Brasil.** Según una fuente secundaria (notagateway.com.br, 08/10/2026), la NT 2025.002 v1.52, la NT 2026.007 v1.10 y la NT 2026.008 v1.00 pasaron de homologación el 05/10/2026 a homologación el **26/10/2026** y producción el **16/11/2026**. Según IOB (también secundaria), la NT 2025.002 v1.30 ya había postergado la producción del 06/10 al 10/11/2025. La rejeição 1115 se aplicó en **producción desde el 05/01/2026 sin fecha definida para homologación**, es decir, en orden inverso al habitual (IOB).
- **Brasil (por UF).** Santa Catarina reprogramó la activación en producción de la regla N12-85 para el 01/04/2025 mediante un comunicado estadual (fuente secundaria).
- **México.** La convivencia CFDI 3.3/4.0 se extendió varias veces: inicialmente hasta el 30/06/2022, luego hasta fin de 2022, y para nómina hasta el 30/06/2023 (fuentes secundarias consistentes entre sí).
- **Colombia.** El anexo técnico 1.9 se publicó con la Resolución 165/2023, pero la Resolución 008/2024 fijó el 01/05/2024 como fecha de adopción. Hasta entonces regía la 1.8 **aunque la 1.9 ya estuviera publicada** (oficio DIAN 1531/2024).

**Patrón recomendado:** la fecha vive en el **efecto**, con la fuente que la fijó (`date_source`). Si una fuente posterior la posterga, se **edita la fecha del efecto** y se agrega a su `date_history` la fuente de la postergación. Git registra cuándo lo supimos. No se crea una "versión nueva de la regla" por una postergación: la regla no cambió, cambió cuándo empieza.

### 2.6 Definir la semántica del tiempo válido (decisión clave)

Las fuentes muestran al menos cuatro fechas distintas por cambio:

1. **Publicación del documento.** Es metadata del `DocumentSource`, no del efecto.
2. **Disponible en ambiente de pruebas.**
3. **Aplicado en producción.**
4. **Fin de convivencia u obligatoriedad.** Peppol separa *publication* de *mandatory to use from*; México y Colombia tuvieron periodos de convivencia.

**Propuesta conceptual:** definir el tiempo válido de la KB como **"periodo en que el SIFEN aplica esta versión de la validación en el ambiente X"**. Las razones:

- Es lo que importa para el troubleshooting: un rechazo es un hecho del servidor, no de la norma.
- Es **verificable empíricamente**: los casos reales (`cases/`) pueden aportar evidencia observada de que la validación ya se aplicaba, sin convertirse en fuente normativa.
- Separa la **obligación legal**, que vive en resoluciones o normativa, de la **validación técnica**. La DIAN lo dice expresamente: las reglas de validación no modifican el requisito legal de oportunidad de emisión (oficio 1532/2024).

**Mínimo de fechas por efecto:** `prod_from` (obligatoria, o `null` = prospectiva) y `test_from` (opcional). Las fechas de convivencia u obligatoriedad se modelan **solo si aparecen en las NT reales de SIFEN**; hay que verificarlo contra DNIT.

**Advertencia sobre la convivencia:** durante una ventana de convivencia hay **dos versiones aceptables a la vez**, así que "la regla vigente" deja de ser única. Si se descubre que SIFEN tiene convivencias, la consulta debe poder devolver "aceptadas: {vieja, nueva}" en vez de forzar una sola. Es especialmente probable para versiones de XSD, menos para validaciones individuales.

---

## 3. "Patch/delta" vs "versiones materializadas + diff calculado"

### 3.1 Precedentes

| Precedente | Qué hace | Lección |
|---|---|---|
| JSON Patch (RFC 6902) | Operaciones `add`/`remove`/`replace`/`move`/`copy`/`test`. Si un `test` falla (el valor actual no es el esperado), **todo el patch falla**. | Un delta solo es seguro si **verifica la base** antes de aplicar. Sin precondición, un patch se aplica "bien" sobre una base equivocada. |
| JSON Merge Patch (RFC 7396) | Fusión por claves; `null` borra. | No puede expresar cambios en elementos de listas sin reemplazar la lista entera, que es justo el caso "la NT agrega un valor a la enumeración". **Riesgo R3 en estado puro.** |
| OSCAL Profiles (NIST) | Un *profile* altera un *catalog* base con `alter` → `add`/`remove`, apuntando por id y con posición. **No existe `modify`**: modificar es remove + add. Es un error que dos `alter` apunten al mismo control. | Incluso un organismo de estándares evitó la semántica "modificar en sitio" por ambigua. La resolución requiere un algoritmo especificado aparte. |
| FedRAMP | Publica el *profile* **y** el *resolved profile catalog* materializado, porque así las herramientas no tienen que resolver referencias. Advierte que el catálogo resuelto **se desactualiza** si perfiles y catálogos cambian. | Si se materializa un derivado, hay que **regenerarlo y compararlo en CI**. |
| Akoma Ntoso `textualMod` | Registra `old` y `new` además del destino. | La cita literal del texto anterior y del nuevo es una **aserción** que permite verificar mecánicamente. |
| legislation.gov.uk | Texto consolidado por versión (materializado, editado por humanos) + tabla de efectos + anotaciones con la fuente. | **El modelo híbrido ya funciona a escala nacional.** |
| NT de Brasil | Cada NT se **reemite completa** (v1.00, v1.10, …) con una tabla de histórico de cambios. | Ni la autoridad publica deltas de deltas: publica el documento completo más un changelog. |
| nfelib (Python, NF-e) | Un cambio menor de esquema **sobrescribe** el directorio de bindings de la versión mayor y la historia queda en `CHANGELOG_SCHEMAS.md`. | Para código alcanza con "último + changelog". Para una KB con consultas `--at` no alcanza, y es la principal diferencia con el prior art de librerías. |

### 3.2 Riesgos comparados

| Riesgo | Patch/delta reproducido | Versión materializada |
|---|---|---|
| Modificación parcial tratada como total (R3) | **Alto**: depende de la granularidad de la operación. Un `replace` de la regla entera borra lo que la NT no tocó. | Medio: el curador puede reescribir mal partes no afectadas. **Mitigable con un test de diff declarado** (§3.3). |
| Base equivocada / orden incorrecto | **Alto**: el replay depende del orden y de la base. | Bajo: cada versión es autocontenida. |
| Error que se propaga en silencio | **Alto**: el error se arrastra a todas las versiones siguientes. | Bajo: el error queda en una versión y el diff lo hace visible. |
| Revisión humana | Difícil: se revisa un delta abstracto. | Fácil: se revisa el resultado completo y el diff que genera Git o la herramienta. |
| Duplicación / tamaño | Bajo. | Medio: N copias de campos que no cambian, pero el corpus es pequeño y es irrelevante. |
| Ver "qué cambió la NT" | Directo. | Requiere calcular el diff (trivial y determinista). |
| Consulta `--at` | Requiere un motor de replay. | Elegir la versión con el mayor `from` ≤ fecha. |
| NT que modifica la fecha de otra NT | Requiere eventos de compensación. | Se edita la fecha del efecto (§2.5). |

### 3.3 Patrón recomendado: versión materializada + efecto declarativo verificable

El "patch" del pedido (`{"rule":"D208c","action":"override",…}`) **no se ejecuta**. Se conserva como **declaración** de lo que la NT dice cambiar y se usa para **verificar** la versión materializada.

Esquema ilustrativo (YAML, nombres a decidir):

```yaml
# effects/NT_E_KUATIA_024.yaml   (un archivo por documento modificador)
document: NT_E_KUATIA_024_MT_V150      # → DocumentSource (con sha256 / revisión)
effects:
  - id: NT024-e3
    target: D208c                        # regla afectada
    type: modify                         # add | modify | remove | replace | scope
    attributes: [condition]              # QUÉ atributos declara cambiar la NT
    quote_old: "…texto literal anterior…"    # opcional; tomado de la NT o del MT
    quote_new: "…texto literal nuevo…"       # obligatorio cuando la NT lo provee
    locator: {page: 12, section: "3.2"}
    prod_from: 2025-01-06                # null = prospectivo (fecha por definir)
    test_from: 2024-12-02                # opcional
    date_source: NT_E_KUATIA_024_MT_V150 # quién fijó la fecha (puede cambiar, §2.5)
    status: applied                      # applied | pending | not_applicable
```

```yaml
# rules/validations/D208c.yaml   (un archivo por regla; versiones materializadas completas)
id: D208c
versions:
  - introduced_by: base:MT_V150          # from = fecha base
    severity: R
    code: "1321"
    condition: {...}                     # contenido COMPLETO
  - introduced_by: NT024-e3              # from DERIVADO del efecto, no copiado
    severity: R
    code: "1321"
    condition: {...}                     # contenido COMPLETO resultante
```

**Tests que convierten el "patch" en aserción** (inspirados en JSON Patch `test`, AKN `old/new` y la tabla de efectos del Reino Unido):

1. `test_diff_matches_declared_effect`: el diff calculado entre la versión n−1 y la n toca **solo** los `attributes` declarados por el efecto. Si el curador reescribió otra cosa, falla. **Este es el test anti-R3.**
2. `test_quote_new_in_raw`: `quote_new` aparece literalmente, tras normalizar espacios, en `raw/` del documento citado, en el `locator` indicado. Detecta alucinaciones del LLM.
3. `test_quote_old_matches_previous`: si hay `quote_old`, aparece en la fuente de la versión anterior.
4. `test_effect_version_bijection`: cada efecto `applied` es referenciado por exactamente una versión. Toda versión no base referencia un efecto. Los efectos `pending` no tienen versión.
5. `test_pending_effects_surface`: cualquier regla con efectos `pending` se marca en la salida de la CLI. No es un fallo del test sino una señal en el reporte.
6. `test_intervals`: los invariantes de §2.2.
7. `test_generated_up_to_date`: regenerar SQLite/JSON/Markdown y comparar con lo versionado. Si difiere, falla (lección FedRAMP).
8. `test_consolidation_oracle`: si DNIT publica un manual consolidado nuevo, el estado de la KB a esa fecha debe coincidir campo por campo con el manual (lección MOC 7.0).

---

## 4. Cómo publican y versionan otros países (facturación electrónica)

### 4.1 Brasil (NF-e/NFC-e): el paralelo más cercano a SIFEN

**Estructura documental:**

- **MOC (Manual de Orientação do Contribuinte).** La versión 7.0 se publicó mediante el Ato COTEPE/ICMS nº 69 del 26/11/2020 y en el portal el 16/12/2020. **Consolida las NT publicadas hasta octubre de 2020.** Cada anexo, incluido el *Anexo I – Leiaute e Regras de Validação*, está identificado con su **clave MD5** en el acto. Hubo minutas intermedias (v7.02, mayo de 2019).
- **Notas Técnicas (NT AAAA.NNN).** Modifican el MOC entre consolidaciones. **Cada NT tiene versiones propias** (p.ej. NT 2019.001 llegó a la v1.70 en agosto de 2025; NT 2025.002 a la v1.52). Cada versión trae una tabla de histórico con la descripción del cambio y las fechas de **teste/homologação** y **produção**. Ejemplo: NT 2023.003 v1.30, "Alteração em regras de validação", teste 27/07/2026, produção 03/08/2026 (fuente secundaria).
- **Pacotes de Liberação (PL) de schemas.** Se versionan aparte (PL_009x, PL_010x…) y a veces **se publican antes de que se activen las reglas**. En 2021 se publicó un schema que permitía emitir sin aplicar ciertas reglas de validación hasta el 31/08/2021 (titular de noticia). **Esquema y regla tienen vigencias independientes.**

**Reglas de validación:**

- Las identifica el ID del campo más una secuencia: `I08-70`, `ZX02-20`, `N12a-30`, `K01-10`, `VC02-50`, `I08-140`.
- Cada regla se asocia a una rejeição (`cStat`) o a un efecto de alerta.
- **Tipos de cambio** declarados en las NT (ejemplo NT 2015.002, resumido por FocusNFe):
  - *incluída*: ZA01-30;
  - *alterada*: C18-14, I08-70 ahora con `idDest` en lugar de CFOP;
  - *excluída*: K01-10; I08-80 por duplicar I08-70;
  - *tornada obrigatória*: ZX02-24;
  - *postergada*: 7C21-10;
  - **opcional a critério da UF**: YA04a-20, ZX02-20 "opcional hasta 01/11/2016".
- Mensajes de rechazo que cambian sin que cambie la regla: I04-10 pasó a incluir el número de ítem.
- **NT de cambio puntual:** la NT 2026.009 v1.00 solo modifica la regla I08-140, sin cambio de leiaute ni de schema (fuente secundaria).
- **Suspensión inmediata:** en la NT 2021.004, la regla 840_K01-10 quedó suspendida y la 873_K01-20 restringida a operaciones de salida.

**Cómo lo manejan las librerías y los proveedores:**

- **nfelib (Akretion, Python).** Bindings generados desde los XSD oficiales con xsdata. Un directorio por versión mayor, y cada minor **sobrescribe** al anterior. Un test detecta cuando se publica un paquete nuevo. **Solo valida XSD**: su página no menciona reglas de negocio.
- **sped-nfe (nfephp, PHP).** Actualiza schemas por NT/PL (PL_010 v1.10b, v1.20b, v1.30 para la NT 2025.002-RTC). Mantiene historia de schemas por carpeta.
- **ACBr (Delphi).** `ValidarRegrasdeNegocios` reimplementa reglas localmente. En el foro de ACBr hay casos documentados de **rechazos locales que SEFAZ habría aceptado** y de reglas que la nueva versión del leiaute ya había corregido y la librería seguía aplicando (la solución fue restringir la regla a versiones < 4.0). Esto es evidencia directa de **R1 y R8**: una reimplementación local de reglas se desactualiza.
- **Proveedores (FocusNFe, Tecnospeed, Inventti, IOB).** Publican resúmenes por NT y versión con listas de reglas incluidas, alteradas o excluidas y fechas por ambiente, es decir, un **registro de efectos legible por humanos**. Ninguno de los consultados expone consultas "regla a fecha X" como producto.

**Lecciones para SIFEN:**

- El ciclo MOC (consolidado con MD5) → NT versionadas → nueva consolidación es casi idéntico a MT v150 → NT_E_KUATIA_0xx. **La consolidación oficial futura es el oráculo de pruebas** (§3.3, test 8).
- **Una NT no es inmutable.** Su identidad es (id, revisión/hash), no el nombre. En el portal de DNIT hay nombres de archivo como `NT_E_KUATIA_021_MT_V150+30.12.24` y `NT_E_KUATIA_018_MT_V150-+Junio`, que **sugieren reemisiones o variantes**; hay que verificarlo contra DNIT. DNIT también publica un "Listado Checksum MD5 de las versiones del Manual Técnico", lo que indica que **puede haber más de un PDF bajo la etiqueta "v150"**. `DocumentSource` debe identificarse por hash.
- **Fechas por ambiente y opcionalidad** son patrones reales. Para SIFEN no hay UF, pero sí ambiente de pruebas y producción.
- La severidad o el efecto (rechazo vs alerta) y la obligatoriedad cambian **sin cambiar el ID de la regla**, así que van en la versión.

### 4.2 México (CFDI 4.0, SAT)

- **Fuentes separadas con ciclos de vida propios:** Anexo 20 (estándar técnico y XSD), Guía de llenado, **Matriz de errores** (códigos `CFDI40xxx`, p.ej. CFDI40140: "El campo RegimenFiscal, no contiene un valor del catálogo c_RegimenFiscal") y **catálogos** (`catCFDI`). La matriz de errores **se actualiza independientemente** del XSD: en noviembre de 2022 se ajustaron códigos y se agregó uno nuevo, según Sovos.
- **Vigencia por clave de catálogo.** Las claves tienen fecha de inicio y fin de vigencia; por ejemplo, las claves 08 y 09 de tipo de relación terminaron el 30/06/2022 (IDC Online). La librería **phpcfdi** materializa esto en columnas `vigencia_desde` / `vigencia_hasta` (verificado en `cfdi_40_formas_pago.sql`).
- **phpcfdi/resources-sat-catalogs** es un patrón docs-as-data muy relevante:
  - la fuente versionada en Git es **SQL de texto** (`database/schemas/*.sql`, `database/data/*.sql`);
  - la base SQLite se **reconstruye** con `cat schemas/*.sql data/*.sql | sqlite3 catalogs.db`;
  - el `.db` se publica como asset de release, no como fuente;
  - la versión es `Estructura.Datos.Fecha` (p.ej. `1.5.20191216`): **versión de esquema separada de la versión de datos**, que es lo que el pedido plantea en la sección 34.
- **Convivencias y prórrogas sucesivas** entre CFDI 3.3 y 4.0 (§2.5).

**Lecciones:**

1. Códigos y mensajes, estructura (XSD), reglas y catálogos tienen **versionado independiente**. No hay que atarlos a una sola "versión SIFEN".
2. La vigencia por **valor de enumeración** existe: una NT puede agregar o retirar un valor de una lista sin tocar la regla. El modelo de enumeraciones necesita `from`/lápida por valor, o al menos la lista completa versionada.
3. "SQL o YAML de texto canónico en Git → SQLite derivado" es un patrón probado en producción.

### 4.3 Perú (SUNAT, CPE UBL 2.1)

- SUNAT publica las **reglas de validación como hoja Excel**, con una pestaña **"CódigosRetorno"**. Las nuevas versiones se publican con fecha de entrada en vigor: una hoja publicada el 09/12/2021 rigió desde el 17/12/2021, y la versión 2.1 entró en vigor en dos fechas, una para el primer grupo y otra para el resto (Sovos).
- **Tipos de severidad:** error (rechazo) vs **observación** (se acepta con observación).
- **Migración por fases de observación a error** (Comunicado N004-2021):
  - excluyó códigos **sin regla de validación** asociada (4016, 4017…);
  - excluyó códigos que aplican solo a ciertos comprobantes (Liquidación de Compra, DAE);
  - excluyó el código 4028 porque "no aplica a OSE": **la aplicabilidad depende del canal** (OSE vs SEE).
- **Artefactos ejecutables.** El facturador de SUNAT (SFS) incluye validaciones en XSLT. La librería `esolutions/xml` dice extraer sus reglas "del XSLT del SFS" e incluir 2077 códigos del Excel. greenter tiene un `cpe-validator`.
- No se verificó la estructura exacta de columnas del Excel vigente: no se descargó.

**Lecciones:**

1. La relación **código ↔ regla no es 1:1**: hay códigos sin regla y reglas que comparten código. El test `test_validation_codes_are_unique_when_expected` del pedido debe partir de que **N:M es posible** y declarar explícitamente cuándo se espera unicidad.
2. La severidad es temporal y por alcance.
3. Si la autoridad publica artefactos ejecutables (XSLT, Schematron), **son mejor fuente que el PDF** para extraer reglas. Para SIFEN hay que verificar si DNIT publica algo ejecutable más allá del XSD.

### 4.4 Colombia (DIAN, Anexo Técnico de Factura Electrónica)

- Los anexos técnicos se versionan (1.8, 1.9) y **se adoptan por resolución**. La Resolución 165/2023 adoptó el anexo 1.9 y la Resolución 008/2024 movió la fecha de adopción al 01/05/2024. Según el oficio 1531/2024, **publicar** la 1.9 no cambiaba la fecha: hasta el plazo regía la 1.8.
- **Reglas con ID alfanumérico** (FAD09c, FAD09e…) con marca **R** (rechazo) o **notificación**.
- **Eliminación y regla nueva en lugar de modificación:** la 1.9 **eliminó FAD09c** ("fecha de emisión no posterior a 10 días calendario") "para evitar interpretaciones diversas" y existe FAD09e ("la fecha de generación… debe coincidir con la fecha de la firma"), con **otro ID y otra semántica** (oficio 1532/2024).
- El mismo oficio aclara que las reglas de validación **no cambian la obligación legal** de oportunidad de emisión.

**Lecciones:**

1. Hace falta una **relación de linaje entre reglas** distinta del versionado: `replaces`/`replaced_by`, con la inversa derivada.
2. "Publicado" ≠ "aplicable": un documento con dos fechas, y a veces una tercera fijada por otro documento.
3. Hay que separar la validación técnica de la obligación normativa (§2.6).

### 4.5 Chile (SII, DTE)

- Las respuestas del SII distinguen al menos **aceptado**, **aceptado con reparos** (documento válido con observaciones; para corregirlo hay que anular) y **rechazado** (LibreDTE, Simplo; fuentes secundarias).
- Los códigos de detalle tienen forma `ÁREA-n-NNN`, por ejemplo `REF-2-780` y `TED-2-510` (reparos) frente a `REF-3-750` y `DTE-3-101` (rechazos). **Inferencia no verificada:** el dígito intermedio parece codificar la severidad.
- El SII sigue agregando validaciones por resolución: la Resolución Exenta SII N° 121 de 2026 implementa nuevas validaciones sobre archivos DTE. No se leyó en detalle.

**Lección:** tres niveles de severidad (aceptado, aceptado con observación, rechazado) son comunes. SIFEN también tendría un estado de "aprobado con observación" según el conocimiento previo de este análisis; **hay que verificarlo contra el Manual v150**. El modelo de severidad no debe ser booleano.

### 4.6 Europa (Peppol BIS Billing 3.0, EN 16931, XRechnung/KoSIT)

- **Peppol** separa tres fechas por release: *member review*, *publication* y **mandatory to use from**. Por ejemplo, la 3.0.21 tuvo revisión el 02/03/2026, publicación el 20/05/2026 y obligatoriedad desde el 17/08/2026.
- **Ciclo de severidad explícito:** las reglas nuevas entran como *warning* y pasan a *fatal* en una release posterior. Ejemplos: PEPPOL-COMMON-R049 en 3.0.13 → 3.0.14; DK-R-017 en 3.0.20 → 3.0.21, con la nota "initially a warning and consecutive release fatal". El plan no siempre se cumple como se anunció: PEPPOL-COMMON-R052 y R053 entraron como *warning* en la 3.0.20 y pasaron a error en la 3.0.21 porque se volvieron obligatorias para todos los perfiles.
- Las **release notes se organizan por ID de regla** con tipo de cambio (added, removed, updated, severity change) y justificación, por ejemplo "removed because duplicates UBL-SR-04".
- **KoSIT (Alemania)** publica configuraciones del validador (XSD + Schematron) etiquetadas **por fecha** (`v2026-01-31`) con la versión de XRechnung en el nombre del artefacto.

**Lecciones:**

1. Un **changelog por release organizado por ID de regla** es el "reporte de NT" del pipeline (sección 33 del pedido, paso 11).
2. El ciclo warning → fatal es exactamente "la severidad pertenece a la versión".
3. **Etiquetar releases de la KB por fecha** es práctica establecida y encaja con la sección 34 del pedido.

### 4.7 Tabla comparativa de patrones

| Patrón | BR | MX | PE | CO | CL | EU | ¿Aplica a SIFEN? |
|---|---|---|---|---|---|---|---|
| Manual base + documentos modificatorios | MOC + NT | Anexo 20 + matriz/catálogos | Excel de reglas | Anexo técnico + resoluciones | Formatos + resoluciones | BIS + releases | **Sí** (MT v150 + NT) |
| Consolidación oficial periódica | MOC 7.0 (NT hasta 10/2020) | — | Nueva hoja completa | Nueva versión del anexo | Nuevas versiones del formato | Cada release | Verificar si DNIT reemite el MT |
| Hash publicado por la autoridad | MD5 por anexo | — | — | — | — | — | **Sí** (MD5 de versiones del MT) |
| Documento modificatorio con versiones propias | NT v1.00…v1.70 | — | — | — | — | hotfix | **Probable** (nombres "+30.12.24"); verificar |
| Fechas distintas test/producción | Sí | — | Escalonadas | — | — | — | Probable; verificar en las NT |
| Prórrogas o postergaciones | Frecuentes | Frecuentes | — | Sí | — | Ocasionales | Asumir que sí |
| Severidad que cambia con el tiempo | Obrigatória/opcional | — | Observación → error | R/notificación | Reparo/rechazo | warning → fatal | **Sí** |
| ID eliminado y reemplazado por otro | Excluída + nueva | Códigos nuevos | — | FAD09c → FAD09e | — | Removed | **Sí** |
| Aplicabilidad por alcance | Por UF | Por complemento | OSE/SEE, tipo de comprobante | — | — | Por país (CIUS) | Ambiente y tipo de DE |
| Vigencia por valor de catálogo | Tablas | `vigencia_desde/hasta` | Catálogos | — | — | Code lists | **Sí** (enumeraciones) |
| Reglas ejecutables oficiales | No (PDF) | No | XSLT (SFS) | No | No | Schematron | Verificar |

---

## 5. Proyectos "docs-as-data" / "policy-as-code"

| Proyecto | Patrón | Qué tomar |
|---|---|---|
| **OpenAPI** (+ generadores de docs y linters como Spectral) | Una spec YAML/JSON canónica; documentación, clientes y validaciones **generados**; reglas de lint como código; `deprecated: true` por operación o campo. | El canónico estructurado genera el Markdown, nunca al revés. El lint de la spec corre en CI. |
| **OpenFisca** (rules as code, fiscal) | Parámetros en YAML con `values` **indexados por fecha de inicio**, `reference` (URL legal) **por valor**, `expected` para valores futuros previstos y tests en YAML con `period`. Un valor rige hasta la siguiente fecha; el orden en el archivo no importa. | **El precedente más directo** de "YAML canónico con tiempo válido + referencia legal por versión + futuro previsto". También el modelo de tests temporales declarativos ("a la fecha X, regla R ⇒ Y"). |
| **Sigma** (reglas de detección, YAML + JSON Schema) | `id` UUID estable; `status` (`stable`, `test`, `experimental`, `deprecated`, `unsupported`); `related` con `type` = `derived`, `obsolete`, `merged`, `renamed`, `similar`; `date` y `modified`. **ID nuevo** ante cambios lógicos mayores. | Vocabulario mínimo de linaje: tomar `obsolete`/`renamed` como `replaces`. Regla explícita de **cuándo un cambio crea ID nuevo y cuándo una versión**. Advertencia: `modified` manual duplica a Git. |
| **MITRE ATT&CK (STIX)** | `revoked` + relación `revoked-by` (reemplazado) vs `x_mitre_deprecated` (retirado sin reemplazo). Las librerías recomiendan filtrar ambos en consultas "actuales". | Distinguir "reemplazada por X" de "eliminada sin reemplazo". |
| **OSV** (vulnerabilidades, JSON + schema) | `published`, `modified` y `withdrawn`. Un registro retirado se excluye de las búsquedas pero **sigue accesible por ID**, para preservar la auditoría y que el ID no cambie de significado. | Las lápidas no se borran. Los IDs nunca cambian de significado. |
| **NIST OSCAL** | Catalog + profile (alteraciones por ID) → resolved catalog. | Ver §3.1: advertencia sobre "modify" y sobre derivados materializados desactualizados. |
| **phpcfdi resources-sat-catalogs** | SQL de texto en Git → SQLite reconstruible; versión `Estructura.Datos.Fecha`. | Canónico textual + SQLite derivado + versión de esquema separada de la versión de datos. |
| **Peppol / EN 16931 / KoSIT** | Artefactos de validación (Schematron) versionados con release notes por ID de regla y releases por fecha. | Changelog por ID, releases por fecha, y reglas ejecutables como artefacto de primera clase. |

**Patrones transversales:**

1. **Un archivo por entidad**: mejor diff, revisión e historia Git por regla.
2. **Schema** (JSON Schema o Pydantic) que valida el canónico en CI.
3. **Derivados regenerados y comparados en CI**: nunca editados a mano.
4. **Vocabulario de ciclo de vida pequeño y cerrado.**
5. **IDs estables, sin reutilización**, y **lápidas** en vez de borrados.
6. **Referencia a la fuente por versión**, no por entidad.
7. **Tests declarativos por fecha.**

---

## 6. Catálogo de conceptos simples reutilizables (sin adoptar estándares)

| # | Concepto | Origen | Forma mínima en la KB SIFEN |
|---|---|---|---|
| C1 | Entidad estable vs versión fechada | FRBR Work/Expression, SCD2 | `Rule{id}` + `RuleVersion{introduced_by, contenido completo}` |
| C2 | Registro de efectos con estado | legislation.gov.uk | `Effect{target, type, attributes, status: applied/pending/not_applicable}` por documento |
| C3 | Fecha en el efecto, inicio de versión derivado, fin derivado | AKN (force en el mod), OpenFisca | Sin `effective_to` ni `is_current` almacenados |
| C4 | Procedencia de la fecha + historia de postergaciones | ELI `commences`, NT de Brasil | `date_source`, `date_history[]` en el efecto |
| C5 | Versión prospectiva sin fecha | UK *prospective*, OpenFisca `expected` | `prod_from: null` y nunca "vigente" |
| C6 | Lápida en vez de borrado | OSV `withdrawn`, MITRE `revoked`/`deprecated` | `RuleVersion{status: removed}` |
| C7 | Linaje entre reglas distinto de versión | Sigma `related`, MITRE `revoked-by`, DIAN FAD09c→e | `replaces: [id]`, con la inversa generada |
| C8 | Citas old/new como aserción | AKN `textualMod`, JSON Patch `test` | `quote_old`/`quote_new` verificados contra `raw/` |
| C9 | Atributos declarados en el cambio | OSCAL `alter` por ID, NT de Brasil "alterada" | `attributes: [condition]` + test de diff |
| C10 | Dimensión de aplicabilidad separada del tiempo | UK *extent*, BR por UF, PE OSE/SEE | `env` (test/prod) y, solo si hace falta, `doc_types` |
| C11 | Severidad en la versión | Peppol warning→fatal, SUNAT observación→error | `severity` dentro de `RuleVersion` |
| C12 | Identidad de documento por hash | MD5 de anexos del MOC, MD5 del MT de DNIT | `DocumentSource{id, revision, sha256}`; el nombre no basta |
| C13 | Consolidación oficial como oráculo | MOC 7.0 | Test de equivalencia KB@fecha vs manual consolidado |
| C14 | La consolidación no es autoridad | EUR-Lex | Toda respuesta cita el documento fuente |
| C15 | Fecha base explícita | UK 1991-02-01 | "Baseline = MT v150 (sha256 …)"; sin historia anterior |
| C16 | Tiempo de transacción = Git disciplinado | Fowler (separar ejes) | Tags `kb-AAAA.MM.DD`, `main` protegido, archivo por entidad |
| C17 | Versión de esquema ≠ versión de datos | phpcfdi `Estructura.Datos.Fecha` | `software 0.x.y` + `kb AAAA.MM.DD (estado NT0xx)` |

---

## 7. Advertencias y anti-patrones detectados

1. **Bitemporalidad implementada en los datos.** Fowler la desaconseja salvo necesidad. Git ya cubre el eje de transacción. → No hacerlo.
2. **Patch ejecutable reproducido sobre la base.** Es frágil ante el orden, ante bases equivocadas y ante cambios parciales (R3). Ni las autoridades lo usan: Brasil reemite NT completas y OSCAL eliminó "modify".
3. **`valid_to` / `is_current` / `updated_at` almacenados.** Son derivables y divergen (R5).
4. **Asumir una única "regla vigente".** Puede haber convivencia, diferencias entre test y producción, o versiones prospectivas. La consulta debe poder responder "depende del ambiente", "fecha por definir" o "hay efectos pendientes".
5. **Asumir que las fechas son estables.** Las postergaciones son la norma en Brasil y México.
6. **Asumir que nombre de documento = identidad.** NT reemitidas o variantes y PDF del MT con varias versiones MD5 → identificar por hash.
7. **Asumir código ↔ regla 1:1.** SUNAT tiene códigos sin regla y reglas que comparten código.
8. **Reimplementar reglas localmente y presentarlas como autoridad.** ACBr muestra el modo de falla: rechazos falsos y reglas obsoletas. `sifen analyze` debe decir "posible violación según la KB (snapshot X, fuente NT Y)".
9. **Importar terminología jurídica (vigencia, eficacia, aplicación) sin definirla.** Ni LegalRuleML la tiene formalizada. Hay que definir la semántica operativa propia (§2.6).
10. **Derivado materializado sin control de frescura.** FedRAMP lo advierte explícitamente. → Test de "regenerar y comparar".
11. **Modelar todas las dimensiones posibles por adelantado** (UF, canal, complemento, extent…). Solo hay que modelar las que aparezcan en las NT de SIFEN (YAGNI, sección 26 del pedido).
12. **Esperar prior art open source que resuelva "regla a fecha X" en e-invoicing.** No se encontró: las librerías trabajan con "último + changelog". La KB debe tomar sus patrones de informática jurídica y de rules-as-code (OpenFisca), no de librerías de facturación.

---

## 8. Qué NO adoptar (y por qué)

| Estándar o tecnología | Motivo para no adoptarlo |
|---|---|
| Akoma Ntoso XML completo | Pensado para legislación textual multinivel con FRBR completo y naming convention. Costo alto y sin beneficio para un manual y unas decenas de NT. |
| ELI (RDF, URIs) | No hay necesidad de interoperar con sistemas de información legislativa. Basta con el vocabulario. |
| LegalRuleML | Semántica temporal no formalizada, ecosistema pequeño y costo cognitivo alto. |
| Base bitemporal (SQL:2011 temporal, XTDB, Datomic) | Git cubre el tiempo de transacción. SQLite no soporta tablas temporales SQL:2011 y no hacen falta. |
| Event store / event sourcing | Ver §2.3. Además lo excluye la sección 30 del pedido. |
| Motor de resolución tipo OSCAL o motor de JSON Patch | Los "patches" son aserciones, no instrucciones (§3.3). |
| Schematron/XSLT propio para reglas de negocio | Solo tendría sentido si DNIT publica artefactos ejecutables. Si no, es reimplementación local con el riesgo de ACBr. |

---

## 9. Puntos a verificar contra documentación DNIT (antes de fijar el modelo)

1. ¿Las NT de SIFEN traen **fechas separadas** para el ambiente de pruebas y para producción? ¿Traen **periodos de convivencia**?
2. ¿DNIT **reemite** NT, con versiones o revisiones del mismo número? ¿Qué significan sufijos de archivo como `+30.12.24` o `-+Junio`?
3. ¿El "Listado Checksum MD5 de las versiones del Manual Técnico" indica que existen **varias revisiones del PDF v150**? ¿Cuál es la base?
4. ¿Los XSD (publicados como RAR sin versión visible en la página) tienen un **número de versión interno**? ¿Cambian con las NT?
5. ¿Hay **postergaciones** de NT comunicadas fuera de la NT (resoluciones, avisos)? Si las hay, son documentos fuente de **fechas**.
6. ¿La relación **código de rechazo ↔ validación** es 1:1 en SIFEN o N:M?
7. ¿Existe en SIFEN el estado **"aprobado con observación"**? ¿Qué validaciones son observación y cuáles rechazo? ¿Alguna NT cambió una de observación a rechazo?
8. ¿DNIT publica algún **artefacto ejecutable** de validación (además del XSD)?
9. ¿Alguna NT **elimina un ID de validación y crea otro** (patrón DIAN) o siempre modifica en el lugar (patrón Brasil)?

---

## 10. Fuentes consultadas

**Informática jurídica**

- OASIS Akoma Ntoso v1.0 – `textualMod`: https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/os-part2-specs_xsd_Element_textualMod.html
- OASIS Akoma Ntoso – tipo `TextualMods`: https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/os-part2-specs_xsd_Simple_Type_TextualMods.html
- OASIS Akoma Ntoso – `timeInterval`: https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/os-part2-specs_xsd_Element_timeInterval.html
- OASIS Akoma Ntoso – atributo `period`: https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/os-part2-specs_xsd_Attribute_Group_period.html
- Laws.Africa – Works and expressions: https://developers.laws.africa/get-started/works-and-expressions
- legislation.gov.uk – ayuda (revised, point in time, prospective, effects): https://www.legislation.gov.uk/help
- legislation.gov.uk – ejemplo de tabla de efectos: https://www.legislation.gov.uk/changes/affecting/ukpga/2018/20
- ELI 2.0 – `LegalExpression`: https://repository.data2type.de/ELI/v_2.0/html/co.LegalExpressionType.html
- EUR-Lex – consolidación (glosario): https://eur-lex.europa.eu/EN/legal-content/glossary/consolidation.html
- EUR-Lex – aviso sobre textos consolidados: https://eur-lex.europa.eu/content/legis/avis_consolidation.html
- OASIS LegalRuleML – issue sobre la falta de definición de in force, efficacy y applicability: https://issues.oasis-open.org/browse/LEGALRULEML-2

**Modelos temporales**

- Martin Fowler, *Bitemporal History*: https://martinfowler.com/articles/bitemporal-history.html
- RFC 6902 (JSON Patch) y RFC 7396 (JSON Merge Patch): conocimiento de referencia, no re-consultadas en esta sesión.

**Brasil**

- Ato COTEPE/ICMS 69/2020 (MOC 7.0): https://www.legisweb.com.br/legislacao/?id=405596
- Publicación del MOC 7.0: https://netcpa.com.br/noticias/nf-e-publicado-manual-de-orientacao-ao-contribuinte-moc-versao-70-nf-e-e-nfc-e/7780
- FocusNFe – cambios de la NT 2015.002: https://focusnfe.com.br/notas-tecnicas/dfe/2015-002/
- Postergación de NT 2025.002 v1.52, NT 2026.007 y NT 2026.008 (fuente secundaria): https://notagateway.com.br/?p=15121
- IOB – fechas de la reforma tributaria en NF-e/NFC-e: https://noticias.iob.com.br/reforma-tributaria-datas-nf-e-nfc-e/
- nfelib (PyPI): https://pypi.org/project/nfelib/
- sped-nfe (Packagist): https://packagist.org/packages/nfephp-org/sped-nfe
- Foro de ACBr (tag "rejeição"): https://www.projetoacbr.com.br/forum/tags/rejeicao/
- Publicación del pacote de schemas 009f: https://netcpa.com.br/colunas/nf-e-12062021-publicado-pacote-de-schemas-009f-da-nf-e/10609
- Schema que permite emitir sin aplicar reglas hasta el 31/08/2021: https://netcpa.com.br/noticias/nf-e-publicado-schema-que-possibilita-a-emissao-de-documentos-fiscais-sem-aplicacao-de-regras-de-validacao-ate-31082021/8866

**México**

- Sovos – actualización de la matriz de errores CFDI 4.0: https://sovos.com/es/cambios-regulatorios/iva/mexico-sat-actualiza-matriz-errores-cfdi-4-0/
- IDC Online – actualización de catálogos CFDI: https://idconline.mx/fiscal-contable/2023/05/12/actualizacion-a-los-catalogos-del-cfdi
- phpcfdi/resources-sat-catalogs: https://github.com/phpcfdi/resources-sat-catalogs
- Esquema `cfdi_40_formas_pago.sql` (columnas de vigencia): https://raw.githubusercontent.com/phpcfdi/resources-sat-catalogs/master/database/schemas/cfdi_40_formas_pago.sql
- Prórroga de CFDI 4.0: https://www.elcontribuyente.mx/2022/06/la-prorroga-a-la-factura-4-0-aplica-para-todos-los-tipos-cfdi/
- Bloomberg Línea – prórroga de CFDI 4.0 (2023): https://www.bloomberglinea.com/2023/04/01/habra-prorroga-del-sat-para-el-cfdi-40-y-para-la-declaracion-anual-de-2023/

**Perú**

- Comunicado N004-2021 de SUNAT (copia de terceros): https://guru-soft.com/wp-content/uploads/2021/06/COMUNICADO_N004-2021_CPE_SUNAT.pdf
- Sovos – nueva hoja de reglas de validación de CPE: https://sovos.com/es/cambios-regulatorios/iva/peru-sunat-publica-nueva-hoja-reglas-validacion-cpe/
- Sovos – versión 2.1 de las reglas de validación de CPE: https://sovos.com/es/cambios-regulatorios/iva/peru-nueva-version-2-1-reglas-validacion-cpes/
- greenter/validator: https://root.packagist.org/packages/greenter/validator

**Colombia**

- Oficio DIAN 1531/2024: https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_1531_2024.htm
- Oficio DIAN 1532/2024: https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_1532_2024.htm
- Resolución DIAN 0165/2023: https://normograma.mintic.gov.co/docs/pdf/resolucion_dian_0165_2023.pdf

**Chile**

- LibreDTE – estados al enviar un DTE al SII: https://www.libredte.cl/docs/procesos-sii/cuales-son-los-estados-al-enviar-un-dte-al-sii.pdf
- Simplo – tabla de errores del SII: https://simplo.cl/recursos/tabla-errores-sii/
- SII – Resolución Exenta 121/2026: https://www.sii.cl/normativa_legislacion/resoluciones/2026/reso121.pdf

**Europa**

- Peppol BIS Billing 3.0 – release notes: https://docs.peppol.eu/poacc/billing/3.0/release-notes/
- KoSIT – configuración del validador para XRechnung: https://github.com/itplr-kosit/validator-configuration-xrechnung

**Docs-as-data**

- OpenFisca – parámetros legislativos: https://openfisca.readthedocs.io/en/latest/coding-the-legislation/legislation_parameters.html
- Especificación de reglas Sigma: https://github.com/SigmaHQ/sigma-specification/blob/main/specification/sigma-rules-specification.md
- mitreattack-python: https://mitreattack-python.readthedocs.io/en/latest/mitre_attack_data/mitre_attack_data.html
- OneUptime – cómo maneja OSV los registros retirados (fuente secundaria): https://oneuptime.com/blog/post/2026-07-23-osv-withdrawn-deleted-updated/view
- NIST OSCAL – definiciones del modelo profile: https://pages.nist.gov/OSCAL-Reference/models/v1.0.6/profile/xml-definitions/
- FedRAMP – resolución de perfiles: https://automate.fedramp.gov/documentation/general-concepts/profile-resolution

**SIFEN (solo para el paralelo)**

- DNIT e-Kuatia – documentación técnica: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica

---

### Nota de proceso

Una consulta WebFetch a un PDF de NT brasileña (NT 2023.003 v1.30) hizo que la herramienta guardara automáticamente una copia binaria en la carpeta de resultados de herramientas de la sesión. No se abrió ni se ejecutó, porque el renderizado de PDF no estaba disponible, y su contenido **no** se usó en este informe. Después no se volvieron a pedir PDF.

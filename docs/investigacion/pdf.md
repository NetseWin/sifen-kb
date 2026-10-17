# Estrategia PDF → estructura para la KB SIFEN (Manual Técnico v150 + Notas Técnicas)

Fecha del análisis: 2026-10-17. Alcance: decisión abierta n.º 1 (Marker vs Docling vs MinerU u otra), sección I del formato exigido y riesgo R6 ("la automatización de PDFs introduce errores silenciosos").

Convención: **[V]** = verificado en fuente primaria (PyPI, repositorio oficial, documentación oficial) durante este análisis; **[S]** = fuente secundaria (blog/reseña), plausible pero no confirmada; **[I]** = inferencia o criterio propio; **[PV]** = pendiente de verificar contra el PDF real o en un spike.

---

## 0. Recomendación en una frase

**Núcleo determinista con pdfplumber (+ pypdfium2 como segundo motor de texto) que extrae las tablas de campos y de validaciones *directamente a registros JSONL con provenance de página y bbox*; Markdown solo como vista generada. Docling (versión fijada, OCR desactivado, modelos descargados localmente) queda como herramienta *opcional y no canónica*: verificación cruzada de tablas, vista legible de la prosa y vía de OCR para Notas Técnicas escaneadas. Marker, MinerU, PyMuPDF y los servicios cloud quedan descartados para el pipeline.**

La propuesta original ("parser estructural → Markdown RAW") es **parcialmente incorrecta**: el problema real del Manual v150 no es convertir a Markdown, sino reconstruir sin pérdidas *tablas de especificación que cruzan páginas*, y ninguna de las tres herramientas candidatas resuelve eso de forma verificable. Markdown como capa de evidencia destruye justo lo que hay que conservar (límites de celda, filas partidas, página/coordenadas).

---

## 1. Qué sabemos del documento (y qué no)

| Hecho | Estado | Implicación |
|---|---|---|
| El Manual v150 tiene 217 páginas (`/Count 217` en el árbol de páginas) | [V] (lectura del PDF publicado por DNIT vía WebFetch) | Volumen pequeño: el rendimiento no es criterio decisivo. |
| Fuentes TrueType embebidas (Calibri, Arial, Times New Roman) → PDF digital, probablemente exportado desde Word | [V] fuentes / [I] origen Word | No hace falta OCR para el manual. Aplicar OCR indiscriminadamente **empeoraría** la fidelidad. |
| El PDF es **etiquetado** (`/StructTreeRoot`, `/MarkInfo <</Marked true>>`) | [V] | Oportunidad importante: si Word etiquetó las tablas como `Table/TR/TD`, el árbol de estructura da la segmentación de celdas *sin heurística geométrica*, incluso para filas que Word partió entre páginas. **[PV]**: la calidad del etiquetado de Word varía; hay que comprobarlo. |
| Páginas muestreadas A4 vertical, sin `/Rotate` | [V] solo páginas 3 y 21 | **[PV]** el resto (puede haber páginas apaisadas con tablas anchas). |
| Hay imágenes embebidas (p. ej. páginas 3 y 21) | [V] | Riesgo de pérdida silenciosa: contenido normativo dentro de imágenes (capturas de tablas, XML, diagramas) es invisible para cualquier extractor de texto. Hay que detectarlo y tratarlo aparte. |
| DNIT publica un "Listado Checksum MD5 de las versiones del Manual Técnico" | [V] | Verificar el MD5 oficial al ingerir; guardar además SHA-256 propio. |
| NT_E_KUATIA_001 a 027, todas sobre MT_V150; los enlaces de Liferay llevan un timestamp (`?t=`) — NT027: 2026-03-09; NT021: 2024-12-30; Manual: 2023-06-21 | [V] enlaces / [I] interpretación del timestamp | El `?t=` es fecha de subida/modificación del archivo en el portal, **no** fecha oficial de publicación ni de vigencia. Útil como señal de "cambió el archivo", nunca como `published_at`. |
| Nombres exactos de columnas de las tablas de campos y validaciones | **[PV]** | No pude leer el contenido (streams comprimidos). Todo lo que sigue sobre columnas ("ID", "Campo", "Nodo Padre", "Tipo Dato", "Longitud", "Ocurrencia", "Observaciones", "Código", "Mensaje"…) es **ilustrativo** y debe confirmarse en el spike. |
| Si alguna NT está escaneada | **[PV]** | Lo decide la etapa de sondeo (sección 7), no una suposición. |

Nota de transparencia: al intentar leer el PDF con WebFetch, la herramienta guardó automáticamente una copia binaria en la caché de resultados de herramientas de Claude Code (`C:\Users\hugo.maldonado\.claude\projects\...\tool-results\webfetch-1792252610187-0hqjfk.pdf`). No se abrió, ejecutó ni procesó; no forma parte de `sources/` y no debe usarse como fuente (la ingesta oficial debe descargar y verificar contra el MD5 de DNIT).

---

## 2. Estado actual de las herramientas (octubre 2026)

| Herramienta | Versión vigente [V] | Licencia del código | Licencia de modelos/pesos | Riesgo para uso comercial |
|---|---|---|---|---|
| **pdfplumber** | 0.11.10 (2026-06-14) | MIT | No usa modelos | Ninguno |
| **pdfminer.six** (base de pdfplumber) | 20260107 | MIT | — | Ninguno. Ojo: CVE-2025-64512 y CVE-2025-70559 (deserialización pickle en CMaps) corregidas en ≥ 20251230 [S]; pdfplumber 0.11.10 ya exige 20260107 [V]. |
| **pypdfium2** | 5.14.0 (2026-10-04) | Apache-2.0 o BSD-3-Clause; PDFium bajo licencia tipo BSD | — | Ninguno |
| **docling** | 2.140.0 (2026-10-16) | MIT | Heron (layout, RT-DETRv2, 17 clases incl. Page-header/Page-footer/Code/Table): apache-2.0 [V]; repo `docling-models` (TableFormer): etiquetas cdla-permissive-2.0 y apache-2.0 [V] | Bajo, **siempre que no se activen presets VLM** que carguen checkpoints de terceros (p. ej. chandra-ocr-2 bajo OpenRAIL) [S] |
| **docling-parse** | 7.22.3 (2026-10-13) | MIT | — | Ninguno. Ruedas Windows x86-64/ARM64 para CPython 3.10–3.14 [V] |
| **docling-slim** | 2.140.0 | MIT | Extras opt-in | Instalación base ~50 MB; torch solo con extras de modelos [V/S] |
| **marker-pdf** | 2.0.0 (2026-07-20) | Apache-2.0 (antes GPL-3.0) [V LICENSE actual] | "Modified AI Pubs Open Rail-M": requiere licencia comercial si la entidad tuvo **> USD 5 M de ingresos brutos el año anterior**, **o levantó > USD 5 M de financiación**, o el uso **compite con Datalab** [V MODEL_LICENSE] | **Alto/indeterminado**: depende de la facturación de la empresa del usuario; según [S], el modelo de layout se usa incluso con OCR desactivado, así que los términos de pesos aplican en todos los modos. |
| **surya** (motor de Marker) | Surya OCR 2 | Apache-2.0 | Mismo OpenRAIL-M modificado con umbral USD 5 M [V] | Igual que Marker |
| **MinerU** | 4.0.12 (2026-10-11) | "MinerU Open Source License" (Apache-2.0 + condiciones) desde 3.1.0 (2026-04-18); antes AGPL-3.0 [V changelog] | Repos torch apache-2.0; repos ONNX/GGUF sin etiqueta de licencia, uno desde cuenta individual [S] | Condiciones: licencia separada si la empresa + afiliadas superan **100 M MAU o USD 20 M de ingresos mensuales**; atribución obligatoria si se ofrece servicio online a terceros; **terminación automática** si se incumple [V LICENSE.md]. Improbable que aplique al usuario, pero es una licencia no estándar (`LicenseRef-…`) que requiere revisión legal. |
| **PyMuPDF / pymupdf4llm / pymupdf-layout** | 1.28.2 (2026-08-06) | **AGPL-3.0 o licencia comercial Artifex** | pymupdf-layout también dual AGPL/comercial [V] | **Alto** en entorno corporativo: AGPL suele estar vetada por políticas de compliance aunque el uso interno no distribuya. |
| **Camelot** | 2.0.0 (2026-06-04) | MIT | Extra `ml` opcional con torch | Ninguno (sin el extra `ml`) |
| **Unstructured** | 0.27.28 (2026-10-16) | Apache-2.0 | Modelos hi_res | Bajo, pero **no soporta Python 3.14** (`>=3.11,<3.14`) [V] y exige tesseract + poppler para PDF |
| **OpenDataLoader PDF** | 2.5.13 (2026-10-13) | Apache-2.0 (antes MPL-2.0) | Modo local sin IA | Bajo; **requiere Java 11+** [V] |
| **LiteParse** (LlamaIndex) | — | "open source", Apache-2.0 según [S] | — | Distribución npm/TypeScript; sin estructura de tablas ni Markdown según la propia LlamaIndex [S]. No aporta. |

Observación sobre ritmo de cambios: Docling publicó de la 2.111 (agosto) a la 2.140 (octubre) — unas 30 versiones menores en dos meses [V/S]; MinerU pasó de 2.x a 4.x en un año, con cambio de licencia en medio [V]; Marker se reescribió por completo en 2.0 [V]. **Para una KB regulatoria, esa volatilidad es un argumento a favor de un núcleo con dependencias estables (pdfminer.six/pdfplumber cambian poco) y en contra de hacer canónica la salida de un modelo.**

---

## 3. Matriz de evaluación para *este* caso

Escala: ●●● bueno · ●● aceptable · ● débil · ✗ descalificante. Basado en documentación oficial + criterio propio; **no** en un benchmark ejecutado sobre el Manual v150 (eso es el spike de la sección 11).

| Criterio | pdfplumber (+pypdfium2) | Docling (pipeline estándar) | MinerU 4 | Marker 2 | PyMuPDF/4llm | Cloud (Azure DI, Mistral OCR 4, LlamaParse) |
|---|---|---|---|---|---|---|
| Fidelidad de texto en PDF digital | ●●● (texto literal de la capa de texto) | ●●● (docling-parse + cell matching) | ●● (pipeline orientado a VLM) | ●● (modo `--disable_ocr` 43,6 % en olmOCR-bench según Datalab) | ●●● | ●● (reconoce imagen; puede "corregir" texto) |
| Tablas largas que cruzan páginas | ●● (por página; *stitching* propio, verificable) | ● (por página, sin fusión nativa; necesita el mismo *stitching*) [S] | ●● (fusión heurística nativa desde 2.2.0, opaca) [V] | ● (fusión solo en modo LLM) [V] | ●● | ●–●● (variable; fusión opaca) |
| Filas partidas por salto de página | ●● (detectable con geometría; ●●● si el árbol de etiquetas sirve) | ● | ● | ● | ●● | ● |
| Headers/footers | ●●● (bandas + repetición + `tag` Artifact, auditable) | ●● (clases Page-header/footer → capa *furniture*; depende del modelo) | ●● | ●● | ●● | ●● |
| XML embebido / código | ●● (literal; requiere detectar bloque) | ●● (clase Code) | ●● | ●● | ●● | ● (riesgo de normalizar espacios/símbolos) |
| Layouts complejos | ● (no lo necesita: documento Word de una columna) [I] | ●●● | ●●● | ●●● | ●● | ●●● |
| OCR | ✗ (no hace OCR) | ●●● (RapidOCR/EasyOCR/Tesseract locales) | ●●● | ●●● | ●● | ●●● |
| Provenance página/bbox | ●●● (cada carácter con coordenadas, fuente, tamaño, `mcid`, `tag`) | ●●● (`prov`: `page_no`, `bbox`, `charspan`; `TableCell` con offsets y bbox) [V] | ●● | ●● | ●●● | ●● |
| Determinismo | ●●● (Python puro; misma versión → misma salida) [I] | ●● (redes neuronales en CPU; repetible en la misma máquina en la práctica, **no garantizado** entre CPU/hilos/versiones de torch) [I, PV] | ● | ● | ●●● | ✗ (modelos cambian del lado del servidor) |
| Instalación Windows / Python 3.13 | ●●● (puro Python + ruedas) | ●● (~1,3 GB de venv + ~0,5 GB de modelos [S]; torch CPU desde PyPI en Windows [V]) | ● (avisos específicos de reinstalación en Windows; torch GPU aparte) [V] | ● (servidor de inferencia vLLM/llama.cpp) [V] | ●●● | ●●● |
| Reproducibilidad (pinning) | ●●● (`uv.lock`) | ●● (paquete fijable; revisiones de modelos HF **[PV]**) | ● | ● | ●●● | ✗ |
| Mantenimiento / estabilidad de API | ●●● | ●● (muy activo, cambios frecuentes) | ● (churn alto) | ● (reescritura reciente) | ●●● | ●● |
| Licencia | ●●● MIT | ●●● MIT + pesos permisivos | ●● (custom, revisión legal) | ✗/● (umbral USD 5 M) | ✗/● (AGPL o pago) | ●● (contrato SaaS) |
| Coste | 0 | 0 | 0 | 0 o licencia | 0 o licencia | Trivial (~217 páginas ≈ 1–3 USD) |
| Automatización | ●●● | ●●● | ●● | ●● | ●●● | ●● (cuenta, claves, red) |

---

## 4. Análisis por herramienta

### 4.1 pdfplumber (MIT) — **núcleo recomendado**
- Da acceso a cada `char`/`word`/`line`/`rect` con coordenadas, `fontname`, `size`, y atributos experimentales `mcid` y `tag` (contenido marcado) [V]. Soporta `Page.structure_tree` para PDFs etiquetados desde 0.10.4 [V].
- Extracción de tablas por estrategia `lines` / `lines_strict` / `text` / `explicit`, con `snap_tolerance`, `join_tolerance`, `intersection_tolerance`; `find_tables()` devuelve `Table` con `bbox`, `cells`, `rows`, `columns` [V]. Depuración visual con `to_image().debug_tablefinder()` [V] — ideal para la revisión humana de páginas marcadas.
- **No** maneja tablas multipágina ni encabezados repetidos: trabaja página a página [V]. Eso es una ventaja disfrazada: el *stitching* lo escribimos nosotros, con reglas explícitas, testeables y con registro de cada decisión.
- Para un documento Word de una columna con tablas con bordes, la estrategia `lines` es la apuesta natural [I, PV].
- Limitaciones: lento comparado con motores en C (para 217 páginas se esperan minutos, no horas [I, PV]); no hace OCR.

### 4.2 pypdfium2 (Apache-2.0/BSD) — segundo motor de texto y renderizado
- Motor independiente (PDFium, el de Chrome) con `get_text_bounded()`/`get_text_range()` [V], ruedas Windows [V].
- Uso: (a) **extracción dual**: comparar el texto normalizado por página entre pdfminer y PDFium detecta problemas de mapeo de glifos/ToUnicode que un solo motor no ve; (b) renderizar páginas a PNG para *golden pages* y revisión visual. pdfplumber ya lo usa para renderizar, así que no agrega dependencia nueva.

### 4.3 Docling (MIT, IBM → LF AI & Data) — **opcional, no canónico**
- Lo que aporta de verdad: modelo de layout Heron (apache-2.0) que clasifica Page-header, Page-footer, Section-header, Table, Code, etc.; TableFormer para estructura de tablas; `DoclingDocument` con JSON sin pérdidas, `body` vs `furniture` (headers/footers fuera del cuerpo), `prov` con `page_no`, `bbox`, `charspan`, y `TableCell` con `start_row_offset_idx`/`end_row_offset_idx`, `column_header`, `row_header`, `bbox` [V].
- Backend de PDFs digitales: docling-parse (por defecto el backend *threaded* desde 2.123.0; se eliminó pypdfium del backend en 2.128.0) [V]. `do_cell_matching=True` toma el texto de las celdas de la capa de texto del PDF, no del modelo [V] — bueno para fidelidad.
- Pipeline `native` (desde 2.126.0): solo docling-parse, sin layout, OCR ni tablas; "un ítem de texto por celda de texto nativa" [V]. Es básicamente lo mismo que pdfplumber en otro formato: **no** resuelve tablas.
- Debilidades para este caso:
  1. **Sin fusión nativa de tablas multipágina** [S: respuesta de bot en discusión #2744 y reseña que remite al issue #3698]. Habría que escribir el mismo *stitching* que con pdfplumber, pero sobre una salida probabilística.
  2. Reseña independiente (Docling 2.111, CPU): 2 de 7 tablas sintéticas **descartadas por clasificarse como imagen** [S]. Para una KB regulatoria, un error de clasificación que hace *desaparecer* una tabla es exactamente el error silencioso a evitar.
  3. Determinismo no documentado [PV]; en CPU suele ser repetible en la misma máquina con el mismo número de hilos, pero no hay garantía entre CPUs/versiones de torch [I].
  4. Peso: ~1,3 GB de entorno + ~0,5 GB de modelos [S]; 6–15 s/página en CPU para PDFs digitales densos según la misma reseña [S] → 217 páginas ≈ 20–55 min. Aceptable puntualmente; inaceptable en cada ejecución de CI.
  5. Cadencia de versiones muy alta → obliga a fijar versión exacta y a regenerar *golden tests* en cada actualización.
- Conclusión: buena herramienta, pero su valor diferencial (layout de páginas complejas, OCR) es justo lo que el Manual v150 **no** necesita. Útil como verificador cruzado y como vía de OCR.

### 4.4 Marker 2 (Datalab) — **descartado**
- El código pasó a Apache-2.0, pero los pesos (Surya) exigen licencia comercial por encima de USD 5 M de ingresos del año anterior **o** USD 5 M de financiación total, y prohíben usos que compitan con Datalab [V]. Para una empresa con uso comercial cuyo tamaño no conocemos, eso es un bloqueo legal hasta que alguien de la empresa confirme las cifras — y además la cláusula de "competencia" es ambigua.
- Técnicamente: la fusión de tablas entre páginas solo existe en modo LLM (`--use_llm`, por defecto contra Gemini) [V] → nube y no determinismo. Según la propia Datalab (olmOCR-bench, benchmark general, no específico de tablas): `balanced` (GPU) 76,0 %, `fast` (por defecto en CPU) 66,6 %, sin OCR 43,6 % [V].
- En Windows: el modo de calidad usa un servidor de inferencia (vLLM requiere Docker + NVIDIA Container Toolkit; CPU vía llama.cpp `llama-server`) [V]. Complejidad sin beneficio para un PDF digital.

### 4.5 MinerU 4 (OpenDataLab) — **descartado (no por licencia AGPL, que ya no aplica)**
- Corrección a un supuesto frecuente: **MinerU ya no es AGPL** desde 3.1.0 (2026-04-18); ahora usa una licencia propia basada en Apache-2.0 con umbrales (100 M MAU / USD 20 M ingresos mensuales), atribución en servicios online y terminación automática [V]. Además retiró dos modelos AGPL y uno CC-BY-NC-SA [S].
- A favor: tiene fusión de tablas entre páginas desde 2.2.0, mejorada en 2.7.2 [V]; soporta CPU y Windows [V].
- En contra: orientado a VLM; fusión heurística opaca (no se puede auditar *por qué* unió dos fragmentos); churn de versiones; licencia no estándar que el área legal debe revisar; algunos artefactos de modelos sin licencia declarada [S]; notas de soporte de Windows sobre procesos residuales y reinstalaciones [V]. Para un PDF digital no aporta lo suficiente para justificar ese riesgo.

### 4.6 PyMuPDF / pymupdf4llm / pymupdf-layout — **descartado salvo compra de licencia**
- Técnicamente excelente (rápido, buen texto, `find_tables()`), pero AGPL-3.0 o licencia comercial Artifex, incluido el nuevo módulo de layout [V]. En uso puramente interno sin distribución ni servicio de red, AGPL probablemente no obliga a nada [I, no es asesoría legal], pero muchas empresas lo prohíben por política y el beneficio frente a pdfplumber+pypdfium2 es marginal para 217 páginas.

### 4.7 Camelot 2.0 (MIT) — **opcional como tercer extractor**
- Reescritura de 2026 con flavors `lattice`, `stream`, `network`, `hybrid`, `ml`, backend pdfium por defecto, sin Ghostscript obligatorio [V]. `lattice` es adecuado para tablas con bordes. Solo merece entrar si el spike muestra que pdfplumber y el árbol de etiquetas discrepan a menudo y hace falta un desempate. No en el MVP.

### 4.8 Unstructured, OpenDataLoader, LiteParse, otros
- **Unstructured**: pesado (tesseract + poppler para PDF), no soporta Python 3.14, sin ventaja sobre Docling para tablas. Descartar.
- **OpenDataLoader PDF**: interesante (Apache-2.0, modo local determinista, JSON con bbox, filtrado de header/footer) [V], pero exige Java 11+ y su detección local de tablas cubre "tablas simples con bordes"; para tablas complejas delega en un backend "hybrid" que usa Docling [V]. Añade un runtime (JVM) sin resolver el *stitching*. Vigilar, no adoptar.
- **LiteParse**: sin estructura de tablas [S]. No aplica.

### 4.9 Servicios cloud — **descartados del pipeline; como mucho "tercera opinión" manual**
- Precios de referencia: Mistral OCR 4 ≈ USD 4/1000 páginas (USD 2 en batch), lanzado en junio de 2026 [S]; Azure Document Intelligence Layout ≈ USD 10/1000 páginas [S, cifras contradictorias]; LlamaParse con créditos (1–45 por página, USD 1,25/1000 créditos) y caché de 48 h [S].
- **El coste no es el argumento** (el manual entero costaría 1–3 USD) y **la confidencialidad tampoco** (los documentos de DNIT son públicos). Los argumentos reales son: (1) **no reproducibles** — el modelo cambia del lado del servidor sin versión fijable, así que "misma fuente → mismo resultado" (métrica de éxito del usuario) se rompe; (2) dependencia de cuenta/clave/red para un `rebuild` que debería funcionar con `git clone + uv sync`; (3) no resuelven mejor el problema difícil (fusión verificable de filas partidas); (4) su salida necesitaría exactamente la misma batería de validaciones.
- Uso aceptable: consultar manualmente una página en disputa como opinión adicional, sin incorporar su salida a `raw/`.

---

## 5. ¿Pipeline híbrido o una sola herramienta?

**Híbrido, pero asimétrico.** No "pdfplumber para tablas + Docling para el resto" como socios iguales, sino:

| Rol | Herramienta | ¿Canónico (evidencia en `raw/`)? |
|---|---|---|
| Texto por página con coordenadas (prosa, observaciones, reglas en texto) | pdfplumber (pdfminer.six) | **Sí** |
| Verificación del texto por un motor independiente | pypdfium2 (PDFium) | No (solo checks) |
| Tablas de campos y validaciones → registros | pdfplumber `lines` + *stitcher* propio; **árbol de etiquetas** `Table/TR/TD` como segunda vía si el spike confirma que es fiable | **Sí** (registros con provenance) |
| Esquema de secciones | *Outline*/marcadores del PDF (Word los genera desde los títulos) + tamaño/negrita de fuente [I, PV] | Sí |
| Vista Markdown legible (humanos/LLM) | Generada desde los registros + texto canónico; Docling Markdown solo como vista alternativa | No (derivado) |
| Verificación cruzada de tablas | Docling TableFormer (opcional) | No (solo checks) |
| OCR de NT escaneadas | Docling con OCR local (Tesseract/EasyOCR con español) u OCRmyPDF + Tesseract | Sí, pero con estado `ocr_unreviewed` hasta revisión humana del 100 % |

Por qué no Docling para "texto/estructura general": porque la prosa del manual **también es evidencia normativa** (observaciones, reglas condicionales escritas en texto). Si la tomamos de Docling, sus errores de clasificación (bloques tomados como imagen, header/footer mal detectado, orden de lectura) se filtran a la capa de evidencia sin que nada lo detecte. Para un documento Word de una sola columna, el orden de lectura por coordenadas de pdfplumber es suficiente [I, PV].

Por qué no una sola herramienta ML "todo en uno": porque ninguna fusiona tablas multipágina de forma **auditable**, todas tienen versiones y pesos que cambian, y la salida en Markdown no conserva la información necesaria para verificar.

Por qué no *solo* pdfplumber sin segundo motor: porque un único extractor no puede autoverificarse. La redundancia barata (pypdfium2, árbol de etiquetas, conteos contra XSD) es la defensa contra R6.

---

## 6. ¿Registros estructurados o Markdown?

**Registros estructurados directamente. Markdown es una vista generada, nunca la evidencia.** Razones técnicas:

1. **Límites de celda**: Markdown no representa celdas multilínea, celdas combinadas ni `|` dentro del contenido sin escapado; reparsear una tabla Markdown es un segundo parser con sus propios errores.
2. **Provenance**: una fila Markdown no lleva página ni bbox; un registro sí (`prov: [{page, bbox}]`, con dos entradas si la fila se partió entre páginas).
3. **Filas partidas**: en Markdown la fusión queda implícita e invisible; en un registro queda explícita (`split_across_pages: true`) y testeable.
4. **Diffs**: JSONL ordenado (una fila por línea, claves en orden estable) da diffs de Git de una línea por campo cambiado cuando DNIT republica el manual.
5. **Separación evidencia/interpretación** (principio del propio usuario): el registro RAW guarda el texto **literal** de cada celda; la normalización ("0-1" → `min_occurs=0, max_occurs=1`) es otra etapa, determinista y testeada, que nunca sobrescribe el literal.

Ejemplo de registro RAW (**ilustrativo**: nombres de columna y valores sin verificar contra el manual):

```json
{"doc_id":"MT_v150","doc_sha256":"<sha256>","table_id":"campos_DE#D","row_kind":"field",
 "cells":{"ID":"D208","Campo":"iTipIDRec","Descripción":"<literal>","Nodo Padre":"<literal>",
          "Tipo Dato":"<literal>","Longitud":"<literal>","Ocurrencia":"<literal>","Observaciones":"<literal>"},
 "prov":[{"page":87,"bbox":[56.7,412.3,538.6,446.1]},{"page":88,"bbox":[56.7,72.0,538.6,95.4]}],
 "split_across_pages":true,
 "extractor":{"name":"pdfplumber","version":"0.11.10","pdfminer":"20260107","settings_sha256":"<hash>"},
 "row_sha256":"<hash del contenido literal>"}
```

`raw/` quedaría, por documento: `pages.jsonl` (texto por página + hash), `tables/*.jsonl` (registros), `furniture.jsonl` (headers/footers eliminados, para auditoría), `images.jsonl` (imágenes detectadas y su cobertura), `manifest.json` (versiones, settings, hashes de entrada y salida). Todo regenerable y versionado en Git.

---

## 7. Pipeline recomendado

```
sources/<doc>.pdf  (inmutable; SHA-256 + MD5 oficial DNIT verificado)
   │
   ├─ 1. SONDEO (pypdfium2/pdfplumber)
   │     páginas, chars por página, cobertura de imágenes, fuentes, ¿etiquetado?, outline,
   │     tamaño/rotación → clasifica cada página: digital | escaneada | mixta | con-imagen-relevante
   │
   ├─ 2. TEXTO CANÓNICO (pdfplumber) + TEXTO DE CONTROL (pypdfium2)
   │     por página: palabras con bbox/fuente/tamaño/tag → pages.jsonl + hash normalizado
   │
   ├─ 3. FURNITURE: headers/footers por (a) tag Artifact si existe, (b) bandas Y repetidas en ≥ N % de
   │     páginas, (c) banda configurada tras inspección → se separan, NUNCA se descartan (furniture.jsonl)
   │
   ├─ 4. TABLAS: find_tables(lines) dentro del área de cuerpo → fragmentos por página con bbox
   │     ├─ 4b. (si el spike lo valida) árbol de etiquetas Table/TR/TD → segmentación independiente
   │     └─ STITCHER: une fragmentos consecutivos si: misma firma de encabezado o encabezado ausente,
   │        mismas fronteras de columna (± tolerancia), sin texto de cuerpo entre ellos;
   │        elimina encabezado repetido; fusiona fila partida (primera fila de página con ID vacío);
   │        detecta filas de grupo (celda que abarca todo el ancho). Cada decisión queda registrada.
   │
   ├─ 5. BLOQUES XML/CÓDIGO: por fuente monoespaciada o líneas que empiezan con '<' y etiquetas
   │     balanceadas [PV: las fuentes vistas son Calibri/Arial/Times] → texto literal con espacios;
   │     lxml comprueba buena formación (si falla: se marca defecto de la fuente, no se "arregla")
   │
   ├─ 6. VALIDACIONES AUTOMÁTICAS (sección 8) → informe; cualquier fallo bloquea
   │
   └─ 7. VISTAS: Markdown legible generado; (opcional) Docling JSON/MD para comparar
          ↓
       normalización determinista (otra etapa) → curación asistida por LLM (otra etapa, con revisión)
```

Decisión de diseño: **Docling en un grupo de dependencias opcional** (`[dependency-groups] docling = [...]` o extra), para que el núcleo (`uv sync`) no arrastre torch. El build canónico y el CI no lo necesitan.

---

## 8. Cómo detectar errores silenciosos (R6) — batería concreta

Cada punto se implementa como test de pytest o como check del pipeline que falla la construcción.

| # | Check | Qué detecta | Cómo |
|---|---|---|---|
| 1 | **Conservación de caracteres por página** | Texto perdido o duplicado | `chars_no_blancos(página) == chars en cuerpo + chars en celdas + chars en furniture + chars ignorados con motivo`. Igualdad exacta; cualquier diferencia falla. Es el check más potente y casi nadie lo hace. |
| 2 | **Extracción dual de texto** | Problemas de glifos/ToUnicode, ligaduras, caracteres privados | Texto normalizado (NFC, espacios colapsados) de pdfminer vs PDFium por página; similitud < umbral → página a revisión. Además: prohibir U+FFFD, rangos de uso privado y ligaduras sin expandir. |
| 3 | **Cobertura de páginas e imágenes** | Contenido normativo dentro de imágenes | Toda página procesada; imagen que cubre > X % del área de cuerpo con poco texto → `needs_manual_transcription`. Las páginas 3 y 21 ya tienen imágenes [V]. |
| 4 | **Furniture auditado** | Eliminar texto real creyendo que es header/footer | El conjunto de cadenas eliminadas (normalizado, con número de página sustituido por `{n}`) debe coincidir con una lista blanca revisada; números de página del pie consecutivos 1..217 (o según formato real). |
| 5 | **Invariantes de stitching** | Fusión incorrecta de fragmentos | Número de columnas constante por tabla lógica; fronteras X dentro de tolerancia; firma de encabezado idéntica; ningún registro con ID vacío salvo filas de grupo; cada fusión de fila partida registrada con ambas proveniencias. |
| 6 | **Extracción dual de tablas** | Segmentación de celdas errónea | Geometría (`lines`) vs árbol de etiquetas (`TR/TD`) — y, opcionalmente, Docling TableFormer — deben coincidir celda a celda en texto normalizado; discrepancia → `needs_review`. Dos métodos independientes que coinciden son mucho más fiables que uno "con alta confianza". |
| 7 | **Formato de IDs y secuencias** | Filas perdidas, duplicadas o mal asignadas | Regex de ID de campo por grupo (p. ej. `^[A-Z]\d{3}$` [PV]); orden ascendente en el orden del documento; **duplicados = error**; huecos → comparados contra una lista de huecos conocidos revisada una vez (un hueco nuevo falla). |
| 8 | **Conteos por grupo (snapshot)** | Pérdidas al cambiar versión de dependencias | `{grupo: n_filas}` comprometido en Git; cualquier cambio exige revisión explícita. |
| 9 | **Dominios de valores** | Celdas desplazadas de columna | "Tipo Dato" ∈ conjunto cerrado observado y revisado; "Ocurrencia" y "Longitud" con regex (`^\d+-(\d+|n)$` o lo que el manual use [PV]); código SIFEN numérico; "Efecto/Severidad" ∈ conjunto cerrado. Una celda que viola su dominio casi siempre indica columna corrida. |
| 10 | **Validación cruzada contra XSD** | Errores de extracción *y* contradicciones reales Manual↔XSD | Todo `xml_name` del manual existe en el XSD vigente; padre del manual = padre del XSD; ocurrencia/longitud/enumeraciones vs facetas del XSD. Discrepancia → estado `conflict` (no se corrige automáticamente: puede ser error del manual). Inverso: todo elemento del XSD aparece en el manual o en una NT; los sobrantes se listan. |
| 11 | **XML de ejemplo** | Fragmentos truncados o corruptos | Buena formación con lxml; si es un DE completo, validación contra XSD; nombres de elementos usados en los ejemplos existen en los registros extraídos. |
| 12 | **Golden pages** | Regresiones del parser | 10–20 páginas elegidas por dificultad (tabla que cruza página, fila partida, fila de grupo, celdas combinadas, XML, página con imagen, inicio/fin de sección); salida esperada verificada a mano **una vez** y comprometida; igualdad exacta en cada ejecución. |
| 13 | **Reproducibilidad byte a byte** | No determinismo o deriva de dependencias | `manifest.json` con versiones (Python, pdfplumber, pdfminer.six, pypdfium2), hash de settings, SHA-256 de entrada y de cada salida; CI regenera `raw/` y exige `git diff --exit-code`. Actualizar una dependencia = cambio de evidencia = PR con diff revisado. |
| 14 | **Checksums por página y por fila** | Saber exactamente qué cambió cuando DNIT republica | Hash del texto normalizado por página y `row_sha256` por registro → diff semántico de "qué filas cambiaron" sin LLM. |
| 15 | **Revisión visual dirigida** | Lo que ningún check anticipó | Para cada página marcada: PNG con overlay de tablas/celdas (`debug_tablefinder`) en un informe; el humano revisa solo lo marcado, no 217 páginas. |

Sobre "confidence": coincido con el usuario en no usar un número de confianza. Los checks anteriores producen estados discretos (`verified` si pasan los checks dobles y el XSD; `conflict` si contradice al XSD; `needs_review` si falla un check de extracción), que son accionables.

---

## 9. Reproducibilidad y particularidades de Windows

- **Fijar todo**: `uv.lock` + `.python-version` (3.13.x). pdfplumber, pdfminer.six, pypdfium2 y docling-parse tienen soporte 3.13/3.14 [V]. Determinismo del núcleo: Python puro + double IEEE-754 → misma salida en Windows y en Linux del CI [I; verificar en el spike ejecutando en ambos].
- **torch (solo si se usa Docling)**: en Windows PyPI sirve ruedas CPU; en Linux sirve ruedas CUDA [V uv docs]. Si Docling corre en CI Linux, declarar el índice `https://download.pytorch.org/whl/cpu` con `explicit = true` en `pyproject.toml` para no descargar CUDA [V].
- **Modelos de Docling**: prebajarlos con `docling-tools models download` a un directorio del proyecto (no a `~/.cache`), usar `artifacts_path`/`DOCLING_ARTIFACTS_PATH` y ejecutar sin red [V]. Registrar en el manifiesto el SHA-256 de cada archivo de modelo; **[PV]** si Docling fija revisiones de Hugging Face o usa `main`.
- **Determinismo de Docling**: no documentado [PV]. Por eso sus salidas, si se usan, se **comprometen** como artefactos y no se regeneran en CI; se fija `OMP_NUM_THREADS` y `accelerator_options.num_threads` para la regeneración manual.
- **Ruta del repositorio**: no trabajar dentro de la carpeta sincronizada con OneDrive (el directorio actual del usuario está en OneDrive): bloqueos de archivos, marcadores de posición en la nube y rutas largas. Habilitar rutas largas de Win32 si hiciera falta [V docs de Python 3.13]. La caché de Hugging Face en Windows sin modo desarrollador no crea symlinks (solo avisa) [I].
- **Seguridad**: pdfminer.six ≥ 20251230 por las CVE de CMaps [S]; los PDF de DNIT son de confianza moderada, pero el pipeline debe procesar cualquier PDF nuevo en un proceso sin privilegios.

---

## 10. Notas Técnicas y OCR

- El sondeo clasifica cada página. Para NT digitales: el mismo pipeline (texto canónico + tablas). Las NT suelen ser cortas y heterogéneas [I]; si sus tablas de "campo modificado" no siguen el formato del manual, se extraen como texto canónico con provenance y la estructuración pasa a la etapa de curación (con revisión humana).
- Para NT escaneadas (si existen [PV]): OCR local con idioma español — Docling con Tesseract/EasyOCR, u OCRmyPDF + Tesseract para producir un PDF derivado con capa de texto (en `derived/`, nunca en `sources/`). Requisitos: (a) estado `ocr_unreviewed` hasta que una persona verifique el 100 % del contenido OCR (son pocas páginas: es barato y obligatorio); (b) guardar motor, versión, idioma y modelo en el manifiesto; (c) nunca mezclar silenciosamente texto OCR con texto nativo. Elegir motor cuando aparezca una NT escaneada real y comparar sobre ella; RapidOCR (motor por defecto en algunos perfiles de Docling) está entrenado sobre todo para chino/inglés [I] — verificar acentos y "ñ" antes de usarlo.

---

## 11. Spike de Fase 0 (antes de escribir el sistema)

Objetivo: decidir con datos, no con reseñas. Sin estimaciones de tiempo; criterios de salida explícitos.

1. Descargar Manual v150 y 2–3 NT por la ruta oficial; verificar MD5 contra el listado de DNIT; guardar SHA-256.
2. Sondeo: ¿todas las páginas tienen capa de texto? ¿qué páginas tienen imágenes relevantes? ¿hay outline? ¿el árbol de etiquetas contiene `Table/TR/TD` y `Artifact` para headers/footers?
3. Elegir 15 *golden pages* y transcribir a mano sus registros esperados (incluye al menos dos tablas que crucen página y una fila partida).
4. Ejecutar: (a) pdfplumber `lines` + stitcher; (b) árbol de etiquetas; (c) Docling 2.140.0 estándar, OCR desactivado, TableFormer ACCURATE.
5. Medir exactitud a nivel de celda contra las golden pages y discrepancias entre métodos; medir tiempo y determinismo (3 ejecuciones en Windows + 1 en Linux, comparar hashes).

Criterios de decisión:
- Si (a) alcanza **100 %** de celdas en las golden pages de tablas de campos y validaciones → adoptar (a) como canónico.
- Si (b) también alcanza 100 % → usar (a)+(b) como extracción dual obligatoria; Docling queda fuera del MVP.
- Si (a) falla y (b) acierta → (b) canónico, (a) como verificación.
- Si ambos fallan en un patrón concreto (p. ej. tablas sin bordes) → evaluar Camelot `network/hybrid` o Docling **solo para ese patrón**, siempre con verificación dual.
- Docling entra en el MVP **solo** si demuestra un beneficio medible que los métodos deterministas no dan (p. ej. OCR de una NT escaneada).

---

## 12. Acuerdos y desacuerdos con la propuesta del usuario

| Propuesta | Veredicto | Razón |
|---|---|---|
| "No aplicar OCR indiscriminadamente; el manual es digital" | **De acuerdo** | Confirmado: fuentes embebidas y PDF etiquetado [V]. OCR solo por página clasificada como escaneada. |
| "Parser estructural → Markdown RAW sin interpretación" | **En desacuerdo parcial** | Sin interpretación: sí. Markdown como RAW: no. RAW = texto por página con coordenadas + registros de tabla JSONL con provenance + furniture auditado. Markdown = vista. |
| Candidatos Marker / Docling / MinerU | **En desacuerdo con la terna** | Los tres son herramientas ML optimizadas para layouts complejos y escaneos; el problema real es determinista (tablas Word con bordes que cruzan páginas). La terna correcta para el núcleo es pdfplumber + pypdfium2 + árbol de etiquetas; Docling como complemento. Marker descartado por licencia de pesos; MinerU por opacidad/churn/licencia no estándar. |
| "No adoptar por moda" | **De acuerdo** | Por eso el spike con golden pages decide, no los benchmarks de terceros (que además suelen ser de los propios autores, como el olmOCR-bench de Datalab). |
| `sources/` inmutable | **De acuerdo** | Añadir verificación de MD5 oficial de DNIT y SHA-256 propio. |
| Un solo paso PDF → RAW | **Ampliar** | Separar: sondeo → extracción → stitching → validaciones → vistas; cada etapa con artefactos y manifiesto propios para poder localizar dónde nace un error. |

---

## 13. Riesgos y verificaciones pendientes

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Fila partida entre páginas asignada al campo equivocado o convertida en registro sin ID | Alta | Alto | Regla explícita de fusión + check 5 + árbol de etiquetas (un `TR` partido sigue siendo un solo elemento) [PV] + golden pages con filas partidas. |
| Contenido normativo en imágenes | Media | Alto | Check 3; transcripción manual con provenance `manual_transcription`. |
| Header/footer mal clasificado (se pierde texto real) | Media | Medio | Check 4 (lista blanca + conservación de caracteres). |
| Actualizar una dependencia cambia la salida sin que nadie lo note | Media | Alto | Check 13: `raw/` regenerado en CI con `git diff --exit-code`. |
| Licencia de pesos (si alguien introduce Marker/Surya o un preset VLM de Docling) | Baja si se sigue la recomendación | Alto | Lista de dependencias permitidas en CLAUDE.md/CI; prohibir `--pipeline vlm` y `[vlm]` en el build. |
| Interpretación errónea de `?t=` como fecha de publicación | Media | Medio | Metadata separada: `portal_file_timestamp` ≠ `published_at` ≠ `effective_from`. |

Verificaciones explícitas pendientes (no las pude confirmar desde aquí):
1. Nombres exactos de columnas y formato de las tablas de campos y validaciones del Manual v150.
2. Calidad del etiquetado del PDF (`Table/TR/TD`, `Artifact`) y si Word dejó filas partidas entre páginas.
3. Existencia de páginas apaisadas y de contenido normativo en imágenes más allá de las páginas 3 y 21.
4. Si alguna NT está escaneada.
5. Determinismo real de Docling en CPU y si fija revisiones de modelos.
6. Facturación/financiación de la empresa (solo relevante si alguien insiste en Marker).
7. Revisión legal de la licencia MinerU si se reconsiderara.

---

## Fuentes consultadas (octubre 2026)

- pdfplumber: https://pypi.org/project/pdfplumber/ · https://github.com/jsvine/pdfplumber · CHANGELOG https://raw.githubusercontent.com/jsvine/pdfplumber/stable/CHANGELOG.md
- pdfminer.six: https://pypi.org/project/pdfminer.six/ · CVE: https://www.wiz.io/vulnerability-database/cve/cve-2025-64512 · https://security-tracker.debian.org/tracker/CVE-2025-70559
- pypdfium2: https://pypi.org/project/pypdfium2/
- Docling: https://pypi.org/project/docling/ · https://github.com/docling-project/docling · CHANGELOG https://raw.githubusercontent.com/docling-project/docling/main/CHANGELOG.md · https://docling-project.github.io/docling/usage/advanced_options/ · https://docling-project.github.io/docling/reference/pipeline_options/ · https://docling-project.github.io/docling/reference/docling_document/ · https://docling-project.github.io/docling/concepts/docling_document/ · discusión #2744 https://github.com/docling-project/docling/discussions/2744
- docling-parse: https://pypi.org/project/docling-parse/ · docling-slim: https://pypi.org/project/docling-slim/
- Modelos Docling: https://huggingface.co/docling-project/docling-layout-heron · https://huggingface.co/docling-project/docling-models
- Reseña Docling (secundaria): https://thunderbit.com/blog/docling-review
- Marker: https://github.com/datalab-to/marker · https://github.com/datalab-to/marker/blob/master/LICENSE · https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE · https://github.com/datalab-to/marker/releases · https://pypi.org/project/marker-pdf/ · Surya: https://github.com/datalab-to/surya · pdftext: https://github.com/datalab-to/pdftext
- MinerU: https://github.com/opendatalab/MinerU · https://github.com/opendatalab/MinerU/blob/master/LICENSE.md · https://pypi.org/project/mineru/ · https://opendatalab.github.io/MinerU/reference/changelog/
- Comparativa de licencias (secundaria): https://particula.tech/blog/docling-vs-mineru-vs-marker-pdf-parser
- PyMuPDF: https://pypi.org/project/PyMuPDF/ · https://pypi.org/project/pymupdf4llm/ · https://pypi.org/project/pymupdf-layout/
- Camelot: https://pypi.org/project/camelot-py/ · Unstructured: https://pypi.org/project/unstructured/ · OpenDataLoader: https://pypi.org/project/opendataloader-pdf/
- LiteParse (secundaria): https://www.llamaindex.ai/blog/liteparse-local-document-parsing-for-ai-agents
- Cloud (secundarias): https://developers.llamaindex.ai/llamaparse/general/pricing/ · https://developers.llamaindex.ai/python/cloud/llamaparse/faq/ · https://www.hpcwire.com/aiwire/2026/06/25/mistral-unveils-ocr-4-for-enterprise-search-rag-and-document-processing/ · https://docs.litellm.ai/docs/providers/azure_document_intelligence
- uv + PyTorch: https://docs.astral.sh/uv/guides/integration/pytorch/
- DNIT: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica · Manual v150 (PDF oficial, solo inspección de estructura)
- Tablas multipágina (contexto general, secundarias): https://docs.tensorlake.ai/document-ingestion/parsing/table-merging · https://arxiv.org/pdf/2512.10888

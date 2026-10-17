# Evaluación del stack Python — SIFEN KB

Fecha: 2026-10-17. Alcance: sección 18 de la especificación (Python 3.13+, uv, Pydantic, pytest, lxml, Typer, Rich; posibles httpx, PyYAML, orjson, Hypothesis) más las preguntas derivadas (formato canonical, XSD, SQLite/FTS5, DSL de condiciones, calidad mínima).

Método y convenciones de evidencia:

- **[V]** verificado hoy en fuente primaria (PyPI, python.org, documentación oficial).
- **[L]** probado localmente en este Windows 11 con intérpretes ya instalados (python.org 3.13.14 y 3.14.6; uv-managed 3.11.15, 3.12.13 y 3.14.5; uv 0.11.20; PyYAML 6.0.3 ya presente). No se instaló ni descargó ningún paquete. Los scripts de prueba están en `scratchpad/sifen/probe/` (`fts_probe.py`, `yaml_probe.py`, `loader_dsl_probe.py`).
- **[S]** fuente secundaria (blog, foro, agregador): indicativa, no concluyente.
- **[I]** criterio propio o inferencia técnica.
- **[P]** pendiente de verificar antes de implementar.

---

## 0. Veredicto y stack mínimo recomendado

**Veredicto: el stack candidato es parcialmente correcto.** El núcleo (Python + uv + Pydantic + pytest) es acertado. Hay que cambiar cuatro cosas:

1. La versión de Python debería ser **3.14**, no "3.13+".
2. Sobran **Typer, Rich, httpx y orjson**. Para este alcance, la librería estándar cubre esas necesidades.
3. **lxml** no es la librería XSD adecuada para el núcleo. La adecuada es **xmlschema**.
4. **PyYAML** solo es aceptable con un *loader* restringido. Con `safe_load` corrompe en silencio los códigos SIFEN que empiezan con cero (lo demuestro en la sección 4).

| Capa | Recomendación | Tipo |
|---|---|---|
| Intérprete | CPython **3.14** gestionado por uv (`.python-version` = `3.14`) | — |
| Entorno y lock | **uv**: `uv.lock` versionado y `uv sync --locked` en CI | herramienta |
| Modelos y validación | **Pydantic 2.x** (`extra="forbid"`, `frozen=True`, tipos con patrón) | runtime |
| Canonical | **YAML restringido** leído con **PyYAML** y un `KBLoader` propio | runtime |
| XSD | **xmlschema 4.x** (introspección y validación con rutas, sin red) | runtime |
| Índice y búsqueda | **sqlite3 de la stdlib** con FTS5 (`unicode61 remove_diacritics 2` y `trigram`) | stdlib |
| CLI | **argparse** (3.14 trae color y `suggest_on_error`) | stdlib |
| Descarga | **urllib.request** + `hashlib` | stdlib |
| JSON | **json** de la stdlib (`sort_keys=True, ensure_ascii=False, indent=2`) | stdlib |
| DSL de condiciones | **`ast` de la stdlib** con lista blanca de nodos y evaluador propio | stdlib |
| Tests | **pytest** + **Hypothesis** (solo en tres módulos) | dev |
| Calidad | **ruff** (lint + format) y **pyright** (`pyright[nodejs]`) o **basedpyright** | dev |
| Secretos | **gitleaks** (binario) + bloqueo de `*.p12`/`*.pfx`/`*.key`/`*.pem` | externo |
| Ingesta PDF | **docling** + **pdfplumber** en un grupo opcional `ingest`, fuera del núcleo | grupo opcional |

El núcleo queda con **tres dependencias de runtime** (pydantic, pyyaml, xmlschema) y cuatro de desarrollo. torch y Docling no entran al entorno de CI ni al de consulta.

---

## 1. Versión de Python: 3.14, no 3.13 ni 3.12; 3.15 todavía no

Estado oficial al 2026-10-17, según python.org [V]:

| Serie | Estado | Última versión | Fin de soporte |
|---|---|---|---|
| 3.15 | bugfix | 3.15.0 (2026-10-09) | 2031-10 |
| 3.14 | bugfix | 3.14.8 (2026-09-30) | 2030-10 |
| 3.13 | **security-only** | 3.13.16 (2026-09-30) | 2029-10 |
| 3.12 | security-only | 3.12.15 (2026-09-30) | 2028-10 |

Compatibilidad del stack con Windows (x86-64):

| Paquete | 3.13 | 3.14 | 3.15 | Fuente |
|---|---|---|---|---|
| torch 2.14.1 (2026-09-30) | rueda `cp313-win_amd64` | rueda `cp314-win_amd64` (más `cp314t`) | no (los classifiers llegan a 3.14) | [V] PyPI |
| docling 2.140.0 (2026-10-16) | sí | sí (classifiers 3.10–3.14 y Windows) | no declarado | [V] PyPI |
| docling-parse 7.22.3 (2026-10-13) | `cp313-win_amd64` | `cp314-win_amd64` | **sin rueda** | [V] PyPI |
| pdfplumber 0.11.10 | sí | sí (probado 3.10–3.14) | — | [V] PyPI |
| lxml 6.1.3 (2026-09-02) | win_amd64, win32 y arm64 | ídem, más `cp314t` | — | [V] PyPI |
| PyYAML 6.0.3 | sí | sí | — | [V] PyPI; [L] funciona en 3.14.6 |
| Pydantic 2.14.1 (2026-10-11) | sí | sí | — | [V] changelog |

Conclusiones:

- **3.12 y 3.13 ya están en fase security-only.** En esa fase python.org publica solo código fuente, sin instaladores nuevos para Windows [I, política habitual del devguide]. Elegir 3.13 hoy es empezar un proyecto con un intérprete que ya no recibe correcciones de bugs. **3.12** no tiene ninguna ventaja: todo el stack publica ruedas para 3.14.
- **3.15** salió hace ocho días. docling-parse no tiene rueda `cp315` y torch no declara 3.15. Lo reevaluaría cuando la cadena de ingesta publique ruedas `cp315`. Ganancia relevante de 3.15 para este proyecto: el modo UTF-8 pasa a ser el predeterminado (PEP 686) [S].
- **Recomendación:** `requires-python = ">=3.14,<3.15"` y `.python-version` = `3.14`. Con un solo minor el lock queda más pequeño y el comportamiento es idéntico en desarrollo y en CI. Migrar a 3.15 será una decisión explícita, hecha en un PR.
- **[P]** Que cada paquete tenga rueda no garantiza que el árbol completo de Docling resuelva en Windows/cp314: falta comprobar OCR, opencv y dependencias de transformers. Lo pondría como condición de Fase 0: `uv sync --locked --group ingest` y convertir cinco páginas del MT v150 en la máquina real. Si falla, solo el grupo `ingest` bajaría a 3.13. El núcleo no.

Particularidades de Windows con impacto real:

1. **Codificación [L].** Al ejecutar las pruebas con la salida redirigida, "Validación" llegó como `Validaci�n`: con 3.14 en Windows, stdout por tubería y `open()` sin `encoding` usan cp1252. Claude Code captura la salida por tubería, así que esto le afecta directamente. Medidas: `encoding="utf-8"` explícito siempre (regla ruff `PLW1514`) y `sys.stdout.reconfigure(encoding="utf-8")` en `main()`, o bien `PYTHONUTF8=1`.
2. **Fin de línea y hashes.** Con `core.autocrlf=true`, Git convierte LF a CRLF al hacer checkout de XSD/XML. Eso cambia el sha256 de `sources/` y rompe la verificación de procedencia entre Windows y el CI en Linux. Se evita con un `.gitattributes` que contenga `sources/** -text` y `* text=auto eol=lf` para el resto [I].
3. **OneDrive.** El escritorio actual está dentro de OneDrive. Un `.venv` con torch ocupa varios GB y OneDrive lo sincronizaría y bloquearía archivos durante `uv sync`. El repositorio debería vivir fuera de OneDrive (por ejemplo `C:\dev\sifen-kb`) [I].
4. Activar `git config core.longpaths true`: la caché de modelos de Hugging Face que usa Docling genera rutas largas [I].

---

## 2. uv

Lo que realmente aporta reproducibilidad, según la documentación de Astral [V]:

- **`uv.lock` universal**: un único lock para todas las plataformas, con hashes. Se versiona en Git.
- **`--locked` frente a `--frozen`**: con `--locked`, *"If the lockfile is not up-to-date, uv will raise an error instead of updating the lockfile"*. `--frozen` usa el lock sin comprobar que coincida con `pyproject.toml`. **En CI siempre `uv sync --locked`**, nunca `--frozen`. `uv lock --check` es el chequeo equivalente sin instalar nada. Las versiones nuevas de un paquete no invalidan el lock; actualizar exige `uv lock --upgrade`.
- **Python gestionado**: uv instala las compilaciones de `python-build-standalone`. Lee `.python-version` en el directorio y sus padres, sin salir del proyecto. `python-preference` admite `only-managed`, `managed` (por defecto), `system` y `only-system`. La documentación advierte que estas compilaciones *"have some behavior quirks"* de portabilidad.
- **Evidencia local [L]**: en esta máquina, el 3.14.6 de python.org trae SQLite 3.50.4 y el 3.14.5 gestionado por uv trae SQLite **3.53.1**. Si cada desarrollador usa el intérprete que tenga instalado, el comportamiento de SQLite puede variar. Fijar el intérprete gestionado (`python-preference = "only-managed"`) homogeneiza el entorno local y el CI.
- **Grupos de dependencias (PEP 735)**: `dev` se instala por defecto e `ingest` solo bajo pedido (`uv sync --group ingest`). Así CI y consultas nunca instalan torch.
- **torch en Linux [V]**: según la guía de uv, PyPI publica ruedas *"CPU-only … for Windows and macOS, and GPU-accelerated wheels on Linux"*. Si algún día se instala `ingest` en Linux, hay que fijar el índice `https://download.pytorch.org/whl/cpu` con `explicit = true`. Si no, se descargan varios GB de bibliotecas CUDA. Para eso, torch debe estar declarado en el grupo [I].
- **Límites**: el lock no fija los modelos de Hugging Face que descarga Docling, ni el binario de gitleaks, ni el paquete npm que el *wrapper* `pyright` baja en tiempo de ejecución (sección 10). Esas versiones deben registrarse aparte, por ejemplo en la procedencia de cada corrida de ingesta.
- Versión de uv: la instalada es 0.11.20 y PyPI muestra 0.13.1 [V]. No hace falta fijarla para el MVP. En CI conviene usar `astral-sh/setup-uv` con una versión fija [I].

---

## 3. Pydantic v2 (2.14.1)

Funciones relevantes y cómo usarlas aquí:

- **Lax frente a strict (tabla de conversión oficial [V])**:
  - En **lax**, un campo `str` **no** acepta `int`, salvo con `coerce_numbers_to_str`. Por eso, si YAML convierte `0160` en `112`, Pydantic lo rechaza con un error visible. El problema aparece solo con tipos laxos como `Any` o `int | str`.
  - Un campo `int` acepta `"123"` en lax y lo rechaza en strict.
  - Un campo `date` acepta `str` en strict solo en modo JSON (*"Format: YYYY-MM-DD, or a unix timestamp"*), no en modo Python.
  - Un campo `bool` en lax acepta `'0'`, `'off'`, `'f'`, `'false'`, `'n'`, `'no'`, `'1'`, `'on'`, `'t'`, `'true'`, `'y'` y `'yes'`.
- **Uniones sin discriminador [V]**: el modo *smart* elige el miembro por exactitud y la documentación advierte que ese algoritmo puede cambiar entre versiones menores. En `left_to_right`, `int | str` convierte `'456'` en `456`. **Regla: nunca `int | str` para códigos o identificadores.** Siempre `str` con patrón.
- **Uniones discriminadas [V]**: `Field(discriminator="action")` o `Discriminator` con `Tag`. Son *"more performant and more predictable"* y los errores vienen solo de la rama elegida. Encajan con los cambios de una NT (`add | modify | replace | deprecate | remove`), con los nodos del IR de condiciones (`kind`) y con la procedencia (`extracted | interpreted`).
- **Exportación de JSON Schema**: `model_json_schema()` (draft 2020-12). Su valor no es validar por segunda vez en Python, que sería redundante. Sirve para dar a la extensión YAML de VS Code (`yaml.schemas` en `.vscode/settings.json`) autocompletado y errores inline mientras humanos o IA editan el canonical, y para consumidores en otros lenguajes. Se genera en el build y CI comprueba que esté actualizado [I].
- **Validación cruzada**:
  - Dentro de un objeto, `@model_validator(mode="after")`. Ejemplos: `effective_to > effective_from`; `action == "replace"` exige `replaces`.
  - Entre documentos (referencias existentes, versiones sin solaparse, sin overrides huérfanos), un **pase de integridad separado** (`integrity.py`) que recorre todo el catálogo y devuelve **todos** los hallazgos. Meter catálogos en `ValidationInfo.context` acopla la carga con la integridad y corta en el primer error [I].
- **Configuración recomendada** [I]:
  - `ConfigDict(extra="forbid", frozen=True, validate_default=True)`. `extra="forbid"` detecta claves inventadas o mal escritas por una IA.
  - **No** `str_strip_whitespace`: el texto literal del manual se conserva intacto.
  - Tipos anotados: `FieldId = Annotated[str, StringConstraints(pattern=r"^[A-K]\d{3}$")]`, `SifenCode` con patrón de cuatro dígitos (**[P]** confirmar el patrón con el inventario real de códigos) e `IsoDate` con `BeforeValidator` que exija `^\d{4}-\d{2}-\d{2}$` antes de parsear. Esto evita que una cadena numérica se interprete como *unix timestamp*.
- **Strict global: no.** Con el loader de la sección 4, YAML solo entrega `str`, `bool`, `None`, listas y mapas. El modo lax se limita entonces a convertir `"0"` en `int` o `"2024-04-01"` en `date`, que es justo lo deseado, y los `str` nunca se convierten. Para los JSON generados (no editados) sí puede usarse `model_validate_json(..., strict=True)`.

---

## 4. Formato canonical y loader YAML

### 4.1 El problema, medido [L]

Resultado de `yaml.safe_load` (PyYAML 6.0.3, YAML 1.1, con libyaml) sobre valores reales de SIFEN escritos **sin comillas**:

| Escrito | PyYAML `safe_load` | YAML 1.2 (ruamel, según documentación) | `KBLoader` propuesto |
|---|---|---|---|
| `0160` | **112** (int, octal) | 160 (int, pierde el cero) [S] | `"0160"` |
| `0260` | **176** | 260 | `"0260"` |
| `0300` | **192** | 300 | `"0300"` |
| `0180`, `0190` | `"0180"`, `"0190"` (str, porque 8 y 9 no son octales) | 180, 190 | `"0180"`, `"0190"` |
| `1321` | 1321 (int) | 1321 (int) | `"1321"` |
| `NO`, `no` | **False** | `"NO"` (en 1.2 solo `true`/`false` son booleanos) | `"NO"` |
| `on` | **True** | `"on"` | `"on"` |
| `2024-04-01` | `datetime.date` | no verificado | `"2024-04-01"`, que Pydantic convierte en `date` |
| `1.50` (versión) | **1.5** (float) | 1.5 | `"1.50"` |
| `1:30` | **90** (sexagesimal) | no verificado | `"1:30"` |
| `0x1A` | 26 | 26 | `"0x1A"` |
| `dup: 1` + `dup: 2` | **2, sin aviso** | error `DuplicateKeyError` por defecto [S] | **error** con número de línea |
| `&a` / `*a` | se aceptan | se aceptan | **error** |

Lo grave no es solo que haya conversión: **es inconsistente**. Los códigos `0160`, `0260` y `0300` se vuelven enteros distintos y `0180` o `0190` siguen siendo texto. YAML 1.2 (ruamel) **no lo resuelve**: deja de interpretar octal, pero igual convierte `0160` en `160`. Las claves duplicadas, aceptadas sin aviso, son un riesgo directo en un canonical que editan IAs.

### 4.2 Opciones

| Opción | A favor | En contra | Veredicto |
|---|---|---|---|
| **PyYAML `safe_load`** | Ubicuo y estable (6.0.3, 3.8–3.14) | Problemas de la tabla; duplicados sin aviso | **No** tal cual |
| **PyYAML + `KBLoader` propio** (unas 30 líneas) | Sin dependencia extra; todo escalar es `str` salvo `true`, `false` y `null`; Pydantic es la única autoridad de tipos; duplicados, anchors y aliases dan error; también sirve para el *frontmatter* de `cases/*.md` | No conserva comentarios al reescribir; no puede usar `CSafeLoader`, irrelevante con cientos de archivos | **Recomendada** |
| **ruamel.yaml 0.19.1** | YAML 1.2; *round-trip* que conserva comentarios y orden; `clib` ahora opcional (extra `oldlibyaml`) [V] | `0160` sigue siendo `160`; un solo mantenedor e historial de cambios de API; los comentarios solo importan si un programa reescribe archivos editados por humanos | Solo si en el futuro una herramienta reescribe YAML humano |
| **StrictYAML** | Todo es `str`, duplicados y *flow style* dan error | Última versión 1.7.3 del **2023-03-10** [V]; duplica el papel de Pydantic | **No** (estancado) |
| **JSON** | Cero ambigüedad, stdlib | Sin comentarios; el texto multilínea del manual queda en `"\n"` escapados y los diffs de PR son ilegibles | **Sí para artefactos generados**, no para el canonical |
| **JSONL** | Ideal para *append-only* | Pésimo para editar registros anidados a mano | Para bitácoras de corridas LLM, índices o salidas de extracción |
| **TOML** | Tipado explícito: `codigo = 0160` es **error de parseo** [L]; fechas nativas; comentarios; `tomllib` en la stdlib | `tomllib` solo lee; arrays de tablas anidadas (`[[versions]]` dentro de `[versions.provenance]`) confusos para humanos e IA; el *frontmatter* de los casos seguiría siendo YAML, con dos formatos en el repo | Alternativa seria, pero inferior aquí |

### 4.3 Recomendación

**Canonical en "YAML restringido", un archivo por entidad** (`rules/validations/D208c.yaml`), leído con `KBLoader`:

- Estilo bloque. Prohibidos anchors, aliases, tags `!!` y merge `<<`. El prototipo desactiva el *merge* por construcción: `<<` queda como clave literal y `extra="forbid"` lo rechaza.
- Todo escalar sin comillas es `str`, salvo `true`, `false` y `null`/`~`/vacío. Fechas, enteros y decimales los tipa **Pydantic**.
- **Comentarios YAML prohibidos para contenido.** Lo que importe va en un campo `notes:`, porque los comentarios son invisibles para el modelo y se pierden al reescribir. Un test simple rechaza líneas que empiecen con `#`.
- El texto literal del manual va siempre en escalares de bloque (`|`). En un escalar plano, `" #"` inicia un comentario y **trunca el texto en silencio**.
- Un test de integridad de alto valor: **todo `literal_text` debe aparecer, con espacios normalizados, en `raw/` en la página citada.** Detecta truncamientos, paráfrasis y alucinaciones de la IA.
- Opcional: `sifen fmt` con `safe_dump(sort_keys=False, allow_unicode=True)` y un *representer* que use `|` para cadenas multilínea. PyYAML ya entrecomilla al volcar los valores ambiguos (`'0160'`, `'NO'`, `'2024-04-01'`, `'1321'`) [L]. Así el archivo también es correcto para herramientas YAML 1.2 de terceros. CI puede exigir que cargar y volcar dé el mismo archivo.

Prototipo verificado [L]. Resultado: `0260`→`'0260'`, `NO`→`'NO'`, `yes`→`'yes'`, `true`→`True`; con clave duplicada, error *"clave duplicada 'a' (línea 2)"*; con anchor, error.

```python
NULL = "tag:yaml.org,2002:null"


class KBLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("alias no permitido")
        if getattr(self.peek_event(), "anchor", None):
            raise yaml.YAMLError("anchor no permitido")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        seen = set()
        for k, _ in node.value:
            key = self.construct_object(k, deep=deep)
            if key in seen:
                raise yaml.YAMLError(f"clave duplicada {key!r} (línea {k.start_mark.line + 1})")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


KBLoader.yaml_implicit_resolvers = {
    c: [(t, rx) for t, rx in rs if t == NULL] for c, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
KBLoader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))
```

Sinergia: la extensión YAML de VS Code trabaja por defecto en YAML 1.2 (configurable con `yaml.yamlVersion`) [P]. Con el JSON Schema de Pydantic, marcará `codigo: 0160` como *"Incorrect type. Expected string"*, lo que empuja al humano a entrecomillar aunque el loader ya lo tolere.

---

## 5. XSD: xmlschema frente a lxml

| Criterio | lxml 6.1.3 (libxml2) | xmlschema 4.3.2 (pure Python + elementpath) |
|---|---|---|
| XSD 1.0 | Sí, rápido (C) | Sí |
| XSD 1.1 | No | Sí (`XMLSchema11`). **No aporta**: SIFEN usa XSD 1.0 [I] |
| Introspección de componentes | Mínima: hay que recorrer el XSD como XML a mano | Completa: `schema.elements`, `schema.types`, `schema.maps`, `iter_components()`, `iter_globals()`, `find()`/`findall()` con XPath, `XsdElement.type`, `occurs`, `validators` de facetas [V]. Atributos `min_occurs`, `max_occurs`, `enumeration`, `patterns` y `min_length`/`max_length` [P, confirmar en el *spike*] |
| Errores de validación | `error_log` con línea y columna (y ruta [P]) | `iter_errors()` con razón, ruta e instancia; el *parse* reporta `Path: /xs:schema/...` [V] |
| Resolución local de imports | `XMLParser(no_network=True)` + `etree.Resolver` o catálogo XML (`XML_CATALOG_FILES`) | `allow="sandbox"` (*"only the file paths and URLs that are under the directory path identified by source"*), `allow="none"`, `locations`, `uri_mapper` (el `LOCATION_MAP` de `download_schemas`), `base_url` [V] |
| Seguridad | `resolve_entities=False`, `load_dtd=False` | `defuse="always"` (`SafeXMLParser`, sin entidades); límites `MAX_XML_DEPTH=1000`, `MAX_MODEL_DEPTH=15` [V] |
| Mantenimiento | Activo | Activo (4.3.0 2026-01, 4.3.2 2026-06; añadió soporte de desarrollo para 3.15) [V] |

**Recomendación: solo xmlschema en el núcleo.**

- La extracción programática que pide la especificación (sección 14: tipo, minOccurs, maxOccurs, restricciones, enumeraciones, patrones, longitudes) **solo es razonable con xmlschema**. Con lxml habría que reimplementar la semántica de XSD: herencia de tipos, `restriction`/`extension`, grupos, `ref`.
- Para SIFEN, la **ruta** del error importa más que la línea: los XML firmados suelen venir minificados en una sola línea, y la ruta (`/rDE/DE/gDatGralOpe/gDatRec/iTipIDRec`) se mapea directo al ID de campo (D208) [I].
- El rendimiento de un validador pure Python basta para analizar documentos individuales (`sifen analyze`, `sifen validate`) [I].

**Imports sin red** (por ejemplo xmldsig):

- Cargar con `XMLSchema(path, allow="sandbox", defuse="always")`. Si un import apunta a una URL remota, falla en lugar de descargar.
- Mapear esas URL a copias locales con `uri_mapper` o `locations`, **sin editar `sources/`**. La copia de xmldsig debe estar dentro del árbol de la sandbox.
- Añadir un test con la red bloqueada: un *fixture* que haga que `socket.socket` lance excepción al cargar todos los XSD.
- **[P]** No pude ver el paquete XSD oficial. Hay que comprobar si el `xs:import` de xmldsig en `siRecepDE_v150.xsd`/`DE_v150.xsd` usa una ruta relativa (se resuelve sola) o una URL absoluta (requiere `uri_mapper`). También si el xmldsig de W3C trae `DOCTYPE` con DTD remota.

**¿Hacen falta ambas?** No en el MVP. lxml entraría solo si se necesita:

- (a) verificar la firma XMLDSig: `signxml`/`xmlsec` dependen de lxml;
- (b) validar lotes grandes por rendimiento;
- (c) *differential testing*: validar los XML de ejemplo con libxml2 **y** con xmlschema, y alertar si discrepan. Es útil pero opcional, como dependencia `dev`.

Docling probablemente ya trae lxml transitivamente en el grupo `ingest` [P]. No hay que depender de eso en el núcleo.

---

## 6. SQLite + FTS5: la stdlib basta

Probado [L] con `PRAGMA compile_options`, creando tablas FTS5 y consultando:

| Intérprete | SQLite | Opciones | FTS5 `unicode61 remove_diacritics 2` | FTS5 `trigram` |
|---|---|---|---|---|
| python.org 3.14.6 | 3.50.4 | FTS3, FTS4, **FTS5**, RTREE, MATH | OK: `validacion` encuentra "Validación" | OK: `TipID` encuentra `iTipIDRec` |
| python.org 3.13.14 | 3.50.4 | ídem | OK | OK |
| uv-managed 3.14.5 | 3.53.1 | ídem + FTS3_PARENTHESIS | OK | OK |
| uv-managed 3.12.13 | 3.53.1 | ídem | OK | OK |
| uv-managed 3.11.15 | 3.53.1 | ídem | OK | OK |

También funciona `json_extract` (JSON1 viene integrado).

- En CPython para Windows, FTS5 se compila de serie: `PCbuild/sqlite3.vcxproj` define `SQLITE_ENABLE_FTS4;SQLITE_ENABLE_FTS5;SQLITE_ENABLE_RTREE` [V].
- **Pero no es un contrato documentado**: la documentación de `sqlite3` no menciona FTS5 [V]. Hubo además una regresión en `python-build-standalone` que uv 0.7.21 corrigió (*"Restore the SQLite fts4, fts5, rtree, and geopoly extensions on macOS and Linux"*) [S]. Por eso hace falta un test `test_sqlite_has_fts5` que corra también en el CI de Linux, y una verificación al arrancar `sifen build`.
- Diseño sugerido [I]:
  - Búsqueda **exacta** de IDs (D208, 1321, D208c, iTipIDRec) con tablas normales e índices, **no** con FTS.
  - FTS5 `unicode61 remove_diacritics 2` para texto en español.
  - Una tabla `trigram` para búsquedas parciales de nombres XML.
  - `sqlite3.connect(..., autocommit=False)`, el valor recomendado desde 3.12 [V].
  - `python -m sqlite3` para consultas ad hoc [V].
- El `.db` es un **artefacto generado, no versionado**. No se compara por hash, porque el contenido binario de FTS puede variar entre versiones de SQLite: se prueba con consultas.
- No hacen falta SQLAlchemy, sqlite-utils, DuckDB ni APSW.

---

## 7. CLI: argparse; Typer no aporta lo suficiente; Rich sobra

Datos de 2026 [V]:

- **Typer 0.27.3** depende **sin condiciones** de `rich`, `shellingham` y `annotated-doc`, y de `colorama` en Windows. Desde **0.26.0 (2026-05-26)** *vendoriza* Click: *"Typer no longer depends on Click … Click-specific functionality is no longer supported"*. En 2026 encadenó varios cambios incompatibles:
  - 0.22: `typer-slim` pasa a ser un envoltorio que siempre exige Rich;
  - 0.24.1: se abandonan `typer-slim` y `typer-cli`;
  - 0.26.0: Click vendorizado;
  - 0.27.0: cambia la impresión de metavars.
- **argparse en 3.14** incorpora `color=True` por defecto y `suggest_on_error` (sugerencias ante subcomandos o *choices* mal escritos).

Recomendación [I]:

- **argparse** para el MVP. Son unos ocho subcomandos (`get-field`, `get-validation`, `rule --at`, `analyze`, `validate`, `diff`, `source`, `build`) y la CLI es un adaptador fino sobre una librería de consultas (`sifen_kb.query`). El MCP futuro reutilizará esa librería, no la CLI.
- **Click 8** sería el punto medio si se quieren decoradores. **Typer** suma cuatro dependencias y cambios incompatibles frecuentes para ahorrar poco código.
- **Rich: no.** Para Claude y los scripts, lo valioso es `--format json`, no tablas con caracteres de caja. Con Typer, Rich llegaría igual como dependencia obligatoria: otra razón para no usar Typer. Si se usa Rich directamente, debe declararse explícitamente aunque llegue de forma transitiva.

---

## 8. Hypothesis (6.170.1, requiere Python ≥ 3.11): dónde aporta y dónde no

**Aporta** [I]:

1. **Resolución temporal (el mayor valor).** Generar historiales aleatorios de versiones (fechas de publicación y vigencia, acciones `modify`/`replace`/`deprecate`/`remove`, orden de entrada mezclado) y comprobar estas propiedades:
   - como máximo una versión vigente por fecha;
   - el resultado solo cambia en las fronteras `effective_from`/`effective_to`;
   - **el orden de los archivos no altera el resultado**;
   - aplicar dos veces el mismo parche es idempotente;
   - después de un `remove`, `resolve` devuelve "inexistente" y no la versión anterior;
   - **prueba diferencial** entre el resolvedor real y uno ingenuo O(n) escrito aparte.
2. **CDC y DV módulo 11.** El oráculo principal son los ejemplos oficiales del manual (tests *golden*). Hypothesis suma propiedades estructurales (44 dígitos, DV en 0–9, `verify(build(x))`) y una comparación diferencial contra una segunda implementación. Ejemplo de lo que encontraría: si el algoritmo es el de la SET con pesos cíclicos 2…11 y `DV = 0` cuando el resto es menor o igual a 1 (**[P]** confirmar contra el MT v150), una sustitución de un dígito en una posición de peso 11 **no cambia el DV** (11·d ≡ 0 mod 11). La propiedad ingenua "todo error de un dígito cambia el DV" es falsa, e Hypothesis lo muestra en segundos. Eso documenta el límite real del algoritmo.
3. **DSL de condiciones.**
   - *Round-trip* `parse(unparse(ir)) == ir` con IR generados mediante `st.recursive`.
   - El evaluador es total: frente a cualquier XML con cualquier patrón de presencia o ausencia devuelve TRUE, FALSE o UNKNOWN y nunca lanza excepción.
   - Se cumplen las leyes de De Morgan bajo lógica de Kleene.
   - Una entrada arbitraria produce IR válido o `ValueError`/`SyntaxError`, nunca otra excepción.

**No aporta** (usar *golden*, ejemplos o integridad determinista): fidelidad PDF→raw, integridad del catálogo real (son datos concretos, no un espacio de entradas), validación XSD de XML reales, curación LLM, formato de salida de la CLI y build de SQLite.

Operación: añadir `.hypothesis/` a `.gitignore` y usar en CI un perfil con `derandomize=True` y un `max_examples` acotado, para que la ejecución sea reproducible y no haya fallos intermitentes.

---

## 9. Representación de condiciones de reglas

| Opción | Legible en PR | Seguridad | Dependencias | Grupos repetidos (ítems) | Veredicto |
|---|---|---|---|---|---|
| **Subconjunto de expresiones Python con `ast` + lista blanca** | Alta (`D011 != 13 and D208 == 5 and (F023 >= 7000000 or F014 >= 7000000)`) | Alta: nunca `eval`/`compile`, evaluador propio, lista blanca de nodos, límite de longitud | 0 (stdlib) | Funciones de la lista blanca: `any_item()`, `all_items()`, `sum()`, `count()`, `exists()` | **Recomendada (MVP)** |
| **Lark 1.3.1** (gramática propia) | Máxima: sintaxis libre (`AND`, `=`) y errores con posición | Alta (evaluador propio) | 1, pure Python, sin dependencias [V] | Lo que defina la gramática | Plan B si la sintaxis Python se queda corta; facilita *fuzzing* con `hypothesis.extra.lark.from_lark` |
| **CEL** | Media-alta (`&&`, `\|\|`; macros `all`/`exists`/`filter` sobre listas) | Alta por diseño: sin efectos y con terminación garantizada | `cel-expr-python` 0.1.3: binding C++, ruedas Windows cp311–cp314, repositorio de solo lectura, anunciado en 2026-03 [V]. `cel-python` 0.5.0: arrastra google-re2, jmespath, lark, pendulum y pyyaml [V] | Muy buena (macros nativas) | No ahora. Aportaría si un ERP en otro lenguaje (Java, .NET, Go) tuviera que evaluar **las mismas** reglas |
| **JSONLogic** | Baja (`{"and":[{"!=":[{"var":"D011"},13]},…]}`) | Alta | Librería Python de mantenimiento dudoso [P] | Limitada | No como canonical |
| **AST JSON escrito a mano** | Muy baja; propenso a errores de humanos e IA | Alta | 0 | La que se diseñe | No como canonical; sí como **artefacto generado** |

**Recomendación:** la opción C de la especificación, **pero con una sola fuente editable**.

- **Canonical:** la condición como **texto** en el YAML.
- **Derivado:** un **IR tipado** (modelos Pydantic con discriminador `kind`), producido al cargar y exportado como JSON en `dist/`, nunca editado.
- **Evidencia junto a la interpretación:** cada regla conserva `literal_text` (texto literal del manual o la NT, que es la evidencia) separado de `condition` (que es interpretación). Un campo `formalization: full | partial | none` evita la falsa precisión: no toda regla es formalizable y `condition` puede ser `null`.

Prototipo verificado [L] (lista blanca: `Expression`, `BoolOp`/`And`/`Or`, `UnaryOp`/`Not`, `Compare` con `== != < <= > >= in not in`, `Name`, `Constant` int o str, `Tuple`, `Call` a funciones permitidas). Resultados:

- extrae los campos `['D011', 'D208', 'F014', 'F023']` del ejemplo de la especificación;
- rechaza `__import__('os').system('x')`, `D208.real` (Attribute), comprensiones de lista, `lambda`, `D208 == True` y la sintaxis en mayúsculas `AND`, que da `SyntaxError`. Conviene un mensaje que sugiera usar `and`.

Detalles de diseño:

- Validar en la carga que todo `Name` exista en el catálogo de campos (test de integridad) y que las constantes sean compatibles con el tipo del campo (N, A, F).
- Convertir los numéricos a `Decimal` vía `repr()` para evitar errores de coma flotante.
- Usar solo `ast.Constant`: `ast.Num` y `ast.Str` están obsoletos [I].
- Decidir si se permiten las comparaciones encadenadas (`1 < D208 < 5`); lo más simple es rechazarlas.

**Semántica contra XML con grupos repetidos** [I]. Esto es lo difícil; elegir Lark o CEL no lo resuelve.

1. **Catálogo**: ID de campo → XPath y cardinalidad del grupo, tomada del XSD. Ejemplo: los E7xx dentro de `gCamItem`, con `maxOccurs` mayor que 1.
2. **Ámbito implícito**: si una condición referencia campos de **un solo** grupo repetido, se evalúa por ocurrencia y la violación informa el índice (`gCamItem[3]`). Los campos de grupos no repetidos se ligan al documento.
3. **Ámbito explícito obligatorio**: si referencia dos grupos repetidos distintos o necesita agregar (por ejemplo, un total igual a la suma de los ítems), debe usar `any_item(...)`, `all_items(...)`, `sum(E7xx)` o `count(...)`. La carga rechaza las referencias ambiguas.
4. **Lógica trivalente**: comparar contra un campo ausente da UNKNOWN y `exists()` lo hace explícito. `sifen analyze` informa UNKNOWN como "no evaluable con este XML", no como violación. Esto mitiga el riesgo R9 (exceso de confianza).
5. **Tipos**: los valores del XML se convierten según el tipo del catálogo, no según su apariencia.

---

## 10. Calidad mínima

| Herramienta | Recomendación | Nota |
|---|---|---|
| **ruff** 0.17.1 [V] | `ruff check` + `ruff format` | Reemplaza black, isort y flake8. Reglas útiles aquí: `E,F,W,I,B,UP,S,DTZ,RUF` y `PLW1514` (open sin encoding; **[P]** verificar si sigue en *preview*). `S506` detecta `yaml.load` inseguro; `DTZ` exige fechas y horas con zona en `downloaded_at` |
| **pyright** 1.1.414 [V] | `standard` en todo el proyecto y `strict` en `model/`, `temporal/` y `dsl/` | Pydantic v2 funciona con pyright vía `dataclass_transform`, sin plugin. Es el mismo motor que Pylance en VS Code. El *wrapper* de PyPI, si no hay `node` en el PATH, descarga Node con nodeenv e *"installs the pyright npm package with npm"* [V], fuera del lock. Usar `pyright[nodejs]` o **basedpyright** 1.40.2 (trae `nodejs-wheel-binaries`; *"no need to install any additional tools"*) [V]. Para reproducibilidad con proxy corporativo, prefiero basedpyright [I] |
| mypy 2.4.0 [V] | Alternativa válida | Necesita el plugin de Pydantic para su mejor resultado; más lento |
| ty 0.0.89 [V] | **No todavía** | *"ty is currently in beta"*, sin API estable. Reevaluar en 1.0 |
| pyrefly | No todavía | Llegó a 1.0 el 2026-05-12 según una fuente secundaria [S]; muy nuevo |
| **pre-commit** 4.7.0 [V] o **prek** 0.5.5 [V] | Opcional; mismo `.pre-commit-config.yaml` | prek es una reimplementación en Rust, *"drop-in alternative to pre-commit"* y Production/Stable. **Importante:** excluir `sources/` y `raw/` de los hooks que reescriben (`end-of-file-fixer`, `trailing-whitespace`, `mixed-line-ending`): si no, alteran fuentes inmutables y salidas byte a byte |
| **gitleaks** 8.30.1 (2026-03) [V] | Hook de pre-commit + paso en CI | El proyecto se declara *"feature complete"* y solo publicará parches de seguridad [V]; aceptable para un escáner de regex. **`gitleaks-action` exige una licencia (gratuita) para cuentas de organización** [V]: en CI es más simple ejecutar el binario. Añadir reglas propias para CSC/IdCSC y bloquear las extensiones `*.p12`, `*.pfx`, `*.key` y `*.pem` (gitleaks no detecta un P12 binario) |
| detect-secrets 1.5.0 [V] | **No** | Última versión del 2024-05-06; su enfoque de *baseline* sirve para repos heredados, que no es el caso |

CI mínimo (un *job*, matriz `ubuntu` + `windows` solo para tests, porque el entorno principal es Windows) [I]:

```
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run pyright            # o basedpyright
uv run pytest
uv run sifen build --check   # regenera artefactos derivados y falla si hay diff
gitleaks git --redact        # binario
```

---

## 11. Descarga y serialización: urllib, no httpx; orjson no

**Estado de httpx en 2026** [V/S]:

- La última versión estable es **0.28.1, del 2024-12-06**, y sus classifiers solo llegan a 3.12 [V].
- Según HN y otras fuentes [S], el mantenedor cerró issues y discusiones el 2026-02-27 y la 1.0 se desarrolla en un repositorio privado con cambios incompatibles.
- Pydantic patrocina un *fork*, **httpx2** (2.9.1, 2026-07), con la misma API pública, al que migraron los SDK de OpenAI y Anthropic [S].

Es un ecosistema en transición. Para descargar unas decenas de PDF/XSD de DNIT y calcular su sha256 no se justifica.

**urllib.request alcanza** [I]:

- GET con `timeout`, redirecciones automáticas, cabecera `User-Agent` y lectura por bloques hacia `hashlib.sha256` y un archivo temporal, con `os.replace` atómico al final.
- En Windows, `ssl.create_default_context()` carga los certificados del almacén del sistema y `getproxies()` lee la configuración de proxy del registro. Así funciona detrás de un proxy corporativo con inspección TLS. httpx usa certifi por defecto y ahí fallaría sin configuración adicional.
- Para detectar NT nuevas en la página de DNIT basta `html.parser` de la stdlib; no hace falta BeautifulSoup. Al principio la detección puede ser incluso manual.

**orjson: no.** La KB tiene a lo sumo miles de registros. `json` de la stdlib con `sort_keys=True, ensure_ascii=False, indent=2` y salto de línea final produce salida determinista y diffs legibles. orjson (3.13.0) añade un binario Rust sin beneficio medible a esta escala [I].

Tampoco añadir: Jinja2 (para generar Markdown bastan f-strings), python-frontmatter (el `KBLoader` lee el *frontmatter*), SQLAlchemy, pandas ni el SDK de MCP (llegará con la fase MCP y traerá su propio cliente HTTP).

---

## 12. Boceto de `pyproject.toml`

```toml
[project]
name = "sifen-kb"
version = "0.1.0"
requires-python = ">=3.14,<3.15"
dependencies = [
  "pydantic>=2.12,<3",   # 2.12+ soporta 3.14
  "pyyaml>=6.0.3",       # ruedas 3.14
  "xmlschema>=4.3,<5",
]

[project.scripts]
sifen = "sifen_kb.cli:main"

[dependency-groups]
dev = ["pytest", "hypothesis", "ruff", "basedpyright"]   # o "pyright[nodejs]"
ingest = ["docling", "pdfplumber"]                        # opt-in: uv sync --group ingest

[tool.uv]
default-groups = ["dev"]
python-preference = "only-managed"   # misma compilación (y SQLite) en todas las máquinas
# environments = ["sys_platform == 'win32'", "sys_platform == 'linux'"]  # lock más acotado

[build-system]
requires = ["uv_build"]   # fijar rango acorde a la versión de uv
build-backend = "uv_build"

[tool.ruff]
target-version = "py314"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "S", "DTZ", "RUF"]

[tool.pyright]
pythonVersion = "3.14"
typeCheckingMode = "standard"
strict = ["src/sifen_kb/model", "src/sifen_kb/temporal", "src/sifen_kb/dsl"]
```

Más `.python-version` (`3.14`), `.gitattributes` (`sources/** -text`, `* text=auto eol=lf`) y `.gitignore` (`.venv/`, `.hypothesis/`, `dist/`, `*.db`, `*.p12`, `*.pfx`, `*.key`, `*.pem`).

---

## 13. Acuerdos y desacuerdos con el candidato

| Candidato | Veredicto | Cambio y razón |
|---|---|---|
| Python 3.13+ | Parcial | **3.14 fijo**. 3.13 ya está en security-only; 3.15 aún no tiene ruedas de docling-parse ni de torch |
| uv | De acuerdo | `uv sync --locked` en CI, `.python-version`, Python gestionado, grupos `dev` e `ingest` |
| Pydantic | De acuerdo | Con `extra="forbid"`, `frozen=True` e identificadores `str` con patrón; integridad entre documentos en un pase aparte |
| pytest | De acuerdo | — |
| lxml | Desacuerdo (núcleo) | **xmlschema**: introspección de facetas y cardinalidades, errores con ruta, sandbox sin red. lxml solo para firma, lotes o pruebas diferenciales |
| Typer | Desacuerdo | **argparse**: unos ocho subcomandos; Typer encadenó varios cambios incompatibles en 2026 (Click vendorizado en 0.26.0) y suma cuatro dependencias |
| Rich | Desacuerdo | Innecesario; lo útil es `--format json` |
| httpx | Desacuerdo | **urllib**: necesidad trivial, mejor integración TLS y proxy en Windows; httpx está en transición (0.28.1 de 2024 frente al *fork* httpx2) |
| PyYAML | De acuerdo con condición | Solo con `KBLoader`; `safe_load` convierte `0160`→112 y `NO`→False, y acepta duplicados sin aviso |
| orjson | Desacuerdo | `json` de la stdlib basta y da salida determinista |
| Hypothesis | De acuerdo, acotado | Temporalidad, CDC y DSL; en nada más |
| (falta) xmlschema | Añadir | Ver sección 5 |
| (falta) ruff, pyright o basedpyright, gitleaks | Añadir (dev/CI) | Ver sección 10 |
| Docling y pdfplumber | Mover | Grupo opcional `ingest`; nunca en el núcleo ni en CI |

---

## 14. Pendientes de verificar y riesgos del stack

1. **[P] Árbol completo de Docling en Windows/cp314**: comprobar `uv sync --group ingest` y una conversión real. Las ruedas individuales están verificadas; la resolución completa no.
2. **[P] Imports de xmldsig en los XSD oficiales de SIFEN**: si son relativos o absolutos, y si hay `DOCTYPE` con DTD remota. Define si hace falta `uri_mapper`.
3. **[P] Nombres exactos de atributos de xmlschema** para facetas (`enumeration`, `patterns`, `min_length`/`max_length`, `min_occurs`/`max_occurs`): verificar en un *spike* de una hora sobre los XSD reales.
4. **[P] Algoritmo de DV del CDC**: confirmar pesos y reglas contra el MT v150 antes de escribir las propiedades.
5. **[P] Patrón de los códigos SIFEN** (¿siempre cuatro dígitos?): inventariar antes de fijar `SifenCode`.
6. **Riesgo: FTS5 no es contractual.** Mitigación: test en Linux y Windows y verificación al arrancar el build.
7. **Riesgo: codificación en Windows con Python 3.14.** Mitigación: `encoding="utf-8"` siempre, reconfigurar stdout y la regla ruff.
8. **Riesgo: el lock no cubre los modelos de Docling, el npm de pyright ni gitleaks.** Mitigación: basedpyright, fijar la versión de gitleaks en CI y registrar los modelos o versiones de Docling en la procedencia de cada corrida de ingesta.
9. **Riesgo: hooks que "arreglan" archivos y alteran `sources/` o `raw/`.** Mitigación: exclusiones explícitas y un test de sha256 de `sources/` contra la metadata.

---

## Fuentes

Primarias:
- python.org, estado de versiones: https://www.python.org/downloads/
- torch en PyPI: https://pypi.org/project/torch/
- docling en PyPI: https://pypi.org/project/docling/ — instalación: https://docling-project.github.io/docling/getting_started/installation/
- docling-parse: https://pypi.org/project/docling-parse/ — pdfplumber: https://pypi.org/project/pdfplumber/ — lxml: https://pypi.org/project/lxml/
- uv, sync y lock: https://docs.astral.sh/uv/concepts/projects/sync/ — versiones de Python: https://docs.astral.sh/uv/concepts/python-versions/ — PyTorch: https://docs.astral.sh/uv/guides/integration/pytorch/
- CPython `PCbuild/sqlite3.vcxproj`: https://raw.githubusercontent.com/python/cpython/main/PCbuild/sqlite3.vcxproj — documentación de sqlite3: https://docs.python.org/3/library/sqlite3.html
- Pydantic, tabla de conversión: https://pydantic.dev/docs/validation/latest/concepts/conversion_table/ — uniones: https://pydantic.dev/docs/validation/latest/concepts/unions/
- ruamel.yaml (JSON de PyPI): https://pypi.org/pypi/ruamel.yaml/json — StrictYAML: https://pypi.org/project/strictyaml/ — PyYAML: https://pypi.org/pypi/PyYAML/json
- xmlschema, uso: https://xmlschema.readthedocs.io/en/latest/usage.html — características y seguridad: https://xmlschema.readthedocs.io/en/latest/features.html — componentes: https://xmlschema.readthedocs.io/en/latest/components.html — changelog: https://github.com/sissaschool/xmlschema/blob/master/CHANGELOG.rst
- Typer, notas de versión: https://typer.tiangolo.com/release-notes/ — dependencias: https://pypi.org/pypi/typer/json
- argparse 3.14: https://docs.python.org/3.14/library/argparse.html
- httpx en PyPI: https://pypi.org/pypi/httpx/json — guía de migración a httpx2: https://pydantic.dev/docs/httpx2/get-started/migration/
- ty: https://pypi.org/project/ty/ — pyright-python: https://github.com/RobertCraigie/pyright-python — basedpyright: https://docs.basedpyright.com/latest/installation/command-line-and-language-server/ y https://pypi.org/pypi/basedpyright/json
- gitleaks: https://github.com/gitleaks/gitleaks — gitleaks-action: https://github.com/gitleaks/gitleaks-action — versiones: https://github.com/gitleaks/gitleaks/releases
- detect-secrets: https://pypi.org/pypi/detect-secrets/json — prek: https://pypi.org/pypi/prek/json — pre-commit: https://pypi.org/pypi/pre-commit/json
- CEL-expr-python (Google, 2026-03): https://opensource.googleblog.com/2026/03/announcing-cel-expr-python-the-common-expression-language-in-python-now-open-source.html — https://pypi.org/pypi/cel-expr-python/json — cel-python: https://pypi.org/pypi/cel-python/json
- Lark: https://pypi.org/project/lark/ — Hypothesis: https://pypi.org/pypi/hypothesis/json — ruff: https://pypi.org/pypi/ruff/json — mypy: https://pypi.org/pypi/mypy/json — orjson: https://pypi.org/pypi/orjson/json — uv: https://pypi.org/pypi/uv/json

Secundarias (indicativas):
- uv 0.7.21, restauración de FTS5 en python-build-standalone: https://newreleases.io/project/pypi/uv/release/0.7.21 — PR de python-build-standalone: https://github.com/astral-sh/python-build-standalone/pull/800/files
- Diferencias entre ruamel y PyYAML (YAML 1.2, octales): https://dokk.org/documentation/ruamel.yaml/0.17.40/pyyaml — caso StarlingX (`0755`→`755`): https://gitea13.opendev.org:3081/starlingx/root/commit/0636bbc87e8adf4e8faa61804f0ff222c8ef57b8.patch
- httpx2 y el estado de httpx: https://hn.nuxt.dev/item/49477212
- ty frente a pyrefly: https://pydevtools.com/handbook/explanation/ty-vs-pyrefly.md
- Python 3.15 y UTF-8 por defecto: https://blog.python.org/2025/10/python-3150-alpha-1/

Pruebas locales: `scratchpad/sifen/probe/fts_probe.py`, `yaml_probe.py` y `loader_dsl_probe.py`, ejecutados con `-I` sobre los intérpretes ya instalados.

# Investigación factual SIFEN (Paraguay) — base para la arquitectura de la Knowledge Base

Fecha de la investigación: 2026-10-17.
Alcance: documentación técnica oficial de DNIT (ex SET) para SIFEN / e-Kuatia, contrastada con fuentes secundarias.

## Leyenda de evidencia

- **VERIFICADO**: comprobado hoy contra un documento o recurso oficial (URL de dnit.gov.py, ekuatia.set.gov.py, sifen*.set.gov.py). Cuando la verificación se hizo leyendo el PDF oficial, se indica la página.
- **PROBABLE**: respaldado por fuente secundaria (librería, artículo, firma consultora) o por inferencia fuerte a partir de evidencia oficial. Se indica la URL.
- **NO VERIFICADO**: no se pudo comprobar. No debe usarse como hecho.

## Método (para trazabilidad)

- Los PDF oficiales (Manual Técnico v150, NT 001–027, guías, checksum) se obtuvieron con WebFetch desde las URL oficiales listadas abajo. La herramienta guardó automáticamente el binario en su caché; el texto se extrajo localmente con `pdftotext` (poppler) hacia stdout, sin escribir copias adicionales. No se ejecutó nada descargado.
- El MD5 del Manual publicado se calculó en streaming (`curl | md5sum`), sin guardar el archivo.
- Los XSD se leyeron como texto desde `https://ekuatia.set.gov.py/sifen/xsd/` y se pidieron solo cabeceras HTTP (`curl -I`).
- **No** se abrieron los RAR oficiales (`Estructura_DE xsd.rar`, `Estructura xml_DE.rar`): su contenido queda NO VERIFICADO.
- Números de página "impresa" = número del pie de página del Manual ("septiembre de 2019 NNN"); "página PDF" = índice físico del PDF. Difieren en 1 (ver §2.6).

---

## 0. Resumen ejecutivo (lo que más impacta en el diseño)

1. **El ejemplo del usuario es real y exacto** (VERIFICADO): D208 = `iTipIDRec`; la validación **D208c** tiene código **1321**, severidad **R**, y su umbral cambió: Manual v150 = 60.000.000 → **NT 21** (fecha 29/12/2023, vigente test/prod 01/01/2024) = 35.000.000 → **NT 24** (fecha 17/12/2024, vigente test/prod 01/01/2025) = **7.000.000**. Condición literal: `D011≠13`, `D208≠5`, `F023 >= 7.000.000 o F014 >= 7.000.000`.
2. **Hay 27 NT sobre el MT v150** (NT 001 a NT 027; la última fechada 09/03/2026). No existe MT v160 ni manual consolidado oficial (VERIFICADO en el portal hoy; la FAQ oficial dice que la versión vigente es la 150).
3. **Los PDF oficiales no son inmutables**: NT 21 fue re-subido el 30/12/2024 con marca de agua "VER NOTA TÉCNICA N° 24 DESDE EL 01/01/2025"; NT 18 fue re-subido en junio de 2024 (archivo `...-+Junio.pdf`); el MD5 del Manual v150 publicado hoy **no coincide** con el MD5 que DNIT lista para el v150 (VERIFICADO).
4. **Los XSD v150 se modifican in situ** sin cambiar nombre de archivo, namespace ni `dVerFor` (VERIFICADO: `DE_v150.xsd` contiene elementos introducidos por NT de 2023–2025, p. ej. `dRucFus`, `gOblAfe`, `dCodConDncp`). No hay historial de versiones de XSD publicado.
5. **Los IDs de validación no son globalmente únicos y los códigos tampoco** (VERIFICADO en el MT v150: `GDE008` aparece con códigos 4006 y 4069; el código 2419 lo usan `H002c` y `H005a`; los códigos 4313–4323 estaban duplicados y NT 18 los corrigió).
6. **La severidad de una validación puede cambiar por NT** (VERIFICADO: `GED003`/4253 era `AO` en el MT v150 y pasa a `R` en NT 19).
7. **La numeración de NT no es cronológica** (VERIFICADO: NT 9 fechada 09/09/2021, NT 8 fechada 21/09/2021, NT 7 fechada 01/02/2022 y "re-enumerada para su publicación").
8. **Las NT marcan cambios con resaltado de color sin leyenda**, y el uso no coincide con la leyenda del Manual (rojo = eliminación en el MT; en NT 21/24 el texto en rojo sigue vigente). Una conversión PDF→Markdown pierde el color y, aunque lo conservara, su semántica no es fiable.
9. **El Manual contiene erratas internas** verificables (CDC de ejemplo con 46 caracteres, `<?xml version="150"…>`, rangos de códigos solapados, URL de WSDL de test con `.wsd`, etc.). La KB debe esperar conflictos documentales como algo normal, no excepcional.

---

## 1. Dónde publica DNIT la documentación técnica

### 1.1 URLs oficiales (VERIFICADO, consultadas hoy)

| Recurso | URL |
|---|---|
| Documentación técnica (Manual, NT, XSD, guías) | https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica |
| Índice de documentación | https://www.dnit.gov.py/web/e-kuatia/documentacion |
| Tablas y Codificaciones (complementos del MT) | https://www.dnit.gov.py/web/e-kuatia/tablas-y-codificaciones |
| Librerías de código abierto enlazadas por DNIT | https://www.dnit.gov.py/web/e-kuatia/librerias |
| Normativas (leyes, decretos, resoluciones) | https://www.dnit.gov.py/web/e-kuatia/normativas (subpáginas `/leyes`, `/decretos`, `/resoluciones`) |
| Preguntas frecuentes | https://www.dnit.gov.py/web/e-kuatia/preguntas-frecuentes |
| XSD publicados (índice Apache, 47 archivos) | https://ekuatia.set.gov.py/sifen/xsd/ |
| Prevalidador SIFEN (herramienta oficial) | https://ekuatia.set.gov.py/prevalidador/ (validación: `/prevalidador/validacion`) |
| Semáforo SIFEN (estado del servicio) | https://semaforo-sifen.dnit.gov.py/semaforo/ |
| Web services producción / test | `https://sifen.set.gov.py/de/ws/...` / `https://sifen-test.set.gov.py/de/ws/...` (MT §7.10; Guía de Mejores Prácticas 2024) |

- El portal antiguo `https://ekuatia.set.gov.py/portal/ekuatia/documentacion/documentaciontecnica` (citado en el MT para la Tabla 2.1) **redirige** (302) a `https://www.set.gov.py/web/e-kuatia`. Los enlaces internos del Manual están, por tanto, desactualizados (VERIFICADO).
- FAQ oficial: "A la fecha la versión vigente del Manual Técnico es la Versión 150" y las NT "son publicadas en el Portal Web y a través de los mecanismos formales de comunicación de la DNIT" (VERIFICADO: https://www.dnit.gov.py/web/e-kuatia/preguntas-frecuentes/-/categories/2704806). Implicación: el portal no es necesariamente el único canal (PROBABLE).

### 1.2 Archivos en "Documentación técnica" (VERIFICADO)

Las rutas son relativas a `https://www.dnit.gov.py`. El parámetro `?t=` es el sello de subida del gestor de contenidos (Liferay, milisegundos epoch), **no** la fecha de publicación oficial del documento.

| Título en portal | Ruta / archivo | `t=` (UTC) |
|---|---|---|
| Recomendaciones – servicio asíncrono | `/documents/20123/420592/Guía de Mejores Prácticas para la Gestión del Envío de DE.pdf/38fe5830-…?t=1729866823709` | 2024-10-25 |
| Manual Técnico Versión 150 | `/documents/20123/420592/Manual Técnico Versión 150.pdf/e706f7c7-6d93-21d4-b45b-5d22d07b2d22?t=1687362295907` | 2023-06-21 |
| Listado Checksum MD5 de las versiones del Manual Técnico | `/documents/20123/420592/Listado Checksum MD5 de las versiones del Manual Tecnico.pdf/303ee6ab-…?t=1687362295755` | 2023-06-21 |
| Estructura xml_DE (RAR) | `/documents/371863/0/Estructura xml_DE.rar/ecbb793c-…?t=1687277733733` | 2023-06-20 |
| Estructura_DE xsd (RAR) | `/documents/20123/420592/Estructura_DE xsd.rar/e956aaac-…?t=1687362293703` | 2023-06-21 |
| Guía de Pruebas para e-kuatia | `/documents/20123/424160/Guia de Pruebas para e-kuatia.pdf/715a15bf-…?t=1770659877488` | 2026-02-09 |

En "Tablas y Codificaciones" (VERIFICADO):
- `CÓDIGO DE REFERENCIA GEOGRAFICA_NOVIEMBRE_2025__.xlsx` (`t=` 2026-01-27).
- `Checksum MD5 - Codigo de Referencia Geografica.pdf` (`t=` 2023-06-21) → el checksum publicado es **anterior** a la versión vigente del XLSX, por lo que no puede validarlo (PROBABLE: el PDF no se leyó; su fecha de subida sí).
- Conclusión: **las codificaciones cambian también fuera de las NT** (el XLSX geográfico de noviembre de 2025 no corresponde a ninguna NT).

### 1.3 Formato de las Notas Técnicas (VERIFICADO salvo indicación)

- **Formato**: PDF de 1 a 5 páginas, generado desde Microsoft Word (metadatos del PDF), cabecera "NOTA TÉCNICA N° NN" (las antiguas "N° 0NN" o "Número 1").
- **Nombre de archivo**: `NT_E_KUATIA_0NN_MT_V150.pdf`. Hay variantes con sufijos que delatan re-subidas o correcciones: `NT_E_KUATIA_006_MT_V150+.pdf`, `NT_E_KUATIA_014_MT_V150X.pdf`, `NT_E_KUATIA_018_MT_V150-+Junio.pdf`, `NT_E_KUATIA_021_MT_V150+30.12.24.pdf`. El título del portal para NT 001–014 es "NT_E_KUATIA_0NN MT_V150" (con espacio).
- **Carpeta**: `/documents/20123/420595/` para todas las NT.
- **Estructura interna** (NT 13 en adelante): "Fecha", tabla con "Fecha puesta a disposición para el Ambiente de Test" y "…para el Ambiente de Producción", "Referencia" (casi siempre "Correcciones y ajustes sobre el Manual Técnico versión 150"), secciones numeradas (Formato de campos XML / Validaciones / Codificaciones / Web Services / URL…), a veces "Observación" con base legal, y al final "Histórico del Documento" (autor, fecha de elaboración, revisor, fecha de revisión, principales alteraciones).
- NT 001–011 no tienen tabla de fechas test/producción: indican "Fecha" y "Cambios desde la fecha X al Y". NT 012 solo tiene "Fecha".
- **Versiones corregidas de una misma NT**: no hay versión explícita en el nombre (no hay "v2"). Las correcciones se manifiestan como:
  - re-subida con otro nombre de archivo en el mismo enlace de portal (NT 21: `+30.12.24`, con marca de agua que remite a NT 24);
  - re-subida con sufijo (`-+Junio` en NT 18: el PDF actual tiene fecha de creación 06/06/2024 aunque la NT dice "Fecha: 17/11/2023" y su histórico solo registra 31/10/2023);
  - filas adicionales en "Histórico del Documento" (p. ej. NT 19: 21/12/2022, 17/04/2023, 17/11/2023; NT 20: "Ajuste del código del mensaje de validación");
  - cambio de fechas de entrada en vigencia en el mismo documento: la librería de Roshka documenta para NT 13 "21/04/2023 desarrollo y 21/05/2023 producción", mientras el PDF oficial actual de NT 13 dice producción **17/06/2023** (PROBABLE prórroga in situ; fuente secundaria: https://github.com/roshkadev/rshk-jsifenlib).
- **Erratas en las propias NT**: NT 25 dice "Fecha: 23/04/2024" pero su histórico y sus fechas de vigencia son de 2025 (VERIFICADO).

### 1.4 Inventario de NT sobre el MT v150 (VERIFICADO, leído el PDF de cada una)

| NT | Fecha del documento | Test | Producción | `t=` subida | Contenido principal (IDs / códigos) |
|---|---|---|---|---|---|
| 001 | 14/10/2019 ("Voluntariedad controlada"; cambios 10/09/2019–14/10/2019) | — | — | 2023-06-21 | Fórmulas EA004, F009, F011, F012, F014, F033–F035; validaciones C004b (1103), EA004 (1862), F011 (2364), F014 (2365); nuevas EA004a (1860), F033 (2383), F034 (2384)… |
| 002 | 16/07/2020 | — | — | 2023-06-21 | Campos D208/D210; **elimina** D208d (1322) y D210a (1323) |
| 003 | 18/11/2020 | — | — | 2023-06-21 | Campos D219/D223; **elimina** validaciones D219 (1324) y D223 (1327) |
| 004 | 29/12/2020 | — | — | 2023-06-21 | **Elimina** D101a (1251) |
| 005 | 09/02/2021 | — | — | 2023-06-21 | Longitudes D204, E965 |
| 006 | 25/03/2021 | — | — | 2023-06-21 | **Agrega** D011a (1216) |
| 007 | 01/02/2022 ("re-enumerar la nota técnica para su publicación") | — | — | 2023-06-21 | B006 `dInfoFisc` (factura de exportación) |
| 008 | 21/09/2021 | — | — | 2023-06-21 | EA797; fórmula F023 `dTotalGs` |
| 009 | 09/09/2021 | — | — | 2023-06-21 | E701, E708 (longitud 1-2000) |
| 010 | 04/02/2022 (cambios 01/02/2021–04/02/2022) | — | — | 2023-06-21 | Elimina A005 `dSisFact`; D012, E505, E751–E761, E980, H009/H010, GEI009, esquemas siRecepDE/siConsDE, E507, C008; validaciones D202 (1300), D220, D208b, **D208e (1331)**, D142 (1265), H004g (2439), H004h (2441), H005b (2440); URL QR; nota sobre error 2501 (CSC); Tabla 6; namespace de eventos; Tabla B |
| 011 | 20/10/2022 (cambios 23/09/2022–20/10/2022) | — | — | 2023-06-21 | **Nuevo WS** consulta masiva de RUC (`rEnviConsArchivoRUCRequest`, `WS_ConsultaArchivoRuc.xsd`, `siConsultaArchivoRuc.xsd`), códigos 0520–0523 |
| 012 | 21/02/2023 | — | — | 2023-06-21 | Nueva D022 (1213), base: Dictamen DEINT N° 344 |
| 013 | 20/03/2023 | 21/04/2023 | 17/06/2023 | 2023-06-21 | E735; nuevo E737 `dBasExe`; F002/F004/F005; validación E737 (1921) |
| 014 | 20/03/2023 | 31/05/2023 | 08/08/2023 | 2024-01-25 (`V150X`) | **Nuevo evento de Nominación de FE** (GENFE001–GENFE027); validaciones 4451–4478 |
| 015 | 14/08/2023 | 21/08/2023 | 21/09/2023 | 2023-08-21 | H004i (2442) |
| 016 | 14/08/2023 | 25/08/2023 | 22/09/2023 | 2023-08-25 | Firma digital (Ley 6822 de servicios de confianza): XS02–XS21, elimina XS14; AC01 (0120), AD01 (0140), AD02 (0141), I002 (2450); causas TLS |
| 017 | 14/08/2023 | 24/08/2023 | 25/08/2023 | 2023-08-25 | Solo mensajes de D222 (1326) y D224 (1329) |
| 018 | 17/11/2023 | 01/12/2023 | 08/01/2024 | 2024-06-06 (`-+Junio`) | Nuevo grupo D1.1 `gOblAfe` (D030–D032, RG90); D031 (1220), D032 (1221); nueva Tabla 12; **corrige códigos** GET022–GET030 a 4325–4335; GET002 (4336) |
| 019 | 17/11/2023 | 15/12/2023 | 31/01/2024 | 2023-11-17 | Eventos del receptor: `dFecEmi` (GEN003/GED003); validaciones GEN/GCO/GDI/GED (4101–4265), **GED003 4253 pasa a R**; AD04 (0143); elimina tabla de relaciones entre eventos; agrega texto normativo sobre plazos |
| 020 | 17/11/2023 | 15/12/2023 | 31/01/2024 | 2023-11-17 | Nuevo E827 `dCodConDncp`; D202b (1332) (OEE ⇒ B2G) |
| 021 | 29/12/2023 | 01/01/2024 | 01/01/2024 | 2024-12-30 (re-subida con marca de agua) | D208c (1321): umbral 35.000.000; base: Art. 6 Decreto 872/2023 |
| 022 | 09/02/2024 | 09/02/2024 | 09/02/2024 | 2024-03-06 | Nueva D031a (1222) |
| 023 | 27/08/2024 | 30/08/2024 | 27/09/2024 | 2024-08-29 | Campos D208 (agrega "6=Tarjeta Diplomática"), D210; E711 `1-10p(0-8)`; E791 `0-9`; E797; nuevo H018 `dRucFus`; validaciones D208e (1331, ahora C002=5,6,7), D210 (1314), D208f (1333), D210b (1334), D208g (1335), H001 (2400), H004g (2439), H018 (2443), H018a (2444); Tabla 5 (unidades 111–140) |
| 024 | 17/12/2024 | 01/01/2025 | 01/01/2025 | 2024-12-19 | D208c (1321): umbral 7.000.000; base: inciso ii), numeral 2, Art. 6 Decreto 872/2023 |
| 025 | "23/04/2024" [sic; 2025] | 28/04/2025 | 28/04/2025 | 2025-04-28 | **Excluye** GEC002c (4004) en cancelación |
| 026 | 06/06/2025 | 09/06/2025 | 16/06/2025 | 2025-06-09 | Observaciones de E704/E705/E020 (opcionales si D202=3); **excluye** E020/E020a (1400/1401) y E704/E705 (1800/1801) |
| 027 | 09/03/2026 | 09/03/2026 | 09/03/2026 | 2026-03-09 | Evento de Nominación: GENFE010 `iTipIDRec` y GENFE011 `dDTipIDRec` (Tarjeta Diplomática pasa a código 6) |

Observaciones derivadas (VERIFICADO salvo marca):
- El margen entre publicación y vigencia es a veces de días (NT 21: documento 29/12/2023, vigencia 01/01/2024; NT 24: subida 19/12/2024, vigencia 01/01/2025) o nulo (NT 25, 27).
- NT 22 declara vigencia 09/02/2024 pero el PDF del portal fue creado y subido el 06/03/2024: la fecha de subida puede ser **posterior** a la vigencia (PROBABLE que se comunicara antes por otro canal; NO VERIFICADO).
- Test y producción pueden diferir semanas (NT 23: 30/08 vs 27/09/2024; NT 18: 01/12/2023 vs 08/01/2024) o coincidir.

### 1.5 ¿Manual consolidado o versión posterior al v150?

- **No hay** MT v160 ni un "v150 consolidado" oficial publicado (VERIFICADO en el portal y la FAQ; la búsqueda web tampoco encontró rastro de una v160).
- El PDF publicado "Manual Técnico Versión 150.pdf" (217 páginas, portada "Versión 150 – 10/09/2019") **no incorpora las NT**: sigue mostrando D208d, D210a, D219, D223 (eliminadas por NT 2 y 3), `dSisFact` (eliminado por NT 10), los mensajes viejos de D222/D224 (NT 17) y E711 `1-10p(0-4)` (NT 23), y no contiene D208e, D202b, D031, E737, GENFE, `dRucFus` (VERIFICADO por búsqueda en el texto).
- **Pero el binario publicado tampoco es el que DNIT certifica**: el "Listado Checksum MD5" lista `MT_E_Kuatia_V141_21_09_2018.pdf → 3831B120BBDAD67AB032DA80DDED689B` y `MT_E_Kuatia_V150_10_09_2019.pdf → 25EB165A8506EFA3A255B863ABCCAE95`; el MD5 del PDF publicado hoy es `f48d7c820a14723ec14e66bfcb02e0df` (5.204.470 bytes; SHA-256 `976cd88c05c31041ee86db1667e1b426e2d9ddf675d941973d5918cbdc5427c6`) (VERIFICADO). Qué cambió entre ambos binarios: NO VERIFICADO.
- Existe además una copia de terceros `MT_E_Kuatia_V150_24_06_2019.pdf` (https://tdn.totvs.com.br/download/attachments/502840885/MT_E_Kuatia_V150_24_06_2019.pdf?api=v2), es decir, hubo al menos otra compilación "v150" anterior (PROBABLE; fuente no oficial, no leída).
- Conclusión: "Manual v150" no designa un único binario. La KB debe fijar el hash exacto del binario usado como base.

---

## 2. Estructura del Manual Técnico v150 (VERIFICADO, PDF oficial)

### 2.1 Capítulos (índice del documento; páginas impresas)

Índices de gráficas, tablas y schemas; Control de versiones (v120 03/05/2018, v130 29/06/2018, v140 23/08/2018, v141 21/09/2018, v150 10/09/2019); 1 Introducción (15); 2 Objetivos; 3 Alcance; 4 SIFEN (estructura, fundamento legal, validez jurídica) (18); 5 Documentos Tributarios Electrónicos (22); 6 Modelo operativo (plazos, rechazo, entrega al receptor) (23); 7 Características tecnológicas del formato (XML, namespace, convenciones de tablas, firma, certificados, URLs de WS, NTP) (28); 8 Aspectos tecnológicos de los WS (síncrono/asíncrono, versión de schemas) (42); 9 Descripción de los WS (siRecepDE, siRecepLoteDE, siResultLoteDE, siConsDE, siRecepEvento, siConsRUC, siConsDEST futuro) (45); 10 Formato de los DE (CDC, DV, código de seguridad, **tabla de campos** págs. 58–111, timbrado y numeración) (56); 11 Gestión de eventos (eventos del emisor, receptor, SET; formatos; reglas de validación de eventos 11.6.x) (112); 12 Validaciones (estructura de códigos, códigos de WS, validaciones de formato 12.4 págs. 159–192) (145); 13 Gráfica KuDE y QR (193); 14 Contingencia (futuro); 15 Codificaciones (210); 16 Glosario (214).

### 2.2 Tablas de especificación de campos

- Columnas reales de las tablas de campos (DE y eventos): **Grupo | ID | Campo | Descripción | Nodo Padre | Tipo Dato | Longitud | Ocurrencia | Observaciones**. En las NT, igual (a veces "Ocu" o "Long.").
- La Tabla A del MT (§7.2.3) define además una columna **"Versión"** ("versión en que el campo fue introducido o modificado por última vez"), pero **no aparece** en las tablas de campos del MT v150 (VERIFICADO). La validación de formato de WS (§12.2.3) sí tiene columna "V" con valor 150.
- **Grupo**: etiqueta jerárquica del capítulo 10.4/Tabla I, p. ej. `AA`, `A`, `B`, `C`, `D`, `D1`, `D1.1` (NT 18), `D2`, `D2.1`, `D3`, `E1`, `E1.1`, `E7.1`, `E8`, `E8.1.1`, `E9.2`, `E10.4`, `F`, `G1`, `H`, `I`, `J`; en eventos `GDE`, `GER`. Cada grupo tiene un rango de IDs (p. ej. "D3. Campos que identifican al receptor (D200-D299)").
- **ID**: letra(s) + número (`D208`, `E711`, `EA004`, `GENFE010`, `XS17`, `ASch03`, `ESch01`…). Esquemas de WS usan `ASch`, `DSch`, `ESch`, `FSch`; firma `XS`.
- **Campo** (nombre XML) con prefijo semántico (Tabla A): `c` = código de tabla del capítulo de codificaciones; `i` = código cuya tabla está en "Observaciones"; `d` = dato común; `g` = grupo; `r` = raíz.
- **Nodo Padre**: ID del grupo contenedor (p. ej. D208 → `D200`).
- **Tipo de dato** (Tabla B): `XML`, `G` (grupo), `CG` (choice group), `CE` (choice element, con sufijo, p. ej. `CEA`), `A` (alfanumérico), `N` (numérico), `F` (fecha `AAAA-MM-DDThh:mm:ss` o `AAAA-MM-DD`), `B` (Base64). En el Schema XML 1 la columna "Descripción" usa además `G`, `A` (algoritmo), `RC`, `E`.

### 2.3 Notación de longitudes (Tabla C, VERIFICADO) y variantes observadas

| Notación | Significado oficial |
|---|---|
| `x` (p. ej. `2`) | tamaño exacto; relleno con ceros a la izquierda |
| `x-y` (p. ej. `0-10`) | mínimo x, máximo y |
| `xpn` (p. ej. `22p4`) | tamaño exacto x con exactamente n decimales |
| `xp(n-m)` (p. ej. `22p(0-7)`) | tamaño exacto x con entre n y m decimales |
| `(x-y)p(n-m)` (p. ej. `1-11p(0-6)`) | mín. x, máx. y, decimales entre n y m |
| valores separados por coma (p. ej. `1, 3, 5, 8`) | uno de esos tamaños exactos |

Variantes reales que un parser debe tolerar (VERIFICADO): `1-15p(0-8)` sin paréntesis externos; `1-11p2` (NT 23, E797: rango + decimales exactos, combinación que la Tabla C no enumera); cortes de línea dentro del valor (`1-15p(0-` / `8)`); `-` para raíces/grupos; celdas desalineadas en la extracción.

### 2.4 Notación de ocurrencia (VERIFICADO)

Formato `m-n` (mínimo-máximo dentro del grupo): `1-1`, `0-1`, `0-9`, `0-11`, `0-999`, `2-2`, `0-n`; también `1` (XS17) y `-` (raíz). La obligatoriedad real casi nunca está en la ocurrencia: está en "Observaciones" como texto condicional ("Obligatorio si D201 = 2 y D202 ≠ 4", "No informar si D201 = 1"). Ejemplo: D208 tiene ocurrencia `0-1` y la condición en Observaciones.

### 2.5 Valores enumerados (VERIFICADO)

- Campos `i…`: lista "código= descripción" en Observaciones (D208: `1= Cédula paraguaya … 5= Innominado, 6=Tarjeta Diplomática de exoneración fiscal, 9= Otro`).
- Campo descriptivo emparejado `d…` con las descripciones textuales exactas entre comillas (D209 `dDTipIDRec`: `1= "Cédula paraguaya"…`), con validación de coincidencia (D209a/1313).
- Campos `c…`: tablas del capítulo 15 (Tabla 1 Tipo de régimen; 2.1 Departamentos/Distritos/Ciudades → archivo XLSX externo; 3 Actividades económicas → servicio web externo `servicios.set.gov.py/eset-publico/consultarActividadEconomicaIService.do`; 4 Países → ISO 3166-1 en XSD; 5 Unidades de medida; 6 Códigos de afectación; 11 Regímenes aduaneros → enlace; 12 Tipo de obligaciones (agregada por NT 18)).
- Las NT amplían/corrigen tablas (NT 10 Tabla 6; NT 18 Tabla 12; NT 23 Tabla 5).

### 2.6 Referencias de página

Las NT citan la página **impresa** del Manual (pie "septiembre de 2019 NNN"). Ejemplo: NT 21/24 dicen "(Página 166)" para D208c; en el PDF D208c está en el índice físico 167 con pie 166 (VERIFICADO). La provenance debe guardar ambas.

### 2.7 Riesgo de extracción PDF (VERIFICADO con `pdftotext`)

- En modo "layout", la tabla del grupo D3 sale con los nombres XML desplazados de fila (p. ej. `iTipIDRec` aparece varias filas arriba de D208). El modo "raw" las recompone mejor.
- En NT 14, 18 y 26, celdas de "Código" de filas contiguas se fusionan (p. ej. "1400 / 1401" en una sola línea, "4325 / 4326"); en NT 20 el ID `E827` se parte en `E82` + `7`.
- El color de resaltado (portador de semántica, §5) se pierde.

---

## 3. Cómo se documentan las validaciones

### 3.1 Tablas de validación (VERIFICADO)

- MT §12 ("Guía de reglas de validación"): columnas **N° VAL | ID | Mensaje de Validación | Código | Observación | E** (más "V – Versión del XML" en la guía, presente solo en algunas tablas, p. ej. §12.2.3).
- En las NT: **ID | Mensaje de la Validación | Código | Observación | E** (a veces con "N° Val").
- "N° VAL" es un correlativo dentro de la sección y **no es estable** (en el MT el N° 60 aparece dos veces: D208a y D209).
- "Observación" contiene la regla en prosa, a menudo con la condición formal entre paréntesis (p. ej. `(D011≠13)`, `(F023 >= 7.000.000 o F014 >= 7.000.000)`).

### 3.2 IDs de validación (VERIFICADO)

- El ID de validación es **el ID del campo + sufijo de letra**: `D208`, `D208a`, `D208b`, `D208c`… La primera validación de un campo lleva el ID "desnudo": **la validación `D208` (código 1310, "Es obligatorio informar el tipo de documento de identidad del receptor") colisiona nominalmente con el campo `D208`**.
- Son razonablemente estables a lo largo de las NT (D208c se mantiene en MT, NT 21, NT 24), pero:
  - **No son únicos globalmente**: `GDE008` existe en 11.6.1 Cancelación (4006) y en 11.6.2 Inutilización (4069); `GDE008a` (4007/4070); `GEN007a` aparece en Notificación (4106) y en Desconocimiento (4256) aunque allí el campo es `GED005` (error de copia).
  - Las NT introducen IDs nuevos para reglas casi idénticas a otras existentes sin declarar reemplazo: NT 23 agrega **D208f (1333)** con la misma observación que **D208b (1319)** del MT, **D210b (1334)** análoga a D210a (1323, eliminada por NT 2), **D208g (1335)** análoga a D208 (1310). Si D208b sigue vigente o fue sustituida por D208f: NO VERIFICADO.
  - En NT 19 aparece la fila combinada "GEN003 / GEN012" con dos códigos (4103 y 4114).

### 3.3 Códigos (VERIFICADO)

- MT §12.1: "Los códigos de incumplimiento de las validaciones están compuestos de **4 dígitos numéricos**". Rangos por grupo (§12.1.1–12.1.3): WS `0000–0619` (AA01…BU20), DE `1000–2599` (A002…J003), eventos `4000–4323` (MT original; NT 14, 18 y 19 extienden hasta 4478).
- **Un código puede corresponder a varias validaciones**:
  - en el MT v150 el código **2419** lo usan `H002c` y `H005a`; los códigos **4313–4323** los usan a la vez GET015–GET020a y GET022–GET030 (corregido por NT 18 reasignando 4325–4335);
  - un mismo código agrupa varias causas: AC01/0120, AD01/0140 y AD02/0141 listan múltiples motivos; **0160 "XML malformado"** devuelve en `dMsgRes` una lista de errores de esquema (ejemplo oficial: "[El valor del elemento: dDirRec es invalido, El valor del elemento: dDirLocEnt es invalido]", Guía de Mejores Prácticas 2024).
- **Una validación puede tener varios códigos** según contexto (GDE008: 4006/4069).
- **Los rangos de la tabla 12.1 son incoherentes**: `BC01 0260 … BC20 0259` (fin menor que inicio), `D130 1261–1262` dentro de `D101 1250–1299`, `G050 2390–2399` dentro de `F001 2350–2399`, `E300 2550–2561` dentro de `J002 2500–2599`. No se puede inferir el grupo a partir del número de código.
- Existen **códigos fuera del MT y de las NT**, documentados solo en guías u observados en producción: **0364** "Consulta extemporánea de Lote" (48 h) y **0422** "CDC encontrado" (el MT dice **0421** "CDC Encontrado"; la guía de 2024 muestra 0422) (VERIFICADO en la Guía de Mejores Prácticas). El código **2501** (hash QR/CSC) aparece en el MT (J002a) y en NT 10.

### 3.4 Severidades y estados de respuesta (VERIFICADO)

- Columna "E" (estado): **A** (Aprobado), **AO** (Aprobado con observaciones), **R** (Rechazado). Ejemplos AO en el MT: A004b/1005 "Transmisión extemporánea del DE", GEN003/4103, GED003/4253.
- Valor no definido en la leyenda: **N** en `BC01 0260 "Autorización del DE satisfactoria"`. El texto del MT menciona "resultados de rechazo y notificación" sin definir "notificación" como severidad.
- En la respuesta del WS: `dEstRes` (string sin enumeración en `protProcesDE_v150.xsd`), `gResProc` con `dCodRes` + `dMsgRes`, `gResProc` con `maxOccurs="100"` (VERIFICADO). Valores observados en documentación oficial: "Rechazado" (ejemplo XML de la Guía 2024); la Guía menciona "Aprobado, Aprobado con Observación o Rechazado". Cadenas exactas de "Aprobado"/"Aprobado con observación": PROBABLE.
- El MT y la FAQ dicen que en el rechazo se informa **el primer error** encontrado (VERIFICADO MT §12; FAQ https://www.dnit.gov.py/web/e-kuatia/preguntas-frecuentes/-/categories/400165 según resumen de búsqueda: PROBABLE en el texto exacto).

### 3.5 ¿Una validación puede pasar de observación a rechazo con el tiempo?

- **Sí, VERIFICADO**: `GED003` (código 4253, "Fecha de emisión del DE/DTE ha superado el plazo para registro del evento") es **AO** en el MT v150 (§11.6.6) y **R** en NT 19 (vigente prod 31/01/2024).
- También ocurre lo contrario (eliminación o "exclusión" de reglas R): NT 4 (D101a), NT 25 (GEC002c), NT 26 (E020, E020a, E704, E705).
- No se encontró en las NT un mecanismo explícito de "periodo de notificación previo al rechazo" (ninguna NT usa términos como "convivencia" o "período de transición"; búsqueda en texto de las 27 NT, VERIFICADO). La transición se gestiona solo con la diferencia entre fecha de test y de producción.

---

## 4. Verificación del ejemplo del usuario

| Elemento | Resultado | Evidencia |
|---|---|---|
| D208 = `iTipIDRec` | **VERIFICADO**. Grupo D3, padre D200, N, longitud 1, ocurrencia 0-1. Valores 1,2,3,4,5 (Innominado),6 (Tarjeta Diplomática),9. Condición actual (NT 23): "Obligatorio si D201 = 2 y D202 ≠ 4; No informar si D201 = 1". | MT p. impresa 71–72; NT 2; NT 23 |
| D201 | **VERIFICADO**: `iNatRec`, Naturaleza del receptor (1 contribuyente, 2 no contribuyente), N 1, 1-1 | MT D3 |
| D202 | **VERIFICADO**: `iTiOpe`, Tipo de operación (1 B2B, 2 B2C, 3 B2G, 4 B2F), N 1, 1-1 | MT D3; XSD `tiTiOpe` pattern `[1-4]` |
| D210 | **VERIFICADO**: `dNumIDRec`, Número de documento de identidad, A 1-20, 0-1; "En caso de DE innominado, completar con 0 (cero)" | MT; NT 2; NT 23; XSD `tdNumDocId` `[0-9A-Za-z\-]{1,20}` |
| D011 | **VERIFICADO**: `iTipTra`, Tipo de transacción, N 1-2, 0-1 (obligatorio si C002 = 1 o 4); valor **13 = "Muestras médicas (Art. 3 RG 24/2014)"** | MT D1; XSD `tiTipTra` 1..13 |
| F014 | **VERIFICADO**: `dTotGralOpe`. Ojo: la tabla de campos lo describe como "Total Neto de la operación" (F008 − F013 + F025), mientras las validaciones lo llaman "total general de la operación" | MT F; NT 1 |
| F023 | **VERIFICADO**: `dTotalGs`, "Total general de la operación en Guaraníes", N 1-15p(0-8), 0-1; no informar si D015 = PYG | MT F; NT 8 |
| Validación D208c, código 1321 | **VERIFICADO**. Mensaje: "Tipo de documento de identidad del receptor incorrecto para el total general de la operación en guaraníes". E = R | MT p. 166; NT 21; NT 24 |
| Regla de innominado con monto | **VERIFICADO**. MT v150: ≥ 60.000.000 · NT 21: ≥ 35.000.000 (desde 01/01/2024) · NT 24: ≥ 7.000.000 (desde 01/01/2025, test y producción) | ídem |
| Regla "vigente NT024" | **VERIFICADO** a hoy: NT 25, 26 y 27 no tocan D208c. (No se revisaron canales no publicados en el portal.) | NT 25–27 |
| Base legal | **VERIFICADO** que las NT citan el Art. 6 del Decreto 872/2023; **PROBABLE** que el decreto fije el escalonamiento 35 M (2024) → 7 M (2025) y use "supere" (estrictamente mayor), mientras la NT usa "mayor o igual" | Fonoa https://www.fonoa.com/resources/blog/paraguay-publishes-new-decree-regulating-e-invoicing-obligations ; Última Hora https://www.ultimahora.com/forma-de-emision-de-las-facturas-electronicas ; EY (Decreto 872 del 18/12/2023, vigente 01/01/2024) |

Texto literal vigente (NT 24): "Si el Tipo de transacción es distinto a Muestras médicas (D011≠13), El Tipo de documento de identidad del receptor no puede ser Innominado (D208≠5) cuando el total general de la operación en guaraníes (cuando la moneda es extranjera) o el total general de la operación (cuando la moneda es PYG) es mayor o igual a 7.000.000 (F023 >= 7.000.000 o F014 >= 7.000.000)".

Precisiones para el modelado (VERIFICADO sobre el texto):
- El paréntesis `(D208≠5)` expresa la **restricción que debe cumplirse**, no la condición de disparo. El predicado de violación es `D011≠13 ∧ D208=5 ∧ monto ≥ 7.000.000`. Ambas polaridades conviven en el mismo texto.
- El monto relevante depende de la moneda: F023 si la moneda es extranjera (F023 solo existe si D015 ≠ PYG), F014 si es PYG. La forma simplificada "F023 ≥ X o F014 ≥ X" no es literalmente equivalente en todos los casos.
- D201 y D202 no aparecen en D208c; se relacionan por la condicionalidad de D208 (obligatorio si D201=2 y D202≠4) y por D208b/D208f (innominado solo en B2C, D202=2).

---

## 5. Cómo especifican las NT sus cambios (VERIFICADO)

- **No hay tablas "antes/después"**. Cada NT reproduce la fila completa en su estado nuevo (campo o validación) bajo un encabezado con verbo: "se modifica(n)", "se agrega(n)", "se elimina(n)", "se excluye(n)", "se incorpora", "se corrige", "se amplía", "se incluye". El estado anterior hay que reconstruirlo del MT o de la NT previa.
- A veces el encabezado precisa la columna afectada ("se modifica el siguiente campo en la Longitud", NT 23 §1.2; "en la ocurrencia", §1.3; "se modifican … de Observaciones", NT 13), pero igualmente se muestra la fila entera.
- **Resaltado de color sin leyenda** en NT 21 y 24 (rojo y amarillo sobre fragmentos del texto). El MT v150 define: Amarillo = modificación, Verde = adición, Rojo = eliminación. En NT 21/24 el texto en rojo ("Si el Tipo de transacción es distinto a Muestras médicas (D011≠13)", "o igual", "=") **sigue vigente** y además ya figuraba en el MT; por tanto la convención no se aplica de forma consistente. **No se puede derivar la acción del color.**
- **Qué modifican**: campos (longitud, ocurrencia, observaciones, nuevos campos/grupos), validaciones (mensaje, código, observación, severidad, alta/baja), codificaciones (tablas 5, 6, 12), web services (NT 11, nuevo WS), esquemas de WS (NT 10), URLs (NT 10, QR), estándar de firma (NT 16), eventos completos (NT 14 nominación), texto normativo/descriptivo (NT 19 §5 sobre plazos de eventos; NT 19 §4 elimina una tabla de relaciones). Un modelo de "patch" limitado a campos y validaciones no cubre todo.
- **Fechas**: desde NT 13, dos fechas: "Fecha puesta a disposición para el Ambiente de Test" y "…de Producción" (pueden diferir). NT 1–12 no traen fechas de vigencia: solo "Fecha" y a veces "Cambios desde X al Y" (vigencia exacta NO VERIFICADO). El término oficial es "puesta a disposición", no "obligatoriedad"; para campos opcionales ("Inclusión opcional de acuerdo a las necesidades", NT 23) la puesta a disposición no implica obligación.
- **Prórrogas**: no se encontró ningún documento oficial separado de "prórroga". Evidencia de cambios de fechas: dentro del propio PDF re-subido (NT 13: producción 21/05/2023 según README de Roshka vs 17/06/2023 en el PDF actual, PROBABLE) y por superposición explícita (marca de agua en NT 21 remitiendo a NT 24, VERIFICADO). Otros canales ("mecanismos formales de comunicación de la DNIT") pueden anunciar cambios: NO VERIFICADO cuáles.
- **Base legal**: algunas NT citan la norma (Decreto 872/2023 en NT 21, 23 y 24; Dictamen DEINT N° 344 en NT 12; RG 90/RG90 en NT 18 y 22; Ley 6822 en NT 16). La vigencia legal y la técnica pueden diferir (§4).
- **Períodos de convivencia/"notificación"**: no hay mecanismo explícito (§3.5). La única "convivencia" observable es entre ambiente de test y producción.

---

## 6. XSD

### 6.1 Dónde se publican (VERIFICADO)

- En línea: `https://ekuatia.set.gov.py/sifen/xsd/` (índice con **47 archivos**): `DE_Ekuatiai_v150.xsd, DE_Types_v150.xsd, DE_v150.xsd, Departamentos_v141.xsd, EventoCanc_v141.xsd, EventoInut_v141.xsd, Evento_Types_v141.xsd, Evento_Types_v150.xsd, Evento_v141.xsd, Evento_v150.xsd, FE_Types_v141.xsd, FE_v141.xsd, Monedas_v100.xsd, Monedas_v150.xsd, Paises_v100.xsd, RecEventoCanc_v141.xsd, RecEventoInut_v141.xsd, SIFEN_Types_v141.xsd, Unidades_Medida_v141.xsd, WS_ConsultaArchivoRuc.xsd, WS_SiConsDE_v141.xsd, WS_SiConsDTE.xsd, WS_SiConsDTEAsync.xsd, WS_SiConsLote_v141.xsd, WS_SiConsRUC_v141.xsd, WS_SiRecepDE_v141.xsd, WS_SiRecepDE_v150.xsd, WS_SiRecepEvento_v141.xsd, WS_SiRecepEvento_v150.xsd, WS_SiRecepLoteDE_v141.xsd, protProcesDE_v141.xsd, protProcesDE_v150.xsd, protProcesEventos_v141.xsd, siConsultaArchivoRuc.xsd, siConsultaDTE.xsd, siConsultaDTEAsync.xsd, siRecepDE_Ekuatiai_v150.xsd, siRecepDE_v141.xsd, siRecepDE_v150.xsd, siRecepEventoEmisor_v150.xsd, siRecepEventoReceptor_v150.xsd, siRecepEventoSet_v150.xsd, siRecepEvento_v141.xsd, siRecepEvento_v150.xsd, siRecepRDE_Ekuatiai_v150.xsd, siRecepRDE_v150.xsd, xmldsig-core-schema.xsd`.
- En el portal DNIT: `Estructura_DE xsd.rar` (subido 21/06/2023). Si coincide con el directorio en línea: NO VERIFICADO.
- Todos los archivos consultados devuelven el mismo `Last-Modified: Fri, 19 Sep 2025 16:40:10 GMT` (VERIFICADO con `curl -I`): parece un despliegue masivo; la cabecera **no** sirve para detectar qué archivo cambió (PROBABLE).

### 6.2 Nombres: manual vs servidor (VERIFICADO)

- El MT (índice de schemas) nombra `xmldsig-core-schema-v150.xsd`, `siRecepDE_v150.xsd`, `resRecepDE_v150.xsd`, `ProtProcesDE_v150.xsd`, `SiRecepLoteDE_v150.xsd`, `ProtProcesLoteDE_v150.xsd`, `resRecepLoteDE_v150.xsd`, `SiResultLoteDE_v150.xsd`, `resResultLoteDE_v150.xsd`, `siConsDE_v150.xsd`, `resConsDE_v150.xsd`, `ContenedorDE_v150.xsd`, `ContenedorEvento_v150.xsd`, `siRecepEvento_v150.xsd`, `resRecepEvento_v150.xsd`, `siConsRUC_v150.xsd`, `resConsRUC_v150.xsd`, `ContenedorRUC_v150.xsd`, `DE_v150.xsd`, `Evento_v150.xsd`. **Muchos no existen** con ese nombre en el servidor; varios WS solo existen en `_v141` (`WS_SiRecepLoteDE_v141.xsd`, `WS_SiConsLote_v141.xsd`, `WS_SiConsDE_v141.xsd`, `WS_SiConsRUC_v141.xsd`).
- MT §8.4.1 dice que el schema de la FE v150 es `FE_v150.xsd` y que los paquetes se llaman `PS_FE_150.zip`; en la práctica existe `DE_v150.xsd` y DNIT publica un `.rar`.
- `siRecepDE_v150.xsd` declara solo `<xs:element name="rDE" type="rDE"/>` e incluye `DE_v150.xsd`; el MT describe en cambio el request `rEnviDe`/`dId`/`xDE` para ese nombre (está en `WS_SiRecepDE_v150.xsd`).
- El sufijo `_vNNN` del archivo no equivale a la versión del formato: `DE_v150.xsd` incluye `Paises_v100.xsd`, `Departamentos_v141.xsd`, `Monedas_v150.xsd`, `Unidades_Medida_v141.xsd`, `DE_Types_v150.xsd`.

### 6.3 Cambios in situ (VERIFICADO)

- `DE_v150.xsd` (mismo nombre, mismo `targetNamespace="http://ekuatia.set.gov.py/sifen/xsd"`, `dVerFor` con `pattern [1][5][0]`) contiene elementos introducidos por NT posteriores a 2019: `dBasExe` (NT 13, 2023), `gOblAfe` (NT 18, 2023), `dCodConDncp` (NT 20, 2023), `dRucFus` (NT 23, 2024), `gGrupEner maxOccurs="9"` (NT 23), `dDncpG`/`dDncpE minOccurs="0"` (NT 26, 2025). `DE_Types_v150.xsd` define `tdCantProSer` con `fractionDigits 8` (NT 23 cambió E711 a `1-10p(0-8)`; el MT dice `1-10p(0-4)`).
- No hay atributo `version`, ni comentarios con fecha, ni referencia a NT en `xs:annotation` (VERIFICADO en `DE_v150.xsd` y `DE_Types_v150.xsd`). **Las versiones anteriores de los XSD no se publican**: el historial de estructura solo puede reconstruirse si la KB guarda instantáneas propias.

### 6.4 Conflictos XSD ↔ MT/NT detectados (VERIFICADO)

| Elemento | XSD actual | MT / NT |
|---|---|---|
| `gOblAfe` | `maxOccurs="12"` | NT 18: ocurrencia `0-11` |
| `dSisFact` (A005) | requerido, `positiveInteger`, `maxInclusive 1` | NT 10: "se elimina el siguiente campo" |
| `dEntCont` | declarado como `name="dEntCont "` (espacio final) | MT: `dEntCont` (E022). El espacio se colapsa al validar como NCName, pero rompe extractores por regex |
| `tiTipDocRec` | `pattern [1-6]\|9`, compartido por D208 y por GENFE010 (nominación) | NT 14 asignaba "5=Tarjeta Diplomática" en nominación; NT 27 lo cambia a 6. El XSD no distingue reglas por contexto |

### 6.5 Imports, enumeraciones y versión XSD (VERIFICADO)

- `DE_v150.xsd`, `Evento_v150.xsd` y `protProcesDE_v150.xsd` importan `http://www.w3.org/2000/09/xmldsig#` desde `schemaLocation="xmldsig-core-schema.xsd"` (ruta relativa) e **incluyen el resto por URL absoluta HTTPS** (`https://ekuatia.set.gov.py/sifen/xsd/...`). La validación offline necesita copias locales y un resolver/catálogo que reescriba esas URL.
- **XSD 1.0**: no se encontraron `xs:assert`, `xs:alternative`, `xs:openContent` ni `xs:override`.
- Muchas "enumeraciones" son patrones o rangos, no `xs:enumeration`: `tiTipDocRec` = `[1-6]|9`; `tiTipTra` = 1..13; `tiTiOpe` = `[1-4]`; `tiNatRec` = `[1-2]`. Las etiquetas de los códigos están solo en el MT/NT (documentación del XSD en algunos casos).
- Montos: `tMontoBase` = `xs:decimal`, `totalDigits 23`, `fractionDigits 8`, `0..999999999999999.99999999` (usado por `dTotGralOpe` y `dTotalGs`); existe también `tMontoBase4` (usado por `dMonEnt`).
- `Evento_v150.xsd` define estructuras de eventos que el MT/NT no documentan o marcan como futuros: `rGeVeEnd` (endoso), `rGeVeRetAce`, `rGeVeRetAnu`, `rGeVeCCFF`, `rGeDevCCFFCue`, `rGeDevCCFFDev`, `rGeVeAnt`, `rGeVeRem`, eventos SET `rGeVeOA`, `rGeVePC`, `rGeVeImp`, `rGeVeDet`. El XSD **no es subconjunto** de la documentación.

---

## 7. Web services, eventos, CDC, QR/CSC, KuDE

### 7.1 Web services (VERIFICADO: MT §7.10, §8, §9, §12.3; NT 11; Guía 2024)

| Servicio | Modo | Endpoint (prod / test: `sifen.set.gov.py` / `sifen-test.set.gov.py`) | Notas |
|---|---|---|---|
| siRecepDE | síncrono | `/de/ws/sync/recibe.wsdl` | 1 DE firmado; límite 1000 KB (0200); éxito `0260` (E = "N") |
| siRecepLoteDE | asíncrono | `/de/ws/async/recibe-lote.wsdl` | Hasta 50 DE, mismo RUC emisor y mismo tipo; XML `rLoteDE` comprimido y en Base64 en `xDE` dentro de `rEnvioLote`; 0300 recibido / 0301 no encolado. Límite: MT dice 10.000 KB (0270), la Guía 2024 dice 1000 KB |
| siResultLoteDE | consulta | `/de/ws/consultas/consulta-lote.wsdl` | Por `dProtConsLote`; 0360 inexistente, 0361 en procesamiento, 0362 concluido, 0364 extemporánea (> 48 h). Procesamiento puede tardar 1–24 h en picos |
| siConsDE | consulta | `/de/ws/consultas/consulta.wsdl` | Por `dCDC`; 0420 no existe/rechazado; 0422 encontrado (MT: 0421) con `xContenDE` |
| siRecepEvento | síncrono | `/de/ws/eventos/evento.wsdl` | 0600 evento registrado |
| siConsRUC | consulta | `/de/ws/consultas/consulta-ruc.wsdl` | 0500 inexistente, 0501 sin permiso, 0502 éxito |
| Consulta masiva de RUC | síncrono | (NT 11) `rEnviConsArchivoRUCRequest` | 0520–0523; una descarga diaria |
| siConsDEST | futuro | — | DE destinados / organismos externos |

- Transporte: SOAP 1.2, document/literal, TLS 1.2 con autenticación mutua; certificado de PSC habilitado (MIC); RUC en `SerialNumber` (persona jurídica) o `SubjectAlternativeName` (persona física). NTP: `aravo1.set.gov.py`, `aravo2.set.gov.py`.
- Reglas operativas (Guía 2024, VERIFICADO; carácter normativo discutible): bloqueo de 10 a 60 minutos por RUC ante lotes vacíos, CDC repetidos o lotes reenviados; consultar lotes cada ≥ 10 minutos; no reenviar un CDC sin respuesta definitiva.
- Errata VERIFICADO: la URL de test del MT para recepción síncrona dice `recibe.wsd?wsdl`.

### 7.2 Eventos (VERIFICADO: MT §11; NT 14, 19, 25, 27)

- **Emisor**: Cancelación (hasta 48 h tras aprobación para FE; 168 h para NCE, NDE, NRE, AFE; motivo libre), Inutilización (rango de hasta 1000 números no usados; dentro de los 15 primeros días del mes siguiente; motivo hasta 150 caracteres; NT 10 agrega serie `dSerieNum`), Devolución y Ajuste de precios (automático por NC/ND), Endoso de FE (futuro), Actualización de datos del transporte (§11.6.7), **Nominación de FE** (NT 14: identifica al receptor de una FE emitida a innominado; regla GENFE002e/4469 exige que la FE original tenga D208=5).
- **Receptor**: Notificación de recepción (informativo, DE o DTE), Conformidad (conclusivo, parcial/total), Disconformidad (conclusivo), Desconocimiento (informativo). Plazo 45 días; NT 19 precisa que para DE se cuenta desde la emisión y para DTE desde la aprobación, y que vale el último evento registrado.
- **SET**: Impugnación (futuro). **Automáticos**: vinculación NC/ND, vinculación NRE, interoperabilidad (Tesaka, Marangatu).
- En e-Kuatia'i (solución gratuita) la cancelación de FE tiene 120 h (FAQ, PROBABLE en texto exacto): **los plazos dependen también de la plataforma y de resoluciones generales**, no solo del MT.

### 7.3 CDC (VERIFICADO salvo marca)

- 44 dígitos; atributo `Id` de `DE` (campo A002) y `Reference URI="#CDC"` en la firma. Se muestra en el KuDE en grupos de 4.
- Composición (inferida de la validación A002/1000, que enumera C002, D101, D102, C005, C006, C007, D103, D002, B002, B004, A003; la tabla gráfica del MT es una imagen; confirmada por la librería TIPS-SA, PROBABLE en el detalle de longitudes):
  `tipo de documento (2) + RUC emisor (8, ceros a la izquierda) + DV del RUC (1) + establecimiento (3) + punto de expedición (3) + número de documento (7) + tipo de contribuyente (1) + fecha de emisión AAAAMMDD (8) + tipo de emisión (1) + código de seguridad dCodSeg (9) + DV del CDC (1)`.
- **No incluye** timbrado ni serie (la unicidad del documento por timbrado + serie la controla A002b/1002).
- DV: módulo 11 (MT §10.2 remite a un PDF de set.gov.py). Algoritmo usual (TIPS-SA, PROBABLE): pesos 2..11 de derecha a izquierda, resto r = suma mod 11, DV = 11 − r si r > 1, si no 0.
- `dCodSeg` (B004): número aleatorio de 9 dígitos, no secuencial, distinto por DE, distinto de `dNumDoc`, sin relación con datos del DE; **forma parte del CDC y es visible**, no es el CSC.
- Errata: el ejemplo de CDC usado en los ejemplos de firma (`0144444401700100100145282201170125158732260988`) tiene **46** caracteres; el del QR tiene 44.

### 7.4 QR y CSC (VERIFICADO: MT §13.8; NT 10; Guía de Pruebas 2026)

- QR ISO/IEC 18004, mínimo 25 mm; contenido en J002 (`dCarQR`).
- **CSC (Código de Seguridad del Contribuyente)**: 32 caracteres alfanuméricos, generado por SIFEN y entregado al facturador; hasta dos activos, identificados por `IdCSC` (4 dígitos). Es **secreto** porque con él se calcula `cHashQR` = SHA-256 (hex) de los parámetros del QR concatenados con el CSC; quien lo conozca puede fabricar QR "auténticos" para documentos no transmitidos. El MT: "Por ningún motivo el contribuyente debe compartir su código de seguridad, ni enviar concatenado como parte de la URL del código QR".
- Parámetros: `nVersion`, `Id` (CDC), `dFeEmiDE` (en hex), `dRucRec`/`dNumIDRec`, `dTotGralOpe`, `dTotIVA`, `cItems`, `DigestValue` (en hex), `IdCSC`, `cHashQR`. URL de consulta: `https://ekuatia.set.gov.py/consultas/qr?` (prod) y `…/consultas-test/qr?` (test). En el XML, `&` → `&amp;`.
- Error 2501: hash del QR inválido / CSC no vigente en la fecha de emisión (MT J002a; NT 10).
- **En test el CSC es público y genérico**: `IdCSC 0001 = ABCD0000000000000000000000000000`, `IdCSC 0002 = EFGH0000000000000000000000000000` (Guía de Pruebas 2026). En producción, secreto.
- Erratas del MT en esta sección: el texto dice "D205 o D210", "F013" y "F016", mientras la tabla dice D206/D210, F014 y F017; el ejemplo mezcla `nVersion=150` y `nVersion=142`.

### 7.5 KuDE (VERIFICADO: MT §13)

Representación gráfica del DE: formatos carta (FE, NCE, NDE, AFE, NRE), cinta de papel y cinta resumen; campos de encabezado, ítems, totales, información de consulta (CDC en grupos de 4, QR). Documentos de test deben llevar la leyenda "DOCUMENTO ELECTRÓNICO SIN VALOR COMERCIAL NI FISCAL - GENERADO EN AMBIENTE DE PRUEBA" (Guía de Pruebas).

---

## 8. Proyectos open source (contraste NO normativo)

| Proyecto | Lenguaje / licencia | Qué codifica | Estado / observaciones |
|---|---|---|---|
| TIPS-SA/facturacionelectronicapy-xmlgen — https://github.com/TIPS-SA/facturacionelectronicapy-xmlgen | Node.js/TypeScript, MIT | JSON → XML del DE, CDC y DV módulo 11, validaciones parciales de entrada, eventos | Enlazado por DNIT en "Librerías". Cita MT v150; no mapea explícitamente NT ni IDs/códigos de validación (no se encontró "D208c" ni "1321" en `jsonDeMainValidate.service.ts`, lectura parcial) (PROBABLE) |
| Paquetes hermanos TIPS: `facturacionelectronicapy-xmlsign`, `-qrgen`, `-setapi`, `-kude` (npm) | Node.js | Firma, QR, cliente WS, KuDE | PROBABLE (README) |
| roshkadev/rshk-jsifenlib — https://github.com/roshkadev/rshk-jsifenlib | Java 8, MIT, v0.2.4 | Cliente de los WS (RUC, DE, lote, consulta lote, eventos), configuración CSC/certificado PFX | Enlazado por DNIT. Soporta NT 13 con flag `sifen.habilitar_nota_tecnica_13`; README dice que NT 14 "aún no está soportada" → atrasado respecto de NT 15–27 (PROBABLE) |
| IonysDev/pkuatia — https://packagist.org/packages/ionysdev/pkuatia | PHP ≥ 8.1 | Generar, firmar, enviar y consultar DTE (MT v150) | PROBABLE |
| fertandil87/sifen — https://packagist.org/packages/fertandil87/sifen | PHP | Generación y envío básico | Poca actividad (PROBABLE) |
| pykude — https://pypi.org/project/pykude/ | Python | KuDE PDF a partir del XML | No genera XML ni CDC (PROBABLE) |
| hugomrj/jsifen — https://www.mintlify.com/hugomrj/jsifen | Java 17+/Quarkus | API REST, generación y firma | Documentación de terceros (PROBABLE) |

- No se encontró una librería Python madura que genere/firme/valide DE SIFEN (PROBABLE).
- Ninguna librería revisada codifica la historia temporal de reglas por NT. Sirven como contraste para CDC, DV, firma, estructura y codelists, y como fuente de casos de prueba, **no** como fuente de verdad. Que DNIT las enlace no las vuelve normativas (la página no trae disclaimer; VERIFICADO).
- Herramientas oficiales útiles como oráculo manual: **Prevalidador** (https://ekuatia.set.gov.py/prevalidador/) y el **ambiente de test** `sifen-test.set.gov.py`.

---

## 9. Supuestos del documento del usuario incorrectos, imprecisos o arriesgados

1. **"Manual v150" como una fuente única y fija**: impreciso. Hay al menos tres binarios "v150" (24/06/2019 en un sitio de terceros; 10/09/2019 listado por MD5; el publicado hoy con otro MD5). La base debe identificarse por hash, no por nombre (VERIFICADO el desajuste de MD5).
2. **`sources/` representa "exactamente lo descargado" y una NT es un PDF**: insuficiente. DNIT re-sube NT con cambios (NT 21 con marca de agua; NT 18 en junio de 2024; NT 14 `V150X`) y cambia fechas dentro del mismo documento (NT 13, PROBABLE). Hace falta guardar **todas las versiones** de cada NT (por hash, con `t=`, nombre de archivo, fecha de descarga y fechas internas) y vigilar re-subidas, no solo NT nuevas.
3. **El orden NT021 → NT024 → NTxxx como orden temporal**: la numeración no es cronológica (NT 9 < NT 8 < NT 7 por fecha). La resolución temporal debe usar fechas de vigencia por ambiente, no el número.
4. **"publication_date" y "effective_date" siempre disponibles**: falso para NT 1–12 (sin fechas de vigencia); hay erratas de fecha (NT 25); la subida al portal puede ser posterior a la vigencia (NT 22). El modelo temporal necesita fechas por ambiente (test/producción), fuente de cada fecha y estado "desconocida/aproximada".
5. **Precedencia "XSD vigente" como fuente estable de estructura**: el XSD se cambia in situ sin versión ni historial, y contradice a MT/NT en casos concretos (`gOblAfe` 12 vs 0-11; `dSisFact` requerido vs eliminado). Hay que versionar instantáneas propias del XSD y registrar conflictos; "XSD manda en estructura" debe ser una política explícita con excepciones, no un supuesto.
6. **Extraer enumeraciones del XSD**: solo parcial. Muchos dominios son `pattern` o rangos (`[1-6]|9`, 1..13); las etiquetas están en el MT/NT; algunas codificaciones viven en archivos externos (XLSX geográfico actualizado en noviembre de 2025 sin NT, XSD de países, servicio de actividades económicas).
7. **Unicidad de IDs y códigos** (`test_validation_codes_are_unique_when_expected`, `sifen get-validation 1321` → una sola validación): un código puede mapear a varias validaciones (2419; 4313–4323 en el MT) y una validación a varios códigos (GDE008: 4006/4069). La clave de validación debe incluir el contexto (documento/evento/sección), y `get-validation <código>` debe poder devolver varios candidatos.
8. **Colisión campo/validación**: "D208" es a la vez un campo y una validación (código 1310). El modelo necesita espacios de nombres separados (p. ej. `field:D208` vs `validation:D208`).
9. **`xml_name` como identificador**: `iTipIDRec` es D208 en el DE y GENFE010 en el evento de nominación, con reglas y enumeraciones distintas en el tiempo; `dTotalGs` existe en F023 y en GEN011. La identidad debe ser (esquema/contexto, ID) o XPath, no el nombre XML.
10. **`group: "D"` en el modelo de campo**: el grupo real es `D3` (subgrupo con rango D200–D299) y el padre es `D200` (`gDatRec`). Usar solo la letra pierde jerarquía.
11. **Asumir que un rechazo trae una validación identificable**: la respuesta trae `dCodRes`/`dMsgRes`; los errores de esquema llegan como **0160** con texto libre que puede listar varios elementos; `gResProc` admite hasta 100 resultados; el MT dice que se informa el primer error. Además existen códigos que solo aparecen en guías (0364, 0422) o difieren del MT (0421 vs 0422). La KB debe admitir códigos "observados" con provenance distinta de la normativa.
12. **Severidad como atributo fijo**: cambia por NT (GED003/4253 AO→R) y existen valores fuera de la leyenda ("N"). Debe ser temporal.
13. **Patch de NT que reemplaza una regla entera**: las NT reescriben la fila completa, pero (a) no dicen qué cambió (no hay antes/después); (b) el color no es fiable; (c) a veces introducen IDs nuevos para reglas equivalentes sin declarar el reemplazo (D208b/1319 vs D208f/1333). El diff semántico debe calcularse contra el estado previo reconstruido y marcar como `needs_review` todo reemplazo no declarado (riesgo R3 del usuario: confirmado como real).
14. **Patches solo para campos y validaciones**: las NT también cambian web services (NT 11), URLs (NT 10), estándar de firma (NT 16), eventos completos (NT 14), codificaciones (NT 10, 18, 23) y texto normativo (NT 19 §4–§5).
15. **Regla técnica = obligación legal**: NT 24 usa "mayor o igual a 7.000.000", mientras las fuentes secundarias citan el decreto con "supere" (PROBABLE). Lo que SIFEN aplica es la NT; lo legal es el decreto. Conviene guardar ambas y señalar la divergencia, no fusionarlas.
16. **Confiar en el Manual como texto correcto**: tiene erratas comprobadas (`<?xml version="150"…>`; CDC de 46 caracteres; QR con D205/F013/F016 en el texto vs D206/F014/F017 en la tabla; `nVersion=142`; `recibe.wsd`; rangos de códigos solapados o invertidos; N° Val duplicado; el control de versiones dice que se eliminaron los códigos 0100–0107 y 0123–0126 pero siguen en las tablas; lote 10.000 KB vs 1000 KB en la guía). Una regla "verified si MT = XSD" dará falsos `conflict` y también falsos `verified`.
17. **Provenance por "página"**: las NT citan la página impresa (pie) y no el índice del PDF (D208c: impresa 166, PDF 167). Guardar ambas.
18. **Ejemplo de caso `gPaConEIni = 700000`**: impreciso. `gPaConEIni` (E605) es un **grupo** (G, 0-999); el monto está en `dMonTiPag` (E608) dentro del grupo. La regla relevante es E605a/E605b (con `dMonEnt`, E645, N `1-15p(0-4)`): si es crédito y existe E645, el grupo es obligatorio (1551); si no existe E645, el grupo no debe informarse.
19. **CSC vs código de seguridad**: el documento habla de "CSC completo" como secreto (correcto), pero no hay que confundirlo con `dCodSeg` (9 dígitos, parte del CDC, público en KuDE y QR). Y los CSC de test son públicos: encontrarlos en ejemplos no es una fuga.
20. **"Fecha de puesta a disposición" = obligatoriedad**: las NT dicen "puesta a disposición" en test y producción; para elementos de "inclusión opcional" no hay obligación. La KB debe separar disponibilidad de exigibilidad.
21. **Sources como PDF únicamente**: parte de la documentación oficial está en RAR (XSD y XML de ejemplo), XLSX (geografía) y en un directorio web de XSD que puede diferir del RAR (NO VERIFICADO). El pipeline de ingesta debe contemplar esos formatos y su verificación (MD5 publicados están desactualizados).
22. **Supuesto implícito de que solo cambian las NT**: también cambian XSD (in situ), codificaciones (XLSX), guías operativas (Guía de Mejores Prácticas 2024, Guía de Pruebas 2026) y plazos por resoluciones generales (p. ej. e-Kuatia'i, RG 06/2024). El detector de cambios debe vigilar el directorio de XSD y la página de tablas, no solo la lista de NT.

---

## 10. Consecuencias factuales directas para el diseño (sin proponer arquitectura)

- Unidad de fuente = **(documento lógico, versión binaria por hash)**, con metadatos: URL, nombre de archivo, `t=`, fecha de descarga, SHA-256, MD5, fechas internas (Fecha, Test, Producción), fechas del PDF (creación/modificación) y fuente de cada fecha.
- Identidad de reglas = **contexto + ID**; mapa código→validaciones **1:N** y temporal.
- Temporalidad **por ambiente** (test/producción) con soporte de fechas desconocidas y de documentos superpuestos por otros (marca de agua de NT 21).
- **Conflictos documentales esperables** (MT vs NT vs XSD vs guías vs decreto): el sistema debe registrarlos como datos, no como fallos de ingesta.
- Golden tests posibles con datos reales y verificados hoy: D208c (60 M → 35 M → 7 M, fechas 2024-01-01 y 2025-01-01), GED003 (AO→R en NT 19), GDE008 (4006/4069), 2419 (H002c/H005a), `gOblAfe` (12 vs 0-11), `tdCantProSer` (fractionDigits 8 vs `1-10p(0-4)`).

---

## Anexo A. Fuentes oficiales consultadas (VERIFICADO)

- Documentación técnica: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica
- Manual Técnico v150: https://www.dnit.gov.py/documents/20123/420592/Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf/e706f7c7-6d93-21d4-b45b-5d22d07b2d22?t=1687362295907
- Listado Checksum MD5: https://www.dnit.gov.py/documents/20123/420592/Listado+Checksum+MD5+de+las+versiones+del+Manual+Tecnico.pdf/303ee6ab-fb9e-e708-9234-acf9e602f18a?t=1687362295755
- NT 027: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_027_MT_V150.pdf/e5376c97-64cf-3fe0-e962-b6f22c8c207a?t=1773076266295
- NT 026: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_026_MT_V150.pdf/605010d6-22fe-b732-24ab-c6e9d7868b4f?t=1749487559733
- NT 025: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_025_MT_V150.pdf/c6ad5e7d-bf0a-2be9-e5a0-a2a948ea1bc1?t=1745856915027
- NT 024: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_024_MT_V150.pdf/8f8c0fc6-ee49-74b6-469d-0f79c18065ed?t=1734614145050
- NT 023: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_023_MT_V150.pdf/9580922b-5dd5-60f9-4857-ae66a757898f?t=1724967650006
- NT 022: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_022_MT_V150.pdf/c7795a15-03be-caac-b664-692853c0f442?t=1709739358545
- NT 021: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_021_MT_V150+30.12.24.pdf/ab12f22b-42a2-9bd4-e3a0-7141d9e4b8d0?t=1735592286335
- NT 020: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_020_MT_V150.pdf/f9a47078-748e-db87-bf2f-e6826ef048b9?t=1700253534040
- NT 019: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_019_MT_V150.pdf/23bd2a28-9449-f31d-3d46-7f037706880d?t=1700253533804
- NT 018: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_018_MT_V150-+Junio.pdf/2ace18c4-5c03-c339-7f5c-bed6d5b5eb5e?t=1717710699642
- NT 017: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_017_MT_V150.pdf/6e3ccc6a-49eb-96fd-b2b6-86405bb2c4c5?t=1692977786216
- NT 016: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_016_MT_V150.pdf/fbb16776-262b-7330-e609-f509304413d4?t=1692977785955
- NT 015: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_015_MT_V150.pdf/f7f54b14-d4a8-d7c1-0549-804da511187e?t=1692655153604
- NT 014: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_014_MT_V150X.pdf/dbbb0294-8678-357a-1657-bcd0318077f9?t=1706200657282
- NT 013: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_013_MT_V150.pdf/ba73ec3b-5901-ae28-5d8c-9bed5632ab89?t=1687364547529
- NT 012: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_012_MT_V150.pdf/28807b7c-a7ee-9033-ab3f-75a0fcd52091?t=1687364547383
- NT 011: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_011_MT_V150.pdf/faada1a3-f158-90fe-795a-c7f30e61fb84?t=1687364547032
- NT 010: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_010_MT_V150.pdf/d64a693b-6c63-86e1-ec6a-d4fe5ec4eeea?t=1687364547196
- NT 009: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_009_MT_V150.pdf/c268a447-11e3-ee1e-b4d5-8d83dd408401?t=1687364546900
- NT 008: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_008_MT_V150.pdf/81fba389-0f27-e757-88c3-ec7b3dbab90b?t=1687364546734
- NT 007: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_007_MT_V150.pdf/d6b31757-8906-a326-4e92-f9ec4b5d7706?t=1687364546603
- NT 006: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_006_MT_V150+.pdf/9554f3e6-ffb6-17b6-bd53-4e4c87a8800d?t=1687364546470
- NT 005: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_005_MT_V150.pdf/098e75de-e878-7bcd-49ec-55c33a45a0a7?t=1687364546324
- NT 004: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_004_MT_V150.pdf/97868c1a-ef6f-af63-025b-515e9564997e?t=1687364546153
- NT 003: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_003_MT_V150.pdf/dd4689ee-164a-29b3-9c3f-44cbef55bcf5?t=1687364545998
- NT 002: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_002_MT_V150.pdf/b3656789-f42a-e578-4141-45046e452f41?t=1687364545841
- NT 001: https://www.dnit.gov.py/documents/20123/420595/NT_E_KUATIA_001_MT_V150.pdf/c4d2ab8e-632b-dc8f-d3f6-6a144a3a3d9c?t=1687364545680
- Guía de Mejores Prácticas (oct. 2024): https://www.dnit.gov.py/documents/20123/420592/Gu%C3%ADa+de+Mejores+Pr%C3%A1cticas+para+la+Gesti%C3%B3n+del+Env%C3%ADo+de+DE.pdf/38fe5830-98c0-2241-9895-671f86f1225f?t=1729866823709
- Guía de Pruebas (feb. 2026): https://www.dnit.gov.py/documents/20123/424160/Guia+de+Pruebas+para+e-kuatia.pdf/715a15bf-d866-afe3-49e2-c10e05242c95?t=1770659877488
- Tablas y codificaciones: https://www.dnit.gov.py/web/e-kuatia/tablas-y-codificaciones
- Librerías: https://www.dnit.gov.py/web/e-kuatia/librerias
- Decretos (incluye Decreto 872/2023; el PDF supera 10 MB y no se leyó): https://www.dnit.gov.py/web/e-kuatia/decretos
- FAQ (MT vigente, NT): https://www.dnit.gov.py/web/e-kuatia/preguntas-frecuentes/-/categories/2704806
- XSD: https://ekuatia.set.gov.py/sifen/xsd/ , https://ekuatia.set.gov.py/sifen/xsd/DE_v150.xsd , https://ekuatia.set.gov.py/sifen/xsd/DE_Types_v150.xsd , https://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd , https://ekuatia.set.gov.py/sifen/xsd/protProcesDE_v150.xsd , https://ekuatia.set.gov.py/sifen/xsd/Evento_v150.xsd

## Anexo B. Fuentes secundarias (PROBABLE)

- Fonoa (Decreto 872/2023, umbrales 35 M / 7 M): https://www.fonoa.com/resources/blog/paraguay-publishes-new-decree-regulating-e-invoicing-obligations
- Última Hora (30/01/2024, "supere G. 7.000.000" desde 01/01/2025): https://www.ultimahora.com/forma-de-emision-de-las-facturas-electronicas
- EY Tax Alert diciembre 2023 (Decreto 872 del 18/12/2023, vigente 01/01/2024): https://www.ey.com/content/dam/ey-unified-site/ey-com/es-py/technical/tax/documents/ey-tax-alert-diciembre-2023-2.pdf
- Copia de terceros del MT v150 24/06/2019: https://tdn.totvs.com.br/download/attachments/502840885/MT_E_Kuatia_V150_24_06_2019.pdf?api=v2
- TIPS-SA xmlgen: https://github.com/TIPS-SA/facturacionelectronicapy-xmlgen (algoritmo CDC/DV en `src/services/jsonDteAlgoritmos.service.ts`)
- Roshka jsifenlib: https://github.com/roshkadev/rshk-jsifenlib
- pkuatia: https://packagist.org/packages/ionysdev/pkuatia · fertandil87/sifen: https://packagist.org/packages/fertandil87/sifen · pykude: https://pypi.org/project/pykude/ · jsifen: https://www.mintlify.com/hugomrj/jsifen

## Anexo C. Pendiente de verificar (NO VERIFICADO)

- Contenido de `Estructura_DE xsd.rar` y `Estructura xml_DE.rar` y si coinciden con el directorio XSD en línea.
- Texto oficial del Decreto 872/2023, Art. 6 (escalonamiento y "supere" vs "mayor o igual").
- Qué difiere entre el binario v150 con MD5 `25EB165A…` y el publicado (`f48d7c82…`).
- Si D208b (1319) sigue vigente junto con D208f (1333), y si D219/D223 y D208d/D210a siguen eliminadas tras NT 23.
- Cadenas exactas de `dEstRes` para aprobado y aprobado con observación.
- Canales oficiales distintos del portal por los que DNIT comunica NT o prórrogas.
- Vigencia efectiva de NT 001–012 (no declaran fechas de test/producción).

# XML sintéticos de prueba

Documentos Electrónicos (DE) y respuestas de SIFEN **inventados**, mínimos, para probar `sifen_kb.xsd`
(`read_values`, `read_emission_date`, `read_processing_date`, `mask`, `validate_xml`) y, más adelante,
`explain --xml` y los veredictos de docs/arquitectura.md §K.6 (`test_xml_fixture_verdicts`).

Datos ficticios evidentes: emisor `EMISOR DE PRUEBA S.A.` con RUC `80000000` (DV `5`), receptor
`RECEPTOR DE PRUEBA`, código de seguridad `123456789`. El CDC (`DE/@Id`) se arma con esos datos; su
dígito verificador **no está verificado** y no corresponde a ningún documento real. Ninguno lleva firma
(`ds:Signature`) ni QR (`gCamFuFD`), así que **ninguno es válido frente al XSD completo** (ver abajo).
No se pueden usar como ejemplo de DE bien formado: solo ejercitan la lectura de los campos del piloto.

## Anidación real (verificada contra la instantánea XSD 2026-10-17)

Padre directo y ruta de cada campo del piloto (`rDE/DE/...`; los nombres no llevan prefijo y todos los
elementos están en el espacio de nombres `http://ekuatia.set.gov.py/sifen/xsd`):

| Campo | Elemento | Ruta | Ocurrencia |
|---|---|---|---|
| D002 | `dFeEmiDE` | `/rDE/DE/gDatGralOpe/dFeEmiDE` | 1-1 |
| D011 | `iTipTra` | `/rDE/DE/gDatGralOpe/gOpeCom/iTipTra` | 0-1 (y `gOpeCom` es 0-1) |
| D015 | `cMoneOpe` | `/rDE/DE/gDatGralOpe/gOpeCom/cMoneOpe` | 1-1 |
| D201 | `iNatRec` | `/rDE/DE/gDatGralOpe/gDatRec/iNatRec` | 1-1 |
| D202 | `iTiOpe` | `/rDE/DE/gDatGralOpe/gDatRec/iTiOpe` | 1-1 |
| D208 | `iTipIDRec` | `/rDE/DE/gDatGralOpe/gDatRec/iTipIDRec` | 0-1 |
| D209 | `dDTipIDRec` | `/rDE/DE/gDatGralOpe/gDatRec/dDTipIDRec` | 0-1 |
| D210 | `dNumIDRec` | `/rDE/DE/gDatGralOpe/gDatRec/dNumIDRec` | 0-1 |
| C002 | `iTiDE` | `/rDE/DE/gTimb/iTiDE` | 1-1 |
| F014 | `dTotGralOpe` | `/rDE/DE/gTotSub/dTotGralOpe` | 1-1 |
| F023 | `dTotalGs` | `/rDE/DE/gTotSub/dTotalGs` | 0-1 |
| respuesta | `dFecProc` | `/rRetEnviDe/rProtDe/dFecProc` | 1-1 (tipo `fecUTC`) |

`tests/unit/test_xsd.py::test_real_pilot_paths` lo comprueba contra la instantánea registrada.

## Documentos Electrónicos

Todos: `iTiDE=1`, `iTipTra=1` (D011 distinto de 13), `iNatRec=2`, `iTiOpe=2`, `dFeEmiDE` a las `09:30:00`
(sin zona: `fecHhmmss`). Los innominados llevan `iTipIDRec=5`, `dDTipIDRec=Innominado`, `dNumIDRec=0`.

| Archivo | Moneda | F014 | F023 | Emisión | Uso previsto (§K.6; la fecha de procesamiento se pasa aparte) |
|---|---|---|---|---|---|
| `de_innominado_pyg_f014_7000000_emision_2025-02-10.xml` | PYG | 7000000 | (ausente) | 2025-02-10 | umbral "mayor o igual" de NT 24: TRUE con procesamiento en 2025-02 |
| `de_innominado_pyg_f014_6999999_emision_2025-02-10.xml` | PYG | 6999999 | (ausente) | 2025-02-10 | un guaraní bajo el umbral: FALSE |
| `de_innominado_pyg_f014_8000000_emision_2024-06-10.xml` | PYG | 8000000 | (ausente) | 2024-06-10 | con la versión de NT 21 (umbral 35 M): FALSE |
| `de_innominado_usd_f023_8000000_emision_2025-02-10.xml` | USD (`dCondTiCam=1`, `dTiCam=8000`) | 1000 | 8000000 | 2025-02-10 | moneda extranjera con F023 >= 7 M: TRUE |
| `de_innominado_usd_f014_7500000_f023_6000000_emision_2025-02-10.xml` | USD (`dTiCam=0.8`, artificial) | 7500000 | 6000000 | 2025-02-10 | F014 >= 7 M con F023 < 7 M: TRUE por el paréntesis, FALSE por la prosa (el *gap*, ISS-0005) |
| `de_receptor_sin_tipo_documento_pyg_f014_10000000_emision_2025-02-10.xml` | PYG | 10000000 | (ausente) | 2025-02-10 | receptor **sin** `iTipIDRec`/`dDTipIDRec`/`dNumIDRec` (D208 ausente): FALSE |
| `de_innominado_pyg_f014_10000000_emision_2024-12-30.xml` | PYG | 10000000 | (ausente) | 2024-12-30 | eje temporal (§G.4): emisión antes y procesamiento después del 2025-01-01; con `respuesta_recepcion_dfecproc_2025-01-02.xml` da `axis_split`, sin fecha de procesamiento `processing_date_unknown` |
| `de_receptor_cedula_pyg_f014_5000000_emision_2025-02-10.xml` | PYG | 5000000 | (ausente) | 2025-02-10 | adicional: receptor identificado (`iTipIDRec=1`, `dNumIDRec=4567890`): D208 distinto de 5, y prueba de enmascarado (`4567890` -> `****890`) |

Valores que `read_values(PILOT)` devuelve para cada uno (ver `DE_FIXTURES` en el test): p. ej. el primero
da `D002=2025-02-10T09:30:00, D011=1, D015=PYG, D201=2, D202=2, D208=5, D209=Innominado, D210=0, C002=1,
F014=7000000, F023=None`.

### Errores de esquema (`validate_xml` contra `sources/XSD_DIR/2026-10-17`)

Todos fallan por **estructura**, nunca por el valor de un campo (`test_real_fixture_values_are_valid_for_their_xsd_types`
comprueba que cada valor es válido para el tipo de su elemento). `xmlschema` informa el primer problema de
cada elemento, así que la lista es corta y no enumera todo lo que falta. Los siete DE con `iTipIDRec`
producen exactamente estos 7 errores:

```
/rDE/DE/gTimb: ... not complete. Tag 'dDesTiDE' expected.
/rDE/DE/gDatGralOpe/gOpeCom: Unexpected child with tag 'cMoneOpe' at position 2. Tag 'iTImp' expected.
/rDE/DE/gDatGralOpe/gEmis: Unexpected child with tag 'dNomEmi' at position 3. Tag 'iTipCont' expected.
/rDE/DE/gDatGralOpe/gDatRec: Unexpected child with tag 'iTipIDRec' at position 3. Tag 'cPaisRec' expected.
/rDE/DE/gTotSub: Unexpected child with tag 'dTotGralOpe' at position 1. Tag 'dTotOpe' expected.
/rDE/DE: Unexpected child with tag 'gOpeDE' at position 1. Tag 'dDVId' expected.
/rDE: ... not complete. Tag 'ds:Signature' expected.
```

El de receptor sin tipo de documento produce los mismos, salvo que el de `gDatRec` es
`Unexpected child with tag 'dNomRec' at position 3. Tag 'cPaisRec' expected.`

## Respuestas de SIFEN

| Archivo | Contenido | Esquema |
|---|---|---|
| `respuesta_recepcion_dfecproc_2025-01-02.xml` | `rRetEnviDe/rProtDe` directo: `dFecProc=2025-01-02T10:15:30-03:00`, rechazo 1321 del DE emitido el 2024-12-30 (`Id` = su CDC sintético) | válida (0 errores) |
| `respuesta_recepcion_soap_dfecproc_utc_cruza_medianoche.xml` | La misma dentro de un sobre SOAP, con `dFecProc=2025-01-03T01:30:00+00:00`: es el 2 de enero a las 22:30 en Asunción, así que la fecha de Paraguay es **2025-01-02** (prueba la conversión de zona) | 1 error: `/Envelope: 'Envelope' is not an element of the schema` (el sobre SOAP no es parte del XSD) |

`fecUTC` (`SIFEN_Types_v141.xsd`) es `xs:dateTime` con el patrón `\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+|-]\d\d:\d\d`:
el desplazamiento es obligatorio, sin fracciones de segundo y sin `Z`. Las dos respuestas lo cumplen.

## Mantenimiento

Son archivos estáticos escritos a mano (LF, UTF-8). Si se agrega uno, hay que registrarlo en `DE_FIXTURES` o
`RESPONSES` de `tests/unit/test_xsd.py` (`test_every_xml_fixture_is_covered` falla si no) y documentarlo aquí.
Nunca copiar aquí un XML real: los reales viven fuera del repo (docs/arquitectura.md §M).

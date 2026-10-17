# Seguridad

## Qué no debe llegar nunca a este repositorio

El repositorio es público y su historial de Git es permanente. **Nunca** subas, ni en un commit, ni en un Issue, ni en un PR, ni en un comentario:

- **XML reales** de documentos electrónicos, ni respuestas de SIFEN, ni logs de rechazos: traen RUC, cédulas, nombres y direcciones de receptores, CDC reales, códigos de seguridad, montos y la firma digital.
- **Certificados y claves**: `*.p12`, `*.pfx`, `*.key`, `*.pem`, `*.jks`, ni su contraseña.
- **El CSC de producción** (código de seguridad del contribuyente) ni su identificador. Con él se fabrican códigos QR "auténticos". Los CSC de **test** que DNIT publica en su documentación sí son públicos.
- **Contraseñas, tokens o claves de API** de cualquier servicio.
- Datos personales de clientes en `cases/`, Issues o mensajes de commit.

Un caso de rechazo se aporta **sanitizado**: valores sintéticos para RUC, documento, nombre y dirección; CDC recalculado; sin la firma, el QR ni `gCamFuFD`. Los casos llevan `sanitized: true` y `origin: observed`, y una prueba valida los elementos personales por nombre contra una lista de valores sintéticos. Ante la duda, no lo subas: describe el caso con palabras en un Issue.

## Qué hace el repositorio para protegerte

- `.gitignore` excluye `*.p12`, `*.pfx`, `*.key`, `*.pem`, `*.jks` y la carpeta `private/`.
- El CI ejecuta **gitleaks** sobre el historial y el check `pr-scope` **rechaza** cualquier PR que agregue un `*.p12`, `*.pfx`, `*.key`, `*.pem` o `*.jks`.
- `.claude/settings.json` deniega a Claude Code la lectura de esos archivos y de `private/`, y `CLAUDE.md` le prohíbe abrir XML reales o pedir certificados.
- `sifen explain --xml` abre el XML en solo lectura, sin red, con protección ante entidades externas, imprime solo los campos que usa la regla y **enmascara** los datos personales por defecto (`--show-pii` es solo para uso humano local).

Estas medidas reducen el riesgo, no lo eliminan: un comando de shell no previsto todavía podría leer un archivo. La regla de fondo es no dejar secretos al alcance del agente.

### Cómo trabajar con XML reales de forma segura

1. Guarda los XML reales en **una carpeta única fuera del repositorio** (por ejemplo `C:\sifen-privado\xml\`, fuera de OneDrive si tu política lo exige).
2. Agrega a `.claude/settings.local.json` (no versionado) una regla de lectura denegada para esa carpeta. Las rutas absolutas se escriben con doble barra inicial; en Windows `C:\sifen-privado` se normaliza a `/c/sifen-privado`:

   ```json
   { "permissions": { "deny": ["Read(//c/sifen-privado/**)"] } }
   ```

   En WSL o Linux la ruta equivalente es, por ejemplo, `Read(//mnt/c/sifen-privado/**)`.
3. Para diagnosticar un rechazo, usa la CLI (`uv run sifen explain <código> --xml RUTA --response RUTA`); no pidas a un agente que abra el XML con `Read`, `cat` ni `grep`.
4. Que un agente lea un XML real significa enviarlo a la API de su proveedor. Si tu organización no lo permite, no lo hagas: comparte solo la salida enmascarada.

## Si subiste algo sensible por error

1. **No lo borres solo con un commit nuevo**: queda en el historial.
2. Si es un secreto (clave, contraseña, token, CSC de producción), **revócalo o renuévalo de inmediato** en su origen; considera que ya está expuesto.
3. Avísanos por el canal privado de abajo para limpiar el historial (reescritura del historial y *force-push* a las ramas afectadas, hecho por la persona mantenedora) y pedir a GitHub que purgue las cachés de las vistas del commit.
4. Si son datos personales de terceros, avisa también a su titular y a tu área legal.

## Cómo reportar una vulnerabilidad

Si encuentras una vulnerabilidad en el código (por ejemplo, una forma de leer archivos fuera del repositorio con `--xml`, de evadir el enmascarado, de ejecutar código desde un YAML o un XSD, o de alterar `sources/` sin que la verificación lo detecte), o un secreto expuesto, **no abras un Issue público**.

- Usa el **aviso de seguridad privado de GitHub**: pestaña *Security* → *Report a vulnerability* en <https://github.com/NetseWin/sifen-kb/security/advisories/new>.
- Si no puedes usarlo, abre un Issue **sin detalles técnicos** que pida un contacto privado, y la persona mantenedora te responderá por un canal privado.

Incluye, en lo posible: la versión o el commit, los pasos para reproducirlo con datos sintéticos, el impacto que ves y, si la tienes, una propuesta de corrección. Nunca adjuntes datos reales. Se responde con acuse de recibo y, tras corregir, se publica un aviso con el crédito que prefieras. El proyecto lo mantiene una sola persona: los plazos son de mejor esfuerzo.

## Alcance

Cuenta como vulnerabilidad un fallo del código o de la configuración del repositorio que exponga datos o permita alterar la evidencia. **No** lo son: un error de contenido en la KB (una regla mal curada, una fecha equivocada), que se reporta con la plantilla de bug; ni los hallazgos sobre los sistemas de DNIT o de SIFEN, que debes comunicar a DNIT. El contenido de este repositorio no sustituye los documentos oficiales ni constituye asesoramiento legal o tributario (ver [`NOTICE`](NOTICE)).

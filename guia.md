# Guía de instalación con Devin + Gemini

Esta guía es para quien va a usar **Devin** para construir su
agente, y quiere que el cerebro de IA use **Google Gemini** (gratis) en vez de la API de
IA anterior. Esta guía cubre el flujo paso a paso.

---

## 1. Qué cambia respecto al README original

| | Original (Claude Code) | Con Devin + Gemini |
|---|---|---|
| Asistente que ejecuta el onboarding | Claude Code (`claude`, comando `/build-agent`) | Devin CLI, ya lo estás usando para leer esto |
| Cómo arranca el proceso | Slash-command `/build-agent` | Le pides a Devin en lenguaje natural que siga `CLAUDE.md` |
| Cerebro del agente generado | API de IA anterior (de pago) | Google Gemini API (**gratis**, capa Free de Google AI Studio) |
| Variable de API key | `API_KEY` | `GEMINI_API_KEY` |
| Modelo por defecto | `modelo-anterior` | `gemini-2.5-flash-lite` |

Todo lo demás (Zernio/Meta, FastAPI, SQLite/PostgreSQL, Docker, Railway) es idéntico.

---

## 2. Requisitos

1. **Python 3.11 o superior**
   - Verifica: `python --version` (Windows) o `python3 --version` (Mac/Linux)
   - Si usas conda: `conda create -n BOT python=3.11 -y && conda activate BOT`

2. **Devin CLI, ya instalado y autenticado**
   - Si estás leyendo esto dentro de una sesión de Devin, ya cumples este requisito.
   - No hace falta instalar Node.js ni ningún paquete adicional para el asistente:
     a diferencia de Claude Code, Devin no se instala vía `npm install -g ...`.

3. **Una API key de Gemini — gratis, sin tarjeta**
   1. Ve a [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
   2. Inicia sesión con tu cuenta de Google
   3. Click en **"Create API key"** (elige o crea un proyecto de Google Cloud si te lo pide)
   4. Copia la key. No hace falta configurar facturación: la capa gratuita se activa sola.

4. **Una cuenta de WhatsApp API** (igual que en el README)
   - [Zernio](https://zernio.com) (recomendado, plan free sin tarjeta) o
   - [Meta Cloud API](https://developers.facebook.com) directo

---

## 3. Cómo arrancar el proceso

### Paso 1 — Preparar el entorno

```bash
git clone https://github.com/Hainrixz/whatsapp-agentkit.git
cd whatsapp-agentkit
bash start.sh
```

`start.sh` verifica tu versión de Python, crea la carpeta `knowledge/` y copia
`.env.example` a `.env`. Ya no chequea si tienes Claude Code instalado.

### Paso 2 — Pedirle a Devin que arranque AgentKit

A diferencia de Claude Code, Devin **no usa slash-commands** para esto. En cambio, Devin
carga automáticamente `CLAUDE.md` como contexto del proyecto en cuanto abres el repo (lo
verás como una regla "always-on" en el sistema). Eso significa que no necesitas ningún
comando especial: basta con pedírselo en lenguaje natural, por ejemplo:

```
Quiero construir mi agente de WhatsApp con AgentKit. Sigue el proceso de las 5 fases
de CLAUDE.md: verifica el entorno, hazme la entrevista de mi negocio, genera el agente
con Gemini, pruébalo conmigo y al final pregúntame si quiero hacer el deploy.
```

Devin va a:
1. Verificar Python y preparar carpetas/dependencias (Fase 1)
2. Hacerte la entrevista de tu negocio, una pregunta a la vez — normalmente usando botones
   de opciones en vez de texto libre cuando la pregunta tiene alternativas cerradas (Fase 2)
3. Generar `agent/`, `config/`, `tests/`, `Dockerfile`, etc. con Gemini como cerebro (Fase 3)
4. Probar el agente contigo en un chat de terminal (Fase 4)
5. Preguntarte si quieres hacer deploy a Railway, y guiarte si dices que sí (Fase 5)

### Diferencias de comportamiento a tener en cuenta

- Devin puede presentarte preguntas de opción múltiple con botones (por ejemplo, para
  elegir el tono del agente o el proveedor de WhatsApp) en vez de pedirte que escribas
  "1", "2", "3". Si prefieres responder libremente, siempre puedes usar la opción "Otro".
- Devin ejecuta comandos reales en tu terminal (crear carpetas, instalar dependencias,
  correr el servidor) y te muestra el resultado; no hace falta que copies/pegues comandos
  a mano como con Claude Code.

---

## 4. Límites de la capa gratuita de Gemini

La API de Gemini es gratis en [Google AI Studio](https://aistudio.google.com), pero tiene
límites de peticiones por minuto (RPM) y por día (RPD) que dependen del modelo. Con
`gemini-2.5-flash-lite` (el default de AgentKit) los límites gratuitos son los más
generosos de la familia 2.5.

**¿Qué pasa si te quedas sin cuota?** La API devuelve un error `429 RESOURCE_EXHAUSTED`.
`agent/brain.py` lo detecta y responde con el mensaje de error configurado en
`config/prompts.yaml` (`error_message`) en vez de romperse. Opciones si esto te pasa
seguido:

1. Esperar a que se reponga la cuota (los límites diarios se resetean a medianoche
   hora del Pacífico).
2. Activar facturación en tu proyecto de Google AI Studio para pasar a un tier pagado.
   `gemini-2.5-flash-lite` sigue siendo muy barato en el tier pagado (~$0.10 entrada /
   $0.40 salida por millón de tokens).
3. Revisar tus límites actuales en la pestaña "Rate limits" de tu proyecto en
   [aistudio.google.com](https://aistudio.google.com).

---

## 5. Comandos útiles (idénticos al README)

```bash
# Probar el agente sin WhatsApp (chat en terminal)
python tests/test_local.py

# Arrancar el servidor localmente
uvicorn agent.main:app --reload --port 8000

# Build Docker para producción
docker compose up --build

# Auditar este repo (los 6 chequeos del sistema)
python3 scripts/audit.py
```

La única diferencia real en tu `.env` es que ya no existe `API_KEY`: la
variable se llama `GEMINI_API_KEY`, y el modelo se elige con `GEMINI_MODEL`
(default `gemini-2.5-flash-lite`).

---

## 6. ¿Y si de verdad quiero usar otra IA en vez de Gemini?

Este proyecto usa Gemini por defecto. Si en algún momento quieres cambiar a otro proveedor,
pídele a tu asistente que reescriba `agent/brain.py` usando el SDK correspondiente. El
contrato que usa `agent/main.py` (`generar_respuesta(mensaje, historial) -> (texto, es_respuesta_real)`)
no cambia, así que es un cambio acotado a ese archivo y a las variables de entorno.

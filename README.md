<p align="center">
  <img src="docs/assets/hero.png" alt="WhatsApp AgentKit — tu agente de WhatsApp con IA" width="820">
</p>

<p align="center">
  <a href="https://github.com/Hainrixz/whatsapp-agentkit"><img src="https://img.shields.io/github/stars/Hainrixz/whatsapp-agentkit?style=flat-square&color=25D366" alt="Estrellas"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licencia-MIT-blue?style=flat-square" alt="Licencia MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/IA-Gemini%20(gratis)-4285F4?style=flat-square" alt="Gemini">
  <img src="https://img.shields.io/badge/WhatsApp-Zernio%20%7C%20Meta-25D366?style=flat-square" alt="Zernio o Meta Cloud API">
</p>

<p align="center">
  <b><a href="https://hainrixz.github.io/whatsapp-agentkit/">Ver el sitio</a></b> ·
  <a href="#inicio-rápido">Inicio rápido</a> ·
  <a href="#cómo-funciona">Cómo funciona</a> ·
  <a href="#preguntas-frecuentes">FAQ</a>
</p>

---

## About

**WhatsApp AgentKit convierte una conversación de 20 minutos en un agente de WhatsApp
que atiende a tus clientes.**

No es una plantilla que copias y adaptas. Es un sistema de instrucciones (`CLAUDE.md`)
que tu asistente de codificación con IA — funciona con [Devin](https://devin.ai) o
cualquier otro que pueda leer archivos del repo — lee para entrevistarte sobre tu
negocio y después escribir, probar y desplegar el agente completo por ti: el servidor,
la conexión con WhatsApp, la memoria de cada cliente y el prompt que le da personalidad.
El cerebro del agente usa la API gratuita de **Google Gemini**.

Tú no escribes código. Respondes preguntas.

> ¿Vas a usar Devin en vez de Claude Code? Mira <a href="guia.md">guia.md</a> para los
> detalles de instalación específicos.

Lo hicimos porque el 90% del trabajo de montar un agente de WhatsApp no es la IA — es la
plomería: webhooks, firmas, tokens, reintentos, deploy. Esa parte ya está resuelta y
auditada acá adentro. Lo que queda es lo único que solo tú sabes: cómo funciona tu negocio.

Es open source, licencia MIT, y está escrito en español porque se hizo para builders
de LATAM.

---

## Inicio rápido

```bash
git clone https://github.com/Hainrixz/whatsapp-agentkit.git
cd whatsapp-agentkit
bash start.sh
```

Después abre tu asistente de codificación (por ejemplo, ejecuta `devin` en esta carpeta)
y pídele que arranque el proceso, por ejemplo:

```
Quiero construir mi agente de WhatsApp con AgentKit, sigue el proceso de CLAUDE.md
```

Muchos asistentes (Devin incluido) ya cargan `CLAUDE.md` automáticamente como contexto
del proyecto, así que no necesitas un comando especial. Ver <a href="guia.md">guia.md</a>
para el detalle paso a paso con Devin.

---

## Cómo funciona

`start.sh` solo verifica tu entorno. El sistema real arranca cuando tu asistente lee
`CLAUDE.md` y ejecuta cinco fases.

### Fase 1 — Verifica tu entorno

Chequea Python 3.11+, crea las carpetas, instala las dependencias y prepara el `.env`.

### Fase 2 — Te entrevista

Diez preguntas, una por una: cómo se llama tu negocio, a qué se dedica, para qué quieres
el agente, cómo se va a llamar, qué tono debe tener, tu horario, tus archivos de precios
o menú, tu API key de Gemini (gratis), y con qué servicio vas a conectar WhatsApp.

### Fase 3 — Construye el agente

Con tus respuestas escribe todo esto:

```
tu-proyecto/
├── agent/
│   ├── main.py              Servidor que recibe los mensajes de WhatsApp
│   ├── brain.py             Conexión con Gemini — el cerebro
│   ├── memory.py            Historial de cada cliente + deduplicación de eventos
│   ├── tools.py             Herramientas específicas de tu negocio
│   └── providers/           Conexión con tu servicio de WhatsApp
│       ├── base.py          Interfaz común
│       ├── __init__.py      Elige el proveedor automáticamente
│       └── zernio.py        Adaptador (o meta.py)
│
├── config/
│   ├── business.yaml        Los datos de tu negocio
│   └── prompts.yaml         El prompt que define la personalidad del agente
│
├── knowledge/               Tus archivos: menú, precios, políticas, FAQ
├── tests/test_local.py      Simulador de chat en tu terminal
├── Dockerfile               Para producción
├── docker-compose.yml
└── .env                     Tus API keys — nunca se sube a GitHub
```

### Fase 4 — Lo pruebas

Un chat en tu terminal donde **tú** escribes como si fueras un cliente:

```
Tu: Hola, qué horarios tienen?
Agente: Hola! Atendemos de lunes a viernes de 9am a 6pm.
        Te ayudo con algo más?

Tu: Cuánto cuesta el americano?
Agente: El americano está en $45 pesos.
        Quieres que te aparte uno?
```

Si algo no te gusta, se lo dices a tu asistente y lo ajusta ahí mismo.

### Fase 5 — Lo pones en línea

Te guía para subirlo a GitHub, conectarlo con Railway, cargar las variables de entorno y
configurar el webhook. Desde ese momento, cualquiera que te escriba por WhatsApp habla
con tu agente.

---

## Conectar con WhatsApp

Eliges uno de los dos durante el setup.

| | **Zernio** | **Meta Cloud API directo** |
|---|---|---|
| Qué es | Corre sobre la WhatsApp Cloud API de Meta y te resuelve la conexión | La API oficial de Meta, conectándote tú mismo |
| App de Facebook | No hace falta | Sí, tipo Business |
| App Review | No | Sí |
| Verificación de negocio | La haces desde el Embedded Signup | Cuenta de Facebook Business verificada |
| Costo | 2 cuentas conectadas gratis, sin tarjeta. En los dos casos las conversaciones se las pagas a Meta | Le pagas a Meta directo, sin intermediario |
| Probar sin número propio | Sí, número de pruebas compartido: 50 mensajes cada 24 h, gratis | Sí, Meta da un número de prueba, pero antes hay que crear la app |
| Para quién | **Recomendado.** Casi todo el mundo | Si ya tienes tu app de Meta armada |

**Zernio** ([zernio.com](https://zernio.com)) es el camino corto: creas la cuenta, conectas
tu WhatsApp Business desde el dashboard, copias la API key y listo. Si todavía no tienes
número de WhatsApp Business, su sandbox te deja ver el agente funcionando hoy mismo —
respondes un mensaje desde tu celular y quedas activado.

**Meta Cloud API** ([developers.facebook.com](https://developers.facebook.com)) te da
control total sobre la integración. Es más trabajo de configuración inicial.

Cambiar de uno a otro después es una frase: abre tu asistente y dile *"quiero migrar de
Zernio a Meta Cloud API"*.

---

## Qué pasa cuando un cliente escribe

```
Un cliente escribe "Hola" por WhatsApp
         │
         ▼
Tu proveedor (Zernio o Meta) recibe el mensaje
         │
         ▼  webhook POST /webhook
main.py verifica la firma del webhook
         │
         ▼
providers/ normaliza el mensaje a un formato común
         │
         ▼
memory.py: ¿ya procesamos este evento? → si sí, se descarta
         │
         ▼
main.py responde 200 AHORA y encola el trabajo
         │
         ▼  ──────── fuera del ciclo del webhook ────────
memory.py busca el historial de ESE cliente
         │
         ▼
brain.py llama a Gemini con el system prompt + historial + mensaje
         │
         ▼
providers/ envía la respuesta por WhatsApp
         │
         ▼
El cliente recibe la respuesta en segundos
```

Tres decisiones de diseño que importan:

**Responde primero, trabaja después.** Los proveedores esperan una confirmación en unos
5 segundos y, si no la reciben, reintentan el mismo mensaje hasta 7 veces. Llamar a Gemini
tarda más que eso. Por eso el webhook confirma de inmediato y procesa en segundo plano —
si no, el cliente recibiría la misma respuesta siete veces.

**Deduplica por id de evento.** La entrega es *at-least-once*: el mismo mensaje puede
llegar dos veces. La base de datos garantiza que solo se responda una.

**Verifica la firma.** Cada webhook viene firmado con HMAC-SHA256 y el agente lo comprueba
antes de tocar el mensaje. Sin esa verificación, cualquiera que conozca tu URL podría
inyectarle mensajes a tu agente. Ojo: la comprobación necesita que hayas cargado
`ZERNIO_WEBHOOK_SECRET` (o `META_APP_SECRET`). Si lo dejas vacío el agente arranca igual
—para que puedas probar sin trabarte— pero avisa en los logs y deja pasar todo. Antes de
poner el agente a atender clientes de verdad, cárgalo.

**Además:** cada cliente tiene su propio historial. Si alguien te escribe hoy y vuelve
mañana, el agente recuerda la conversación anterior. Y nunca inventa información — si no
sabe algo, lo dice y ofrece pasar el contacto a una persona.

---

## Requisitos

**1. Python 3.11 o superior**
- Mac: `brew install python` o [python.org](https://python.org/downloads)
- Windows: [python.org](https://python.org/downloads) (marca "Add to PATH")
- Linux: `sudo apt install python3.11`
- Verifica: `python3 --version`

**2. Un asistente de codificación con IA**

Cualquiera que pueda leer y ejecutar comandos sobre el repo sirve. Por ejemplo
[Devin CLI](https://devin.ai) — ver <a href="guia.md">guia.md</a> para el detalle —
o Claude Code, si prefieres seguir usándolo.

**3. API key de Google Gemini (gratis)**
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) → inicia sesión con tu
cuenta de Google → "Create API key". No pide tarjeta de crédito.

**4. Una cuenta de WhatsApp API**
[Zernio](https://zernio.com) (recomendado) o
[Meta Cloud API](https://developers.facebook.com).

---

## Cuánto cuesta

AgentKit es gratis y open source. Lo que pagas es el uso, y conviene verlo con números
reales en vez de un "es súper barato".

| Concepto | Costo real |
|---|---|
| AgentKit | Gratis, MIT |
| Zernio | Las primeras 2 cuentas conectadas son gratis, sin tarjeta. Si conectas tu propio número de WhatsApp Business, ahí termina el costo. Si necesitas que Zernio te dé un número, son entre $3 y $21 al mes según el país |
| Meta Cloud API | Las conversaciones que abre el cliente son gratis. Solo pagas las que inicias tú con plantilla |
| Gemini API | **Gratis** en la capa Free de Google AI Studio. Ver el detalle de límites abajo |
| Railway | Ya no hay plan gratuito de verdad: arrancas con $5 de crédito de prueba y después el plan Hobby son $5 al mes |

### Elegir el modelo de Gemini

Se cambia con la variable `GEMINI_MODEL`, sin tocar código.

| Modelo | ID | Costo | Cuándo usarlo |
|---|---|---|---|
| Gemini 2.5 Pro | `gemini-2.5-pro` | De pago (sin capa gratuita) | Razonar sobre catálogos, agendas o reglas muy complejas |
| Gemini 2.5 Flash | `gemini-2.5-flash` | Gratis, límites más bajos | Si `flash-lite` no alcanza en calidad |
| **Gemini 2.5 Flash-Lite** | `gemini-2.5-flash-lite` | **Default. Gratis**, sin tarjeta | El balance correcto para atención a clientes |

**La capa gratuita tiene límites, no es ilimitada.** Google limita las peticiones por
minuto (RPM) y por día (RPD) según el modelo — se ven en tu proyecto de
[Google AI Studio](https://aistudio.google.com). Si tu agente recibe mucho volumen y
empiezas a ver errores `429 RESOURCE_EXHAUSTED`, las opciones son esperar a que se
reponga la cuota, o activar la facturación en el proyecto para pasar a un tier pagado
(Flash-Lite sigue siendo muy barato: $0.10 / $0.40 por millón de tokens de entrada/salida).

A diferencia de Claude o GPT, aquí no hace falta calcular cuánto vas a gastar por
conversación: mientras te mantengas dentro de los límites gratuitos, el costo de IA
es $0.

---

## Casos de uso

| Negocio | Qué hace el agente | Ejemplo |
|---|---|---|
| **Restaurante** | Menú, horarios, ubicación | "El platillo del día es..." |
| **Clínica / salón** | Agenda citas y reservaciones | "Tu cita quedó el martes a las 3pm" |
| **Inmobiliaria** | Califica leads y manda info | "Tenemos 3 departamentos en tu rango..." |
| **Tienda online** | Toma pedidos por WhatsApp | "Tu pedido de 2 pasteles quedó confirmado" |
| **SaaS / software** | Soporte post-venta | "Para resetear tu contraseña, sigue estos pasos..." |
| **Cualquier negocio** | Preguntas frecuentes 24/7 | "Nuestro horario es..." |

**Qué hace y qué no, para que no haya sorpresas.** El agente conversa: entiende, responde
con la información de tu negocio, toma los datos y te los deja en el historial. Lo que
todavía no hace solo es *ejecutar* la acción del otro lado — escribir en tu calendario,
descontar stock, cobrar. `agent/tools.py` es el lugar donde va esa parte, y las funciones
quedan listas para conectar; pedírselo a tu asistente (Devin, etc.) es el siguiente paso,
no algo que salga andando de la caja.


---

## Comandos útiles

```bash
# Probar el agente sin WhatsApp (chat en terminal)
python tests/test_local.py

# Arrancar el servidor localmente
uvicorn agent.main:app --reload --port 8000

# Build Docker para producción
docker compose up --build

# Ver logs del agente
docker compose logs -f agent

# Auditar este repo (los 6 chequeos del sistema)
python3 scripts/audit.py
```

---

## Personalizarlo después

No necesitas tocar código. Abre tu asistente (Devin, etc.) en la carpeta del proyecto y
pídele cambios en lenguaje natural:

```
"El agente está muy formal. Hazlo más amigable y casual."
"Agregamos servicio de delivery. Actualiza el agente."
"Quiero que pueda consultar disponibilidad de citas."
"Quiero migrar de Zernio a Meta Cloud API."
```

---

## Stack técnico

| Componente | Tecnología | Para qué sirve |
|---|---|---|
| IA | Google Gemini (`gemini-2.5-flash-lite` por default, gratis) | Genera las respuestas |
| Servidor | FastAPI + Uvicorn | Recibe los webhooks de WhatsApp |
| WhatsApp | Zernio / Meta Cloud API | Conecta con WhatsApp — tú eliges |
| Base de datos | SQLite local / PostgreSQL en producción | Historial y deduplicación |
| Deploy | Docker + Railway | Pone tu agente en internet |
| Config | python-dotenv + YAML | API keys y configuración |

El sistema usa un **patrón adaptador** para los proveedores: cada uno implementa la misma
interfaz, así que `main.py` no sabe ni le importa cuál estás usando. Solo llama
`proveedor.verificar_firma()`, `proveedor.parsear_webhook()` y `proveedor.enviar_mensaje()`.

---

## Preguntas frecuentes

**¿Necesito saber programar?**
No. Tu asistente de IA escribe todo el código. Tú respondes preguntas sobre tu negocio.

**¿Puedo usarlo con mi negocio real?**
Sí. Después de probarlo localmente lo subes a Railway y queda atendiendo de verdad.

**¿Y si el agente no sabe algo?**
Responde algo como *"No tengo esa información, déjame conectarte con alguien del equipo."*
Nunca inventa datos.

**¿Puedo tener varios agentes?**
Sí. Clona el repo una vez por negocio. Cada agente es independiente.

**¿Puedo cambiar de proveedor de WhatsApp después?**
Sí. Abre tu asistente y dile qué quieres cambiar. Regenera los archivos necesarios.

**¿El agente puede escribirle primero a un cliente?**
No de entrada, y no es una limitación de AgentKit: WhatsApp solo permite texto libre
dentro de las 24 horas posteriores al último mensaje del cliente. Fuera de esa ventana
hace falta una plantilla aprobada por Meta. Como el agente siempre responde a alguien que
acaba de escribir, en la práctica nunca es un problema.

**¿Qué pasa con mis datos?**
Todo corre en tu infraestructura: tu servidor, tu base de datos, tus API keys. AgentKit
no tiene backend ni telemetría.

---

## Contribuir

Los issues y pull requests son bienvenidos. Antes de abrir un PR, corre la auditoría:

```bash
python3 scripts/audit.py
```

Verifica que el código de las plantillas compile, que el YAML parsee, que las variables de
entorno estén documentadas y que los links del README respondan.

---

## Créditos

Creado por **Todo de IA** — [@soyenriquerocha](https://instagram.com/soyenriquerocha)

Construido para builders de LATAM. Funciona con [Devin](https://devin.ai), Claude Code
o cualquier asistente de codificación con IA capaz de leer este repo.

---

## Licencia

MIT — Usa este proyecto como quieras, para lo que quieras.

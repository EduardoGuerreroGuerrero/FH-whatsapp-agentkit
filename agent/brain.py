# agent/brain.py — Cerebro del agente: conexion con Gemini
# Generado por AgentKit

"""
Logica de IA del agente. Lee el system prompt de config/prompts.yaml y genera las
respuestas con la API gratuita de Google Gemini (google-genai).
"""

import logging
import os
import re
import unicodedata

import httpx
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from agent.horario import es_antes_de_abrir, esta_abierto

load_dotenv()
logger = logging.getLogger("agentkit")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODELO = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS") or "1024")

# En los modelos Gemini 3.x el razonamiento interno consume el mismo cupo que la respuesta.
# Con un tope bajo el modelo se queda sin espacio pensando y devuelve texto vacio, y el
# cliente termina recibiendo "no entendi tu mensaje". Bajar el esfuerzo de razonamiento
# deja el cupo para el texto que se ve.
#
# Ojo: en gemini-3.5-flash-lite `thinking_budget=0` no existe (devuelve 400), el campo que
# funciona es `thinking_level`. Como no todas las versiones del SDK ni todos los modelos lo
# aceptan, se detecta en caliente y se recuerda la respuesta.
NIVEL_RAZONAMIENTO = os.getenv("GEMINI_THINKING_LEVEL") or "low"
_razonamiento_soportado: bool | None = None

# Respaldo: si Gemini agota su cuota gratuita (429), se reintenta con OpenRouter.
# OPENROUTER_API_KEY es opcional; si no esta configurada, el respaldo simplemente no se usa.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or ""
# "openrouter/free" es un router que elige automaticamente entre TODOS los modelos
# gratuitos disponibles en ese momento. Se prefiere sobre fijar un modelo especifico
# porque los modelos ":free" individuales suelen saturarse (rate-limit compartido) y
# van cambiando con el tiempo; el router siempre encuentra alguno disponible.
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL") or "openrouter/free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def cargar_config_prompts() -> dict:
    """Lee toda la configuracion desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    """El system prompt: quien es el agente y que sabe del negocio."""
    return cargar_config_prompts().get(
        "system_prompt", "Eres un asistente util. Responde siempre en espanol."
    )


def obtener_mensaje_error() -> str:
    """Que decirle al cliente cuando algo falla de nuestro lado."""
    return cargar_config_prompts().get(
        "error_message",
        "Lo siento, estoy teniendo problemas tecnicos. Por favor intenta de nuevo en unos minutos.",
    )


def obtener_mensaje_tipo_no_soportado() -> str:
    """Que decirle al cliente que manda audio, foto o cualquier cosa que no sea texto."""
    return cargar_config_prompts().get(
        "unsupported_type_message",
        "Por ahora solo puedo leer mensajes de texto. Escribeme lo que necesitas y con gusto "
        "te ayudo. Mira nuestro menu en www.fruppyhelados.com",
    )


def obtener_mensaje_fallback() -> str:
    """Que decirle al cliente cuando no se entendio el mensaje."""
    return cargar_config_prompts().get(
        "fallback_message", "Disculpa, no entendi tu mensaje. Podrias reformularlo?"
    )


def obtener_mensaje_saludo() -> str:
    """Saludo fijo para la primera interaccion o cualquier saludo del cliente."""
    return cargar_config_prompts().get(
        "greeting_message",
        "¡Hola! 🍦 Bienvenido a Fruppy Helados. Mira nuestro menu: www.fruppyhelados.com. ¿Que te provoca pedir hoy? 🍓✨",
    )


def obtener_mensaje_fuera_de_tema() -> str:
    """Frase exacta cuando el cliente pregunta algo ajeno a la heladeria."""
    return cargar_config_prompts().get(
        "off_topic_message",
        "Ese tema no esta dentro de lo que te puedo ayudar en Fruppy Helados. Solo te respondo cosas de la heladeria. Mira nuestro menu en www.fruppyhelados.com 🍦",
    )


def obtener_mensaje_fuera_de_horario() -> str:
    """Frase fija cuando el negocio esta cerrado, segun sea antes de abrir o despues de cerrar."""
    config = cargar_config_prompts()
    if es_antes_de_abrir():
        return config.get(
            "closed_before_message",
            "¡Buenos dias! ☀️ Aun no abrimos. Nuestro horario es de 9am a 9pm. "
            "Desde las 9am te atendemos con todo gusto.",
        )
    return config.get(
        "closed_after_message",
        "Por ahora estamos cerrados 🌙 Nuestro horario es de 9am a 9pm todos los dias. "
        "Manana desde las 9am te atendemos con gusto.",
    )


def obtener_mensaje_numero_pago() -> str:
    """Frase exacta cuando el cliente pide el numero de Nequi o llave."""
    return cargar_config_prompts().get(
        "payment_number_message",
        "Nequi / llave: 3045686743. Cuando hagas el pago, confirmanos para que nuestro equipo revise la transaccion y te informe.",
    )


def obtener_mensaje_confirmacion_pago() -> str:
    """Frase exacta cuando el cliente confirma que ya pago Y ya dio sus datos de envio."""
    return cargar_config_prompts().get(
        "payment_confirmation_message",
        "¡Perfecto! 📱 Nuestro equipo revisara la transaccion y te informaremos cuanto antes. ¡Gracias por tu compra! ✨",
    )


def obtener_mensaje_solicitud_datos_envio() -> str:
    """Frase exacta para pedir nombre, direccion y telefono tras confirmar el pago.

    Sin estos datos el pedido no se puede despachar, asi que este paso es obligatorio
    antes de dar por cerrada la venta (ver obtener_mensaje_confirmacion_pago).
    """
    return cargar_config_prompts().get(
        "shipping_data_request_message",
        "¡Genial! 📦 Para poder enviarte tu pedido necesito estos datos:\n"
        "- Nombre completo\n- Direccion de entrega\n- Numero de telefono de contacto\n"
        "¿Me los compartes, por favor?",
    )


def obtener_mensaje_datos_envio_incompletos() -> str:
    """Frase exacta cuando el cliente responde a la solicitud de datos pero faltan cosas."""
    return cargar_config_prompts().get(
        "shipping_data_incomplete_message",
        "Me falta algun dato para poder despachar tu pedido 🙏 Por favor enviame: "
        "nombre completo, direccion de entrega y numero de telefono, todo junto.",
    )


_SALUDOS = {
    "hola",
    "buenas",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "buen dia",
    "que mas",
    "q mas",
    "que hubo",
    "q hubo",
    "saludos",
    "hey",
    "holi",
    "hello",
    "hola buenas",
    "hola buenos dias",
    "hola buenas tardes",
    "hola buenas noches",
}


_PATRONES_CONFIRMACION_PAGO = re.compile(
    r"\b(ya?\s*pague?|pago\s*(hecho|confirmado|realizado|listo)|ya\s*(transfiri|transferi|hice\s*el\s*pago|hice\s*la\s*transferencia|pague\s*por|transferi\s*por)|transferencia\s*(hecha|realizada)|ya\s*cancele|pago\s*cancele|pague\s*por\s*(nequi|llave))\b",
    re.IGNORECASE,
)


_PATRONES_NUMERO_PAGO = re.compile(
    r"\b(numero\s*de\s*nequi|nequi\s*numero|cual\s*es\s*(la\s*)?llave|dame\s*(el\s*)?nequi|dame\s*(la\s*)?llave|pago\s*por\s*nequi|pago\s*con\s*nequi|numero\s*(de\s*)?(pago|llave))\b",
    re.IGNORECASE,
)


def _normalizar(texto: str) -> str:
    """Quita acentos, pasa a minusculas y elimina signos de puntuacion y emojis decorativos."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", "", texto)
    return " ".join(texto.strip().lower().split())


def _es_saludo(mensaje: str) -> bool:
    """Detecta si el mensaje es solo un saludo, para responder con el saludo fijo."""
    limpio = _normalizar(mensaje)
    if not limpio:
        return False
    return limpio in _SALUDOS


def _es_confirmacion_pago(mensaje: str) -> bool:
    """Detecta frases tipo 'ya pague', 'pago hecho', etc."""
    return bool(_PATRONES_CONFIRMACION_PAGO.search(mensaje))


def _es_solicitud_numero_pago(mensaje: str) -> bool:
    """Detecta frases como 'numero de nequi', 'cual es la llave', etc."""
    return bool(_PATRONES_NUMERO_PAGO.search(mensaje))


_PATRON_TELEFONO_EN_TEXTO = re.compile(r"\d[\d\s\-]{5,}\d")


def _incluye_datos_de_envio(mensaje: str) -> bool:
    """
    Heuristica para aceptar los datos de envio (nombre, direccion, telefono): el mensaje
    debe traer al menos un numero de telefono (6+ digitos, permitiendo espacios/guiones) y
    una extension minima, para no confundir un "ok" o una pregunta cualquiera con los datos
    reales. No es perfecto, pero evita cerrar el pedido sin con que despacharlo.
    """
    return bool(_PATRON_TELEFONO_EN_TEXTO.search(mensaje)) and len(mensaje.strip()) >= 15


def _se_pidieron_datos_de_envio(historial: list[dict]) -> bool:
    """True si el ULTIMO mensaje del bot en la conversacion fue la solicitud de datos."""
    if not historial:
        return False
    ultimo = historial[-1]
    return ultimo["role"] == "assistant" and ultimo["content"].strip() == (
        obtener_mensaje_solicitud_datos_envio().strip()
    )


def _construir_config(system_instruction: str, max_tokens: int) -> types.GenerateContentConfig:
    """Arma la config de Gemini, con el razonamiento bajo si el SDK lo soporta."""
    parametros = {
        "system_instruction": system_instruction,
        "max_output_tokens": max_tokens,
    }
    if _razonamiento_soportado is not False:
        try:
            parametros["thinking_config"] = types.ThinkingConfig(
                thinking_level=NIVEL_RAZONAMIENTO
            )
        except Exception:  # noqa: BLE001
            # El SDK instalado no conoce thinking_level: se sigue sin el.
            pass
    return types.GenerateContentConfig(**parametros)


async def _llamar_modelo(contents: list, system_instruction: str, max_tokens: int):
    """
    Llama a Gemini y, si el modelo rechaza el thinking_level, reintenta una vez sin el.
    La decision se recuerda para no pagar el reintento en cada mensaje.
    """
    global _razonamiento_soportado

    try:
        respuesta = await client.aio.models.generate_content(
            model=MODELO,
            contents=contents,
            config=_construir_config(system_instruction, max_tokens),
        )
    except genai_errors.ClientError as e:
        rechazo_por_razonamiento = (
            _razonamiento_soportado is None
            and getattr(e, "code", None) == 400
            and "thinking" in str(e).lower()
        )
        if not rechazo_por_razonamiento:
            raise
        logger.warning(
            f"El modelo {MODELO} no acepta thinking_level; se sigue sin configurarlo"
        )
        _razonamiento_soportado = False
        respuesta = await client.aio.models.generate_content(
            model=MODELO,
            contents=contents,
            config=_construir_config(system_instruction, max_tokens),
        )

    if _razonamiento_soportado is None:
        _razonamiento_soportado = True
    return respuesta


def _se_corto_por_tokens(respuesta) -> bool:
    """True si el modelo se quedo sin cupo antes de terminar."""
    candidatos = getattr(respuesta, "candidates", None)
    if not candidatos:
        return False
    return str(getattr(candidatos[0], "finish_reason", "")).endswith("MAX_TOKENS")


def _recortar_a_fin_de_oracion(texto: str) -> str:
    """
    Corta el texto en el ultimo punto/signo de cierre/salto de linea para no dejar una
    palabra o frase a medias cuando no hay forma de conseguir la respuesta completa.
    Si no encuentra ningun cierre razonable (respuesta de una sola frase muy larga),
    devuelve el texto tal cual: es preferible una frase larga a una vacia.
    """
    texto = texto.rstrip()
    mejor_corte = -1
    for cierre in (".", "!", "?", "\n"):
        posicion = texto.rfind(cierre)
        if posicion > mejor_corte:
            mejor_corte = posicion
    # Solo vale la pena recortar si queda una porcion razonable del mensaje; si el corte
    # deja muy poco texto (p. ej. el modelo se corto en la primera frase), es mejor
    # mandar todo antes que una respuesta casi vacia.
    if mejor_corte >= 10:
        return texto[: mejor_corte + 1].strip()
    return texto


def _extraer_texto(respuesta) -> str:
    """
    Junta el texto de la respuesta de Gemini.
    """
    if not getattr(respuesta, "candidates", None):
        return ""
    partes = []
    for candidato in respuesta.candidates:
        contenido = getattr(candidato, "content", None)
        if not contenido or not contenido.parts:
            continue
        for parte in contenido.parts:
            if getattr(parte, "text", None):
                partes.append(parte.text)
    return "\n".join(p for p in partes if p).strip()


async def _es_sobre_negocio(mensaje: str, historial: list[dict]) -> bool:
    """
    Clasificador rapido SI/NO. Pregunta a Gemini si la consulta es del negocio.
    Devuelve True a menos que el modelo responda rotundamente NO.
    """
    try:
        lineas = []
        for m in historial[-6:]:
            quien = "Cliente" if m["role"] == "user" else "Fruppy"
            lineas.append(f"{quien}: {m['content']}")
        lineas.append(f"Cliente: {mensaje}")
        prompt = (
            "Responde UNICAMENTE 'SI' o 'NO'. No justifiques. "
            "¿La ULTIMA consulta del cliente esta relacionada con Fruppy Helados "
            "(heladeria/fruteria de Barranquilla), su menu, precios, productos, "
            "pedidos, horario, ubicacion, delivery, metodos de pago o redes sociales?\n\n"
            + "\n".join(lineas)
            + "\n\nRespuesta (SI o NO):"
        )
        respuesta = await _llamar_modelo(
            [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            "Eres un clasificador estricto. Responde SI o NO.",
            24,
        )
        texto = _extraer_texto(respuesta).upper().strip().rstrip(".")
        return not ("NO" in texto and "SI" not in texto)
    except Exception as e:
        logger.warning(f"No se pudo clasificar la pregunta, se asume que es del negocio: {e}")
        return True


async def _generar_respuesta_openrouter(mensaje: str, historial: list[dict]) -> str | None:
    """
    Respaldo cuando Gemini no puede responder (p. ej. cuota agotada). Usa OpenRouter,
    que expone una API compatible con OpenAI. Devuelve None si tambien falla.
    """
    if not OPENROUTER_API_KEY:
        return None

    mensajes = [{"role": "system", "content": cargar_system_prompt()}]
    mensajes += [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    try:
        async with httpx.AsyncClient(timeout=30.0) as cliente:
            r = await cliente.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": OPENROUTER_MODEL,
                    "messages": mensajes,
                    "max_tokens": MAX_TOKENS,
                },
            )
    except httpx.HTTPError as e:
        logger.error(f"Error de red hablando con OpenRouter (respaldo): {e}")
        return None

    if r.status_code != 200:
        logger.error(f"OpenRouter (respaldo) respondio [{r.status_code}]: {r.text[:500]}")
        return None

    datos = r.json()
    texto = (
        datos.get("choices", [{}])[0].get("message", {}).get("content", "")
    ).strip()
    if not texto:
        logger.warning("OpenRouter (respaldo) devolvio una respuesta sin texto")
        return None

    logger.info(f"Respuesta generada con OpenRouter ({OPENROUTER_MODEL}) como respaldo de Gemini")
    return texto


async def generar_respuesta(mensaje: str, historial: list[dict]) -> tuple[str, bool]:
    """
    Genera una respuesta con Gemini.

    Returns:
        (texto, es_respuesta_real)
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback(), False

    # 1. Saludos: respuesta fija exacta, sin gastar llamada al LLM.
    if _es_saludo(mensaje):
        return obtener_mensaje_saludo(), True

    # 2. Datos de envio pendientes: si el ultimo mensaje del bot fue pedir nombre,
    #    direccion y telefono, este mensaje del cliente deberia traerlos. Va antes que la
    #    deteccion de "ya pague" porque el cliente puede repetir esa frase al responder
    #    (p. ej. "ya pague, mis datos son..."). Sin esto el pedido queda sin como despacharse.
    if _se_pidieron_datos_de_envio(historial):
        if _incluye_datos_de_envio(mensaje):
            logger.info(f"Datos de envio recibidos, se cierra la venta: {mensaje}")
            return obtener_mensaje_confirmacion_pago(), True
        return obtener_mensaje_datos_envio_incompletos(), True

    # 3. Pago: confirmacion de pago pide primero los datos de envio (nombre, direccion,
    #    telefono); la venta solo se da por cerrada cuando el cliente los entrega (paso 2).
    if _es_confirmacion_pago(mensaje):
        return obtener_mensaje_solicitud_datos_envio(), True
    if _es_solicitud_numero_pago(mensaje):
        return obtener_mensaje_numero_pago(), True

    # 4. Fuera del horario de atencion no se llama al modelo: el ni sabe que hora es y
    #    terminaba aceptando pedidos a medianoche. Va despues de los avisos de pago para
    #    no dejar colgado a quien pago justo antes de cerrar.
    if not esta_abierto():
        logger.info("Mensaje recibido fuera del horario de atencion; no se llama al modelo")
        return obtener_mensaje_fuera_de_horario(), False

    # 5. Verificar que la consulta sea del negocio. Si no, frase de rechazo exacta.
    if not await _es_sobre_negocio(mensaje, historial):
        return obtener_mensaje_fuera_de_tema(), True

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in historial
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=mensaje)]))

    system_prompt = cargar_system_prompt()

    try:
        respuesta = await _llamar_modelo(contents, system_prompt, MAX_TOKENS)
    except genai_errors.ClientError as e:
        if getattr(e, "code", None) == 429:
            logger.error(f"Limite de la capa gratuita de Gemini alcanzado: {e}")
        else:
            logger.error(f"Error llamando a Gemini: {e}")
        texto_respaldo = await _generar_respuesta_openrouter(mensaje, historial)
        if texto_respaldo:
            return texto_respaldo, True
        return obtener_mensaje_error(), False
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error llamando a Gemini: {e}")
        texto_respaldo = await _generar_respuesta_openrouter(mensaje, historial)
        if texto_respaldo:
            return texto_respaldo, True
        return obtener_mensaje_error(), False

    texto = _extraer_texto(respuesta)

    if _se_corto_por_tokens(respuesta):
        # Se quedo sin cupo antes de terminar (normalmente por el razonamiento interno que
        # consume el mismo presupuesto que el texto visible). Esto pasa tanto si no alcanzo
        # a escribir nada como si escribio una frase o hasta una palabra a la mitad — el
        # segundo caso es el que los clientes reportaron como "respuestas cortadas". En
        # ambos vale la pena un intento mas con el doble de espacio antes de conformarse.
        logger.warning(
            f"La respuesta se corto en {MAX_TOKENS} tokens "
            f"({'sin texto' if not texto else 'texto incompleto: ' + texto[-60:]!r}); "
            f"se reintenta con {MAX_TOKENS * 2}"
        )
        try:
            respuesta_reintento = await _llamar_modelo(contents, system_prompt, MAX_TOKENS * 2)
            texto_reintento = _extraer_texto(respuesta_reintento)
            # Solo se reemplaza si el reintento realmente mejoro las cosas: termino
            # completo, o al menos trajo mas texto que el intento original.
            if texto_reintento and (
                not _se_corto_por_tokens(respuesta_reintento)
                or len(texto_reintento) > len(texto)
            ):
                respuesta, texto = respuesta_reintento, texto_reintento
        except Exception as e:  # noqa: BLE001
            logger.error(f"El reintento con mas tokens tambien fallo: {e}")

    if not texto:
        logger.warning("Gemini devolvio una respuesta sin texto")
        return obtener_mensaje_fallback(), False

    if _se_corto_por_tokens(respuesta):
        # Sigue cortada incluso despues del reintento. Mejor mandar una frase completa y
        # mas corta que una a medias con una palabra partida al final.
        texto_recortado = _recortar_a_fin_de_oracion(texto)
        logger.warning(
            "La respuesta sigue cortada tras el reintento; se recorta a la ultima frase "
            f"completa. Si pasa seguido, sube GEMINI_MAX_TOKENS o acorta el system prompt. "
            f"Original: {texto!r}"
        )
        texto = texto_recortado or texto

    uso = getattr(respuesta, "usage_metadata", None)
    entrada = getattr(uso, "prompt_token_count", "?") if uso else "?"
    salida = getattr(uso, "candidates_token_count", "?") if uso else "?"
    logger.info(f"Respuesta generada con {MODELO} ({entrada} in / {salida} out)")
    return texto, True

# agent/brain.py — Cerebro del agente: conexion con Gemini
# Generado por AgentKit

"""
Logica de IA del agente. Lee el system prompt de config/prompts.yaml y genera las
respuestas con la API gratuita de Google Gemini (google-genai).
"""

import logging
import os

import httpx
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

load_dotenv()
logger = logging.getLogger("agentkit")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODELO = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash-lite"
MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS") or "1024")

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


def obtener_mensaje_fallback() -> str:
    """Que decirle al cliente cuando no se entendio el mensaje."""
    return cargar_config_prompts().get(
        "fallback_message", "Disculpa, no entendi tu mensaje. Podrias reformularlo?"
    )


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

    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in historial
    ]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=mensaje)]))

    config = types.GenerateContentConfig(
        system_instruction=cargar_system_prompt(),
        max_output_tokens=MAX_TOKENS,
    )

    try:
        respuesta = await client.aio.models.generate_content(
            model=MODELO, contents=contents, config=config
        )
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

    candidato_0 = respuesta.candidates[0] if respuesta.candidates else None
    if candidato_0 is not None and getattr(candidato_0, "finish_reason", None) == "MAX_TOKENS":
        logger.warning(
            f"La respuesta se corto por llegar al tope de {MAX_TOKENS} tokens. "
            "Si pasa seguido, sube GEMINI_MAX_TOKENS o acorta el system prompt."
        )

    texto = _extraer_texto(respuesta)
    if not texto:
        logger.warning("Gemini devolvio una respuesta sin texto")
        return obtener_mensaje_fallback(), False

    uso = getattr(respuesta, "usage_metadata", None)
    entrada = getattr(uso, "prompt_token_count", "?") if uso else "?"
    salida = getattr(uso, "candidates_token_count", "?") if uso else "?"
    logger.info(f"Respuesta generada con {MODELO} ({entrada} in / {salida} out)")
    return texto, True

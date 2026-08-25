# agent/pedidos.py — Extraccion y notificacion de pedidos confirmados
# Generado por AgentKit

"""
Cuando la conversacion con el cliente ya tiene todo lo necesario para armar y despachar
un pedido (nombre, direccion, telefono, producto/cantidad y medio de pago), se le avisa
por WhatsApp al numero encargado de prepararlo (ver config/business.yaml -> pedidos.numero_preparador).

Import local de agent.brain dentro de las funciones (no arriba del archivo): brain.py
importa cosas de este modulo, e importarse mutuamente arriba rompe con ImportError.
"""

import json
import logging
import re

from agent.tools import cargar_info_negocio

logger = logging.getLogger("agentkit")

# Claves del pedido y como pedirlas cuando faltan.
CAMPOS_REQUERIDOS: dict[str, str] = {
    "pedido": "que producto(s) quieres y en que cantidad",
    "medio_pago": "como vas a pagar (efectivo o transferencia/Nequi)",
    "nombre": "tu nombre completo",
    "direccion": "la direccion de entrega",
    "telefono": "un numero de telefono de contacto",
}

_VALORES_VACIOS = {"", "null", "none", "no especificado", "no disponible", "n/a", "desconocido"}

_PROMPT_EXTRACCION = """Lee la conversacion entre un cliente y el negocio y extrae, si aparecen,
estos datos del pedido. Responde UNICAMENTE un JSON valido con exactamente estas 5 claves,
sin texto adicional, sin markdown, sin explicaciones:

{{
  "pedido": "productos y cantidades que pidio el cliente, o null si no se sabe",
  "medio_pago": "efectivo o transferencia/nequi, o null si no lo ha dicho",
  "nombre": "nombre completo del cliente, o null si no lo dio",
  "direccion": "direccion de entrega, o null si no la dio",
  "telefono": "numero de telefono de contacto, o null si no lo dio"
}}

Conversacion:
{conversacion}

Ultimo mensaje del cliente:
{mensaje}

JSON:"""


def _formatear_conversacion(historial: list[dict]) -> str:
    lineas = []
    for m in historial[-20:]:
        quien = "Cliente" if m["role"] == "user" else "Negocio"
        lineas.append(f"{quien}: {m['content']}")
    return "\n".join(lineas) if lineas else "(sin mensajes previos)"


def _parsear_json(texto: str) -> dict:
    """Extrae el primer objeto JSON del texto, tolerando ```json fences o texto alrededor."""
    texto = texto.strip()
    texto = re.sub(r"^```(json)?", "", texto).strip()
    texto = re.sub(r"```$", "", texto).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio != -1 and fin != -1 and fin > inicio:
            try:
                return json.loads(texto[inicio : fin + 1])
            except json.JSONDecodeError:
                pass
    return {}


async def extraer_datos_pedido(mensaje: str, historial: list[dict]) -> dict:
    """
    Le pide a Gemini que lea la conversacion y devuelva los datos del pedido en JSON.
    Si algo falla (red, JSON invalido), devuelve {} y se trata como "todo falta" para no
    cerrar un pedido a medias por error.
    """
    from agent.brain import _extraer_texto, _llamar_modelo  # import local: ver docstring del modulo
    from google.genai import types

    prompt = _PROMPT_EXTRACCION.format(
        conversacion=_formatear_conversacion(historial), mensaje=mensaje
    )
    try:
        respuesta = await _llamar_modelo(
            [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            "Eres un extractor de datos. Respondes UNICAMENTE JSON valido, nada mas.",
            300,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo extraer los datos del pedido: {e}")
        return {}

    datos = _parsear_json(_extraer_texto(respuesta))
    if not datos:
        logger.warning(f"La extraccion de pedido no devolvio JSON valido: {_extraer_texto(respuesta)!r}")
    return datos


def campos_faltantes(pedido: dict) -> list[str]:
    """Claves de CAMPOS_REQUERIDOS que no vinieron (o vinieron vacias) en el pedido."""
    faltantes = []
    for clave in CAMPOS_REQUERIDOS:
        valor = pedido.get(clave)
        if valor is None or str(valor).strip().lower() in _VALORES_VACIOS:
            faltantes.append(clave)
    return faltantes


def mensaje_pidiendo_faltantes(faltantes: list[str]) -> str:
    """Arma el mensaje que le pide al cliente los datos que aun faltan."""
    from agent.brain import cargar_config_prompts  # import local: ver docstring del modulo

    intro = cargar_config_prompts().get(
        "missing_fields_intro",
        "¡Ya casi! Para completar tu pedido me falta que me compartas: {campos}. 🙌",
    )
    lista = ", ".join(CAMPOS_REQUERIDOS[c] for c in faltantes)
    return intro.format(campos=lista)


def _es_pago_por_transferencia(medio_pago: str | None) -> bool:
    medio_pago = (medio_pago or "").lower()
    return "transfer" in medio_pago or "nequi" in medio_pago


def construir_texto_notificacion(pedido: dict, telefono_cliente: str | None) -> str:
    """Arma el mensaje que recibe el numero encargado de preparar el pedido."""
    telefono = pedido.get("telefono") or telefono_cliente or "no informado"
    texto = (
        "🛒 Nuevo pedido confirmado\n\n"
        f"Cliente: {pedido.get('nombre', '?')}\n"
        f"Telefono: {telefono}\n"
        f"Direccion: {pedido.get('direccion', '?')}\n"
        f"Pedido: {pedido.get('pedido', '?')}\n"
        f"Medio de pago: {pedido.get('medio_pago', '?')}"
    )
    if _es_pago_por_transferencia(pedido.get("medio_pago")):
        texto += (
            "\n\n⚠️ Pago por transferencia — confirmar que el Nequi fue recibido antes de despachar."
        )
    return texto


def obtener_numero_preparador() -> str | None:
    """Numero de WhatsApp (E.164 sin '+') al que se avisan los pedidos confirmados."""
    info = cargar_info_negocio()
    numero = (info.get("pedidos", {}) or {}).get("numero_preparador")
    return numero.strip() if numero else None


def resumen_para_dedup(pedido: dict) -> str:
    """Representacion estable del pedido, para no notificar el mismo pedido dos veces."""
    return json.dumps(pedido, sort_keys=True, ensure_ascii=False)

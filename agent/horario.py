# agent/horario.py — Horario de atencion del negocio
# Generado por AgentKit

"""
Horario de atencion, resuelto de forma determinista.

El modelo no sabe que hora es: si el system prompt dice "atendemos de 9am a 9pm" y a las
22:30 alguien pregunta "puedo pedir?", Gemini contesta que si. Por eso el horario NO se
delega al modelo: se calcula aca y, si el negocio esta cerrado, se responde con una frase
fija sin llamar al LLM (cero tokens).

La configuracion vive en config/business.yaml, en negocio.atencion.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agent.tools import cargar_info_negocio

logger = logging.getLogger("agentkit")

ZONA_DEFAULT = "America/Bogota"
APERTURA_DEFAULT = 9 * 60
CIERRE_DEFAULT = 21 * 60


def _a_minutos(valor, default: int) -> int:
    """Convierte "09:00" (o 9) a minutos desde medianoche."""
    if isinstance(valor, int):
        return valor * 60
    if isinstance(valor, str) and ":" in valor:
        horas, _, minutos = valor.partition(":")
        try:
            return int(horas) * 60 + int(minutos)
        except ValueError:
            pass
    if valor is not None:
        logger.warning(f"Horario mal configurado en business.yaml: {valor!r}; se usa el default")
    return default


def _config() -> tuple[int, int, ZoneInfo]:
    """Lee zona horaria y horas de apertura/cierre desde config/business.yaml."""
    atencion = (cargar_info_negocio().get("negocio", {}) or {}).get("atencion", {}) or {}

    nombre_zona = atencion.get("zona_horaria") or ZONA_DEFAULT
    try:
        zona = ZoneInfo(nombre_zona)
    except (ZoneInfoNotFoundError, ValueError):
        logger.error(f"Zona horaria desconocida: {nombre_zona}; se usa {ZONA_DEFAULT}")
        zona = ZoneInfo(ZONA_DEFAULT)

    return (
        _a_minutos(atencion.get("abre"), APERTURA_DEFAULT),
        _a_minutos(atencion.get("cierra"), CIERRE_DEFAULT),
        zona,
    )


def ahora_local() -> datetime:
    """La hora actual en la zona horaria del negocio."""
    return datetime.now(_config()[2])


def esta_abierto(momento: datetime | None = None) -> bool:
    """True si el negocio esta atendiendo en este momento."""
    apertura, cierre, zona = _config()
    momento = momento.astimezone(zona) if momento else datetime.now(zona)
    minutos = momento.hour * 60 + momento.minute
    if apertura <= cierre:
        return apertura <= minutos < cierre
    # Horario que cruza la medianoche (p. ej. abre 18:00, cierra 02:00).
    return minutos >= apertura or minutos < cierre


def es_antes_de_abrir(momento: datetime | None = None) -> bool:
    """True si aun no abre hoy (madrugada), False si ya cerro."""
    apertura, cierre, zona = _config()
    momento = momento.astimezone(zona) if momento else datetime.now(zona)
    minutos = momento.hour * 60 + momento.minute
    if apertura <= cierre:
        return minutos < apertura
    return cierre <= minutos < apertura

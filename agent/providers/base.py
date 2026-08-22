# agent/providers/base.py — Clase base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define la interfaz comun que todos los proveedores de WhatsApp implementan.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from fastapi import Request


@dataclass
class MensajeEntrante:
    """Mensaje normalizado: el mismo formato sin importar el proveedor."""

    telefono: str
    texto: str
    mensaje_id: str
    es_propio: bool
    contexto: dict = field(default_factory=dict)


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Extrae y normaliza los mensajes del payload del webhook."""
        ...

    @abstractmethod
    async def enviar_mensaje(
        self, telefono: str, mensaje: str, contexto: dict | None = None
    ) -> bool:
        """Envia un mensaje de texto. Retorna True si salio bien."""
        ...

    async def verificar_firma(self, request: Request) -> bool:
        """Confirma que el webhook viene de verdad del proveedor."""
        return True

    async def validar_webhook(self, request: Request) -> str | None:
        """Verificacion GET del webhook. Solo Meta la usa."""
        return None

    async def verificar_conexion(self) -> tuple[bool, str]:
        """Chequea que las credenciales sirvan."""
        return True, "Este proveedor no expone un chequeo de conexion"

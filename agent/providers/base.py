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
    """
    Mensaje normalizado: el mismo formato sin importar el proveedor.

    Desde abril de 2026 Meta puede omitir el telefono del cliente y mandar solo un
    business-scoped user id (BSUID, formato "CO.1744031683476064"). Por eso el mensaje
    lleva las dos identidades por separado y una `identidad` canonica, que es la que se
    usa como llave del historial:

        identidad = bsuid si vino en el webhook, si no el telefono

    Para responder pasa al reves: se prefiere el telefono (Meta recomienda usarlo cuando
    se conoce, asi lo sigue incluyendo en los webhooks) y el BSUID queda de respaldo.
    """

    identidad: str
    texto: str
    mensaje_id: str
    es_propio: bool
    telefono: str | None = None
    bsuid: str | None = None
    # Tipo de mensaje del proveedor: "text", "audio", "image", etc. Los que no son texto
    # no se le pasan al modelo, pero tampoco se ignoran: el cliente merece una respuesta.
    tipo: str = "text"
    contexto: dict = field(default_factory=dict)


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Extrae y normaliza los mensajes del payload del webhook."""
        ...

    @abstractmethod
    async def enviar_mensaje(
        self, identidad: str, mensaje: str, contexto: dict | None = None
    ) -> bool:
        """
        Envia un mensaje de texto. Retorna True si salio bien.

        `identidad` es la llave canonica del cliente (solo para logs). El destinatario real
        sale de `contexto`, que trae "telefono" y/o "bsuid".
        """
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

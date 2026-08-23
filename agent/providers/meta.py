# agent/providers/meta.py — Adaptador para Meta WhatsApp Cloud API
# Generado por AgentKit

"""
Conexion directa contra la API oficial de Meta.
Documentacion: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import asyncio
import hashlib
import hmac
import logging
import os
import re

import httpx
from fastapi import Request

from agent.providers.base import MensajeEntrante, ProveedorWhatsApp

logger = logging.getLogger("agentkit")

# Un business-scoped user id (BSUID) es el codigo de pais ISO 3166 alpha-2, un punto y
# hasta 128 alfanumericos: "CO.1744031683476064". Los BSUID "padre" meten ENT en el medio:
# "CO.ENT.11815799212886844830".
_RE_BSUID = re.compile(r"^[A-Z]{2}\.(ENT\.)?[A-Za-z0-9]{1,128}$")

# Reintentos de envio: solo para fallos que se arreglan solos (red, 429, 5xx).
_ESPERAS_REINTENTO = (1.0, 3.0)

# Errores de Meta que conviene explicar en el log en vez de dejar el JSON crudo.
_ERRORES_CONOCIDOS = {
    131009: "el destinatario no tiene formato de telefono valido (¿se mando un BSUID en 'to'?)",
    131047: "fuera de la ventana de 24 horas: haria falta una plantilla aprobada",
    131026: "mensaje no entregable: el numero no tiene WhatsApp o no puede recibirlo",
    131062: "ese tipo de mensaje no se puede mandar a un BSUID",
    190: "el META_ACCESS_TOKEN vencio o fue revocado",
}


def es_bsuid(valor: str | None) -> bool:
    """True si el valor tiene forma de business-scoped user id y no de telefono."""
    return bool(valor) and bool(_RE_BSUID.match(valor))


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando la API oficial de Meta (Cloud API)."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN", "")
        self.phone_number_id = os.getenv("META_PHONE_NUMBER_ID", "")
        # Mismo cuidado que en zernio.py: una variable declarada pero vacia en el .env
        # devuelve "" y no el default, asi que se usa "or".
        self.verify_token = os.getenv("META_VERIFY_TOKEN") or "agentkit-verify"
        self.app_secret = os.getenv("META_APP_SECRET", "")
        self.api_version = os.getenv("META_API_VERSION") or "v25.0"

        if not self.access_token or not self.phone_number_id:
            logger.warning(
                "Faltan META_ACCESS_TOKEN o META_PHONE_NUMBER_ID: el agente no va a poder responder"
            )
        if not self.app_secret:
            logger.warning(
                "META_APP_SECRET no esta configurado: los webhooks NO se verifican. "
                "Sirve para probar, pero no lo dejes asi en produccion."
            )

    # ── Recibir ──────────────────────────────────────────────────────────

    async def validar_webhook(self, request: Request) -> str | None:
        """
        Meta hace un GET con hub.challenge la primera vez, para comprobar que la URL es tuya.
        Hay que devolver el challenge tal cual, como texto plano.
        """
        params = request.query_params
        if (
            params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == self.verify_token
        ):
            return params.get("hub.challenge") or ""
        return None

    async def verificar_firma(self, request: Request) -> bool:
        """Compara el header X-Hub-Signature-256 contra el HMAC-SHA256 del cuerpo crudo."""
        if not self.app_secret:
            return True  # modo pruebas, ya se advirtio al arrancar

        cabecera = request.headers.get("X-Hub-Signature-256", "")
        if not cabecera.startswith("sha256="):
            logger.warning("Llego un webhook sin firma X-Hub-Signature-256: rechazado")
            return False

        cuerpo = await request.body()
        firma_esperada = hmac.new(
            self.app_secret.encode("utf-8"), cuerpo, hashlib.sha256
        ).hexdigest()

        # Igual que en zernio.py: compare_digest sobre str exige ASCII puro y un header
        # con bytes raros tiraria TypeError, devolviendo 500 en vez de 401.
        try:
            iguales = hmac.compare_digest(firma_esperada, cabecera.removeprefix("sha256="))
        except TypeError:
            logger.warning("La firma del webhook trae caracteres invalidos: rechazado")
            return False

        if not iguales:
            logger.warning("Firma de webhook invalida: rechazado")
            return False
        return True

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Recorre el payload anidado de Meta Cloud API."""
        body = await request.json()
        mensajes: list[MensajeEntrante] = []

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value") or {}

                # Los webhooks de estado (sent/delivered/read/failed) no traen mensajes del
                # cliente, pero son la unica forma de enterarse de que Meta acepto un envio
                # y despues no lo entrego.
                self._registrar_estados(value)

                # El bloque "contacts" a veces trae el par telefono <-> BSUID completo
                # aunque el mensaje solo traiga uno de los dos.
                contactos = self._mapear_contactos(value)

                for msg in value.get("messages", []):
                    mensaje = self._parsear_mensaje(msg, contactos)
                    if mensaje is not None:
                        mensajes.append(mensaje)

        return mensajes

    def _mapear_contactos(self, value: dict) -> dict[str, str]:
        """Devuelve {bsuid: telefono} a partir del bloque "contacts" del webhook."""
        mapa: dict[str, str] = {}
        for contacto in value.get("contacts", []):
            bsuid = contacto.get("user_id")
            telefono = contacto.get("wa_id")
            if bsuid and telefono:
                mapa[bsuid] = telefono
        return mapa

    def _parsear_mensaje(self, msg: dict, contactos: dict[str, str]) -> MensajeEntrante | None:
        """Normaliza un mensaje entrante. Devuelve None si no hay forma de responderlo."""
        telefono = msg.get("from") or None
        bsuid = msg.get("from_user_id") or None

        # Defensa por si Meta empieza a mandar el BSUID dentro de "from": nunca hay que
        # meter un BSUID en el campo "to" al responder.
        if telefono and es_bsuid(telefono):
            bsuid = bsuid or telefono
            telefono = None

        if bsuid and not telefono:
            telefono = contactos.get(bsuid)

        identidad = bsuid or telefono
        if not identidad:
            # Sin ninguna identidad no hay a quien responder (mensajes de sistema, payloads
            # raros). Se descarta antes de gastar una llamada al modelo.
            logger.warning(f"Mensaje sin identidad de remitente, se descarta: {msg}")
            return None

        tipo = msg.get("type") or "text"
        texto = (msg.get("text") or {}).get("body", "") if tipo == "text" else ""

        return MensajeEntrante(
            identidad=identidad,
            texto=texto,
            mensaje_id=msg.get("id", ""),
            # Meta solo entrega mensajes entrantes por este canal
            es_propio=False,
            telefono=telefono,
            bsuid=bsuid,
            tipo=tipo,
            contexto={
                "evento_id": msg.get("id", ""),
                "telefono": telefono,
                "bsuid": bsuid,
            },
        )

    def _registrar_estados(self, value: dict) -> None:
        """
        Deja en el log los webhooks de estado de los mensajes que mandamos.

        Meta responde 200 al aceptar un envio, no al entregarlo. Sin esto, un mensaje que
        Meta acepta y despues descarta es invisible.
        """
        for estado in value.get("statuses", []):
            nombre = estado.get("status")
            destino = estado.get("recipient_id") or estado.get("recipient_user_id") or "?"
            mensaje_id = estado.get("id", "?")

            if nombre == "failed":
                for error in estado.get("errors", []) or [{}]:
                    codigo = error.get("code")
                    detalle = (
                        error.get("error_data", {}).get("details")
                        or error.get("title")
                        or error.get("message")
                        or "sin detalle"
                    )
                    pista = _ERRORES_CONOCIDOS.get(codigo)
                    logger.error(
                        f"Meta NO entrego el mensaje {mensaje_id} a {destino} "
                        f"[{codigo}]: {detalle}" + (f" — {pista}" if pista else "")
                    )
            else:
                logger.info(f"Estado del mensaje {mensaje_id} a {destino}: {nombre}")

    # ── Enviar ───────────────────────────────────────────────────────────

    async def enviar_mensaje(
        self, identidad: str, mensaje: str, contexto: dict | None = None
    ) -> bool:
        """
        Envia un mensaje de texto por la Cloud API.

        El destinatario sale del contexto: si se conoce el telefono va en "to", y si solo
        hay BSUID va en "recipient". No son intercambiables — un BSUID en "to" lo rechaza
        Meta con el error 131009.
        """
        if not self.access_token or not self.phone_number_id:
            logger.error("No se puede enviar: faltan META_ACCESS_TOKEN o META_PHONE_NUMBER_ID")
            return False

        contexto = contexto or {}
        telefono = contexto.get("telefono")
        bsuid = contexto.get("bsuid")

        # Si no vino contexto, la identidad misma dice de que tipo es.
        if not telefono and not bsuid:
            if es_bsuid(identidad):
                bsuid = identidad
            else:
                telefono = identidad

        cuerpo = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "type": "text",
            # preview_url=True: si el mensaje trae un link (p. ej. al menu en
            # fruppyhelados.com), WhatsApp muestra una tarjeta con miniatura en
            # vez de solo texto plano.
            "text": {"body": mensaje, "preview_url": True},
        }

        # Meta recomienda usar el telefono cuando se conoce: asi lo sigue incluyendo en los
        # webhooks siguientes. Nunca se mandan los dos campos: "to" tendria precedencia.
        if telefono and not es_bsuid(telefono):
            cuerpo["to"] = telefono
            destino = f"to={telefono}"
        elif bsuid:
            cuerpo["recipient"] = bsuid
            destino = f"recipient={bsuid}"
        else:
            logger.error(f"No se puede enviar a {identidad}: no hay telefono ni BSUID valido")
            return False

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        cabeceras = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        for intento in range(len(_ESPERAS_REINTENTO) + 1):
            try:
                async with httpx.AsyncClient(timeout=30.0) as cliente:
                    r = await cliente.post(url, json=cuerpo, headers=cabeceras)
            except httpx.HTTPError as e:
                if not await self._esperar_reintento(intento, f"error de red: {e}"):
                    logger.error(f"Error de red hablando con Meta ({destino}): {e}")
                    return False
                continue

            if r.status_code == 200:
                logger.info(f"Meta acepto el envio ({destino}, id={self._id_mensaje(r)})")
                return True

            self._loguear_error(r, destino)

            # Los 4xx no se arreglan reintentando: el 429 es la excepcion.
            reintentable = r.status_code >= 500 or r.status_code == 429
            if not reintentable or not await self._esperar_reintento(
                intento, f"Meta respondio {r.status_code}"
            ):
                return False

        return False

    async def _esperar_reintento(self, intento: int, motivo: str) -> bool:
        """Duerme antes del siguiente intento. False si ya no quedan intentos."""
        if intento >= len(_ESPERAS_REINTENTO):
            return False
        espera = _ESPERAS_REINTENTO[intento]
        logger.warning(f"Reintentando el envio en {espera}s ({motivo})")
        await asyncio.sleep(espera)
        return True

    @staticmethod
    def _id_mensaje(respuesta: httpx.Response) -> str:
        try:
            return (respuesta.json().get("messages") or [{}])[0].get("id", "?")
        except Exception:  # noqa: BLE001
            return "?"

    @staticmethod
    def _loguear_error(respuesta: httpx.Response, destino: str) -> None:
        """Deja el codigo y el detalle de Meta en el log, no el JSON crudo."""
        try:
            error = respuesta.json().get("error") or {}
        except Exception:  # noqa: BLE001
            error = {}

        codigo = error.get("code")
        detalle = (
            (error.get("error_data") or {}).get("details")
            or error.get("message")
            or respuesta.text[:300]
        )
        pista = _ERRORES_CONOCIDOS.get(codigo)
        traza = error.get("fbtrace_id", "?")
        logger.error(
            f"Meta rechazo el envio ({destino}) [HTTP {respuesta.status_code} / {codigo}]: "
            f"{detalle}" + (f" — {pista}" if pista else "") + f" (fbtrace_id={traza})"
        )

    # ── Diagnostico ──────────────────────────────────────────────────────

    async def verificar_conexion(self) -> tuple[bool, str]:
        """Lee el numero desde la Graph API para confirmar que el token sirve."""
        if not self.access_token or not self.phone_number_id:
            return False, "Faltan META_ACCESS_TOKEN o META_PHONE_NUMBER_ID"

        try:
            async with httpx.AsyncClient(timeout=15.0) as cliente:
                r = await cliente.get(
                    f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}",
                    params={"fields": "display_phone_number,verified_name,quality_rating"},
                    headers={"Authorization": f"Bearer {self.access_token}"},
                )
        except httpx.HTTPError as e:
            return False, f"No se pudo contactar a Meta: {e}"

        if r.status_code != 200:
            return False, f"Meta respondio {r.status_code}: {r.text[:200]}"

        datos = r.json()
        return True, (
            f"Numero {datos.get('display_phone_number', '?')} conectado "
            f"(calidad: {datos.get('quality_rating', '?')})"
        )

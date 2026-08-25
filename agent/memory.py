# agent/memory.py — Memoria de conversaciones
# Generado por AgentKit

"""
Guarda el historial de cada conversacion por identidad del cliente, y lleva registro de
que eventos de webhook ya se atendieron.

La identidad canonica es el BSUID de Meta cuando existe, y el telefono cuando no. Ver
`agent/providers/base.py` para el porque.

SQLite en local, PostgreSQL en produccion.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import DateTime, Integer, String, Text, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

load_dotenv()
logger = logging.getLogger("agentkit")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

if DATABASE_URL.startswith("sqlite") and os.getenv("ENVIRONMENT") == "production":
    logger.warning(
        "Estas en produccion con SQLite. El historial se va a borrar en cada redespliegue. "
        "Agrega PostgreSQL y configura DATABASE_URL para que el agente recuerde a sus clientes."
    )

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def ahora() -> datetime:
    """Hora actual en UTC, con zona horaria."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    """Un mensaje del historial de conversacion."""

    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # La columna se sigue llamando "telefono" por compatibilidad con los datos que ya
    # estan en produccion, pero guarda la IDENTIDAD canonica: el BSUID si existe.
    telefono: Mapped[str] = mapped_column(String(140), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Identidad(Base):
    """
    Par BSUID <-> telefono de un mismo cliente.

    Sirve para dos cosas: saber que ya se fusiono su historial, y dejar rastro de la
    correspondencia entre las dos identidades que usa Meta.
    """

    __tablename__ = "identidades"

    bsuid: Mapped[str] = mapped_column(String(140), primary_key=True)
    telefono: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class EventoProcesado(Base):
    """
    Eventos de webhook que ya se atendieron.
    """

    __tablename__ = "eventos_procesados"

    evento_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=ahora, index=True
    )


class PedidoNotificado(Base):
    """
    Ultimo pedido de cada cliente que ya se le avisamos al preparador.

    Evita reenviar el mismo pedido dos veces si el cliente repite el mensaje de cierre,
    pero permite avisar un pedido NUEVO/distinto del mismo cliente mas adelante (el
    resumen cambia).
    """

    __tablename__ = "pedidos_notificados"

    identidad: Mapped[str] = mapped_column(String(140), primary_key=True)
    resumen: Mapped[str] = mapped_column(Text)
    notificado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


async def inicializar_db():
    """Crea las tablas si no existen y ajusta las columnas que cambiaron de tamano."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # La columna "telefono" nacio como VARCHAR(50) y ahora tambien guarda BSUIDs, que
        # pueden llegar a 131 caracteres. create_all no modifica tablas existentes, asi que
        # el ensanche va aparte. SQLite ignora los limites de longitud, no hace falta.
        if DATABASE_URL.startswith("postgresql"):
            await conn.exec_driver_sql(
                "ALTER TABLE mensajes ALTER COLUMN telefono TYPE VARCHAR(140)"
            )


async def vincular_identidad(bsuid: str | None, telefono: str | None):
    """
    Registra que un BSUID y un telefono son el mismo cliente y fusiona su historial.

    La primera vez que Meta manda las dos identidades juntas, los mensajes que quedaron
    guardados bajo el telefono se pasan al BSUID. Asi el cliente no arranca de cero cuando
    Meta deja de enviar su numero. Es idempotente: la segunda vez no hace nada.
    """
    if not bsuid or not telefono:
        return

    async with async_session() as session:
        ya_vinculado = await session.get(Identidad, bsuid)
        if ya_vinculado is not None and ya_vinculado.telefono == telefono:
            return

        resultado = await session.execute(
            update(Mensaje).where(Mensaje.telefono == telefono).values(telefono=bsuid)
        )

        if ya_vinculado is None:
            session.add(Identidad(bsuid=bsuid, telefono=telefono, actualizado_en=ahora()))
        else:
            ya_vinculado.telefono = telefono
            ya_vinculado.actualizado_en = ahora()

        await session.commit()

    if resultado.rowcount:
        logger.info(
            f"Historial fusionado: {resultado.rowcount} mensajes de {telefono} "
            f"ahora estan bajo {bsuid}"
        )


async def marcar_evento_procesado(evento_id: str) -> bool:
    """
    Registra un evento. Retorna True si es nuevo, False si ya se habia procesado.
    """
    if not evento_id:
        return True

    async with async_session() as session:
        session.add(EventoProcesado(evento_id=evento_id, creado_en=ahora()))
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def liberar_evento(evento_id: str):
    """Borra la marca de un evento para que el reintento del proveedor SI se procese."""
    if not evento_id:
        return
    async with async_session() as session:
        await session.execute(delete(EventoProcesado).where(EventoProcesado.evento_id == evento_id))
        await session.commit()


async def limpiar_eventos_viejos(dias: int = 7):
    """Borra los eventos de hace mas de N dias."""
    limite = ahora() - timedelta(days=dias)
    async with async_session() as session:
        resultado = await session.execute(
            delete(EventoProcesado).where(EventoProcesado.creado_en < limite)
        )
        await session.commit()
    if resultado.rowcount:
        logger.info(f"Se limpiaron {resultado.rowcount} eventos de mas de {dias} dias")


async def pedido_ya_notificado(identidad: str, resumen: str) -> bool:
    """True si a este cliente ya se le noto este MISMO pedido al preparador."""
    async with async_session() as session:
        existente = await session.get(PedidoNotificado, identidad)
        return existente is not None and existente.resumen == resumen


async def marcar_pedido_notificado(identidad: str, resumen: str):
    """Registra (o actualiza) el ultimo pedido notificado de un cliente."""
    async with async_session() as session:
        existente = await session.get(PedidoNotificado, identidad)
        if existente is None:
            session.add(
                PedidoNotificado(identidad=identidad, resumen=resumen, notificado_en=ahora())
            )
        else:
            existente.resumen = resumen
            existente.notificado_en = ahora()
        await session.commit()


async def guardar_mensaje(identidad: str, role: str, content: str):
    """Guarda un mensaje en el historial de esa conversacion."""
    async with async_session() as session:
        session.add(Mensaje(telefono=identidad, role=role, content=content, timestamp=ahora()))
        await session.commit()


async def obtener_historial(identidad: str, limite: int = 20) -> list[dict]:
    """Devuelve los ultimos N mensajes de una conversacion, en orden cronologico."""
    async with async_session() as session:
        resultado = await session.execute(
            select(Mensaje)
            .where(Mensaje.telefono == identidad)
            .order_by(Mensaje.id.desc())
            .limit(limite)
        )
        mensajes = list(resultado.scalars().all())

    mensajes.reverse()

    while mensajes and mensajes[0].role != "user":
        mensajes.pop(0)

    return [{"role": m.role, "content": m.content} for m in mensajes]


async def limpiar_historial(identidad: str):
    """Borra todo el historial de una conversacion."""
    async with async_session() as session:
        await session.execute(delete(Mensaje).where(Mensaje.telefono == identidad))
        await session.commit()

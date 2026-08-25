# tests/test_pedidos.py — Pedido completo -> aviso al preparador (3002797970)
#
#   pytest tests/test_pedidos.py

import pytest


@pytest.fixture
def brain(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-de-prueba")
    import agent.brain

    return agent.brain


@pytest.fixture
def pedidos(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-de-prueba")
    import agent.pedidos

    return agent.pedidos


PEDIDO_COMPLETO_EFECTIVO = {
    "pedido": "1 banana split",
    "medio_pago": "efectivo",
    "nombre": "Juan Perez",
    "direccion": "Cra 21 #50-08",
    "telefono": "3001234567",
}

PEDIDO_COMPLETO_TRANSFERENCIA = {**PEDIDO_COMPLETO_EFECTIVO, "medio_pago": "transferencia"}


def test_campos_faltantes_detecta_huecos(pedidos):
    incompleto = {**PEDIDO_COMPLETO_EFECTIVO, "direccion": None, "telefono": ""}
    assert set(pedidos.campos_faltantes(incompleto)) == {"direccion", "telefono"}


def test_campos_faltantes_trata_null_como_vacio(pedidos):
    incompleto = {**PEDIDO_COMPLETO_EFECTIVO, "nombre": "null", "pedido": "No especificado"}
    assert set(pedidos.campos_faltantes(incompleto)) == {"nombre", "pedido"}


def test_campos_faltantes_vacio_si_todo_esta(pedidos):
    assert pedidos.campos_faltantes(PEDIDO_COMPLETO_EFECTIVO) == []


def test_construir_texto_notificacion_efectivo_sin_nota_extra(pedidos):
    texto = pedidos.construir_texto_notificacion(PEDIDO_COMPLETO_EFECTIVO, "3001234567")
    assert "Juan Perez" in texto
    assert "banana split" in texto
    assert "confirmar que el Nequi" not in texto


def test_construir_texto_notificacion_transferencia_agrega_nota(pedidos):
    texto = pedidos.construir_texto_notificacion(PEDIDO_COMPLETO_TRANSFERENCIA, "3001234567")
    assert "confirmar que el Nequi fue recibido" in texto


def test_resumen_para_dedup_es_estable(pedidos):
    a = pedidos.resumen_para_dedup(PEDIDO_COMPLETO_EFECTIVO)
    b = pedidos.resumen_para_dedup(dict(reversed(list(PEDIDO_COMPLETO_EFECTIVO.items()))))
    assert a == b


async def test_pedido_completo_dispara_notificacion_efectivo(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _completo(mensaje, historial):
        return PEDIDO_COMPLETO_EFECTIVO

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _completo)

    respuesta, es_real, pedido = await brain.generar_respuesta_completa(
        "pago en efectivo", []
    )

    assert es_real is True
    assert pedido == PEDIDO_COMPLETO_EFECTIVO
    assert "efectivo" not in respuesta.lower()  # confirmacion generica, no repite el medio de pago


async def test_pedido_completo_transferencia_usa_mensaje_de_transferencia(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _completo(mensaje, historial):
        return PEDIDO_COMPLETO_TRANSFERENCIA

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _completo)

    respuesta, es_real, pedido = await brain.generar_respuesta_completa("ya pague", [])

    assert es_real is True
    assert pedido == PEDIDO_COMPLETO_TRANSFERENCIA
    assert respuesta == brain.obtener_mensaje_confirmacion_pago()


async def test_pedido_incompleto_pide_lo_que_falta_y_no_notifica(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _incompleto(mensaje, historial):
        return {**PEDIDO_COMPLETO_EFECTIVO, "direccion": None, "telefono": None}

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _incompleto)

    respuesta, es_real, pedido = await brain.generar_respuesta_completa(
        "confirmo el pedido", []
    )

    assert es_real is True
    assert pedido is None
    assert "direccion" in respuesta.lower() or "dirección" in respuesta.lower()
    assert "telefono" in respuesta.lower() or "teléfono" in respuesta.lower()


async def test_dame_el_numero_de_nequi_no_entra_al_flujo_de_pedido(brain, monkeypatch):
    """'nequi' aparece en el mensaje, pero es solo una pregunta por el numero de pago."""
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _explotar(mensaje, historial):
        raise AssertionError("no deberia intentar extraer un pedido para esta pregunta")

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _explotar)

    respuesta, es_real, pedido = await brain.generar_respuesta_completa(
        "dame el numero de nequi", []
    )

    assert pedido is None
    assert "3045686743" in respuesta


async def test_memoria_dedup_no_repite_el_mismo_pedido(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'pedidos.db'}")
    import importlib

    import agent.memory as memory

    importlib.reload(memory)
    await memory.inicializar_db()

    resumen = '{"nombre": "Juan"}'
    assert await memory.pedido_ya_notificado("cliente-1", resumen) is False

    await memory.marcar_pedido_notificado("cliente-1", resumen)
    assert await memory.pedido_ya_notificado("cliente-1", resumen) is True

    otro_resumen = '{"nombre": "Otro"}'
    assert await memory.pedido_ya_notificado("cliente-1", otro_resumen) is False

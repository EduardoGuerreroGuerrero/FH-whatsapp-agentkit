# tests/test_pedidos.py — Pedido completo -> aviso al preparador (3045686743)
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
    "valor_producto": 15000,
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


def test_formatear_pesos_usa_puntos_como_separador(pedidos):
    assert pedidos.formatear_pesos(15000) == "$15.000"
    assert pedidos.formatear_pesos(1234567) == "$1.234.567"


def test_texto_valor_producto_usa_fallback_si_no_hay_valor(pedidos):
    assert pedidos.texto_valor_producto({}) == "el valor de tus productos"
    assert pedidos.texto_valor_producto({"valor_producto": None}) == "el valor de tus productos"
    assert pedidos.texto_valor_producto({"valor_producto": "no disponible"}) == "el valor de tus productos"


def test_texto_valor_producto_formatea_el_valor_calculado(pedidos):
    assert pedidos.texto_valor_producto({"valor_producto": 20000}) == "$20.000"
    assert pedidos.texto_valor_producto({"valor_producto": "20000"}) == "$20.000"


def test_resumen_para_dedup_es_estable(pedidos):
    a = pedidos.resumen_para_dedup(PEDIDO_COMPLETO_EFECTIVO)
    b = pedidos.resumen_para_dedup(dict(reversed(list(PEDIDO_COMPLETO_EFECTIVO.items()))))
    assert a == b


async def test_pedido_completo_primero_muestra_resumen_sin_notificar(brain, monkeypatch):
    """Al completar los 5 datos, se le pide confirmar el resumen; todavia NO se notifica."""
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _completo(mensaje, historial):
        return PEDIDO_COMPLETO_EFECTIVO

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _completo)

    respuesta, es_real, pedido = await brain.generar_respuesta_completa(
        "pago en efectivo", []
    )

    assert es_real is True
    assert pedido is None  # no se notifica hasta que el cliente confirme
    assert "Juan Perez" in respuesta
    assert "banana split" in respuesta
    assert "confirmas" in respuesta.lower()


async def test_cliente_confirma_el_resumen_dispara_notificacion_efectivo(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _completo(mensaje, historial):
        return PEDIDO_COMPLETO_EFECTIVO

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _completo)

    resumen = brain.obtener_mensaje_resumen_intro().format(detalle="(lo que sea)")
    historial = [{"role": "assistant", "content": resumen}]

    respuesta, es_real, pedido = await brain.generar_respuesta_completa("si, todo bien", historial)

    assert es_real is True
    assert pedido == PEDIDO_COMPLETO_EFECTIVO
    assert "Ya tengo todo tu pedido" in respuesta
    assert "$15.000" in respuesta
    assert "valor del domicilio" in respuesta.lower()


async def test_cliente_confirma_el_resumen_transferencia_usa_mensaje_de_transferencia(
    brain, monkeypatch
):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _completo(mensaje, historial):
        return PEDIDO_COMPLETO_TRANSFERENCIA

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _completo)

    resumen = brain.obtener_mensaje_resumen_intro().format(detalle="(lo que sea)")
    historial = [{"role": "assistant", "content": resumen}]

    respuesta, es_real, pedido = await brain.generar_respuesta_completa("confirmo", historial)

    assert es_real is True
    assert pedido == PEDIDO_COMPLETO_TRANSFERENCIA
    assert "Nuestro equipo revisara la transaccion" in respuesta
    assert "$15.000" in respuesta
    assert "valor del domicilio" in respuesta.lower()


async def test_cliente_rechaza_el_resumen_sin_decir_que_corregir(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    async def _explotar(mensaje, historial):
        raise AssertionError("no deberia re-extraer si el cliente no dijo que corregir")

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _explotar)

    resumen = brain.obtener_mensaje_resumen_intro().format(detalle="(lo que sea)")
    historial = [{"role": "assistant", "content": resumen}]

    respuesta, es_real, pedido = await brain.generar_respuesta_completa("no", historial)

    assert es_real is True
    assert pedido is None
    assert respuesta == brain.obtener_mensaje_pedir_correccion()


async def test_cliente_corrige_un_dato_muestra_resumen_actualizado(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)

    corregido = {**PEDIDO_COMPLETO_EFECTIVO, "direccion": "Calle nueva 123"}

    async def _corregido(mensaje, historial):
        return corregido

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _corregido)

    resumen = brain.obtener_mensaje_resumen_intro().format(detalle="(lo que sea)")
    historial = [{"role": "assistant", "content": resumen}]

    respuesta, es_real, pedido = await brain.generar_respuesta_completa(
        "no, mi direccion es Calle nueva 123", historial
    )

    assert es_real is True
    assert pedido is None  # se le vuelve a pedir confirmar, todavia no se notifica
    assert "Calle nueva 123" in respuesta
    assert "confirmas" in respuesta.lower()


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

# tests/test_horario.py — El agente no puede tomar pedidos con el local cerrado
#
# Bug real: el prompt decia "atendemos de 9am a 9pm", pero el modelo no sabe que hora es,
# asi que a las 22:00 respondia que si a un "puedo pedir?".
#
#   pytest tests/test_horario.py

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

BOGOTA = ZoneInfo("America/Bogota")


@pytest.fixture
def brain(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key-de-prueba")
    import agent.brain

    return agent.brain


def _a_las(hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 8, 23, hora, minuto, tzinfo=BOGOTA)


@pytest.mark.parametrize("hora,abierto", [(0, False), (8, False), (9, True), (20, True), (20, True), (21, False), (23, False)])
def test_ventana_de_atencion(hora, abierto):
    from agent.horario import esta_abierto

    assert esta_abierto(_a_las(hora)) is abierto


def test_los_bordes_son_exactos():
    from agent.horario import esta_abierto

    assert esta_abierto(_a_las(8, 59)) is False
    assert esta_abierto(_a_las(9, 0)) is True
    assert esta_abierto(_a_las(20, 59)) is True
    assert esta_abierto(_a_las(21, 0)) is False


def test_distingue_madrugada_de_noche():
    from agent.horario import es_antes_de_abrir

    assert es_antes_de_abrir(_a_las(3)) is True
    assert es_antes_de_abrir(_a_las(22)) is False


def test_la_hora_se_evalua_en_colombia_no_en_utc():
    """A las 02:00 UTC en Colombia son las 21:00 del dia anterior: cerrado."""
    from agent.horario import esta_abierto

    assert esta_abierto(datetime(2026, 8, 24, 2, 30, tzinfo=ZoneInfo("UTC"))) is False


async def test_fuera_de_horario_no_llama_al_modelo(brain, monkeypatch):
    """El corte tiene que ahorrar la llamada al LLM, no solo cambiar el texto."""

    async def explotar(*args, **kwargs):
        raise AssertionError("no se debe llamar a Gemini con el local cerrado")

    monkeypatch.setattr(brain, "_llamar_modelo", explotar)
    monkeypatch.setattr(brain, "esta_abierto", lambda: False)
    monkeypatch.setattr(brain, "es_antes_de_abrir", lambda: False)

    respuesta, es_real = await brain.generar_respuesta("puedo pedir?", [])

    assert "cerrado" in respuesta.lower()
    assert es_real is False


async def test_dentro_de_horario_si_llama_al_modelo(brain, monkeypatch):
    monkeypatch.setattr(brain, "esta_abierto", lambda: True)
    monkeypatch.setattr(brain, "_es_sobre_negocio", _si)
    monkeypatch.setattr(brain, "_llamar_modelo", _responder_claro)

    respuesta, es_real = await brain.generar_respuesta("puedo pedir?", [])

    assert respuesta == "¡Claro! ¿Que te provoca?"
    assert es_real is True


async def test_confirmacion_de_pago_se_responde_aunque_este_cerrado(brain, monkeypatch):
    """Alguien que pago a las 20:58 no merece un "estamos cerrados" a las 21:01."""
    monkeypatch.setattr(brain, "esta_abierto", lambda: False)

    async def _sin_datos(mensaje, historial):
        return {}

    monkeypatch.setattr("agent.pedidos.extraer_datos_pedido", _sin_datos)

    respuesta, es_real = await brain.generar_respuesta("ya pague", [])

    assert "cerrado" not in respuesta.lower()
    assert es_real is True


async def _si(mensaje, historial):
    return True


async def _responder_claro(contents, system_instruction, max_tokens):
    class _Parte:
        text = "¡Claro! ¿Que te provoca?"

    class _Contenido:
        parts = [_Parte()]

    class _Candidato:
        content = _Contenido()
        finish_reason = "STOP"

    class _Respuesta:
        candidates = [_Candidato()]
        usage_metadata = None

    return _Respuesta()

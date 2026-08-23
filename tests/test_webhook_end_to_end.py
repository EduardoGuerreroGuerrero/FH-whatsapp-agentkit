# tests/test_webhook_end_to_end.py — El recorrido completo de un mensaje
#
# Reproduce el bug real: un cliente escribe desde un numero que Meta ya no identifica con
# telefono, y el agente tiene que responderle igual.
#
#   pip install -r requirements.txt -r requirements-dev.txt
#   pytest

import importlib
import os

import pytest
from fastapi.testclient import TestClient

BSUID = "CO.1744031683476064"
TELEFONO = "573002797970"


@pytest.fixture
def app_agente(monkeypatch, tmp_path):
    """Levanta la app con un proveedor Meta apuntando a credenciales de mentira."""
    monkeypatch.setenv("WHATSAPP_PROVIDER", "meta")
    monkeypatch.setenv("META_ACCESS_TOKEN", "token-de-prueba")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "1342434335611320")
    monkeypatch.setenv("META_APP_SECRET", "")
    monkeypatch.setenv("GEMINI_API_KEY", "key-de-prueba")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'e2e.db'}")
    monkeypatch.setenv("ENVIRONMENT", "test")
    os.environ.pop("GEMINI_MAX_TOKENS", None)

    import agent.memory
    import agent.main

    importlib.reload(agent.memory)
    main = importlib.reload(agent.main)

    enviados: list[tuple[str, str, dict]] = []

    async def enviar_falso(identidad, mensaje, contexto=None):
        enviados.append((identidad, mensaje, contexto or {}))
        return True

    async def responder_falso(mensaje, historial):
        return f"respuesta a: {mensaje}", True

    monkeypatch.setattr(main.proveedor, "enviar_mensaje", enviar_falso)
    monkeypatch.setattr(main, "generar_respuesta", responder_falso)
    # El chequeo de conexion del arranque hablaria con la Graph API de verdad.
    monkeypatch.setattr(main.proveedor, "verificar_conexion", lambda: _ok())

    return main, enviados


async def _ok():
    return True, "conexion simulada"


def _payload(mensaje: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1665775721443658",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "1342434335611320"},
                            "messages": [mensaje],
                        },
                    }
                ],
            }
        ],
    }


def test_cliente_sin_telefono_recibe_respuesta(app_agente):
    """
    El bug original. Este payload salio tal cual de los logs de produccion y terminaba en
    "Mensaje sin 'from', se descarta": el cliente nunca recibia nada.
    """
    main, enviados = app_agente

    with TestClient(main.app) as cliente:
        r = cliente.post(
            "/webhook",
            json=_payload(
                {
                    "from_user_id": BSUID,
                    "id": "wamid.e2e.1",
                    "timestamp": "1787496577",
                    "type": "text",
                    "text": {"body": "Buenas"},
                }
            ),
        )

    assert r.status_code == 200
    assert r.json()["encolados"] == 1

    assert len(enviados) == 1
    identidad, respuesta, contexto = enviados[0]
    assert identidad == BSUID
    assert respuesta == "respuesta a: Buenas"
    assert contexto["bsuid"] == BSUID


def test_cliente_con_telefono_sigue_funcionando(app_agente):
    main, enviados = app_agente

    with TestClient(main.app) as cliente:
        cliente.post(
            "/webhook",
            json=_payload(
                {"from": TELEFONO, "id": "wamid.e2e.2", "type": "text", "text": {"body": "Hola"}}
            ),
        )

    assert enviados[0][0] == TELEFONO
    assert enviados[0][2]["telefono"] == TELEFONO


def test_nota_de_voz_recibe_aviso_en_vez_de_silencio(app_agente):
    main, enviados = app_agente

    with TestClient(main.app) as cliente:
        cliente.post(
            "/webhook",
            json=_payload(
                {
                    "from_user_id": BSUID,
                    "id": "wamid.e2e.3",
                    "type": "audio",
                    "audio": {"id": "media-1"},
                }
            ),
        )

    assert len(enviados) == 1
    assert "texto" in enviados[0][1].lower()


def test_evento_repetido_no_responde_dos_veces(app_agente):
    """Meta reintenta los webhooks; el cliente no debe recibir la respuesta duplicada."""
    main, enviados = app_agente
    payload = _payload(
        {"from_user_id": BSUID, "id": "wamid.e2e.4", "type": "text", "text": {"body": "Hola"}}
    )

    with TestClient(main.app) as cliente:
        cliente.post("/webhook", json=payload)
        cliente.post("/webhook", json=payload)

    assert len(enviados) == 1


def test_historial_se_guarda_bajo_el_bsuid(app_agente):
    main, enviados = app_agente

    with TestClient(main.app) as cliente:
        cliente.post(
            "/webhook",
            json=_payload(
                {
                    "from": TELEFONO,
                    "from_user_id": BSUID,
                    "id": "wamid.e2e.5",
                    "type": "text",
                    "text": {"body": "Quiero un helado"},
                }
            ),
        )

    import asyncio

    import agent.memory as memory

    historial = asyncio.run(memory.obtener_historial(BSUID))
    assert [m["content"] for m in historial] == [
        "Quiero un helado",
        "respuesta a: Quiero un helado",
    ]

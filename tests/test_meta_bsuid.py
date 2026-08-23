# tests/test_meta_bsuid.py — Identidad del cliente en el proveedor Meta
#
# Cubre el caso que dejaba mudo al agente: desde abril de 2026 Meta puede mandar el
# webhook sin el telefono del cliente, solo con su business-scoped user id (BSUID).
#
#   pip install -r requirements.txt -r requirements-dev.txt
#   pytest

import json

import httpx
import pytest

from agent.providers.meta import ProveedorMeta, es_bsuid

# BSUIDs reales tomados de los logs de produccion de Fruppy Helados.
BSUID_CLIENTE = "CO.1744031683476064"
BSUID_OTRO = "CO.1435932075071966"
TELEFONO_DUENO = "573002797970"


class _PeticionFalsa:
    """Lo minimo que parsear_webhook necesita de un Request de FastAPI."""

    def __init__(self, cuerpo: dict):
        self._cuerpo = cuerpo

    async def json(self):
        return self._cuerpo


def _webhook(*mensajes, contactos=None, estados=None) -> _PeticionFalsa:
    value = {"messaging_product": "whatsapp", "metadata": {}}
    if mensajes:
        value["messages"] = list(mensajes)
    if contactos:
        value["contacts"] = contactos
    if estados:
        value["statuses"] = estados
    return _PeticionFalsa(
        {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": value}]}]}
    )


@pytest.fixture
def proveedor(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "token-de-prueba")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "1342434335611320")
    monkeypatch.setenv("META_APP_SECRET", "")
    return ProveedorMeta()


# ── Deteccion de BSUID ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("CO.1744031683476064", True),
        ("US.13491208655302741918", True),
        ("CO.ENT.11815799212886844830", True),
        ("573002797970", False),
        ("+573002797970", False),
        ("", False),
        (None, False),
    ],
)
def test_es_bsuid(valor, esperado):
    assert es_bsuid(valor) is esperado


# ── Lectura del webhook ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mensaje_clasico_con_telefono(proveedor):
    """El payload de siempre sigue funcionando igual."""
    peticion = _webhook(
        {"from": TELEFONO_DUENO, "id": "wamid.1", "type": "text", "text": {"body": "Hola"}}
    )

    (msg,) = await proveedor.parsear_webhook(peticion)

    assert msg.identidad == TELEFONO_DUENO
    assert msg.telefono == TELEFONO_DUENO
    assert msg.bsuid is None
    assert msg.texto == "Hola"


@pytest.mark.asyncio
async def test_mensaje_solo_con_bsuid_no_se_descarta(proveedor):
    """
    El bug original: este payload (real, de los logs) se descartaba con
    "Mensaje sin 'from', se descarta" y el cliente nunca recibia respuesta.
    """
    peticion = _webhook(
        {
            "from_user_id": BSUID_CLIENTE,
            "id": "wamid.2",
            "timestamp": "1787496577",
            "type": "text",
            "text": {"body": "Buenas"},
        }
    )

    (msg,) = await proveedor.parsear_webhook(peticion)

    assert msg.identidad == BSUID_CLIENTE
    assert msg.bsuid == BSUID_CLIENTE
    assert msg.telefono is None
    assert msg.texto == "Buenas"
    assert msg.contexto["bsuid"] == BSUID_CLIENTE


@pytest.mark.asyncio
async def test_con_ambas_identidades_manda_el_bsuid(proveedor):
    """El BSUID es la llave del historial; el telefono queda como dato de contacto."""
    peticion = _webhook(
        {
            "from": TELEFONO_DUENO,
            "from_user_id": BSUID_CLIENTE,
            "id": "wamid.3",
            "type": "text",
            "text": {"body": "Hola"},
        }
    )

    (msg,) = await proveedor.parsear_webhook(peticion)

    assert msg.identidad == BSUID_CLIENTE
    assert msg.bsuid == BSUID_CLIENTE
    assert msg.telefono == TELEFONO_DUENO


@pytest.mark.asyncio
async def test_telefono_se_completa_desde_contacts(proveedor):
    """Si el telefono solo viene en el bloque contacts, igual se aprovecha."""
    peticion = _webhook(
        {"from_user_id": BSUID_CLIENTE, "id": "wamid.4", "type": "text", "text": {"body": "Hola"}},
        contactos=[{"user_id": BSUID_CLIENTE, "wa_id": TELEFONO_DUENO}],
    )

    (msg,) = await proveedor.parsear_webhook(peticion)

    assert msg.identidad == BSUID_CLIENTE
    assert msg.telefono == TELEFONO_DUENO


@pytest.mark.asyncio
async def test_bsuid_dentro_de_from_no_se_confunde_con_telefono(proveedor):
    """Defensa: si Meta empieza a mandar el BSUID en 'from', no debe ir al campo 'to'."""
    peticion = _webhook(
        {"from": BSUID_OTRO, "id": "wamid.5", "type": "text", "text": {"body": "Hola"}}
    )

    (msg,) = await proveedor.parsear_webhook(peticion)

    assert msg.bsuid == BSUID_OTRO
    assert msg.telefono is None


@pytest.mark.asyncio
async def test_mensaje_de_audio_se_conserva(proveedor):
    """Antes se ignoraba y el cliente quedaba esperando; ahora llega con su tipo."""
    peticion = _webhook(
        {"from_user_id": BSUID_CLIENTE, "id": "wamid.6", "type": "audio", "audio": {"id": "x"}}
    )

    (msg,) = await proveedor.parsear_webhook(peticion)

    assert msg.tipo == "audio"
    assert msg.texto == ""
    assert msg.identidad == BSUID_CLIENTE


@pytest.mark.asyncio
async def test_sin_ninguna_identidad_se_descarta(proveedor):
    peticion = _webhook({"id": "wamid.7", "type": "text", "text": {"body": "Hola"}})

    assert await proveedor.parsear_webhook(peticion) == []


@pytest.mark.asyncio
async def test_webhook_de_estados_no_genera_mensajes(proveedor, caplog):
    """Los statuses solo se registran: son la unica pista de un envio no entregado."""
    peticion = _webhook(
        estados=[
            {
                "id": "wamid.8",
                "status": "failed",
                "recipient_user_id": BSUID_CLIENTE,
                "errors": [
                    {"code": 131026, "title": "Message undeliverable"},
                ],
            }
        ]
    )

    assert await proveedor.parsear_webhook(peticion) == []
    assert "131026" in caplog.text
    assert "no entrego" in caplog.text.lower()


# ── Envio ────────────────────────────────────────────────────────────────


class _RespuestaFalsa:
    def __init__(self, status_code: int, cuerpo: dict):
        self.status_code = status_code
        self._cuerpo = cuerpo
        self.text = json.dumps(cuerpo)

    def json(self):
        return self._cuerpo


class _ClienteFalso:
    """Reemplaza httpx.AsyncClient y guarda los cuerpos enviados."""

    enviados: list = []
    respuestas: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        _ClienteFalso.enviados.append(json)
        indice = min(len(_ClienteFalso.enviados) - 1, len(_ClienteFalso.respuestas) - 1)
        return _ClienteFalso.respuestas[indice]


@pytest.fixture
def cliente_falso(monkeypatch):
    _ClienteFalso.enviados = []
    _ClienteFalso.respuestas = [_RespuestaFalsa(200, {"messages": [{"id": "wamid.ok"}]})]
    monkeypatch.setattr(httpx, "AsyncClient", _ClienteFalso)
    # Los reintentos no deben dormir de verdad dentro de los tests.
    monkeypatch.setattr("agent.providers.meta._ESPERAS_REINTENTO", (0.0, 0.0))
    return _ClienteFalso


@pytest.mark.asyncio
async def test_envio_con_telefono_usa_to(proveedor, cliente_falso):
    ok = await proveedor.enviar_mensaje(
        TELEFONO_DUENO, "Hola", {"telefono": TELEFONO_DUENO, "bsuid": None}
    )

    assert ok is True
    (cuerpo,) = cliente_falso.enviados
    assert cuerpo["to"] == TELEFONO_DUENO
    assert "recipient" not in cuerpo


@pytest.mark.asyncio
async def test_envio_solo_con_bsuid_usa_recipient(proveedor, cliente_falso):
    """Un BSUID en 'to' lo rechaza Meta con 131009: tiene que ir en 'recipient'."""
    ok = await proveedor.enviar_mensaje(
        BSUID_CLIENTE, "Hola", {"telefono": None, "bsuid": BSUID_CLIENTE}
    )

    assert ok is True
    (cuerpo,) = cliente_falso.enviados
    assert cuerpo["recipient"] == BSUID_CLIENTE
    assert cuerpo["recipient_type"] == "individual"
    assert "to" not in cuerpo


@pytest.mark.asyncio
async def test_con_ambos_datos_prefiere_el_telefono(proveedor, cliente_falso):
    """Meta recomienda el telefono: asi lo sigue incluyendo en los webhooks siguientes."""
    await proveedor.enviar_mensaje(
        BSUID_CLIENTE, "Hola", {"telefono": TELEFONO_DUENO, "bsuid": BSUID_CLIENTE}
    )

    (cuerpo,) = cliente_falso.enviados
    assert cuerpo["to"] == TELEFONO_DUENO
    assert "recipient" not in cuerpo


@pytest.mark.asyncio
async def test_sin_contexto_deduce_el_tipo_de_identidad(proveedor, cliente_falso):
    await proveedor.enviar_mensaje(BSUID_CLIENTE, "Hola")

    (cuerpo,) = cliente_falso.enviados
    assert cuerpo["recipient"] == BSUID_CLIENTE


@pytest.mark.asyncio
async def test_error_500_se_reintenta(proveedor, cliente_falso):
    cliente_falso.respuestas = [
        _RespuestaFalsa(500, {"error": {"message": "Internal"}}),
        _RespuestaFalsa(200, {"messages": [{"id": "wamid.ok"}]}),
    ]

    ok = await proveedor.enviar_mensaje(BSUID_CLIENTE, "Hola", {"bsuid": BSUID_CLIENTE})

    assert ok is True
    assert len(cliente_falso.enviados) == 2


@pytest.mark.asyncio
async def test_error_400_no_se_reintenta(proveedor, cliente_falso, caplog):
    cliente_falso.respuestas = [
        _RespuestaFalsa(
            400,
            {
                "error": {
                    "code": 131009,
                    "message": "Parameter value is not valid",
                    "error_data": {"details": "El formato del numero es incorrecto"},
                    "fbtrace_id": "abc",
                }
            },
        )
    ]

    ok = await proveedor.enviar_mensaje(TELEFONO_DUENO, "Hola", {"telefono": TELEFONO_DUENO})

    assert ok is False
    assert len(cliente_falso.enviados) == 1
    assert "131009" in caplog.text

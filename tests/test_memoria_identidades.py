# tests/test_memoria_identidades.py — Fusion del historial telefono -> BSUID
#
#   pip install -r requirements.txt -r requirements-dev.txt
#   pytest

import importlib

import pytest

BSUID = "CO.1744031683476064"
TELEFONO = "573002797970"


@pytest.fixture
async def memoria(monkeypatch, tmp_path):
    """Recarga memory.py apuntando a una base SQLite descartable."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("ENVIRONMENT", "test")

    import agent.memory as memory

    memory = importlib.reload(memory)
    await memory.inicializar_db()
    yield memory
    await memory.engine.dispose()


@pytest.mark.asyncio
async def test_fusiona_el_historial_viejo_guardado_por_telefono(memoria):
    """
    Un cliente que ya hablaba con el bot cuando Meta mandaba su telefono no debe
    empezar de cero el dia que Meta deja de mandarlo.
    """
    await memoria.guardar_mensaje(TELEFONO, "user", "Quiero dos malteadas")
    await memoria.guardar_mensaje(TELEFONO, "assistant", "Listo, dos malteadas")

    await memoria.vincular_identidad(BSUID, TELEFONO)

    assert await memoria.obtener_historial(TELEFONO) == []
    historial = await memoria.obtener_historial(BSUID)
    assert [m["content"] for m in historial] == ["Quiero dos malteadas", "Listo, dos malteadas"]


@pytest.mark.asyncio
async def test_vincular_dos_veces_no_rompe_nada(memoria):
    await memoria.guardar_mensaje(TELEFONO, "user", "Hola")

    await memoria.vincular_identidad(BSUID, TELEFONO)
    await memoria.guardar_mensaje(BSUID, "assistant", "Hola!")
    await memoria.vincular_identidad(BSUID, TELEFONO)

    historial = await memoria.obtener_historial(BSUID)
    assert [m["content"] for m in historial] == ["Hola", "Hola!"]


@pytest.mark.asyncio
async def test_sin_una_de_las_dos_identidades_no_hace_nada(memoria):
    await memoria.guardar_mensaje(TELEFONO, "user", "Hola")

    await memoria.vincular_identidad(None, TELEFONO)
    await memoria.vincular_identidad(BSUID, None)

    assert len(await memoria.obtener_historial(TELEFONO)) == 1


@pytest.mark.asyncio
async def test_guarda_un_bsuid_largo_sin_truncar(memoria):
    """La columna crecio a 140 caracteres justamente para esto."""
    largo = "CO." + "9" * 120
    await memoria.guardar_mensaje(largo, "user", "Hola")

    assert len(await memoria.obtener_historial(largo)) == 1

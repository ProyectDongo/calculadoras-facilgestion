"""
Tests del cliente mindicador.cl — mockeo HTTP y cache para no depender de red
ni de un Redis corriendo.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

from config.tributario import UF_VALOR_FALLBACK, UTM_VALOR_FALLBACK


def _mock_response(payload):
    fake = MagicMock()
    fake.raise_for_status.return_value = None
    fake.json.return_value = payload
    return fake


def test_get_uf_fallback_si_api_falla():
    from core.services import mindicador
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", side_effect=Exception("network down")):
        mc.get.return_value = None
        uf = mindicador.get_uf()
    assert uf == UF_VALOR_FALLBACK


def test_get_utm_fallback_si_api_falla():
    from core.services import mindicador
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", side_effect=Exception("network down")):
        mc.get.return_value = None
        utm = mindicador.get_utm()
    assert utm == UTM_VALOR_FALLBACK


def test_get_uf_parsea_serie_correctamente():
    from core.services import mindicador
    payload = {"serie": [{"fecha": "2026-05-12T04:00:00.000Z", "valor": 40290.47}]}
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", return_value=_mock_response(payload)):
        mc.get.return_value = None
        uf = mindicador.get_uf()
    assert uf == Decimal("40290.47")


def test_get_uf_lee_cache_y_no_consulta_api():
    """Si cache tiene valor, la API NO debe llamarse."""
    from core.services import mindicador
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get") as mock_get:
        mc.get.return_value = "39900"
        uf = mindicador.get_uf()
        mock_get.assert_not_called()
    assert uf == Decimal("39900")


def test_get_uf_serie_vacia_es_fallback():
    from core.services import mindicador
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", return_value=_mock_response({"serie": []})):
        mc.get.return_value = None
        uf = mindicador.get_uf()
    assert uf == UF_VALOR_FALLBACK


def test_get_uf_json_sin_serie_es_fallback():
    from core.services import mindicador
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", return_value=_mock_response({"error": "rate limited"})):
        mc.get.return_value = None
        uf = mindicador.get_uf()
    assert uf == UF_VALOR_FALLBACK


def test_get_uf_valor_nulo_es_fallback():
    """Si el primer elemento de la serie tiene valor=null, fallback."""
    from core.services import mindicador
    payload = {"serie": [{"fecha": "2026-05-12", "valor": None}]}
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", return_value=_mock_response(payload)):
        mc.get.return_value = None
        uf = mindicador.get_uf()
    assert uf == UF_VALOR_FALLBACK


def test_cache_caido_no_rompe_get_uf():
    """Si cache.get o cache.set fallan, get_uf sigue devolviendo un valor sano."""
    from core.services import mindicador
    payload = {"serie": [{"valor": 40000}]}
    with patch.object(mindicador, "cache") as mc, \
         patch.object(mindicador.requests, "get", return_value=_mock_response(payload)):
        mc.get.side_effect = Exception("redis down")
        mc.set.side_effect = Exception("redis down")
        uf = mindicador.get_uf()
    assert uf == Decimal("40000")

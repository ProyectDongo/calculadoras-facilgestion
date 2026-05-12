"""
calculadoras/tests/conftest.py — Fixtures locales.

Mockea get_uf y get_utm de mindicador.cl para que los tests sean
determinísticos (no dependen de la API ni de qué fallback esté pineado
en config/tributario.py).
"""
from decimal import Decimal
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _mock_indicadores():
    """Forzar UF=$39.200 y UTM=$70.000 (los valores históricos de los tests)."""
    with patch("calculadoras.services_sueldo.get_uf", return_value=Decimal("39200")), \
         patch("calculadoras.services_sueldo.get_utm", return_value=Decimal("70000")):
        yield

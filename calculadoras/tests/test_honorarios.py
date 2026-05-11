"""Tests del cálculo de honorarios con tasa 2026 (15,25%)."""
from decimal import Decimal

import pytest

from calculadoras.services_honorarios import (
    calcular_desde_bruto,
    calcular_desde_liquido,
)


# ── Snapshot del brief: $1.000.000 bruto → $847.500 líquido + $152.500 retención
def test_bruto_un_millon_a_liquido():
    r = calcular_desde_bruto(1_000_000)
    assert r.bruto     == Decimal("1000000")
    assert r.retencion == Decimal("152500")
    assert r.liquido   == Decimal("847500")
    assert r.modo      == "bruto_a_liquido"


def test_liquido_847500_a_bruto():
    r = calcular_desde_liquido(847_500)
    # 847_500 / 0.8475 = 1_000_000 exacto
    assert r.bruto     == Decimal("1000000")
    assert r.liquido   == Decimal("847500")
    assert r.retencion == Decimal("152500")
    assert r.modo      == "liquido_a_bruto"


# ── Bordes ──────────────────────────────────────────────────────────────────

def test_bruto_cero():
    r = calcular_desde_bruto(0)
    assert r.bruto == r.retencion == r.liquido == Decimal("0")


def test_bruto_negativo_lanza():
    with pytest.raises(ValueError):
        calcular_desde_bruto(-1)


def test_liquido_negativo_lanza():
    with pytest.raises(ValueError):
        calcular_desde_liquido(-1)


def test_round_trip_consistente():
    """Bruto → Líquido → Bruto debe redondear cerca del original."""
    inicial = 500_000
    r1 = calcular_desde_bruto(inicial)
    r2 = calcular_desde_liquido(r1.liquido)
    assert abs(int(r2.bruto) - inicial) <= 1


def test_string_acepta():
    r = calcular_desde_bruto("2000000")
    assert r.liquido == Decimal("1695000")

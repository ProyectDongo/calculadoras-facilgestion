"""
Tests del cálculo de IVA — snapshots con valores canónicos.

Se ejecuta sin Django (los módulos services_*.py no importan Django).
"""
from decimal import Decimal

import pytest

from calculadoras.services_iva import calcular_desde_neto, calcular_desde_bruto


# ── Snapshots del brief: $1.000.000 neto ↔ $1.190.000 bruto ──────────────────

def test_neto_un_millon_a_bruto():
    r = calcular_desde_neto(1_000_000)
    assert r.neto  == Decimal("1000000")
    assert r.iva   == Decimal("190000")
    assert r.bruto == Decimal("1190000")
    assert r.modo  == "neto_a_bruto"


def test_bruto_un_millon_ciento_noventa_a_neto():
    r = calcular_desde_bruto(1_190_000)
    assert r.neto  == Decimal("1000000")
    assert r.iva   == Decimal("190000")
    assert r.bruto == Decimal("1190000")
    assert r.modo  == "bruto_a_neto"


# ── Bordes ───────────────────────────────────────────────────────────────────

def test_neto_cero():
    r = calcular_desde_neto(0)
    assert r.neto == r.iva == r.bruto == Decimal("0")


def test_neto_negativo_lanza():
    with pytest.raises(ValueError):
        calcular_desde_neto(-1)


def test_bruto_negativo_lanza():
    with pytest.raises(ValueError):
        calcular_desde_bruto(-1)


def test_monto_string_acepta():
    r = calcular_desde_neto("100000")
    assert r.bruto == Decimal("119000")


def test_round_half_up_consistente():
    # 1.00 / 1.19 → 0.84033... → quantize a 1 → 1 (HALF_UP)
    r = calcular_desde_bruto(1)
    assert r.neto + r.iva == r.bruto
    assert r.bruto == Decimal("1")

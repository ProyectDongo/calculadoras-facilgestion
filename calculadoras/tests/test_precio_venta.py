"""Tests del cálculo de precio de venta."""
from decimal import Decimal

import pytest

from calculadoras.services_precio_venta import calcular


def test_ejemplo_brief_30pct_con_flete():
    """
    Brief: 'caso con flete + 30% utilidad + IVA, verificar márgenes'.
    Caso canónico:
        costo = 10.000, flete = 2.000, markup = 30%
        costo_total = 12.000
        utilidad    = 3.600
        precio_neto = 15.600
        iva 19%     = 2.964
        con IVA     = 18.564
        margen real = 3600 / 15600 = 23,08 %
    """
    r = calcular(costo=10_000, flete=2_000, porcentaje_utilidad=30)
    assert r.costo           == Decimal("10000")
    assert r.flete           == Decimal("2000")
    assert r.costo_total     == Decimal("12000")
    assert r.utilidad        == Decimal("3600")
    assert r.precio_neto     == Decimal("15600")
    assert r.iva             == Decimal("2964")
    assert r.precio_con_iva  == Decimal("18564")
    assert r.margen_real_pct == Decimal("23.08")


def test_sin_flete():
    r = calcular(costo=100_000, porcentaje_utilidad=20)
    assert r.flete       == Decimal("0")
    assert r.costo_total == Decimal("100000")
    assert r.utilidad    == Decimal("20000")
    assert r.precio_neto == Decimal("120000")
    assert r.iva         == Decimal("22800")
    assert r.precio_con_iva == Decimal("142800")


def test_costo_cero():
    r = calcular(costo=0, porcentaje_utilidad=30)
    assert r.precio_neto == Decimal("0")
    assert r.margen_real_pct == Decimal("0")


def test_costo_negativo_lanza():
    with pytest.raises(ValueError):
        calcular(costo=-1, porcentaje_utilidad=10)


def test_pct_negativo_lanza():
    with pytest.raises(ValueError):
        calcular(costo=1000, porcentaje_utilidad=-5)


def test_string_input_acepta():
    r = calcular(costo="50000", flete="0", porcentaje_utilidad="20")
    assert r.precio_neto == Decimal("60000")

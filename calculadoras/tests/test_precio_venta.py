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


def test_sin_comision_tarjeta_precio_tarjeta_es_cero():
    r = calcular(costo=10_000, porcentaje_utilidad=30)
    assert r.comision_tarjeta_pct == Decimal("0")
    assert r.precio_tarjeta == Decimal("0")
    assert r.recargo_tarjeta == Decimal("0")


def test_comision_tarjeta_no_afecta_utilidad():
    """La comisión de tarjeta no modifica precio_neto ni utilidad."""
    r_sin = calcular(costo=10_000, porcentaje_utilidad=30)
    r_con = calcular(costo=10_000, porcentaje_utilidad=30, comision_tarjeta=2)
    assert r_sin.precio_neto == r_con.precio_neto
    assert r_sin.utilidad == r_con.utilidad
    assert r_sin.precio_con_iva == r_con.precio_con_iva


def test_comision_tarjeta_calculo_correcto():
    """
    precio_con_iva / (1 - 0.02) = precio_tarjeta.
    Caso: costo=10.000, markup=30% → precio_con_iva=14.637 (sin flete).
    Con flete=0 y markup=30: precio_neto=13.000, iva=2.470, precio_con_iva=15.470
    (corrección: costo=10000, markup=30% → utilidad=3000, neto=13000, iva=2470, bruto=15470)
    comision=2% → precio_tarjeta = 15470 / 0.98 = 15785 (redondeado).
    """
    r = calcular(costo=10_000, porcentaje_utilidad=30, comision_tarjeta=2)
    assert r.precio_con_iva == Decimal("15470")
    expected_tarjeta = (Decimal("15470") / Decimal("0.98")).quantize(Decimal("1"))
    assert r.precio_tarjeta == expected_tarjeta
    assert r.recargo_tarjeta == r.precio_tarjeta - r.precio_con_iva


def test_comision_negativa_lanza():
    with pytest.raises(ValueError):
        calcular(costo=10_000, porcentaje_utilidad=30, comision_tarjeta=-1)

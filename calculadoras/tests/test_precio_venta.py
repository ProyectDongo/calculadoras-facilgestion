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
    precio_con_iva / (1 - comision_efectiva) = precio_tarjeta.
    La comisión EFECTIVA incluye IVA: comision_nominal × 1.19.

    Caso: costo=10.000, markup=30%, sin flete:
      precio_neto = 13.000, iva = 2.470, precio_con_iva = 15.470
      comision=2% → comision_efectiva = 2 × 1.19 = 2.38%
      precio_tarjeta = 15.470 / (1 - 0.0238) ≈ 15.847
    """
    r = calcular(costo=10_000, porcentaje_utilidad=30, comision_tarjeta=2)
    assert r.precio_con_iva == Decimal("15470")
    # 2% × 1.19 = 2.38% (comisión efectiva con IVA)
    comision_efectiva = Decimal("0.02") * Decimal("1.19")
    expected_tarjeta = (Decimal("15470") / (Decimal("1") - comision_efectiva)).quantize(Decimal("1"))
    assert r.precio_tarjeta == expected_tarjeta
    assert r.recargo_tarjeta == r.precio_tarjeta - r.precio_con_iva


def test_comision_efectiva_replica_transbank_real():
    """
    Caso del usuario: costo=10.000 (sin flete), markup=30%, comisión POS=3%.
    Con la comisión efectiva (3% × 1.19 = 3.57%) el comercio recibe exactamente
    el precio_con_iva cuando paga con tarjeta — sin pérdida del IVA de la comisión.
    """
    r = calcular(costo=10_000, porcentaje_utilidad=30, comision_tarjeta=3)
    # Comisión efectiva 3.57%: precio_tarjeta = 15470 / 0.9643 ≈ 16043
    comision_efectiva = Decimal("0.03") * Decimal("1.19")
    expected = (r.precio_con_iva / (Decimal("1") - comision_efectiva)).quantize(Decimal("1"))
    assert r.precio_tarjeta == expected
    # Verificar: si el comercio cobra precio_tarjeta y la red descuenta
    # comision_efectiva, el depósito final ≈ precio_con_iva (±1 CLP por redondeo).
    descuento = r.precio_tarjeta * comision_efectiva
    deposito = r.precio_tarjeta - descuento
    assert abs(deposito - r.precio_con_iva) <= Decimal("1")


def test_comision_negativa_lanza():
    with pytest.raises(ValueError):
        calcular(costo=10_000, porcentaje_utilidad=30, comision_tarjeta=-1)


# ── Modo Markup vs Margen sobre venta ────────────────────────────────────────

def test_modo_markup_default_es_compatible():
    r_default = calcular(costo=10_000, porcentaje_utilidad=30)
    r_markup  = calcular(costo=10_000, porcentaje_utilidad=30, modo_porcentaje="markup")
    assert r_default.precio_neto == r_markup.precio_neto == Decimal("13000")


def test_modo_margen_sobre_venta():
    """30% margen sobre venta → precio_neto = costo / (1 - 0.30)."""
    r = calcular(costo=10_000, porcentaje_utilidad=30, modo_porcentaje="margen")
    # precio_neto = 10000 / 0.70 ≈ 14286
    assert r.precio_neto == Decimal("14286")
    assert r.utilidad == Decimal("4286")
    assert r.precio_con_iva == Decimal("17000")  # 14286 × 1.19 (con redondeo)


def test_margen_y_markup_son_equivalentes_invertidos():
    """Markup 30% ⇄ margen 23.08% (mismo precio final)."""
    r_markup = calcular(costo=10_000, porcentaje_utilidad=30, modo_porcentaje="markup")
    # Margen real del 30% markup
    margen_eq = float(r_markup.porcentaje_margen)
    # Calcular con ese margen y debe dar (cerca de) el mismo precio_neto
    r_margen = calcular(costo=10_000, porcentaje_utilidad=margen_eq, modo_porcentaje="margen")
    # Toleramos 1 CLP de diferencia por redondeo en el porcentaje display
    assert abs(r_markup.precio_neto - r_margen.precio_neto) <= Decimal("1")


def test_modo_invalido_lanza():
    with pytest.raises(ValueError):
        calcular(costo=10_000, porcentaje_utilidad=30, modo_porcentaje="otro")


def test_margen_100_lanza():
    """Margen 100% sobre venta es imposible (precio infinito)."""
    with pytest.raises(ValueError):
        calcular(costo=10_000, porcentaje_utilidad=100, modo_porcentaje="margen")

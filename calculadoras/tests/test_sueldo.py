"""Tests de la calculadora de sueldo líquido."""
from decimal import Decimal

import pytest

from calculadoras.services_sueldo import calcular


def test_sueldo_bajo_sin_impuesto():
    """
    Sueldo bruto $500.000, Fonasa, indefinido, comisión AFP promedio 1.04%.
    Descuentos esperados:
        AFP total = 500000 * 0.1104 = 55.200
        Salud     = 500000 * 0.07   = 35.000
        Cesantía  = 500000 * 0.006  = 3.000
        Base IGC  = 500000 - 55200 - 35000 - 3000 = 406.800
        IGC: 406800 / 70000 ≈ 5.811 UTM → tramo 0-13.5 UTM → 0%
        Líquido   = 500.000 - 93.200 = 406.800
    """
    r = calcular(500_000)
    assert r.bruto == Decimal("500000")
    assert r.afp_total == Decimal("55200")
    assert r.salud == Decimal("35000")
    assert r.cesantia == Decimal("3000")
    assert r.igc == Decimal("0")
    assert r.liquido == Decimal("406800")


def test_sueldo_medio_paga_igc():
    """
    Sueldo $1.500.000 — debería entrar al tramo 13.5-30 UTM (4%).
        Renta imponible (≤ tope) = 1.500.000
        AFP    = 1500000 * 0.1104 = 165.600
        Salud  = 1500000 * 0.07   = 105.000
        Ces.   = 1500000 * 0.006  = 9.000
        Base IGC = 1500000 - 165600 - 105000 - 9000 = 1.220.400
        base_UTM = 1220400 / 70000 ≈ 17.434
        tramo 13.5-30: 17.434 * 0.04 - 0.54 = 0.6974 UTM
        IGC = 0.6974 * 70000 ≈ 48.815
        Líquido ≈ 1.500.000 - 165.600 - 105.000 - 9.000 - 48.815 = 1.171.585
    """
    r = calcular(1_500_000)
    assert r.afp_total == Decimal("165600")
    assert r.salud == Decimal("105000")
    assert r.cesantia == Decimal("9000")
    assert r.igc > Decimal("40000")
    assert r.igc < Decimal("60000")
    assert r.liquido > Decimal("1150000")
    assert r.liquido < Decimal("1200000")


def test_bruto_cero():
    r = calcular(0)
    assert r.liquido == Decimal("0")


def test_bruto_negativo_lanza():
    with pytest.raises(ValueError):
        calcular(-1)


def test_plazo_fijo_sin_cesantia():
    r = calcular(500_000, contrato="plazo_fijo")
    assert r.cesantia == Decimal("0")


def test_isapre_monto_fijo():
    r = calcular(800_000, salud_tipo="isapre", salud_isapre_uf=Decimal("3.5"))
    # 3.5 UF * 39200 = 137.200 (en lugar de 7% de 800k = 56k)
    assert r.salud == Decimal("137200")
    assert r.salud_tipo == "isapre"


def test_tope_imponible_aplica():
    """Sueldos altos: imponible se topa en 85.7 UF ≈ 3.36M CLP."""
    r = calcular(10_000_000)
    tope = Decimal("85.7") * Decimal("39200")
    assert r.renta_imponible == tope.quantize(Decimal("1"))
    # AFP/salud/cesantía se calculan sobre tope, NO sobre 10M
    assert r.afp_total < Decimal("400000")  # mucho menos que 10M*0.1104


def test_comision_fuera_de_rango_lanza():
    with pytest.raises(ValueError):
        calcular(500_000, afp_comision=Decimal("0.10"))   # 10% irreal


def test_tipo_salud_invalido_lanza():
    with pytest.raises(ValueError):
        calcular(500_000, salud_tipo="otro")


def test_tope_cesantia_independiente_del_tope_afp():
    """
    Para sueldos entre tope AFP (85,7 UF ≈ $3.359k con UF=$39.200) y tope
    cesantía (128,5 UF ≈ $5.037k), la cesantía debe seguir creciendo aunque
    la base AFP ya esté topeada.
    """
    # Bruto $4.000.000 — por encima del tope AFP, por debajo del tope cesantía
    r = calcular(4_000_000, contrato="indefinido")
    # base_AFP = min(4M, 85.7 × 39200) = min(4M, 3_359_440) = 3_359_440
    # base_Cesantia = min(4M, 128.5 × 39200) = min(4M, 5_037_200) = 4_000_000
    # cesantia = 4_000_000 × 0.006 = 24_000
    assert r.cesantia == Decimal("24000")
    # AFP topeada al imponible AFP
    base_afp_esperada = Decimal("85.7") * Decimal("39200")
    assert r.afp_total == (base_afp_esperada * Decimal("0.1104")).quantize(Decimal("1"))


def test_tope_cesantia_se_aplica_para_sueldos_muy_altos():
    """Bruto $10M supera ambos topes; cesantía debe topear en 128.5 UF."""
    r = calcular(10_000_000, contrato="indefinido")
    base_cesantia_esperada = (Decimal("128.5") * Decimal("39200")) * Decimal("0.006")
    assert r.cesantia == base_cesantia_esperada.quantize(Decimal("1"))

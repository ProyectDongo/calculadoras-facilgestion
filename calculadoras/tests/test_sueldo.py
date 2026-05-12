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
    """Sueldos altos: imponible se topa en 90 UF (previred abr 2026)."""
    r = calcular(10_000_000)
    tope = Decimal("90") * Decimal("39200")   # UF mockeada = 39200
    assert r.renta_imponible == tope.quantize(Decimal("1"))
    # AFP/salud/cesantía se calculan sobre tope, NO sobre 10M
    assert r.afp_total < Decimal("420000")


def test_comision_fuera_de_rango_lanza():
    with pytest.raises(ValueError):
        calcular(500_000, afp_comision=Decimal("0.10"))   # 10% irreal


def test_tipo_salud_invalido_lanza():
    with pytest.raises(ValueError):
        calcular(500_000, salud_tipo="otro")


def test_tope_cesantia_independiente_del_tope_afp():
    """
    Para sueldos entre tope AFP (90 UF ≈ $3.528k con UF=$39.200) y tope
    cesantía (135.2 UF ≈ $5.299k), la cesantía debe seguir creciendo aunque
    la base AFP ya esté topeada.
    """
    # Bruto $4.000.000: > tope AFP, < tope cesantía → cesantía sobre bruto entero
    r = calcular(4_000_000, contrato="indefinido")
    assert r.cesantia == Decimal("24000")  # 4M × 0.6%
    # AFP topeada al imponible AFP (90 UF × 39200)
    base_afp_esperada = Decimal("90") * Decimal("39200")
    assert r.afp_total == (base_afp_esperada * Decimal("0.1104")).quantize(Decimal("1"))


def test_tope_cesantia_se_aplica_para_sueldos_muy_altos():
    """Bruto $10M supera ambos topes; cesantía debe topear en 135.2 UF."""
    r = calcular(10_000_000, contrato="indefinido")
    base_cesantia_esperada = (Decimal("135.2") * Decimal("39200")) * Decimal("0.006")
    assert r.cesantia == base_cesantia_esperada.quantize(Decimal("1"))


def test_gratificacion_legal_es_imponible():
    """
    Marcar gratificación legal: se suma al sueldo_base como bruto imponible
    y todos los descuentos se calculan sobre el total.
    """
    r = calcular(1_000_000, gratificacion_legal=True)
    # sueldo_base × 25% = 250.000 ; tope = 4.75 × 539.000 / 12 ≈ 213.354
    # gratificación = min(250000, 213354) = 213.354
    assert r.sueldo_base == Decimal("1000000")
    assert r.gratificacion_legal == Decimal("213354")
    assert r.bruto == Decimal("1213354")
    # Los descuentos se aplican sobre 1.213.354, no sobre 1M
    assert r.afp_total > Decimal("130000")  # > 1M × 0.1104 = 110.400


def test_gratificacion_legal_sin_checkbox_no_aplica():
    r = calcular(1_000_000, gratificacion_legal=False)
    assert r.gratificacion_legal == Decimal("0")
    assert r.bruto == r.sueldo_base == Decimal("1000000")


def test_asignaciones_no_imponibles_se_suman_al_liquido():
    """Colación y movilización no descuentan, pero suman al líquido total."""
    sin = calcular(1_000_000)
    con = calcular(1_000_000, colacion=Decimal("30000"), movilizacion=Decimal("20000"))
    # Líquido base no cambia (no descuentan)
    assert sin.liquido == con.liquido
    # Líquido total = líquido + 50k
    assert con.liquido_total == con.liquido + Decimal("50000")


def test_modo_invertido_con_gratificacion_sueldo_bajo():
    """
    Bug regresión: con gratificación marcada y sueldos bajos (sin IGC), la
    búsqueda binaria fallaba porque arrancaba con lo=líquido_objetivo. Cuando
    el sueldo_base correcto era MENOR que ese líquido (porque la gratif 25%
    suma al bruto), nunca convergía.

    Caso: líquido $475.000, AFP Uno 0.49%, con gratificación.
    El líquido resultante debe ser exactamente $475.000 (±$1 por redondeo).
    """
    r = calcular(
        475_000,
        modo="liquido_a_bruto",
        afp_comision=Decimal("0.0049"),  # AFP Uno
        gratificacion_legal=True,
    )
    # Verifica que el líquido calculado coincide con el objetivo
    assert abs(r.liquido - Decimal("475000")) <= Decimal("1")
    # El sueldo_base debe ser menor que el líquido (sin IGC + gratif al 25%)
    assert r.sueldo_base < Decimal("475000")

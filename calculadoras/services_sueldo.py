"""
calculadoras/services_sueldo.py — Cálculo de sueldo líquido en Chile.

Fórmula (trabajador dependiente, contrato indefinido):
    1. Renta imponible = min(bruto, tope_imponible)
    2. AFP   = renta_imponible * (0.10 + comision_afp)
    3. Salud = renta_imponible * 0.07           (Fonasa)
             o monto fijo en UF                 (Isapre — el usuario lo declara)
    4. Cesantía = renta_imponible * 0.006        (indefinido)
    5. Base IGC = bruto - AFP - salud - cesantía
    6. IGC = aplicar tramos sobre base_IGC / UTM
    7. Líquido = bruto - AFP - salud - cesantía - IGC

Notas:
    - Para Isapre el monto se entrega en UF y se convierte con UF_VALOR_REFERENCIAL.
      Esto es una aproximación; el cálculo "real" lo hace la Isapre con la UF del mes.
    - No incluimos asignaciones (colación, movilización, bono) ni aportes
      adicionales (APV). Es una calc "estándar".
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from config.tributario import (
    AFP_COTIZACION_OBLIGATORIA,
    IGC_TRAMOS_2026,
    SALUD_FONASA,
    SEGURO_CESANTIA_INDEFINIDO,
    SEGURO_CESANTIA_PLAZO_FIJO,
    TOPE_IMPONIBLE_UF,
)
from core.services.mindicador import get_uf, get_utm

_CLP_QUANTIZER: Final = Decimal("1")


@dataclass(frozen=True, slots=True)
class ResultadoSueldo:
    bruto: Decimal
    renta_imponible: Decimal     # con tope aplicado
    afp_total: Decimal           # 10% + comisión
    afp_obligatoria: Decimal     # solo el 10%
    afp_comision: Decimal        # solo la comisión
    salud: Decimal
    salud_tipo: str              # "fonasa" | "isapre"
    cesantia: Decimal
    base_igc: Decimal            # bruto - AFP - salud - cesantía
    igc: Decimal                 # impuesto único
    liquido: Decimal
    total_descuentos: Decimal


def _to_decimal(valor) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, str)):
        try:
            return Decimal(str(valor))
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc
    if isinstance(valor, float):
        return Decimal(str(valor))
    raise ValueError(f"Tipo no soportado: {type(valor).__name__}")


def _q(d: Decimal) -> Decimal:
    return d.quantize(_CLP_QUANTIZER, rounding=ROUND_HALF_UP)


def _calcular_igc(base_imponible_clp: Decimal, utm_valor: Decimal) -> Decimal:
    """
    Calcula el Impuesto Único de Segunda Categoría (mensual).

    Pasos:
        1. base_UTM = base_imponible_clp / UTM
        2. ubicar tramo (lim_inf, lim_sup, tasa, rebaja_UTM)
        3. impuesto_UTM = base_UTM * tasa - rebaja_UTM
        4. impuesto_clp = impuesto_UTM * UTM
    """
    if base_imponible_clp <= 0:
        return Decimal("0")

    base_utm = base_imponible_clp / utm_valor

    for lim_inf, lim_sup, tasa, rebaja_utm in IGC_TRAMOS_2026:
        if base_utm >= lim_inf and (lim_sup is None or base_utm < lim_sup):
            impuesto_utm = (base_utm * tasa) - rebaja_utm
            impuesto_clp = impuesto_utm * utm_valor
            return _q(max(Decimal("0"), impuesto_clp))

    return Decimal("0")


def calcular(
    bruto,
    *,
    afp_comision=Decimal("0.0104"),
    salud_tipo: str = "fonasa",
    salud_isapre_uf=Decimal("0"),
    contrato: str = "indefinido",
) -> ResultadoSueldo:
    """
    Args:
        bruto:           renta mensual bruta en CLP.
        afp_comision:    comisión adicional de la AFP (ej: 0.0104 = 1.04%).
                         No incluye el 10% obligatorio (ese va aparte).
        salud_tipo:      'fonasa' o 'isapre'.
        salud_isapre_uf: si isapre, plan en UF mensual.
        contrato:        'indefinido' | 'plazo_fijo'.
    """
    bruto_d = _to_decimal(bruto)
    comision_d = _to_decimal(afp_comision)
    if bruto_d < 0:
        raise ValueError("El sueldo bruto no puede ser negativo.")
    if comision_d < 0 or comision_d > Decimal("0.05"):
        raise ValueError("Comisión AFP fuera de rango razonable.")

    # Valores de indicadores en tiempo real (con fallback hardcoded si la API cae)
    uf_clp = get_uf()
    utm_clp = get_utm()

    # 1. Renta imponible con tope
    tope_clp = TOPE_IMPONIBLE_UF * uf_clp
    renta_imponible = min(bruto_d, tope_clp)

    # 2. AFP
    afp_obligatoria = renta_imponible * AFP_COTIZACION_OBLIGATORIA
    afp_comision_clp = renta_imponible * comision_d
    afp_total = afp_obligatoria + afp_comision_clp

    # 3. Salud
    if salud_tipo == "fonasa":
        salud = renta_imponible * SALUD_FONASA
    elif salud_tipo == "isapre":
        salud_uf = _to_decimal(salud_isapre_uf)
        if salud_uf < 0:
            raise ValueError("Monto Isapre no puede ser negativo.")
        salud = salud_uf * uf_clp
    else:
        raise ValueError(f"salud_tipo inválido: {salud_tipo!r}")

    # 4. Seguro Cesantía
    if contrato == "indefinido":
        cesantia = renta_imponible * SEGURO_CESANTIA_INDEFINIDO
    elif contrato == "plazo_fijo":
        cesantia = renta_imponible * SEGURO_CESANTIA_PLAZO_FIJO
    else:
        raise ValueError(f"contrato inválido: {contrato!r}")

    # 5. Base imponible IGC
    base_igc = bruto_d - afp_total - salud - cesantia
    base_igc = max(Decimal("0"), base_igc)

    # 6. IGC
    igc = _calcular_igc(base_igc, utm_clp)

    # 7. Líquido
    total_descuentos = afp_total + salud + cesantia + igc
    liquido = bruto_d - total_descuentos

    return ResultadoSueldo(
        bruto=_q(bruto_d),
        renta_imponible=_q(renta_imponible),
        afp_total=_q(afp_total),
        afp_obligatoria=_q(afp_obligatoria),
        afp_comision=_q(afp_comision_clp),
        salud=_q(salud),
        salud_tipo=salud_tipo,
        cesantia=_q(cesantia),
        base_igc=_q(base_igc),
        igc=_q(igc),
        liquido=_q(liquido),
        total_descuentos=_q(total_descuentos),
    )

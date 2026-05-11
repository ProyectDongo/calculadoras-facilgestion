"""
calculadoras/services_precio_venta.py — Cálculo puro de precio de venta.

Fórmula:
    costo_total       = costo + flete
    utilidad          = costo_total * (porcentaje_utilidad / 100)
    precio_neto       = costo_total + utilidad
    iva               = precio_neto * 0.19
    precio_con_iva    = precio_neto + iva
    margen_real_pct   = utilidad / precio_neto * 100      (margen sobre venta)

Nota terminológica:
    - "% utilidad" del input es markup sobre el costo (utilidad/costo).
    - "margen_real_pct" del output es margen sobre venta (utilidad/precio_neto).
    Ambos números son útiles y se reportan por separado.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from config.tributario import IVA_TASA

_CLP_QUANTIZER: Final = Decimal("1")
_PCT_QUANTIZER: Final = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ResultadoPrecioVenta:
    costo:           Decimal
    flete:           Decimal
    costo_total:     Decimal
    porcentaje_markup: Decimal   # input del usuario, en porcentaje (ej: 30)
    utilidad:        Decimal
    precio_neto:     Decimal
    iva:             Decimal
    precio_con_iva:  Decimal
    margen_real_pct: Decimal     # utilidad/precio_neto * 100


def _to_decimal(valor, default="0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(default)
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, str)):
        try:
            return Decimal(str(valor))
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc
    if isinstance(valor, float):
        return Decimal(str(valor))
    raise ValueError(f"Tipo de monto no soportado: {type(valor).__name__}")


def _q_clp(d: Decimal) -> Decimal:
    return d.quantize(_CLP_QUANTIZER, rounding=ROUND_HALF_UP)


def _q_pct(d: Decimal) -> Decimal:
    return d.quantize(_PCT_QUANTIZER, rounding=ROUND_HALF_UP)


def calcular(costo, flete=0, porcentaje_utilidad=0) -> ResultadoPrecioVenta:
    """
    Args:
        costo:               costo neto del producto, en CLP.
        flete:               costo de transporte opcional, en CLP.
        porcentaje_utilidad: markup deseado en %  (30 = 30 %).
    """
    costo_d = _to_decimal(costo)
    flete_d = _to_decimal(flete, default="0")
    pct_d   = _to_decimal(porcentaje_utilidad, default="0")

    if costo_d < 0 or flete_d < 0:
        raise ValueError("Costo y flete no pueden ser negativos.")
    if pct_d < 0:
        raise ValueError("El porcentaje de utilidad no puede ser negativo.")

    costo_total = costo_d + flete_d
    utilidad    = costo_total * (pct_d / Decimal("100"))
    precio_neto = costo_total + utilidad
    iva         = precio_neto * IVA_TASA
    precio_con_iva = precio_neto + iva

    # margen real sobre venta (no sobre costo)
    if precio_neto > 0:
        margen_pct = (utilidad / precio_neto) * Decimal("100")
    else:
        margen_pct = Decimal("0")

    return ResultadoPrecioVenta(
        costo=           _q_clp(costo_d),
        flete=           _q_clp(flete_d),
        costo_total=     _q_clp(costo_total),
        porcentaje_markup=_q_pct(pct_d),
        utilidad=        _q_clp(utilidad),
        precio_neto=     _q_clp(precio_neto),
        iva=             _q_clp(iva),
        precio_con_iva=  _q_clp(precio_con_iva),
        margen_real_pct= _q_pct(margen_pct),
    )

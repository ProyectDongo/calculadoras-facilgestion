"""
calculadoras/services_precio_venta.py — Cálculo puro de precio de venta.

Fórmula:
    costo_total       = costo + flete
    utilidad          = costo_total * (porcentaje_utilidad / 100)
    precio_neto       = costo_total + utilidad
    iva               = precio_neto * 0.19
    precio_con_iva    = precio_neto + iva          ("bruto", pago en efectivo)

    # Comisión efectiva: Transbank/Getnet/Klap facturan al comercio con IVA.
    # Si dicen "3%", el descuento real al depósito es 3% × 1.19 = 3.57%.
    comision_efectiva = (comision_tarjeta / 100) * (1 + 0.19)
    precio_tarjeta    = precio_con_iva / (1 - comision_efectiva)

    margen_real_pct   = utilidad / precio_neto * 100      (margen sobre venta)

Nota terminológica:
    - "% utilidad" del input es markup sobre el costo (utilidad/costo).
    - "margen_real_pct" del output es margen sobre venta (utilidad/precio_neto).
    - La comisión de tarjeta NO afecta la utilidad deseada; se suma después
      para evitar referencia circular.
    - La comisión NOMINAL del operador siempre se le aplica IVA 19% (es un
      servicio facturado). Si el comercio cobra precio_tarjeta y la red descuenta
      tasa+IVA, el depósito final es exactamente precio_con_iva.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from config.tributario import IVA_TASA

_CLP_QUANTIZER: Final = Decimal("1")
_PCT_QUANTIZER: Final = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ResultadoPrecioVenta:
    costo:              Decimal
    flete:              Decimal
    costo_total:        Decimal
    porcentaje_markup:  Decimal   # markup sobre costo (utilidad/costo × 100)
    porcentaje_margen:  Decimal   # margen sobre venta (utilidad/precio_neto × 100)
    modo_porcentaje:    str       # "markup" | "margen" — qué interpretó el input
    utilidad:           Decimal
    precio_neto:        Decimal
    iva:                Decimal
    precio_con_iva:     Decimal   # bruto (efectivo/transferencia)
    comision_tarjeta_pct: Decimal # input usuario, en % (ej: 1.99)
    precio_tarjeta:     Decimal   # precio a cobrar con tarjeta (0 si sin comisión)
    recargo_tarjeta:    Decimal   # precio_tarjeta - precio_con_iva
    margen_real_pct:    Decimal   # alias backward-compat = porcentaje_margen


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


def calcular(
    costo,
    flete=0,
    porcentaje_utilidad=0,
    comision_tarjeta=0,
    modo_porcentaje: str = "markup",
) -> ResultadoPrecioVenta:
    """
    Args:
        costo:               costo neto del producto, en CLP.
        flete:               costo de transporte opcional, en CLP.
        porcentaje_utilidad: % deseado de utilidad (30 = 30 %).
        modo_porcentaje:     'markup' → porcentaje sobre el COSTO (precio = costo × (1+%))
                             'margen' → porcentaje sobre la VENTA (precio = costo / (1−%))
        comision_tarjeta:    comisión de tarjeta en % nominal (1.99 = 1.99 %).
                             Se aplica DESPUÉS del markup para evitar referencia circular.
                             Internamente se le suma IVA: efectiva = nominal × 1.19.
    """
    if modo_porcentaje not in ("markup", "margen"):
        raise ValueError(f"modo_porcentaje inválido: {modo_porcentaje!r}")

    costo_d    = _to_decimal(costo)
    flete_d    = _to_decimal(flete, default="0")
    pct_d      = _to_decimal(porcentaje_utilidad, default="0")
    comision_d = _to_decimal(comision_tarjeta, default="0")

    if costo_d < 0 or flete_d < 0:
        raise ValueError("Costo y flete no pueden ser negativos.")
    if pct_d < 0:
        raise ValueError("El porcentaje de utilidad no puede ser negativo.")
    if modo_porcentaje == "margen" and pct_d >= Decimal("100"):
        raise ValueError("El margen sobre venta debe ser menor a 100%.")
    if comision_d < 0 or comision_d >= Decimal("100"):
        raise ValueError("La comisión de tarjeta debe estar entre 0 y 100.")

    costo_total = costo_d + flete_d
    if modo_porcentaje == "margen":
        # precio_neto = costo_total / (1 - margen%)
        precio_neto = costo_total / (Decimal("1") - pct_d / Decimal("100"))
        utilidad    = precio_neto - costo_total
    else:
        # precio_neto = costo_total × (1 + markup%)
        utilidad    = costo_total * (pct_d / Decimal("100"))
        precio_neto = costo_total + utilidad
    iva            = precio_neto * IVA_TASA
    precio_con_iva = precio_neto + iva  # precio bruto (efectivo/transferencia)

    # Equivalencia para mostrar ambos al usuario
    if costo_total > 0:
        markup_pct = (utilidad / costo_total) * Decimal("100")
    else:
        markup_pct = Decimal("0")

    # Precio para cobro con tarjeta: aplicamos la comisión EFECTIVA (con IVA).
    # Si el operador dice "3%", al comercio le descuentan 3% × 1.19 = 3.57%.
    # Sin este ajuste, el comercio recibiría menos que precio_con_iva.
    if comision_d > 0:
        comision_efectiva = (comision_d / Decimal("100")) * (Decimal("1") + IVA_TASA)
        if comision_efectiva >= Decimal("1"):
            raise ValueError("La comisión efectiva (con IVA) no puede ser >= 100%.")
        precio_tarjeta = precio_con_iva / (Decimal("1") - comision_efectiva)
        recargo_tarjeta = precio_tarjeta - precio_con_iva
    else:
        precio_tarjeta = Decimal("0")
        recargo_tarjeta = Decimal("0")

    # margen real sobre venta (no sobre costo)
    if precio_neto > 0:
        margen_pct = (utilidad / precio_neto) * Decimal("100")
    else:
        margen_pct = Decimal("0")

    return ResultadoPrecioVenta(
        costo=                _q_clp(costo_d),
        flete=                _q_clp(flete_d),
        costo_total=          _q_clp(costo_total),
        porcentaje_markup=    _q_pct(markup_pct),
        porcentaje_margen=    _q_pct(margen_pct),
        modo_porcentaje=      modo_porcentaje,
        utilidad=             _q_clp(utilidad),
        precio_neto=          _q_clp(precio_neto),
        iva=                  _q_clp(iva),
        precio_con_iva=       _q_clp(precio_con_iva),
        comision_tarjeta_pct= _q_pct(comision_d),
        precio_tarjeta=       _q_clp(precio_tarjeta),
        recargo_tarjeta=      _q_clp(recargo_tarjeta),
        margen_real_pct=      _q_pct(margen_pct),
    )

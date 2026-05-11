"""
calculadoras/services_iva.py — Cálculo puro de IVA (sin Django, sin I/O).

Mantener este módulo libre de imports de Django para que sea snapshot-testable
con un simple `import` y sin overhead de framework.

Tasa: 19% (config.tributario.IVA_TASA).
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from config.tributario import IVA_TASA

# Quantización: pesos chilenos no usan centavos. Redondeo half-up estándar.
_CLP_QUANTIZER: Final = Decimal("1")


@dataclass(frozen=True, slots=True)
class ResultadoIVA:
    """Resultado canónico para ambos modos."""
    neto: Decimal
    iva: Decimal
    bruto: Decimal
    tasa: Decimal               # 0.19
    modo: str                   # "neto_a_bruto" | "bruto_a_neto"


def _to_decimal(valor) -> Decimal:
    """Convierte int/str/Decimal/float a Decimal. Float pasa por str para evitar IEEE."""
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, str)):
        try:
            return Decimal(valor)
        except InvalidOperation as exc:
            raise ValueError(f"Monto inválido: {valor!r}") from exc
    if isinstance(valor, float):
        return Decimal(str(valor))
    raise ValueError(f"Tipo de monto no soportado: {type(valor).__name__}")


def _quantize_clp(d: Decimal) -> Decimal:
    """Redondea a peso chileno (sin decimales)."""
    return d.quantize(_CLP_QUANTIZER, rounding=ROUND_HALF_UP)


def calcular_desde_neto(neto) -> ResultadoIVA:
    """
    Modo Neto → Bruto.
        iva   = neto * 0.19
        bruto = neto + iva
    """
    neto_d = _to_decimal(neto)
    if neto_d < 0:
        raise ValueError("El monto neto no puede ser negativo.")

    iva = _quantize_clp(neto_d * IVA_TASA)
    neto_q = _quantize_clp(neto_d)
    bruto = neto_q + iva
    return ResultadoIVA(
        neto=neto_q, iva=iva, bruto=bruto, tasa=IVA_TASA, modo="neto_a_bruto",
    )


def calcular_desde_bruto(bruto) -> ResultadoIVA:
    """
    Modo Bruto → Neto.
        neto  = bruto / 1.19
        iva   = bruto - neto
    """
    bruto_d = _to_decimal(bruto)
    if bruto_d < 0:
        raise ValueError("El monto bruto no puede ser negativo.")

    divisor = Decimal("1") + IVA_TASA
    neto = _quantize_clp(bruto_d / divisor)
    bruto_q = _quantize_clp(bruto_d)
    iva = bruto_q - neto
    return ResultadoIVA(
        neto=neto, iva=iva, bruto=bruto_q, tasa=IVA_TASA, modo="bruto_a_neto",
    )

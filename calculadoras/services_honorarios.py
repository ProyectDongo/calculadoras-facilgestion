"""
calculadoras/services_honorarios.py — Cálculo puro de boleta de honorarios.

Tasa de retención: config.tributario.RETENCION_HONORARIOS (15,25% en 2026,
sube a 16% en 2027 y 17% en 2028 — Ley 21.133, art. 17 transitorio).

Sin imports de Django: snapshot-testable.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Final

from config.tributario import RETENCION_HONORARIOS

_CLP_QUANTIZER: Final = Decimal("1")


@dataclass(frozen=True, slots=True)
class ResultadoHonorarios:
    bruto: Decimal
    retencion: Decimal
    liquido: Decimal
    tasa: Decimal         # 0.1525
    modo: str             # "bruto_a_liquido" | "liquido_a_bruto"


def _to_decimal(valor) -> Decimal:
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


def _q(d: Decimal) -> Decimal:
    return d.quantize(_CLP_QUANTIZER, rounding=ROUND_HALF_UP)


def calcular_desde_bruto(bruto) -> ResultadoHonorarios:
    """
    Bruto → Líquido.
        retencion = bruto * tasa
        liquido   = bruto - retencion
    """
    bruto_d = _to_decimal(bruto)
    if bruto_d < 0:
        raise ValueError("El monto bruto no puede ser negativo.")

    bruto_q = _q(bruto_d)
    retencion = _q(bruto_d * RETENCION_HONORARIOS)
    liquido = bruto_q - retencion
    return ResultadoHonorarios(
        bruto=bruto_q, retencion=retencion, liquido=liquido,
        tasa=RETENCION_HONORARIOS, modo="bruto_a_liquido",
    )


def calcular_desde_liquido(liquido) -> ResultadoHonorarios:
    """
    Líquido → Bruto.
        bruto     = liquido / (1 - tasa)
        retencion = bruto - liquido
    """
    liquido_d = _to_decimal(liquido)
    if liquido_d < 0:
        raise ValueError("El monto líquido no puede ser negativo.")

    divisor = Decimal("1") - RETENCION_HONORARIOS
    if divisor <= 0:
        raise ValueError("Tasa de retención inválida (≥ 100%).")

    bruto = _q(liquido_d / divisor)
    liquido_q = _q(liquido_d)
    retencion = bruto - liquido_q
    return ResultadoHonorarios(
        bruto=bruto, retencion=retencion, liquido=liquido_q,
        tasa=RETENCION_HONORARIOS, modo="liquido_a_bruto",
    )

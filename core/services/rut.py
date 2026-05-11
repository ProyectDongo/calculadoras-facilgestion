"""
core/services/rut.py — Validación de RUT chileno (módulo 11).

API pública:
    normalizar(rut) -> str    "12.345.678-K" → "12345678-K"
    formatear(rut)  -> str    "12345678K"    → "12.345.678-K"
    validar(rut)    -> bool   módulo 11 estándar

Casos cubiertos:
    - Con/sin puntos
    - Con/sin guión
    - DV en mayúscula o minúscula ('k'/'K' aceptados, normalizado a 'K')
    - Espacios sobrantes
"""
import re
from typing import Optional

_LIMPIAR_RE = re.compile(r"[.\s]")


def _solo_digitos_y_dv(rut: str) -> Optional[tuple[str, str]]:
    """
    Devuelve (cuerpo, dv) en mayúscula, o None si el formato es inválido.
    Acepta tanto '12345678-K' como '12345678K'.
    """
    if not rut or not isinstance(rut, str):
        return None
    s = _LIMPIAR_RE.sub("", rut).upper()
    if not s:
        return None

    if "-" in s:
        partes = s.split("-")
        if len(partes) != 2 or not partes[0] or not partes[1]:
            return None
        cuerpo, dv = partes
    else:
        cuerpo, dv = s[:-1], s[-1]

    if not cuerpo.isdigit():
        return None
    if not (dv.isdigit() or dv == "K"):
        return None
    if not (1 <= len(cuerpo) <= 8):
        return None

    return cuerpo, dv


def normalizar(rut: str) -> str:
    """
    Normaliza a 'NNNNNNNN-D' (sin puntos, con guión, DV mayúscula).

    Raises:
        ValueError si el RUT no tiene formato válido.
    """
    parsed = _solo_digitos_y_dv(rut)
    if parsed is None:
        raise ValueError(f"RUT con formato inválido: {rut!r}")
    cuerpo, dv = parsed
    return f"{cuerpo}-{dv}"


def calcular_dv(cuerpo: str) -> str:
    """
    Calcula el dígito verificador para un cuerpo de RUT (sin DV).

    Algoritmo módulo 11:
        - Multiplicar dígitos de derecha a izquierda por 2,3,4,5,6,7 (cíclico)
        - Sumar todo
        - DV = 11 - (suma % 11)
        - Si DV == 11 → '0'
        - Si DV == 10 → 'K'
        - Resto → str(DV)
    """
    if not cuerpo.isdigit():
        raise ValueError("Cuerpo del RUT debe contener sólo dígitos.")

    suma = 0
    multiplicador = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplicador
        multiplicador = 2 if multiplicador == 7 else multiplicador + 1

    resto = suma % 11
    dv = 11 - resto
    if dv == 11:
        return "0"
    if dv == 10:
        return "K"
    return str(dv)


def validar(rut: str) -> bool:
    """
    True si el RUT es válido (formato + DV calculado correctamente).
    No lanza excepciones — devuelve False en cualquier caso erróneo.
    """
    try:
        parsed = _solo_digitos_y_dv(rut)
        if parsed is None:
            return False
        cuerpo, dv_dado = parsed
        return calcular_dv(cuerpo) == dv_dado
    except (ValueError, TypeError):
        return False


def formatear(rut: str) -> str:
    """
    Formatea para mostrar: '12345678K' → '12.345.678-K'.

    Raises:
        ValueError si el RUT no es válido en formato.
    """
    parsed = _solo_digitos_y_dv(rut)
    if parsed is None:
        raise ValueError(f"RUT con formato inválido: {rut!r}")
    cuerpo, dv = parsed

    # Insertar puntos cada 3 dígitos desde la derecha
    cuerpo_invertido = cuerpo[::-1]
    grupos = [cuerpo_invertido[i:i + 3] for i in range(0, len(cuerpo_invertido), 3)]
    cuerpo_formateado = ".".join(grupos)[::-1]
    return f"{cuerpo_formateado}-{dv}"

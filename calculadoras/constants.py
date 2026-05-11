"""
calculadoras/constants.py — Identificadores y strings fijos de las calcs.

Centralizados para que no haya magic strings dispersos por views/templates.
"""

# Claves canónicas de cada calculadora (usadas en URLs, templates y email).
CALC_IVA = "iva"
CALC_PRECIO_VENTA = "precio_venta"
CALC_HONORARIOS = "honorarios"

CALCULADORAS_VALIDAS = (CALC_IVA, CALC_PRECIO_VENTA, CALC_HONORARIOS)

# Asuntos de email — texto fijo, no template del usuario.
ASUNTOS_EMAIL = {
    CALC_IVA:           "Tu cálculo de IVA · FácilGestión",
    CALC_PRECIO_VENTA:  "Tu cálculo de Precio de Venta · FácilGestión",
    CALC_HONORARIOS:    "Tu cálculo de Boleta de Honorarios · FácilGestión",
}

# Nombres descriptivos para mostrar en UI / PDF.
NOMBRES_DISPLAY = {
    CALC_IVA:           "Calculadora de IVA",
    CALC_PRECIO_VENTA:  "Calculadora de Precio de Venta",
    CALC_HONORARIOS:    "Calculadora de Boleta de Honorarios",
}

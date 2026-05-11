"""
config/tributario.py — Constantes tributarias chilenas.

⚠ REVISIÓN ANUAL OBLIGATORIA. Cada cambio aquí debe llevar:
   - Fecha de verificación
   - Fuente (link a SII o ley)
   - Nota del próximo cambio conocido

Última verificación: 2026-05-11 contra SII Chile y Ley 21.133.
"""
from decimal import Decimal


# ── IVA ──────────────────────────────────────────────────────────────────────
# Tasa fija establecida en el DL 825. No ha cambiado desde 1990.
# Fuente: https://www.sii.cl/normativa_legislacion/ley_iva.pdf
IVA_TASA = Decimal("0.19")


# ── Boleta de honorarios — retención ─────────────────────────────────────────
# Ley 21.133 (2019) escalonó las retenciones para autónomos:
#   2020: 10.75%  → 2025: 14.50%  → 2026: 15.25%
#   2027: 16%     → 2028: 17%     (cambia a la tasa final)
#
# Fuente:
#   - Ley 21.133, art. 17º transitorio
#   - SII — Tasa de Retención Honorarios:
#     https://www.sii.cl/destacados/honorarios/
#
# TODO 2027-01-15: actualizar a 0.16 y verificar contra SII.
# TODO 2028-01-15: actualizar a 0.17 (tasa final, ya no cambia).
RETENCION_HONORARIOS = Decimal("0.1525")
RETENCION_HONORARIOS_PROXIMO_CAMBIO = "2027-01-01"  # → 0.16


# ── UTM mensual (Unidad Tributaria Mensual) ──────────────────────────────────
# Cambia cada mes según el reajuste del IPC. Para el cálculo del Impuesto
# Único de Segunda Categoría, el SII usa la UTM del mes en que se devengó.
# Fuente mensual: https://www.sii.cl/valores_y_fechas/utm/utm2026.htm
#
# TODO mensual: si nos importa precisión, leer la UTM via API mindicador.cl
# y cachear en Redis. Por ahora hardcoded — exactitud razonable para el caso
# de uso "calculadora rápida".
UTM_VALOR_ACTUAL = Decimal("70000")   # Aprox mayo 2026, actualizar mensualmente


# ── Tramos del Impuesto Único de Segunda Categoría (IGC mensual 2026) ────────
# Tasa marginal por tramo (en UTM). Fórmula: impuesto = base * tasa - rebaja.
# Fuente: SII — Tabla mensual IGC.
#
# Estructura: tuple de (limite_inferior_UTM, limite_superior_UTM_o_None, tasa, rebaja_UTM)
# rebaja en UTM también, para evitar conversión doble.
IGC_TRAMOS_2026 = (
    (Decimal("0"),      Decimal("13.5"),    Decimal("0.00"),    Decimal("0")),
    (Decimal("13.5"),   Decimal("30"),      Decimal("0.04"),    Decimal("0.54")),
    (Decimal("30"),     Decimal("50"),      Decimal("0.08"),    Decimal("1.74")),
    (Decimal("50"),     Decimal("70"),      Decimal("0.135"),   Decimal("4.49")),
    (Decimal("70"),     Decimal("90"),      Decimal("0.23"),    Decimal("11.14")),
    (Decimal("90"),     Decimal("120"),     Decimal("0.304"),   Decimal("17.80")),
    (Decimal("120"),    Decimal("310"),     Decimal("0.35"),    Decimal("23.32")),
    (Decimal("310"),    None,               Decimal("0.40"),    Decimal("38.82")),
)


# ── Cotizaciones previsionales ────────────────────────────────────────────────
# Cargas obligatorias para trabajador dependiente con contrato indefinido.
# Fuente: Superintendencia de Pensiones y Superintendencia de Salud.
AFP_COTIZACION_OBLIGATORIA = Decimal("0.10")   # 10% sobre renta imponible
AFP_COMISION_PROMEDIO = Decimal("0.0104")      # Promedio simple, 2026
SALUD_FONASA = Decimal("0.07")                 # 7% obligatorio Fonasa
SEGURO_CESANTIA_INDEFINIDO = Decimal("0.006")  # 0.6% indefinido (trab.)
SEGURO_CESANTIA_PLAZO_FIJO = Decimal("0.0")    # plazo fijo: lo paga el empleador

# Tope imponible mensual (UF). Sobre este monto no se cotiza.
# Cambia anualmente. Fuente: Superintendencia de Pensiones.
TOPE_IMPONIBLE_UF = Decimal("85.7")   # 2026 aprox.
UF_VALOR_REFERENCIAL = Decimal("39200")  # Aproximado mayo 2026. TODO API mindicador.cl

# Choices de AFPs comunes con sus comisiones (% sobre renta imponible).
# Fuente: Superintendencia de Pensiones — variables, revisar trimestralmente.
AFP_COMISIONES_2026 = (
    ("capital",   "Capital",   Decimal("0.0144")),
    ("cuprum",    "Cuprum",    Decimal("0.0144")),
    ("habitat",   "Habitat",   Decimal("0.0127")),
    ("modelo",    "Modelo",    Decimal("0.0058")),
    ("planvital", "PlanVital", Decimal("0.0116")),
    ("provida",   "ProVida",   Decimal("0.0145")),
    ("uno",       "Uno",       Decimal("0.0049")),
)


# ── Cloudflare Turnstile — URL de verificación server-side ───────────────────
# Endpoint estable documentado por Cloudflare desde el lanzamiento de Turnstile.
# Fuente: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


# ── Branding (centralizado para reuso en templates y PDF) ────────────────────
# Colores extraídos del ERP FácilGestión (static/css del repo principal).
BRAND_COLOR_PRIMARY = "#2563eb"     # Azul principal — botones, headers
BRAND_COLOR_PRIMARY_HOVER = "#1D4ED8"
BRAND_COLOR_DARK = "#0f172a"        # Navy oscuro — textos
BRAND_COLOR_MID = "#1e293b"
BRAND_COLOR_LIGHT = "#475569"       # Gris medio — secundarios
BRAND_COLOR_BG = "#f8fafc"          # Fondo
BRAND_COLOR_SUCCESS = "#22c55e"
BRAND_COLOR_DANGER = "#ef4444"
BRAND_COLOR_WARNING = "#f59e0b"
BRAND_COLOR_INDIGO = "#6366f1"    # Acento secundario para diferenciar cards
BRAND_COLOR_EMERALD = "#10b981"   # Acento alternativo

BRAND_NAME = "FácilGestión"
BRAND_TAGLINE = "ERP modular para PyMEs chilenas"
BRAND_URL = "https://gestion.facilgestion.cl"           # Landing/ERP principal
BRAND_SUBDOMAIN = "https://calculadoras.facilgestion.cl"  # Este proyecto

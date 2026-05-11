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

BRAND_NAME = "FácilGestión"
BRAND_TAGLINE = "ERP modular para PyMEs chilenas"
BRAND_URL = "https://facilgestion.cl"
BRAND_SUBDOMAIN = "https://calculadoras.facilgestion.cl"

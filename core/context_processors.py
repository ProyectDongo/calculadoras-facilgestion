"""
core/context_processors.py — Variables disponibles en todos los templates.
"""
from django.conf import settings
from config import tributario


def brand(_request):
    """Colores, nombre, tagline y URLs de marca."""
    return {
        "BRAND": {
            "name": tributario.BRAND_NAME,
            "tagline": tributario.BRAND_TAGLINE,
            "url": tributario.BRAND_URL,
            "subdomain_url": tributario.BRAND_SUBDOMAIN,
            "color_primary": tributario.BRAND_COLOR_PRIMARY,
            "color_primary_hover": tributario.BRAND_COLOR_PRIMARY_HOVER,
            "color_dark": tributario.BRAND_COLOR_DARK,
            "color_mid": tributario.BRAND_COLOR_MID,
            "color_light": tributario.BRAND_COLOR_LIGHT,
            "color_bg": tributario.BRAND_COLOR_BG,
            "color_success": tributario.BRAND_COLOR_SUCCESS,
            "color_danger": tributario.BRAND_COLOR_DANGER,
            "color_warning": tributario.BRAND_COLOR_WARNING,
        }
    }


def turnstile(_request):
    """Site key de Cloudflare Turnstile para inyectar en templates."""
    return {"TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY}

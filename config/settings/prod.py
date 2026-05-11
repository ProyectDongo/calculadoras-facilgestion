"""
config/settings/prod.py — Configuración de producción.

Endurecimiento sobre base:
    - DEBUG = False (no negociable)
    - HSTS 1 año con preload + subdomains
    - SECURE_PROXY_SSL_HEADER para Cloudflare Tunnel (envía X-Forwarded-Proto)
    - SSL redirect on
    - Cookies SECURE
    - CSP estricta (heredada de base)

Cloudflare Tunnel termina TLS y reenvía a 127.0.0.1:8000.
"""
from .base import *  # noqa: F401,F403

DEBUG = False

# Cloudflare Tunnel ya valida TLS. Confiamos en X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

# HSTS — 1 año, preload, subdominios. Solo activar tras validar todo HTTPS.
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookies
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Static files: WhiteNoise con hashing + compresión gzip/brotli + cache eterno.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

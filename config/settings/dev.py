"""
config/settings/dev.py — Configuración de desarrollo local.

Diferencias vs prod:
    - DEBUG = True (errores con traceback en el navegador)
    - Cookies sin SECURE (HTTP local)
    - HSTS off
    - Email a consola (no SMTP real salvo que se exporten las vars)
    - CSP permite localhost para que el dev server funcione
"""
from .base import *  # noqa: F401,F403
from decouple import config

DEBUG = True

INTERNAL_IPS = ["127.0.0.1"]

# Cookies en HTTP local
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Sin HSTS en dev
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0

# Email a consola por defecto si EMAIL_HOST_PASSWORD no está
if not config("EMAIL_HOST_PASSWORD", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Permitir hosts locales
ALLOWED_HOSTS = ["*"]

"""
config/settings/base.py — Configuración compartida entre dev y prod.

Decisiones arquitectónicas (ver README/SECURITY):
    1. Sin Postgres. La app es stateless: cero PII server-side.
    2. Sessions = signed_cookies (firmadas con SECRET_KEY, sin storage).
    3. Redis SOLO para rate limiting (TTLs cortos, sin PII).
    4. CSP por-vista vía decoradores @csp_update, NO global.
    5. INSTALLED_APPS mínimo: nada de admin/auth (la app es anónima).

NO importar nada de aquí directamente. Importar desde dev.py o prod.py.
"""
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ─── Identidad / hosts ───────────────────────────────────────────────────────
SECRET_KEY = config("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = config(
    "DJANGO_ALLOWED_HOSTS",
    default="calculadoras.facilgestion.cl",
    cast=Csv(),
)


# ─── Apps mínimas ────────────────────────────────────────────────────────────
# Sin contrib.auth, contrib.admin, contrib.contenttypes: la app es anónima.
# Sin contrib.sessions tampoco — usamos signed_cookies pero el módulo no es
# necesario, sólo el middleware que ya está como tal.
INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.humanize",          # formato CLP en templates
    "core.apps.CoreConfig",
    "calculadoras.apps.CalculadorasConfig",
]


# ─── Middleware ──────────────────────────────────────────────────────────────
# Orden importa. CSPMiddleware debe ir DESPUÉS de SecurityMiddleware.
MIDDLEWARE = [
    "core.middleware.CloudflareRealIPMiddleware",      # reescribe REMOTE_ADDR (antes que ratelimit)
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",      # sirve /static/ sin nginx delante
    "csp.middleware.CSPMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SignedCookieSessionMiddleware",   # signed cookies para T&C accept
    "core.middleware.AntiFloodMiddleware",             # rate limit global anti-abuso
    "core.middleware.SecurityHeadersMiddleware",       # Permissions-Policy + COOP
]


# ─── URLs / WSGI ─────────────────────────────────────────────────────────────
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ─── Templates ───────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.static",
                "core.context_processors.brand",        # inyecta colores/logo
                "core.context_processors.turnstile",    # inyecta SITE_KEY
                "core.context_processors.indicadores",  # UF/USD/UTM/IPC para banner
            ],
        },
    },
]


# ─── DB ──────────────────────────────────────────────────────────────────────
# La app NO almacena datos. Configuramos un dummy para que Django no chille.
# `django.db.backends.dummy` lanza error si alguien intenta usarlo → desired.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.dummy",
    }
}


# ─── Sesiones: signed cookies (sin storage server-side) ──────────────────────
# La única cosa que guardamos en sesión es el flag de aceptación de T&C.
# 4KB de límite es más que suficiente.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_NAME = "calc_session"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30       # 30 días para que no pidan T&C cada vez
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# SESSION_COOKIE_SECURE → ver prod.py


# ─── Cache / rate limiting (Redis) ───────────────────────────────────────────
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 3,
            "SOCKET_TIMEOUT": 3,
            "IGNORE_EXCEPTIONS": True,  # si Redis cae, no tumba la app
        },
        "KEY_PREFIX": "calc",
        "TIMEOUT": 300,
    }
}

# django-ratelimit usa el cache "default" automáticamente.
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = "default"


# ─── Internacionalización ────────────────────────────────────────────────────
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True


# ─── Static files ────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = []  # cada app tiene su static/ subcarpeta (django.contrib.staticfiles lo descubre)
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",  # nada que escribir
    },
    "staticfiles": {
        # En dev usamos StaticFilesStorage (sin hashing). En prod, prod.py
        # cambia a ManifestStaticFilesStorage para cache eterno + cache-bust.
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ─── Email ───────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@facilgestion.cl")
EMAIL_TIMEOUT = 10


# ─── Cloudflare Turnstile ────────────────────────────────────────────────────
TURNSTILE_SITE_KEY = config("TURNSTILE_SITE_KEY", default="")
TURNSTILE_SECRET_KEY = config("TURNSTILE_SECRET_KEY", default="")


# ─── Security headers base (refinados en prod.py) ────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ─── CSP (django-csp 4.x — NO usar CSP_* legacy) ─────────────────────────────
# Política base: solo self + Turnstile. Inline script/style sólo se permite
# en vistas concretas con @csp_update si lo necesitan (NO aquí).
from csp.constants import SELF, NONE  # noqa: E402

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        # 'unsafe-inline': script de config de Tailwind CDN.
        # 'unsafe-eval':   Alpine.js usa new Function() para sus directivas (x-data, x-model, @click).
        # Tailwind CDN + Turnstile widget loader.
        # DEUDA TÉCNICA FASE 9:
        #   - cambiar Tailwind CDN → build standalone (quita 'unsafe-inline')
        #   - cambiar alpine.min.js → @alpinejs/csp build (quita 'unsafe-eval')
        "script-src":  [SELF, "'unsafe-inline'", "'unsafe-eval'", "https://cdn.tailwindcss.com", "https://challenges.cloudflare.com"],
        "style-src":   [SELF, "'unsafe-inline'"],
        "img-src":     [SELF, "data:"],
        "font-src":    [SELF, "data:"],
        "connect-src": [SELF, "https://challenges.cloudflare.com"],
        "frame-src":   ["https://challenges.cloudflare.com"],
        "frame-ancestors": [NONE],
        "form-action": [SELF],
        "base-uri":    [SELF],
        "object-src":  [NONE],
    },
}


# ─── CSRF ────────────────────────────────────────────────────────────────────
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = [
    "https://calculadoras.facilgestion.cl",
]
# CSRF_COOKIE_SECURE → ver prod.py


# ─── Hash salt (para keys efímeras del ratelimiter, NUNCA para PII) ──────────
IP_HASH_SALT = config("IP_HASH_SALT", default="dev-only-salt-change-in-prod")


# ─── Logging ─────────────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "filters": {
        "no_pii": {"()": "core.logging_filters.NoPIIFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["no_pii"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.security": {
            "level": "WARNING", "handlers": ["console"], "propagate": False,
        },
        "django.request": {
            "level": "WARNING", "handlers": ["console"], "propagate": False,
        },
    },
}

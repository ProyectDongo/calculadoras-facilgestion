"""
core/middleware.py — Middleware del proyecto.

    CloudflareRealIPMiddleware     → reescribe REMOTE_ADDR a la IP real
    SignedCookieSessionMiddleware  → habilita sessions cookie-firmadas
    AntiFloodMiddleware            → bloqueo temporal por IP-hash via Redis
    SecurityHeadersMiddleware      → Permissions-Policy + CORP
"""
import json
import logging

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.http import HttpResponse

from core.services.ip_hash import request_ip_hash

logger = logging.getLogger(__name__)


# ── 0. IP real del cliente (REMOTE_ADDR) ─────────────────────────────────────

class CloudflareRealIPMiddleware:
    """
    Reescribe REMOTE_ADDR a la IP real del cliente cuando el request viene por
    Cloudflare Tunnel.

    Necesario porque django-ratelimit con key='ip' lee REMOTE_ADDR directo, y
    en este deploy REMOTE_ADDR es siempre 127.0.0.1 (cloudflared corre en el
    host y reenvía al container). Sin este middleware, todo el tráfico se
    cuenta como una sola IP y dispara los rate limits inmediatamente.

    Confiamos en CF-Connecting-IP / X-Forwarded-For porque el container está
    bind a 127.0.0.1 y solo es alcanzable vía tunnel; un atacante directo
    contra el host tendría que primero comprometer la red local.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
        if cf_ip:
            request.META["REMOTE_ADDR"] = cf_ip.strip()
        else:
            xff = request.META.get("HTTP_X_FORWARDED_FOR")
            if xff:
                request.META["REMOTE_ADDR"] = xff.split(",")[0].strip()
        return self.get_response(request)


# ── 1. Sessions cookie-firmadas ──────────────────────────────────────────────

class SignedCookieSessionMiddleware(SessionMiddleware):
    """
    Hereda el SessionMiddleware estándar; el backend signed_cookies se
    selecciona via SESSION_ENGINE en settings.
    Punto de extensión futuro para validar tamaño de sesión.
    """


# ── 2. Anti-flood (rate limit global con Redis) ──────────────────────────────

# Umbrales por ventana de 5 minutos por IP-hash:
_WINDOW_SECONDS = 5 * 60
_BLOCK_SECONDS = 15 * 60

_LIMITS = {
    "post_total":      30,   # total de requests POST
    "calc_calls":      50,   # llamadas a /api/calcular/
    "captcha_failed":  10,   # tokens turnstile inválidos
}

# Métodos que cuentan para "post_total"
_RATE_LIMITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _key(prefix: str, ip_hash: str) -> str:
    return f"af:{prefix}:{ip_hash}"


def _blocked_key(ip_hash: str) -> str:
    return f"af:blocked:{ip_hash}"


def _incr(prefix: str, ip_hash: str) -> int:
    """Incrementa contador con TTL. Retorna el valor actual."""
    key = _key(prefix, ip_hash)
    try:
        # django-redis expone incr/expire via low-level client
        client = cache.client.get_client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _WINDOW_SECONDS)
        valor, _ = pipe.execute()
        return int(valor)
    except Exception:
        # Si Redis cae, no bloqueamos al usuario (IGNORE_EXCEPTIONS=True ya
        # cubre lectura, esto cubre escritura).
        logger.warning("antiflood: redis incr failed for prefix=%s", prefix)
        return 0


def _is_blocked(ip_hash: str) -> bool:
    try:
        return bool(cache.get(_blocked_key(ip_hash)))
    except Exception:
        return False


def _block(ip_hash: str, reason: str) -> None:
    try:
        cache.set(_blocked_key(ip_hash), reason, _BLOCK_SECONDS)
    except Exception:
        logger.warning("antiflood: redis set failed for block reason=%s", reason)


def registrar_captcha_fallido(request) -> None:
    """
    Llamar desde la view cuando Turnstile devuelve success=False.
    Si supera el límite, queda bloqueado en la siguiente request.
    """
    ip_hash = request_ip_hash(request)
    if _is_blocked(ip_hash):
        return
    valor = _incr("captcha_failed", ip_hash)
    if valor > _LIMITS["captcha_failed"]:
        _block(ip_hash, "captcha_failed")
        logger.warning("antiflood: bloqueo por captcha_failed ip_hash=%s", ip_hash[:8])


def registrar_calculo(request) -> None:
    """Llamar desde la view de /api/calcular/ después del cálculo."""
    ip_hash = request_ip_hash(request)
    if _is_blocked(ip_hash):
        return
    valor = _incr("calc_calls", ip_hash)
    if valor > _LIMITS["calc_calls"]:
        _block(ip_hash, "calc_calls")
        logger.warning("antiflood: bloqueo por calc_calls ip_hash=%s", ip_hash[:8])


class AntiFloodMiddleware:
    """
    Bloquea (HTTP 429) requests de IPs (hasheadas) que superaron el límite
    de POST en una ventana corta, o que ya están en lista negra temporal.

    No toca métodos GET — esos los maneja Cloudflare WAF.

    Si Redis está caído, no bloquea (fail-open) y deja log; preferimos
    UX rota a UX denegada por error de infra.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Bypass total cuando el rate limit está desactivado (dev).
        # En prod RATELIMIT_ENABLE = True (default), el middleware funciona.
        if not getattr(settings, "RATELIMIT_ENABLE", True):
            return self.get_response(request)

        # Sólo monitoreamos métodos mutantes
        if request.method not in _RATE_LIMITED_METHODS:
            return self.get_response(request)

        ip_hash = request_ip_hash(request)

        if _is_blocked(ip_hash):
            return _too_many_requests(_BLOCK_SECONDS)

        valor = _incr("post_total", ip_hash)
        if valor > _LIMITS["post_total"]:
            _block(ip_hash, "post_total")
            logger.warning("antiflood: bloqueo por post_total ip_hash=%s", ip_hash[:8])
            return _too_many_requests(_BLOCK_SECONDS)

        return self.get_response(request)


def _too_many_requests(retry_after_seconds: int) -> HttpResponse:
    """429 con Retry-After. JSON si el request lo pide, HTML si no."""
    body = json.dumps({
        "error": "rate_limited",
        "retry_after_seconds": retry_after_seconds,
    })
    resp = HttpResponse(body, content_type="application/json", status=429)
    resp["Retry-After"] = str(retry_after_seconds)
    return resp


# ── 3. Security headers extra ────────────────────────────────────────────────

class SecurityHeadersMiddleware:
    """
    Headers adicionales no cubiertos por SecurityMiddleware:
      - Permissions-Policy
      - Cross-Origin-Resource-Policy
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response

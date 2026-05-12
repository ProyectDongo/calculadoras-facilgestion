"""
core/services/mindicador.py — Cliente para API pública mindicador.cl.

Obtiene UF y UTM en tiempo real. Cache Redis 24h porque la UF se actualiza
una vez al día y la UTM una vez al mes; no tiene sentido golpear la API en
cada request.

Diseño:
    - Llamadas con timeout corto (3s) para no bloquear el cálculo.
    - Fallback a valores hardcoded de config/tributario.py si la API falla.
    - El cliente nunca lanza excepción: si todo falla, devuelve el fallback.

API doc: https://mindicador.cl/api  (gratis, sin auth, sin rate limit oficial)
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import requests
from django.core.cache import cache

from config.tributario import UF_VALOR_FALLBACK, UTM_VALOR_FALLBACK

logger = logging.getLogger(__name__)

_API_BASE = "https://mindicador.cl/api"
_CACHE_TTL_SECONDS = 24 * 60 * 60   # 24h
_HTTP_TIMEOUT_SECONDS = 3


def _cache_key(indicador: str) -> str:
    return f"mindicador:{indicador}"


def _fetch_remote(indicador: str) -> Optional[Decimal]:
    """Llama mindicador.cl/api/<indicador>. Devuelve None si falla."""
    url = f"{_API_BASE}/{indicador}"
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        serie = data.get("serie") or []
        if not serie:
            return None
        valor_raw = serie[0].get("valor")
        if valor_raw is None:
            return None
        return Decimal(str(valor_raw))
    except (requests.RequestException, ValueError, InvalidOperation, KeyError, IndexError) as exc:
        logger.warning("mindicador: fallo fetch %s: %s", indicador, exc.__class__.__name__)
        return None


def _get_cached_or_fetch(indicador: str, fallback: Decimal) -> Decimal:
    """Lee de cache; si no, hace fetch y cachea; si todo falla, fallback."""
    key = _cache_key(indicador)
    try:
        cached = cache.get(key)
        if cached is not None:
            return Decimal(str(cached))
    except Exception:
        pass   # cache caído → seguimos al fetch

    valor = _fetch_remote(indicador)
    if valor is None:
        return fallback

    try:
        cache.set(key, str(valor), _CACHE_TTL_SECONDS)
    except Exception:
        pass   # cache caído → devolvemos el valor sin cachear

    return valor


def get_uf() -> Decimal:
    """UF del día (en pesos). Fallback a config/tributario.UF_VALOR_FALLBACK."""
    return _get_cached_or_fetch("uf", UF_VALOR_FALLBACK)


def get_utm() -> Decimal:
    """UTM del mes (en pesos). Fallback a config/tributario.UTM_VALOR_FALLBACK."""
    return _get_cached_or_fetch("utm", UTM_VALOR_FALLBACK)

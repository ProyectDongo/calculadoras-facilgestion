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

import datetime
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


def _ultimo_dia_mes_anterior(hoy: datetime.date | None = None) -> datetime.date:
    """Último día calendario del mes pasado. Para liquidaciones del mes M,
    las cotizaciones se calculan con la UF de esta fecha."""
    if hoy is None:
        hoy = datetime.date.today()
    primer_dia_mes_actual = hoy.replace(day=1)
    return primer_dia_mes_actual - datetime.timedelta(days=1)


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


def get_uf_liquidacion() -> Decimal:
    """
    UF para liquidaciones de sueldo: la del ÚLTIMO día del mes anterior.

    Esta es la UF que el SII/AFP/Isapres exigen para calcular las
    cotizaciones del mes en curso. Por ejemplo, para una liquidación de
    mayo 2026 se usa la UF del 30/abril/2026.

    Fallback: si la API falla, devuelve get_uf() (la actual). Esto
    introduce un pequeño error pero permite operar.
    """
    fecha = _ultimo_dia_mes_anterior()
    fecha_str = fecha.strftime("%d-%m-%Y")   # mindicador usa dd-mm-yyyy
    cache_key = f"mindicador:uf_liquidacion:{fecha.isoformat()}"

    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return Decimal(str(cached))
    except Exception:
        pass

    url = f"{_API_BASE}/uf/{fecha_str}"
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        serie = data.get("serie") or []
        if serie:
            valor = Decimal(str(serie[0].get("valor")))
            try:
                cache.set(cache_key, str(valor), _CACHE_TTL_SECONDS)
            except Exception:
                pass
            return valor
    except (requests.RequestException, ValueError, InvalidOperation, KeyError, IndexError) as exc:
        logger.warning("mindicador: fallo UF de %s: %s", fecha_str, exc.__class__.__name__)

    # Fallback: UF actual
    return get_uf()


def get_utm() -> Decimal:
    """UTM del mes (en pesos). Fallback a config/tributario.UTM_VALOR_FALLBACK."""
    return _get_cached_or_fetch("utm", UTM_VALOR_FALLBACK)


def get_dolar() -> Decimal:
    """Dólar observado del día (en pesos). Fallback razonable."""
    return _get_cached_or_fetch("dolar", Decimal("950"))


def get_euro() -> Decimal:
    """Euro del día (en pesos). Fallback razonable."""
    return _get_cached_or_fetch("euro", Decimal("1050"))


def get_ipc() -> Decimal:
    """IPC mensual (% variación). Fallback 0."""
    return _get_cached_or_fetch("ipc", Decimal("0.2"))


def get_indicadores_resumen() -> dict:
    """Snapshot de los 5 principales indicadores para el banner sticky."""
    return {
        "uf":    get_uf(),
        "utm":   get_utm(),
        "dolar": get_dolar(),
        "euro":  get_euro(),
        "ipc":   get_ipc(),
    }

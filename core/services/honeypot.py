"""
core/services/honeypot.py — Anti-bot: honeypot field + tiempo mínimo de submit.

Patrón en views (POST):
    if not honeypot.validar(request):
        return HttpResponseBadRequest(...)        # bot detectado

    if not honeypot.tiempo_suficiente(request):
        return HttpResponseBadRequest(...)        # submit demasiado rápido

Patrón en templates:
    {% load honeypot %}
    {% honeypot_fields %}                          # ← inyecta los 2 inputs
"""
import time
from typing import Final

from django.conf import settings
from django.core.signing import BadSignature, TimestampSigner

# El campo honeypot — los bots tienden a llenar todo input que vean.
HONEYPOT_FIELD_NAME: Final[str] = "website"

# El timestamp firmado del momento en que se renderizó el form.
TIMESTAMP_FIELD_NAME: Final[str] = "ts"

# Tiempo mínimo razonable para que un humano lea y llene un form.
MIN_SUBMIT_SECONDS: Final[float] = 1.5

# Si el form lleva más de esto sin enviarse, asumimos sesión vieja.
MAX_SUBMIT_SECONDS: Final[int] = 60 * 30   # 30 min

_SIGNER_SALT = "calc-honeypot-ts-v1"


def generar_timestamp() -> str:
    """Devuelve un timestamp actual firmado, para meter en hidden field."""
    return TimestampSigner(salt=_SIGNER_SALT).sign(str(int(time.time())))


def validar_honeypot(request) -> bool:
    """
    True si el campo honeypot viene vacío (humano).
    False si viene con cualquier valor (bot).
    """
    valor = request.POST.get(HONEYPOT_FIELD_NAME, "")
    return valor == ""


def tiempo_suficiente(request) -> bool:
    """
    True si pasó al menos MIN_SUBMIT_SECONDS entre render y submit,
    y como máximo MAX_SUBMIT_SECONDS (anti replay viejo).

    False si:
        - falta el campo
        - firma inválida (tampering)
        - tiempo fuera del rango [MIN, MAX]
    """
    firmado = request.POST.get(TIMESTAMP_FIELD_NAME, "")
    if not firmado:
        return False
    try:
        ts_str = TimestampSigner(salt=_SIGNER_SALT).unsign(
            firmado, max_age=MAX_SUBMIT_SECONDS,
        )
        ts = int(ts_str)
    except (BadSignature, ValueError):
        return False

    delta = time.time() - ts
    return MIN_SUBMIT_SECONDS <= delta <= MAX_SUBMIT_SECONDS

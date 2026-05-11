"""
core/services/turnstile.py — Verificación server-side de Cloudflare Turnstile.

Llama a https://challenges.cloudflare.com/turnstile/v0/siteverify con el
token recibido del cliente + el secret_key del servidor.

Documentación:
    https://developers.cloudflare.com/turnstile/get-started/server-side-validation/

Política:
    - timeout corto (3s); si Cloudflare no responde, fail-closed
    - el remoteip es opcional y va hasheado si lo enviamos (no lo enviamos)
    - NO logueamos el token (es de un solo uso pero igual sensible)
"""
import logging
from dataclasses import dataclass
from typing import Optional

import requests
from django.conf import settings

from config.tributario import TURNSTILE_VERIFY_URL

logger = logging.getLogger(__name__)

# Timeout para la llamada a Cloudflare. 3s es generoso; si pasa, hay problema.
_TIMEOUT_SECONDS = 3


@dataclass(frozen=True, slots=True)
class TurnstileResult:
    success: bool
    error_codes: tuple[str, ...] = ()
    hostname: Optional[str] = None
    action: Optional[str] = None
    cdata: Optional[str] = None

    @property
    def failed(self) -> bool:
        return not self.success


def verificar(token: str, *, expected_action: Optional[str] = None) -> TurnstileResult:
    """
    Verifica un token de Turnstile contra Cloudflare.

    Args:
        token: el `cf-turnstile-response` enviado por el cliente.
        expected_action: si se pasa, el response.action debe coincidir.

    Returns:
        TurnstileResult con success=True sólo si:
            - Cloudflare devuelve success=true
            - (opcional) la acción coincide

    Fail-closed: timeouts, errores de red o respuesta no-2xx → success=False.
    """
    if not token or not isinstance(token, str):
        return TurnstileResult(success=False, error_codes=("missing-input-response",))

    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        # Misconfig — falla cerrada y avisa por log (sin filtrar secrets).
        logger.error("turnstile: TURNSTILE_SECRET_KEY no configurado")
        return TurnstileResult(success=False, error_codes=("missing-input-secret",))

    try:
        resp = requests.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": secret, "response": token},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        # No expongas el token en el log
        logger.warning("turnstile: network error: %s", exc.__class__.__name__)
        return TurnstileResult(success=False, error_codes=("network-error",))

    if resp.status_code != 200:
        logger.warning("turnstile: non-200 status: %s", resp.status_code)
        return TurnstileResult(success=False, error_codes=("non-200",))

    try:
        data = resp.json()
    except ValueError:
        logger.warning("turnstile: respuesta no-JSON")
        return TurnstileResult(success=False, error_codes=("invalid-json",))

    result = TurnstileResult(
        success=bool(data.get("success")),
        error_codes=tuple(data.get("error-codes", []) or ()),
        hostname=data.get("hostname"),
        action=data.get("action"),
        cdata=data.get("cdata"),
    )

    if result.success and expected_action and result.action != expected_action:
        logger.warning(
            "turnstile: action mismatch (esperado=%s recibido=%s)",
            expected_action, result.action,
        )
        return TurnstileResult(
            success=False,
            error_codes=("action-mismatch",),
            hostname=result.hostname,
            action=result.action,
        )

    return result

"""
core/forms.py — Mixin reutilizable para forms con anti-bot integrado.

Uso:
    class MiForm(AntiBotFormMixin, forms.Form):
        ...

    # En la view:
    form = MiForm(request.POST, request=request)
    if form.is_valid():
        ...

El mixin valida en este orden (todos al instante, devuelve False al primer fallo):
    1. Honeypot vacío (sino: bot evidente)
    2. Timestamp firmado dentro de [MIN, MAX] segundos
    3. Token Turnstile válido server-side
"""
from django import forms

from core.services import honeypot
from core.services.turnstile import verificar as verificar_turnstile

# Nombre del input que el widget Turnstile setea automáticamente.
TURNSTILE_RESPONSE_FIELD = "cf-turnstile-response"


class AntiBotFormMixin:
    """
    Form mixin que agrega validación anti-bot post-clean.

    Requiere que la view pase el request:
        form = MiForm(request.POST, request=request)
    """

    expected_turnstile_action: str | None = None

    def __init__(self, *args, request=None, **kwargs):
        self._request = request
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if self._request is None:
            # Defensa de programación: si se olvidó pasar el request,
            # la validación anti-bot debe fallar (fail-closed).
            raise forms.ValidationError("Validación anti-bot inalcanzable.")

        # 1. Honeypot
        if not honeypot.validar_honeypot(self._request):
            # Mensaje genérico — no le decimos al bot por qué falló
            raise forms.ValidationError("Validación falló. Recarga e intenta de nuevo.")

        # 2. Tiempo mínimo / máximo
        if not honeypot.tiempo_suficiente(self._request):
            raise forms.ValidationError("Validación falló. Recarga e intenta de nuevo.")

        # 3. Turnstile
        token = self._request.POST.get(TURNSTILE_RESPONSE_FIELD, "")
        resultado = verificar_turnstile(
            token, expected_action=self.expected_turnstile_action,
        )
        if not resultado.success:
            # Registramos el captcha fallido en el contador antiflood
            from core.middleware import registrar_captcha_fallido
            registrar_captcha_fallido(self._request)
            raise forms.ValidationError("Verificación de seguridad falló.")

        return cleaned

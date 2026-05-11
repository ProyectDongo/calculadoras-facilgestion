"""
calculadoras/forms.py — Forms de las 3 calculadoras.

Convención:
    - Form de "cálculo" (no requiere PDF/email): hereda forms.Form puro.
      El cálculo es barato y no creamos lead, no requerimos Turnstile.
    - Form de "descarga/envío": hereda AntiBotFormMixin → exige Turnstile.

El RUT y email del usuario son opcionales y NUNCA se almacenan; sólo se usan
para renderizar el PDF (RUT) o enviarlo (email) y se descartan.
"""
from decimal import Decimal

from django import forms
from django.core.validators import validate_email

from core.forms import AntiBotFormMixin
from core.services import rut as rut_svc


# ─── IVA ─────────────────────────────────────────────────────────────────────

class IVACalcForm(forms.Form):
    """
    Cálculo de IVA en cualquiera de los 2 modos.

    Validación:
        - modo en {neto_a_bruto, bruto_a_neto}
        - monto positivo
    """
    MODO_CHOICES = [
        ("neto_a_bruto", "Neto → Bruto"),
        ("bruto_a_neto", "Bruto → Neto"),
    ]

    modo = forms.ChoiceField(choices=MODO_CHOICES)
    monto = forms.DecimalField(
        min_value=Decimal("0"),
        max_value=Decimal("9999999999"),     # 10 dígitos — suficiente
        max_digits=10,
        decimal_places=0,
    )

    def clean_monto(self):
        # En CLP no manejamos decimales; el form ya valida pero por las dudas
        # quantizamos a entero.
        return Decimal(int(self.cleaned_data["monto"]))


class EnviarOdescargarForm(AntiBotFormMixin, forms.Form):
    """
    Form común para "Descargar PDF" y "Enviar a mi correo".

    Estos endpoints sí requieren Turnstile (lo crítico es el envío de email).
    """
    # Resultado serializado del cálculo, viene del frontend (Alpine).
    # NO confiamos en estos datos — los re-validamos en la view recalculando.
    resultado_json = forms.CharField(max_length=4_000)

    # Tipo de calc (iva | precio_venta | honorarios)
    calculadora = forms.CharField(max_length=20)

    # Email obligatorio sólo en "enviar". Para "descargar" puede venir vacío.
    email = forms.EmailField(required=False)

    # RUT opcional en cualquiera de los 2 casos.
    rut = forms.CharField(required=False, max_length=12)

    # Modo: "descargar" | "enviar"
    accion = forms.ChoiceField(choices=[("descargar", "Descargar"), ("enviar", "Enviar")])

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if not email:
            return ""
        # Django ya validó formato; validate_email es defensivo.
        validate_email(email)
        return email

    def clean_rut(self):
        valor = (self.cleaned_data.get("rut") or "").strip()
        if not valor:
            return ""
        if not rut_svc.validar(valor):
            raise forms.ValidationError("RUT inválido.")
        return rut_svc.normalizar(valor)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("accion") == "enviar" and not cleaned.get("email"):
            raise forms.ValidationError(
                "Email es obligatorio para enviar el PDF por correo.",
            )
        return cleaned

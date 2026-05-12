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
    """Cálculo de IVA en cualquiera de los 2 modos."""
    MODO_CHOICES = [
        ("neto_a_bruto", "Neto → Bruto"),
        ("bruto_a_neto", "Bruto → Neto"),
    ]

    modo = forms.ChoiceField(choices=MODO_CHOICES)
    monto = forms.DecimalField(
        min_value=Decimal("0"),
        max_value=Decimal("9999999999"),
        max_digits=10,
        decimal_places=0,
    )

    def clean_monto(self):
        return Decimal(int(self.cleaned_data["monto"]))


class HonorariosCalcForm(forms.Form):
    """Cálculo de honorarios en cualquiera de los 2 modos."""
    MODO_CHOICES = [
        ("bruto_a_liquido", "Bruto → Líquido"),
        ("liquido_a_bruto", "Líquido → Bruto"),
    ]

    modo = forms.ChoiceField(choices=MODO_CHOICES)
    monto = forms.DecimalField(
        min_value=Decimal("0"),
        max_value=Decimal("9999999999"),
        max_digits=10,
        decimal_places=0,
    )

    def clean_monto(self):
        return Decimal(int(self.cleaned_data["monto"]))


class SueldoCalcForm(forms.Form):
    """Cálculo de sueldo líquido. Soporta ambos sentidos (bruto↔líquido)."""
    MODO_CHOICES = [
        ("bruto_a_liquido", "Bruto → Líquido"),
        ("liquido_a_bruto", "Líquido → Bruto"),
    ]
    modo = forms.ChoiceField(choices=MODO_CHOICES, required=False)
    monto = forms.DecimalField(
        min_value=Decimal("0"), max_value=Decimal("9999999999"),
        max_digits=10, decimal_places=0,
    )
    afp_comision = forms.DecimalField(
        required=False, min_value=Decimal("0"), max_value=Decimal("0.05"),
        max_digits=6, decimal_places=4,
    )
    salud_tipo = forms.ChoiceField(
        choices=[("fonasa", "Fonasa"), ("isapre", "Isapre")],
        required=False,
    )
    salud_isapre_uf = forms.DecimalField(
        required=False, min_value=Decimal("0"), max_value=Decimal("100"),
        max_digits=6, decimal_places=2,
    )
    contrato = forms.ChoiceField(
        choices=[("indefinido", "Indefinido"), ("plazo_fijo", "Plazo fijo")],
        required=False,
    )

    def clean_modo(self):
        return self.cleaned_data.get("modo") or "bruto_a_liquido"

    def clean_monto(self):
        return Decimal(int(self.cleaned_data["monto"]))

    def clean_afp_comision(self):
        v = self.cleaned_data.get("afp_comision")
        return v if v is not None else Decimal("0.0104")

    def clean_salud_tipo(self):
        return self.cleaned_data.get("salud_tipo") or "fonasa"

    def clean_salud_isapre_uf(self):
        v = self.cleaned_data.get("salud_isapre_uf")
        return v if v is not None else Decimal("0")

    def clean_contrato(self):
        return self.cleaned_data.get("contrato") or "indefinido"


class PrecioVentaCalcForm(forms.Form):
    """Cálculo de precio de venta."""
    costo = forms.DecimalField(
        min_value=Decimal("0"), max_value=Decimal("9999999999"),
        max_digits=10, decimal_places=0,
    )
    flete = forms.DecimalField(
        required=False, min_value=Decimal("0"), max_value=Decimal("9999999999"),
        max_digits=10, decimal_places=0,
    )
    porcentaje_utilidad = forms.DecimalField(
        min_value=Decimal("0"), max_value=Decimal("1000"),
        max_digits=6, decimal_places=2,
    )
    comision_tarjeta = forms.DecimalField(
        required=False, min_value=Decimal("0"), max_value=Decimal("99"),
        max_digits=5, decimal_places=2,
    )

    def clean_flete(self):
        v = self.cleaned_data.get("flete")
        return Decimal(int(v)) if v else Decimal("0")

    def clean_comision_tarjeta(self):
        v = self.cleaned_data.get("comision_tarjeta")
        return v if v is not None else Decimal("0")


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

"""
calculadoras/forms.py — Forms de las 3 calculadoras.

Convención:
    - Form de "cálculo" (no requiere PDF/email): hereda forms.Form puro.
      El cálculo es barato y no creamos lead, no requerimos Turnstile.
    - Form de "descarga/envío": hereda AntiBotFormMixin → exige Turnstile.

El RUT y email del usuario son opcionales y NUNCA se almacenan; sólo se usan
para renderizar el PDF (RUT) o enviarlo (email) y se descartan.
"""
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.validators import validate_email

from core.forms import AntiBotFormMixin
from core.services import rut as rut_svc


def _parse_decimal_es(valor) -> Decimal | None:
    """
    Acepta '3,5' y '3.5' como input decimal (locale es-CL usa coma).
    Devuelve None si el valor está vacío o es inválido.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, Decimal):
        return valor
    s = str(valor).strip().replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


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
    # CharField + parse manual porque el locale chileno usa coma como
    # separador decimal y type=number HTML rechaza el punto en ese caso.
    salud_isapre_uf = forms.CharField(required=False, max_length=10)
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
        v = _parse_decimal_es(self.cleaned_data.get("salud_isapre_uf"))
        if v is None:
            return Decimal("0")
        if v < 0 or v > Decimal("100"):
            raise forms.ValidationError("Plan Isapre fuera de rango (0–100 UF).")
        return v

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
    # CharFields para decimales con coma chilena (parse manual en clean_*).
    porcentaje_utilidad = forms.CharField(max_length=10)
    modo_porcentaje = forms.ChoiceField(
        choices=[("markup", "Markup sobre costo"), ("margen", "Margen sobre venta")],
        required=False,
    )
    comision_tarjeta = forms.CharField(required=False, max_length=10)

    def clean_flete(self):
        v = self.cleaned_data.get("flete")
        return Decimal(int(v)) if v else Decimal("0")

    def clean_modo_porcentaje(self):
        return self.cleaned_data.get("modo_porcentaje") or "markup"

    def clean_porcentaje_utilidad(self):
        v = _parse_decimal_es(self.cleaned_data.get("porcentaje_utilidad"))
        if v is None or v < 0:
            raise forms.ValidationError("Porcentaje inválido.")
        if v > Decimal("1000"):
            raise forms.ValidationError("Porcentaje fuera de rango.")
        return v

    def clean_comision_tarjeta(self):
        v = _parse_decimal_es(self.cleaned_data.get("comision_tarjeta"))
        if v is None:
            return Decimal("0")
        if v < 0 or v >= Decimal("100"):
            raise forms.ValidationError("Comisión fuera de rango (0–99).")
        return v


class EnviarOdescargarForm(AntiBotFormMixin, forms.Form):
    """
    Form para "Descargar PDF" y "Enviar a mi correo".

    Ahora capturamos lead obligatorio (email + empresa + acepto_politica).
    Sin estos campos no se entrega el PDF. Cumple Ley 19.628 (consentimiento
    explícito para tratamiento de datos personales).

    Sigue requiriendo Turnstile (anti-bot).
    """
    # ── Datos del cálculo ────────────────────────────────────────────────
    # Resultado serializado del cálculo (Alpine). NO confiamos: re-calculamos.
    resultado_json = forms.CharField(max_length=4_000)
    calculadora    = forms.CharField(max_length=20)
    accion         = forms.ChoiceField(choices=[("descargar", "Descargar"), ("enviar", "Enviar")])

    # ── Datos del lead (todos obligatorios excepto fantasía/rubro/nombre) ──
    email           = forms.EmailField(required=True)
    nombre_contacto = forms.CharField(max_length=120, required=False)
    empresa         = forms.CharField(max_length=200, required=True)
    nombre_fantasia = forms.CharField(max_length=200, required=False)
    rubro           = forms.CharField(max_length=20, required=False)
    rut             = forms.CharField(max_length=12, required=False)

    # ── Consentimiento ───────────────────────────────────────────────────
    acepto_politica  = forms.BooleanField(required=True, error_messages={
        "required": "Debes aceptar la política de privacidad para continuar.",
    })
    acepto_marketing = forms.BooleanField(required=False)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email es obligatorio.")
        validate_email(email)
        return email

    def clean_empresa(self):
        v = (self.cleaned_data.get("empresa") or "").strip()
        if not v:
            raise forms.ValidationError("Empresa es obligatoria.")
        return v

    def clean_nombre_contacto(self):
        return (self.cleaned_data.get("nombre_contacto") or "").strip()

    def clean_nombre_fantasia(self):
        return (self.cleaned_data.get("nombre_fantasia") or "").strip()

    def clean_rubro(self):
        return (self.cleaned_data.get("rubro") or "").strip()

    def clean_rut(self):
        valor = (self.cleaned_data.get("rut") or "").strip()
        if not valor:
            return ""
        if not rut_svc.validar(valor):
            raise forms.ValidationError("RUT inválido.")
        return rut_svc.normalizar(valor)

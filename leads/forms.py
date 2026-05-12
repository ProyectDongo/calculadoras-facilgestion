"""
leads/forms.py — Form de captura de datos antes de descargar/enviar.

Validaciones:
    - email obligatorio (formato + dominio razonable)
    - empresa obligatoria
    - rut opcional pero si viene se valida con módulo 11
    - acepto_politica obligatorio (sin él, no creamos lead)
    - acepto_marketing opcional
"""
from django import forms
from django.core.validators import validate_email

from core.services import rut as rut_svc

from .models import Accion, Calculadora, Rubro


class LeadCaptureForm(forms.Form):
    # ── Datos del lead ────────────────────────────────────────────────────
    email           = forms.EmailField(max_length=254)
    nombre_contacto = forms.CharField(max_length=120, required=False)
    empresa         = forms.CharField(max_length=200)
    nombre_fantasia = forms.CharField(max_length=200, required=False)
    rubro           = forms.ChoiceField(choices=Rubro.choices, required=False)
    rut             = forms.CharField(max_length=12, required=False)

    # ── Contexto ──────────────────────────────────────────────────────────
    calculadora = forms.ChoiceField(choices=Calculadora.choices)
    accion      = forms.ChoiceField(choices=Accion.choices)

    # ── Consentimiento ────────────────────────────────────────────────────
    acepto_politica  = forms.BooleanField(required=True)
    acepto_marketing = forms.BooleanField(required=False)

    # ── Limpieza ──────────────────────────────────────────────────────────

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        validate_email(email)
        return email

    def clean_empresa(self):
        return (self.cleaned_data.get("empresa") or "").strip()

    def clean_nombre_contacto(self):
        return (self.cleaned_data.get("nombre_contacto") or "").strip()

    def clean_nombre_fantasia(self):
        return (self.cleaned_data.get("nombre_fantasia") or "").strip()

    def clean_rut(self):
        valor = (self.cleaned_data.get("rut") or "").strip()
        if not valor:
            return ""
        if not rut_svc.validar(valor):
            raise forms.ValidationError("RUT inválido.")
        return rut_svc.normalizar(valor)

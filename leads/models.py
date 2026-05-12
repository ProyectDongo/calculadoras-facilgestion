"""
leads/models.py — Captura de leads que descargan PDF o piden envío por correo.

Diseño:
    - email/nombre/empresa/fantasía/rubro: en claro (necesarios para CRM).
    - rut: cifrado con Fernet (sensible bajo Ley 19.628). Recuperable solo
      con RUT_ENCRYPTION_KEY del .env.
    - acepto_politica: required. Sin él, no creamos el lead.
    - acepto_marketing: opt-in explícito. Si es False, no enviamos promos.
    - ip_hash: SHA-256 de la IP + IP_HASH_SALT. Para correlacionar abuso
      sin guardar la IP en claro.

El acceso al RUT descifrado se hace solo desde un panel admin con
permisos estrictos (TODO fase 3: agregar django-admin con auth).
"""
from __future__ import annotations

import uuid

from django.db import models


# ── Choices ──────────────────────────────────────────────────────────────────

class Calculadora(models.TextChoices):
    IVA          = "iva",          "IVA"
    PRECIO_VENTA = "precio_venta", "Precio de venta"
    HONORARIOS   = "honorarios",   "Honorarios"
    SUELDO       = "sueldo",       "Sueldo líquido"
    COTIZACION   = "cotizacion",   "Cotización"


class Accion(models.TextChoices):
    DESCARGAR = "descargar", "Descargar PDF"
    ENVIAR    = "enviar",    "Enviar por correo"


class Rubro(models.TextChoices):
    """Rubros principales en Chile. No exhaustivo — capturamos free-text
    si no encaja en ninguno, vía OTRO + nota."""
    COMERCIO_RETAIL   = "comercio",       "Comercio / Retail"
    SERVICIOS         = "servicios",      "Servicios profesionales"
    CONSTRUCCION      = "construccion",   "Construcción"
    GASTRONOMIA       = "gastronomia",    "Gastronomía / HoReCa"
    INDUSTRIA         = "industria",      "Industria / Manufactura"
    TRANSPORTE        = "transporte",     "Transporte y logística"
    TECNOLOGIA        = "tecnologia",     "Tecnología / Software"
    SALUD             = "salud",          "Salud"
    EDUCACION         = "educacion",      "Educación"
    AGRICULTURA       = "agricultura",    "Agro / Pesca / Minería"
    INMOBILIARIA      = "inmobiliaria",   "Inmobiliaria / Construcción"
    INDEPENDIENTE     = "independiente",  "Profesional independiente"
    OTRO              = "otro",           "Otro"


# ── Modelo principal ─────────────────────────────────────────────────────────

class Lead(models.Model):
    """Registro de cada captura de datos por descarga o envío de PDF."""

    # Identificación
    id          = models.BigAutoField(primary_key=True)
    uuid        = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at  = models.DateTimeField(auto_now=True)

    # Datos del lead (en claro, salvo rut)
    email           = models.EmailField(max_length=254, db_index=True)
    nombre_contacto = models.CharField(max_length=120, blank=True, default="")
    empresa         = models.CharField(max_length=200)
    nombre_fantasia = models.CharField(max_length=200, blank=True, default="")
    rubro           = models.CharField(max_length=20, choices=Rubro.choices, blank=True, default="")
    rut_encrypted   = models.BinaryField(blank=True, default=b"")

    # Contexto de la captura
    calculadora = models.CharField(max_length=20, choices=Calculadora.choices)
    accion      = models.CharField(max_length=10, choices=Accion.choices)

    # Consentimiento (Ley 19.628)
    acepto_politica   = models.BooleanField(default=False)
    acepto_marketing  = models.BooleanField(default=False)
    politica_version  = models.CharField(max_length=10, default="2026-05", help_text="Versión de T&C aceptada")

    # Telemetría anti-fraude (sin PII)
    ip_hash      = models.CharField(max_length=64, blank=True, default="", db_index=True)
    user_agent   = models.CharField(max_length=300, blank=True, default="")

    # Estado del envío (solo aplica a accion='enviar')
    email_enviado    = models.BooleanField(default=False)
    email_error      = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "leads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "created_at"]),
            models.Index(fields=["calculadora", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.email} · {self.empresa} · {self.calculadora}"

    # ── Helpers ────────────────────────────────────────────────────────────

    def set_rut(self, rut: str) -> None:
        """Cifra y guarda el RUT. Lo deja como bytes en `rut_encrypted`."""
        from core.services.crypto import encrypt_rut
        self.rut_encrypted = encrypt_rut(rut)

    def get_rut(self) -> str:
        """Descifra el RUT. Devuelve "" si falla o está vacío."""
        from core.services.crypto import decrypt_rut
        return decrypt_rut(bytes(self.rut_encrypted) if self.rut_encrypted else b"")

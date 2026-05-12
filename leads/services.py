"""
leads/services.py — Crear leads desde view de captura.
"""
from __future__ import annotations

import logging

from core.services.ip_hash import request_ip_hash

from .models import Lead

logger = logging.getLogger(__name__)


def crear_lead_desde_form(form, request) -> Lead:
    """
    Toma un LeadCaptureForm validado + request HTTP y persiste el Lead.

    El RUT (si vino) se cifra antes de guardar.
    El email/empresa/fantasía/rubro quedan en claro.
    El IP del usuario se hashea y se guarda solo el digest.
    """
    cd = form.cleaned_data

    lead = Lead(
        email=cd["email"],
        nombre_contacto=cd.get("nombre_contacto", ""),
        empresa=cd["empresa"],
        nombre_fantasia=cd.get("nombre_fantasia", ""),
        rubro=cd.get("rubro", ""),
        calculadora=cd["calculadora"],
        accion=cd["accion"],
        acepto_politica=cd["acepto_politica"],
        acepto_marketing=cd.get("acepto_marketing", False),
        ip_hash=request_ip_hash(request),
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
    )

    rut = cd.get("rut", "")
    if rut:
        lead.set_rut(rut)

    lead.save()
    logger.info(
        "lead_creado",
        extra={"lead_uuid": str(lead.uuid), "calc": lead.calculadora, "accion": lead.accion},
    )
    return lead

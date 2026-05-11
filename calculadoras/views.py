"""
calculadoras/views.py — Vistas y endpoints API.

Estructura:
    landing                GET  /calculadoras/
    iva                    GET  /calculadoras/iva/
    precio_venta           GET  /calculadoras/precio-venta/   (stub)
    honorarios             GET  /calculadoras/honorarios/     (stub)

    api_calcular_iva       POST /api/calcular/iva/            (HTMX, retorna partial)
    api_pdf                POST /api/pdf/                     (descarga)
    api_enviar             POST /api/enviar/                  (email)
"""
import json
import logging
from datetime import datetime

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.timezone import now as tz_now
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from calculadoras.constants import (
    CALC_IVA, CALCULADORAS_VALIDAS, NOMBRES_DISPLAY,
)
from calculadoras.forms import EnviarOdescargarForm, IVACalcForm
from calculadoras.services_iva import calcular_desde_bruto, calcular_desde_neto
from core.middleware import registrar_calculo
from core.services.email_sender import enviar_calculo
from core.services.pdf import render_pdf

logger = logging.getLogger(__name__)


# ─── Páginas HTML ────────────────────────────────────────────────────────────

@require_GET
def landing(request):
    """Landing pública con 3 cards: IVA, Precio Venta, Honorarios."""
    return render(request, "calculadoras/landing.html", {
        "calculadoras": [
            {
                "key": "iva",
                "nombre": NOMBRES_DISPLAY["iva"],
                "url_name": "calc_iva",
                "descripcion": "Convierte montos netos a brutos y viceversa con la tasa vigente del 19%.",
                "icono": "%",
            },
            {
                "key": "precio_venta",
                "nombre": NOMBRES_DISPLAY["precio_venta"],
                "url_name": "calc_precio_venta",
                "descripcion": "Calcula el precio de venta sugerido a partir del costo, flete y utilidad deseada.",
                "icono": "$",
            },
            {
                "key": "honorarios",
                "nombre": NOMBRES_DISPLAY["honorarios"],
                "url_name": "calc_honorarios",
                "descripcion": "Convierte bruto a líquido con la retención vigente del 15,25% (Ley 21.133).",
                "icono": "📑",
            },
        ],
    })


@require_GET
def iva(request):
    return render(request, "calculadoras/iva.html", {
        "calc_key": CALC_IVA,
        "nombre": NOMBRES_DISPLAY[CALC_IVA],
    })


@require_GET
def precio_venta(request):
    return render(request, "calculadoras/proximamente.html", {
        "nombre": NOMBRES_DISPLAY["precio_venta"],
    })


@require_GET
def honorarios(request):
    return render(request, "calculadoras/proximamente.html", {
        "nombre": NOMBRES_DISPLAY["honorarios"],
    })


# ─── API: calcular ───────────────────────────────────────────────────────────

@require_POST
@ratelimit(key="ip", rate="60/m", method="POST", block=True)
def api_calcular_iva(request):
    """
    POST {modo, monto} → partial HTMX con resultado.
    No requiere Turnstile (es cálculo barato). Sí rate-limit por IP.
    """
    form = IVACalcForm(request.POST)
    if not form.is_valid():
        return HttpResponse(
            "<div class='text-red-600 text-sm'>Datos inválidos.</div>",
            status=400,
        )

    modo  = form.cleaned_data["modo"]
    monto = form.cleaned_data["monto"]

    if modo == "neto_a_bruto":
        r = calcular_desde_neto(monto)
    else:
        r = calcular_desde_bruto(monto)

    # Métrica antiflood (no almacena nada del cálculo)
    registrar_calculo(request)

    return render(request, "calculadoras/_resultado_iva.html", {"r": r})


# ─── API: PDF / Enviar ───────────────────────────────────────────────────────

def _recalcular_iva(payload: dict):
    """Re-cálculo defensivo desde inputs serializados."""
    modo = payload.get("modo")
    monto = payload.get("monto")
    if modo == "neto_a_bruto":
        return calcular_desde_neto(monto)
    if modo == "bruto_a_neto":
        return calcular_desde_bruto(monto)
    raise ValueError("Modo inválido.")


def _generar_pdf_iva(payload: dict, *, rut: str = "") -> tuple[bytes, str]:
    """Renderiza PDF de IVA. Devuelve (bytes, filename)."""
    r = _recalcular_iva(payload)
    ts = tz_now()
    contexto = {
        "r": r,
        "rut": rut,
        "generado_en": ts,
        "doc_titulo": "Cálculo de IVA",
    }
    pdf_bytes = render_pdf("calculadoras/pdf/iva.html", contexto)
    filename = f"facilgestion-iva-{ts.strftime('%Y%m%d-%H%M%S')}.pdf"
    return pdf_bytes, filename


@require_POST
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def api_pdf(request):
    """POST → descarga directa del PDF."""
    form = EnviarOdescargarForm(request.POST, request=request)
    if not form.is_valid():
        # No filtrar mensajes de error (pueden filtrar info del antibot)
        return JsonResponse({"error": "validation_failed"}, status=400)

    calc = form.cleaned_data["calculadora"]
    if calc not in CALCULADORAS_VALIDAS:
        return JsonResponse({"error": "calc_invalida"}, status=400)

    try:
        payload = json.loads(form.cleaned_data["resultado_json"])
    except json.JSONDecodeError:
        return JsonResponse({"error": "payload_invalido"}, status=400)

    if calc != CALC_IVA:
        return JsonResponse({"error": "calc_no_implementada"}, status=501)

    pdf_bytes, filename = _generar_pdf_iva(payload, rut=form.cleaned_data["rut"])

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(pdf_bytes))
    return response


@require_POST
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@ratelimit(key="post:email", rate="15/h", method="POST", block=True)
def api_enviar(request):
    """POST → envía PDF por email. Email obligatorio. Sin retención."""
    form = EnviarOdescargarForm(request.POST, request=request)
    if not form.is_valid():
        return JsonResponse({"error": "validation_failed"}, status=400)

    calc = form.cleaned_data["calculadora"]
    if calc != CALC_IVA:
        return JsonResponse({"error": "calc_no_implementada"}, status=501)

    try:
        payload = json.loads(form.cleaned_data["resultado_json"])
    except json.JSONDecodeError:
        return JsonResponse({"error": "payload_invalido"}, status=400)

    email = form.cleaned_data["email"]
    if not email:
        return JsonResponse({"error": "email_requerido"}, status=400)

    pdf_bytes, pdf_filename = _generar_pdf_iva(payload, rut=form.cleaned_data["rut"])
    r = _recalcular_iva(payload)

    contexto = {
        "r": r,
        "subject": "Tu cálculo de IVA",
        "generado_en": tz_now(),
    }
    html_body = render(request, "email/calculo_iva.html", contexto).content.decode("utf-8")
    text_body = render(request, "email/calculo_iva.txt", contexto).content.decode("utf-8")

    ok = enviar_calculo(
        to_email=email,
        calculadora=CALC_IVA,
        html_body=html_body,
        text_body=text_body,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
    )
    if not ok:
        return JsonResponse({"error": "email_send_failed"}, status=502)
    return JsonResponse({"ok": True})


# ─── Páginas legales (placeholders fase 7) ───────────────────────────────────

@require_GET
def privacidad(request):
    return render(request, "calculadoras/privacidad.html")

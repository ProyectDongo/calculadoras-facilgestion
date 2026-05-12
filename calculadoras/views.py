"""
calculadoras/views.py — Vistas y endpoints API de las 3 calculadoras.

Convención de dispatch:
    Cada calc tiene su propio (página + endpoint cálculo + template PDF + email).
    El endpoint api_pdf / api_enviar es UN sólo handler que despacha por
    `calculadora` (recibido del form) a la lógica correspondiente.
"""
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils.timezone import now as tz_now
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from calculadoras.constants import (
    CALC_HONORARIOS, CALC_IVA, CALC_PRECIO_VENTA, CALC_SUELDO,
    CALCULADORAS_VALIDAS, NOMBRES_DISPLAY,
)
from calculadoras.forms import (
    EnviarOdescargarForm, HonorariosCalcForm, IVACalcForm, PrecioVentaCalcForm,
    SueldoCalcForm,
)
from calculadoras.services_honorarios import (
    calcular_desde_bruto as honorarios_bruto,
    calcular_desde_liquido as honorarios_liquido,
)
from calculadoras.services_iva import calcular_desde_bruto, calcular_desde_neto
from calculadoras.services_precio_venta import calcular as calc_precio_venta
from calculadoras.services_sueldo import calcular as calc_sueldo
from core.middleware import registrar_calculo
from core.services.email_sender import enviar_calculo
from core.services.pdf import render_pdf
from leads.services import crear_lead_desde_form as _crear_lead

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PÁGINAS
# ═══════════════════════════════════════════════════════════════════════════════

@require_GET
def landing(request):
    """Landing pública con las 4 cards de calculadoras."""
    return render(request, "calculadoras/landing.html", {
        "calculadoras": [
            {
                "key": "iva",
                "nombre": NOMBRES_DISPLAY["iva"],
                "url_name": "calc_iva",
                "descripcion": "Convierte montos netos a brutos y viceversa con la tasa vigente del 19%.",
                "tasa_display": "19%",
                "tasa_label":   "IVA",
                "ejemplo_input":  "$1.000.000",
                "ejemplo_output": "$1.190.000",
                "ejemplo_etiqueta": "Neto → Bruto",
                "color_tw": "blue",
                "disponible": True,
                "icono_svg": "calculator",
            },
            {
                "key": "precio_venta",
                "nombre": NOMBRES_DISPLAY["precio_venta"],
                "url_name": "calc_precio_venta",
                "descripcion": "Calcula el precio sugerido a partir del costo, flete y utilidad deseada. Crea listas para cotizaciones.",
                "tasa_display": "+30%",
                "tasa_label":   "Markup ejemplo",
                "ejemplo_input":  "Costo $12.000",
                "ejemplo_output": "Venta $18.564",
                "ejemplo_etiqueta": "Costo → Precio con IVA",
                "color_tw": "emerald",
                "disponible": True,
                "icono_svg": "tag",
            },
            {
                "key": "honorarios",
                "nombre": NOMBRES_DISPLAY["honorarios"],
                "url_name": "calc_honorarios",
                "descripcion": "Convierte bruto a líquido con la retención vigente del 15,25% (Ley 21.133).",
                "tasa_display": "15,25%",
                "tasa_label":   "Retención 2026",
                "ejemplo_input":  "$1.000.000",
                "ejemplo_output": "$847.500",
                "ejemplo_etiqueta": "Bruto → Líquido",
                "color_tw": "indigo",
                "disponible": True,
                "icono_svg": "document",
            },
            {
                "key": "sueldo",
                "nombre": NOMBRES_DISPLAY["sueldo"],
                "url_name": "calc_sueldo",
                "descripcion": "Calcula tu sueldo líquido con AFP, salud (Fonasa/Isapre), cesantía e impuesto IGC 2026.",
                "tasa_display": "Líquido",
                "tasa_label":   "Bruto → Mano",
                "ejemplo_input":  "$1.500.000 bruto",
                "ejemplo_output": "$1.209.384 líquido",
                "ejemplo_etiqueta": "Trabajador dependiente",
                "color_tw": "rose",
                "disponible": True,
                "icono_svg": "wallet",
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
def honorarios(request):
    return render(request, "calculadoras/honorarios.html", {
        "calc_key": CALC_HONORARIOS,
        "nombre": NOMBRES_DISPLAY[CALC_HONORARIOS],
    })


@require_GET
def precio_venta(request):
    from config.tributario import COMISIONES_TARJETA_2026
    return render(request, "calculadoras/precio_venta.html", {
        "calc_key": CALC_PRECIO_VENTA,
        "nombre": NOMBRES_DISPLAY[CALC_PRECIO_VENTA],
        "COMISIONES_TARJETA": COMISIONES_TARJETA_2026,
    })


@require_GET
def sueldo(request):
    from config.tributario import AFP_COMISIONES_2026, TOPE_IMPONIBLE_UF
    from core.services.mindicador import get_utm
    # Tabla AFP con comisión expresada como porcentaje display (ej "1.44")
    afps = [
        {
            "key": k,
            "nombre": n,
            "comision": str(c),
            "comision_pct": (f"{c * 100:.2f}".rstrip("0").rstrip(".") or "0"),
        }
        for k, n, c in AFP_COMISIONES_2026
    ]
    return render(request, "calculadoras/sueldo.html", {
        "calc_key": CALC_SUELDO,
        "nombre": NOMBRES_DISPLAY[CALC_SUELDO],
        "afps": afps,
        "TOPE_IMPONIBLE_UF": TOPE_IMPONIBLE_UF,
        "UTM_VALOR": get_utm(),
    })


@require_GET
def cotizacion(request):
    """Página que renderiza la lista de productos guardada en localStorage."""
    return render(request, "calculadoras/cotizacion.html")


@require_GET
def glosario(request):
    return render(request, "calculadoras/glosario.html")


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS DE CÁLCULO (HTMX partials)
# ═══════════════════════════════════════════════════════════════════════════════

def _error_partial(msg: str = "Datos inválidos.") -> HttpResponse:
    return HttpResponse(
        f"<div class='text-red-600 text-sm'>{msg}</div>",
        status=400,
    )


def _payload_iva(r) -> str:
    """JSON serializado para el atributo data-resultado (siempre . decimal)."""
    monto = int(r.neto) if r.modo == "neto_a_bruto" else int(r.bruto)
    return json.dumps({
        "modo":  r.modo,
        "monto": monto,
        "neto":  int(r.neto),
        "iva":   int(r.iva),
        "bruto": int(r.bruto),
    })


def _payload_honorarios(r) -> str:
    monto = int(r.bruto) if r.modo == "bruto_a_liquido" else int(r.liquido)
    return json.dumps({
        "modo":      r.modo,
        "monto":     monto,
        "bruto":     int(r.bruto),
        "retencion": int(r.retencion),
        "liquido":   int(r.liquido),
    })


def _payload_precio_venta(r) -> str:
    return json.dumps({
        "costo":                int(r.costo),
        "flete":                int(r.flete),
        "porcentaje_utilidad":  float(r.porcentaje_markup),
        "modo_porcentaje":      r.modo_porcentaje,
        "comision_tarjeta":     float(r.comision_tarjeta_pct),
        "costo_total":          int(r.costo_total),
        "utilidad":             int(r.utilidad),
        "precio_neto":          int(r.precio_neto),
        "iva":                  int(r.iva),
        "precio_con_iva":       int(r.precio_con_iva),
        "precio_tarjeta":       int(r.precio_tarjeta),
        "recargo_tarjeta":      int(r.recargo_tarjeta),
        "margen_real_pct":      float(r.margen_real_pct),
    })


def _payload_sueldo(r) -> str:
    return json.dumps({
        "bruto":             int(r.bruto),
        "renta_imponible":   int(r.renta_imponible),
        "afp_total":         int(r.afp_total),
        "afp_obligatoria":   int(r.afp_obligatoria),
        "afp_comision":      int(r.afp_comision),
        "afp_comision_pct":  float(r.afp_comision_pct),
        "salud":             int(r.salud),
        "salud_tipo":        r.salud_tipo,
        "cesantia":          int(r.cesantia),
        "cesantia_pct":      float(r.cesantia_pct),
        "base_igc":          int(r.base_igc),
        "igc":               int(r.igc),
        "liquido":           int(r.liquido),
        "total_descuentos":  int(r.total_descuentos),
        "modo":              r.modo,
        "utm_usada":         int(r.utm_usada),
        "uf_usada":          int(r.uf_usada),
    })


@require_POST
@ratelimit(key="ip", rate="60/m", method="POST", block=True)
def api_calcular_iva(request):
    form = IVACalcForm(request.POST)
    if not form.is_valid():
        return _error_partial()

    modo = form.cleaned_data["modo"]
    monto = form.cleaned_data["monto"]
    r = calcular_desde_neto(monto) if modo == "neto_a_bruto" else calcular_desde_bruto(monto)
    registrar_calculo(request)
    return render(request, "calculadoras/_resultado_iva.html", {
        "r": r, "r_json": _payload_iva(r),
    })


@require_POST
@ratelimit(key="ip", rate="60/m", method="POST", block=True)
def api_calcular_honorarios(request):
    form = HonorariosCalcForm(request.POST)
    if not form.is_valid():
        return _error_partial()

    modo = form.cleaned_data["modo"]
    monto = form.cleaned_data["monto"]
    r = honorarios_bruto(monto) if modo == "bruto_a_liquido" else honorarios_liquido(monto)
    registrar_calculo(request)
    return render(request, "calculadoras/_resultado_honorarios.html", {
        "r": r, "r_json": _payload_honorarios(r),
    })


@require_POST
@ratelimit(key="ip", rate="60/m", method="POST", block=True)
def api_calcular_precio_venta(request):
    form = PrecioVentaCalcForm(request.POST)
    if not form.is_valid():
        return _error_partial()

    r = calc_precio_venta(
        costo=form.cleaned_data["costo"],
        flete=form.cleaned_data["flete"],
        porcentaje_utilidad=form.cleaned_data["porcentaje_utilidad"],
        modo_porcentaje=form.cleaned_data["modo_porcentaje"],
        comision_tarjeta=form.cleaned_data["comision_tarjeta"],
    )
    registrar_calculo(request)
    return render(request, "calculadoras/_resultado_precio_venta.html", {
        "r": r, "r_json": _payload_precio_venta(r),
    })


@require_POST
@ratelimit(key="ip", rate="60/m", method="POST", block=True)
def api_calcular_sueldo(request):
    form = SueldoCalcForm(request.POST)
    if not form.is_valid():
        return _error_partial()

    r = calc_sueldo(
        form.cleaned_data["monto"],
        modo=form.cleaned_data["modo"],
        afp_comision=form.cleaned_data["afp_comision"],
        salud_tipo=form.cleaned_data["salud_tipo"],
        salud_isapre_uf=form.cleaned_data["salud_isapre_uf"],
        contrato=form.cleaned_data["contrato"],
    )
    registrar_calculo(request)

    # Inputs originales en el payload para que PDF/email puedan re-calcular
    payload = json.loads(_payload_sueldo(r))
    payload["afp_comision_ratio"] = float(form.cleaned_data["afp_comision"])
    payload["salud_isapre_uf"]    = float(form.cleaned_data["salud_isapre_uf"])
    payload["contrato"]           = form.cleaned_data["contrato"]

    return render(request, "calculadoras/_resultado_sueldo.html", {
        "r": r, "r_json": json.dumps(payload),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DISPATCH para PDF / EMAIL
# ═══════════════════════════════════════════════════════════════════════════════

def _recalcular(calc: str, payload: dict):
    """Re-cálculo defensivo desde inputs serializados (NO confiamos en outputs cliente)."""
    if calc == CALC_IVA:
        modo = payload.get("modo")
        monto = payload.get("monto")
        if modo == "neto_a_bruto":
            return calcular_desde_neto(monto)
        if modo == "bruto_a_neto":
            return calcular_desde_bruto(monto)
        raise ValueError("Modo IVA inválido.")

    if calc == CALC_HONORARIOS:
        modo = payload.get("modo")
        monto = payload.get("monto")
        if modo == "bruto_a_liquido":
            return honorarios_bruto(monto)
        if modo == "liquido_a_bruto":
            return honorarios_liquido(monto)
        raise ValueError("Modo Honorarios inválido.")

    if calc == CALC_PRECIO_VENTA:
        return calc_precio_venta(
            costo=payload.get("costo"),
            flete=payload.get("flete", 0),
            porcentaje_utilidad=payload.get("porcentaje_utilidad"),
            modo_porcentaje=payload.get("modo_porcentaje", "markup"),
            comision_tarjeta=payload.get("comision_tarjeta", 0),
        )

    if calc == CALC_SUELDO:
        from decimal import Decimal
        return calc_sueldo(
            payload.get("bruto"),
            modo="bruto_a_liquido",   # PDF/email siempre recalcula desde bruto guardado
            afp_comision=Decimal(str(payload.get("afp_comision_ratio", "0.0104"))),
            salud_tipo=payload.get("salud_tipo", "fonasa"),
            salud_isapre_uf=Decimal(str(payload.get("salud_isapre_uf", "0"))),
            contrato=payload.get("contrato", "indefinido"),
        )

    raise ValueError(f"Calc desconocida: {calc!r}")


# Mapa calc → (template_pdf, slug_filename, template_email_html, template_email_txt)
_RENDER_CONFIG = {
    CALC_IVA: (
        "calculadoras/pdf/iva.html", "iva",
        "email/calculo_iva.html", "email/calculo_iva.txt",
        "Cálculo de IVA",
    ),
    CALC_HONORARIOS: (
        "calculadoras/pdf/honorarios.html", "honorarios",
        "email/calculo_honorarios.html", "email/calculo_honorarios.txt",
        "Cálculo de Boleta de Honorarios",
    ),
    CALC_PRECIO_VENTA: (
        "calculadoras/pdf/precio_venta.html", "precio-venta",
        "email/calculo_precio_venta.html", "email/calculo_precio_venta.txt",
        "Cálculo de Precio de Venta",
    ),
    CALC_SUELDO: (
        "calculadoras/pdf/sueldo.html", "sueldo-liquido",
        "email/calculo_sueldo.html", "email/calculo_sueldo.txt",
        "Cálculo de Sueldo Líquido",
    ),
}


def _generar_pdf(calc: str, payload: dict, *, rut: str = "") -> tuple[bytes, str]:
    pdf_template, slug, _, _, doc_titulo = _RENDER_CONFIG[calc]
    r = _recalcular(calc, payload)
    ts = tz_now()
    ctx = {"r": r, "rut": rut, "generado_en": ts, "doc_titulo": doc_titulo}
    pdf_bytes = render_pdf(pdf_template, ctx)
    filename = f"facilgestion-{slug}-{ts.strftime('%Y%m%d-%H%M%S')}.pdf"
    return pdf_bytes, filename


@require_POST
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def api_pdf(request):
    """POST → captura lead + descarga del PDF de la calc indicada."""
    form = EnviarOdescargarForm(request.POST, request=request)
    if not form.is_valid():
        return JsonResponse({"error": "validation_failed", "errors": form.errors.as_json()}, status=400)

    calc = form.cleaned_data["calculadora"]
    if calc not in CALCULADORAS_VALIDAS:
        return JsonResponse({"error": "calc_invalida"}, status=400)

    try:
        payload = json.loads(form.cleaned_data["resultado_json"])
    except json.JSONDecodeError:
        return JsonResponse({"error": "payload_invalido"}, status=400)

    # Persistir lead PRIMERO. Por compliance, sin consentimiento guardado no
    # entregamos el PDF (fail-closed). Si la DB cae, devolvemos 503.
    try:
        _crear_lead(form, request)
    except Exception as exc:
        logger.exception("api_pdf: fallo guardar lead. err=%s", exc.__class__.__name__)
        return JsonResponse({"error": "internal"}, status=503)

    try:
        pdf_bytes, filename = _generar_pdf(calc, payload, rut=form.cleaned_data["rut"])
    except (ValueError, KeyError) as exc:
        logger.warning("api_pdf: payload error calc=%s err=%s", calc, exc.__class__.__name__)
        return JsonResponse({"error": "payload_invalido"}, status=400)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(pdf_bytes))
    return response


@require_POST
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@ratelimit(key="post:email", rate="15/h", method="POST", block=True)
def api_enviar(request):
    """POST → captura lead + genera PDF + envía por email."""
    form = EnviarOdescargarForm(request.POST, request=request)
    if not form.is_valid():
        return JsonResponse({"error": "validation_failed", "errors": form.errors.as_json()}, status=400)

    calc = form.cleaned_data["calculadora"]
    if calc not in CALCULADORAS_VALIDAS:
        return JsonResponse({"error": "calc_invalida"}, status=400)

    email = form.cleaned_data["email"]

    try:
        payload = json.loads(form.cleaned_data["resultado_json"])
    except json.JSONDecodeError:
        return JsonResponse({"error": "payload_invalido"}, status=400)

    # Persistir lead PRIMERO (compliance Ley 19.628). Sin consentimiento guardado
    # no enviamos email.
    try:
        lead = _crear_lead(form, request)
    except Exception as exc:
        logger.exception("api_enviar: fallo guardar lead. err=%s", exc.__class__.__name__)
        return JsonResponse({"error": "internal"}, status=503)

    try:
        pdf_bytes, filename = _generar_pdf(calc, payload, rut=form.cleaned_data["rut"])
        r = _recalcular(calc, payload)
    except (ValueError, KeyError) as exc:
        logger.warning("api_enviar: payload error calc=%s err=%s", calc, exc.__class__.__name__)
        return JsonResponse({"error": "payload_invalido"}, status=400)

    _, _, html_tpl, txt_tpl, _ = _RENDER_CONFIG[calc]
    ctx = {"r": r, "generado_en": tz_now()}
    html_body = render_to_string(html_tpl, ctx, request=request)
    text_body = render_to_string(txt_tpl, ctx, request=request)

    ok = enviar_calculo(
        to_email=email,
        calculadora=calc,
        html_body=html_body,
        text_body=text_body,
        pdf_bytes=pdf_bytes,
        pdf_filename=filename,
    )

    # Actualizar lead con resultado del envío.
    lead.email_enviado = bool(ok)
    if not ok:
        lead.email_error = "smtp_error"
    lead.save(update_fields=["email_enviado", "email_error"])

    if not ok:
        return JsonResponse({"error": "email_send_failed"}, status=502)
    return JsonResponse({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════════
# OTRAS PÁGINAS
# ═══════════════════════════════════════════════════════════════════════════════

@require_GET
def privacidad(request):
    return render(request, "calculadoras/privacidad.html")


# ═══════════════════════════════════════════════════════════════════════════════
# COTIZACIÓN MULTI-ÍTEM (Lista de productos → PDF)
# ═══════════════════════════════════════════════════════════════════════════════

# Schema esperado del request:
#   {
#     "emisor": {"empresa": "...", "rut": "...", "email": "...", "telefono": "..."},
#     "cliente": {"nombre": "...", "rut": "..."},  # opcional
#     "items": [
#         {"descripcion": "...", "cantidad": 1, "precio_unitario": 15600},
#         ...
#     ],
#     "validez_dias": 30,
#     "observaciones": "..."
#   }
#
# Validación defensiva: campos requeridos, items <= 50, longitudes razonables.

_MAX_ITEMS_COTIZACION = 50
_MAX_LEN_TEXTO = 200


def _sanitizar_cotizacion(payload: dict) -> dict:
    """Valida y limpia un payload de cotización recibido del cliente."""
    if not isinstance(payload, dict):
        raise ValueError("Payload inválido.")

    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValueError("La cotización debe tener al menos un producto.")
    if len(items) > _MAX_ITEMS_COTIZACION:
        raise ValueError(f"Máximo {_MAX_ITEMS_COTIZACION} productos por cotización.")

    items_clean = []
    for it in items:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("descripcion", ""))[:_MAX_LEN_TEXTO].strip()
        if not desc:
            continue
        try:
            cantidad = int(float(it.get("cantidad", 1)))
            precio = int(float(it.get("precio_unitario", 0)))
        except (ValueError, TypeError):
            continue
        if cantidad <= 0 or precio < 0:
            continue
        items_clean.append({
            "descripcion": desc,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "subtotal": cantidad * precio,
        })

    if not items_clean:
        raise ValueError("Ningún ítem válido en la cotización.")

    def _trim(d: dict, fields: tuple) -> dict:
        if not isinstance(d, dict):
            return {}
        return {f: str(d.get(f, ""))[:_MAX_LEN_TEXTO].strip() for f in fields}

    emisor = _trim(payload.get("emisor", {}), ("empresa", "rut", "email", "telefono"))
    cliente = _trim(payload.get("cliente", {}), ("nombre", "rut"))

    try:
        validez = int(payload.get("validez_dias", 30))
    except (ValueError, TypeError):
        validez = 30
    validez = max(1, min(validez, 365))

    return {
        "emisor": emisor,
        "cliente": cliente,
        "items": items_clean,
        "subtotal_neto": sum(it["subtotal"] for it in items_clean),
        "validez_dias": validez,
        "observaciones": str(payload.get("observaciones", ""))[:1000].strip(),
    }


@require_POST
@ratelimit(key="ip", rate="10/m", method="POST", block=True)
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def api_cotizacion_pdf(request):
    """Recibe JSON de la lista (vive en localStorage del cliente) y devuelve PDF."""
    form = EnviarOdescargarForm(request.POST, request=request)
    if not form.is_valid():
        return JsonResponse({"error": "validation_failed"}, status=400)

    if form.cleaned_data["calculadora"] != "cotizacion":
        return JsonResponse({"error": "calc_invalida"}, status=400)

    try:
        raw = json.loads(form.cleaned_data["resultado_json"])
        data = _sanitizar_cotizacion(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("cotizacion: payload error %s", exc.__class__.__name__)
        return JsonResponse({"error": "payload_invalido"}, status=400)

    # Calcular totales
    subtotal = data["subtotal_neto"]
    iva = round(subtotal * 0.19)
    total = subtotal + iva

    ts = tz_now()
    ctx = {
        **data,
        "iva":   iva,
        "total": total,
        "generado_en": ts,
        "vence_el":    ts.replace(microsecond=0),  # solo para fecha
        "doc_titulo":  "Cotización",
    }
    pdf_bytes = render_pdf("calculadoras/pdf/cotizacion.html", ctx)
    filename = f"facilgestion-cotizacion-{ts.strftime('%Y%m%d-%H%M%S')}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(pdf_bytes))
    return response

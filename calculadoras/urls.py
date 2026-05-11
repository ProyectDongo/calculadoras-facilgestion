"""calculadoras/urls.py — Rutas de la app pública."""
from django.urls import path

from calculadoras import views

app_name = "calculadoras"

urlpatterns = [
    # ── Páginas HTML ─────────────────────────────────────────────────────────
    path("",                views.landing,         name="landing"),
    path("iva/",            views.iva,             name="calc_iva"),
    path("precio-venta/",   views.precio_venta,    name="calc_precio_venta"),
    path("honorarios/",     views.honorarios,      name="calc_honorarios"),
    path("sueldo/",         views.sueldo,          name="calc_sueldo"),

    path("cotizacion/",     views.cotizacion,      name="cotizacion"),
    path("glosario/",       views.glosario,        name="glosario"),
    path("privacidad/",     views.privacidad,      name="privacidad"),

    # ── APIs de cálculo (HTMX partials) ──────────────────────────────────────
    path("api/calcular/iva/",          views.api_calcular_iva,          name="api_calcular_iva"),
    path("api/calcular/honorarios/",   views.api_calcular_honorarios,   name="api_calcular_honorarios"),
    path("api/calcular/precio-venta/", views.api_calcular_precio_venta, name="api_calcular_precio_venta"),
    path("api/calcular/sueldo/",       views.api_calcular_sueldo,       name="api_calcular_sueldo"),

    # ── APIs de salida (PDF y email) ─────────────────────────────────────────
    path("api/pdf/",                   views.api_pdf,                   name="api_pdf"),
    path("api/enviar/",                views.api_enviar,                name="api_enviar"),
    path("api/cotizacion/pdf/",        views.api_cotizacion_pdf,        name="api_cotizacion_pdf"),
]

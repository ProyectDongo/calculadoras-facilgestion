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
    path("privacidad/",     views.privacidad,      name="privacidad"),

    # ── APIs ─────────────────────────────────────────────────────────────────
    path("api/calcular/iva/", views.api_calcular_iva, name="api_calcular_iva"),
    path("api/pdf/",          views.api_pdf,          name="api_pdf"),
    path("api/enviar/",       views.api_enviar,       name="api_enviar"),
]

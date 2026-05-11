"""
config/urls.py — Routing global.

Fase 1 (setup): solo healthz y redirect raíz.
Fase 2+ añadirá calculadoras.urls.
"""
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import include, path


def healthz(_request):
    """Endpoint de salud sin información sensible."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("", lambda r: redirect("/calculadoras/", permanent=False)),
    path("healthz/", healthz, name="healthz"),
    path("calculadoras/", include("calculadoras.urls")),
    # path("privacidad/",   ...),                            # ← Fase 7
]

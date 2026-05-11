"""
core/services/pdf.py — Render de HTML a PDF con WeasyPrint.

Convenciones:
    - Las plantillas viven en `calculadoras/templates/calculadoras/pdf/`.
    - Las imágenes (logo) se referencian con `{{ logo_path }}` apuntando al
      path absoluto del filesystem. WeasyPrint NO resuelve {% static %}
      (lo trata como ruta absoluta del root y no encuentra el archivo).
    - No tomamos input HTML del usuario — sólo renderizamos templates Django
      con context controlado, que ya están auto-escapados.
"""
from __future__ import annotations

import os
from io import BytesIO
from typing import Mapping, Optional

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string


def _resolve_static(relative_path: str) -> Optional[str]:
    """
    Devuelve el path absoluto del filesystem para un static, o None.

    Estrategia:
        1. `finders.find()` — funciona en dev (busca en app static dirs).
        2. STATIC_ROOT/<path> — para prod después de collectstatic.
    """
    found = finders.find(relative_path)
    if found:
        return found
    fallback = os.path.join(str(settings.STATIC_ROOT), relative_path)
    return fallback if os.path.exists(fallback) else None


def render_pdf(template_name: str, context: Mapping[str, object]) -> bytes:
    """
    Renderiza un template de Django a PDF.

    Inyecta automáticamente al contexto:
        logo_path  — ruta absoluta del logo de la marca.

    Args:
        template_name: ej: "calculadoras/pdf/iva.html"
        context: dict con variables del template.

    Returns:
        bytes del PDF generado.
    """
    from weasyprint import HTML  # import diferido

    enriched_ctx = dict(context)
    enriched_ctx.setdefault("logo_path", _resolve_static("calculadoras/logo.png"))

    html_string = render_to_string(template_name, enriched_ctx)
    base_url = str(settings.STATIC_ROOT)
    buffer = BytesIO()
    HTML(string=html_string, base_url=base_url).write_pdf(target=buffer)
    return buffer.getvalue()

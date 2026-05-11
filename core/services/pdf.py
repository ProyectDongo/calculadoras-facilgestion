"""
core/services/pdf.py — Render de HTML a PDF con WeasyPrint.

Convenciones:
    - Las plantillas viven en `calculadoras/templates/calculadoras/pdf/`.
    - base_url se setea a STATIC_ROOT para que `<img src="/static/...">`
      resuelva contra el filesystem del contenedor (más rápido y privado
      que dejar a WeasyPrint hacer fetches HTTP a sí mismo).
    - No tomamos input HTML del usuario — sólo renderizamos templates Django
      con context controlado, que ya están auto-escapados.
"""
from __future__ import annotations

from io import BytesIO
from typing import Mapping

from django.conf import settings
from django.template.loader import render_to_string


def render_pdf(template_name: str, context: Mapping[str, object]) -> bytes:
    """
    Renderiza un template de Django a PDF.

    Args:
        template_name: ruta relativa al template, ej:
            "calculadoras/pdf/iva.html"
        context: dict con variables del template.

    Returns:
        bytes del PDF generado.

    Notas:
        - Import diferido de WeasyPrint para no penalizar el arranque del
          worker si no se usa PDF.
        - base_url apunta al filesystem (STATIC_ROOT) para que <link>/<img>
          con paths /static/... resuelvan localmente sin HTTP fetch.
    """
    from weasyprint import HTML  # import diferido

    html_string = render_to_string(template_name, dict(context))
    base_url = str(settings.STATIC_ROOT)
    buffer = BytesIO()
    HTML(string=html_string, base_url=base_url).write_pdf(target=buffer)
    return buffer.getvalue()

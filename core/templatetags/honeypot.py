"""
core/templatetags/honeypot.py — Tag para inyectar los hidden fields anti-bot.

Uso en template:
    {% load honeypot %}
    <form method="post" ...>
        {% csrf_token %}
        {% honeypot_fields %}
        ...
    </form>
"""
from django import template
from django.utils.safestring import mark_safe

from core.services import honeypot as svc

register = template.Library()


@register.simple_tag
def honeypot_fields() -> str:
    """
    Inyecta dos inputs:
        - <input name="website">  honeypot oculto con CSS/aria-hidden
        - <input name="ts">       timestamp firmado del render
    """
    ts = svc.generar_timestamp()
    html = (
        f'<div aria-hidden="true" style="position:absolute;left:-9999px;'
        f'top:-9999px;height:0;width:0;overflow:hidden">'
        f'<label for="hp_website">No completar este campo</label>'
        f'<input type="text" id="hp_website" name="{svc.HONEYPOT_FIELD_NAME}" '
        f'tabindex="-1" autocomplete="off" value="">'
        f'</div>'
        f'<input type="hidden" name="{svc.TIMESTAMP_FIELD_NAME}" value="{ts}">'
    )
    return mark_safe(html)

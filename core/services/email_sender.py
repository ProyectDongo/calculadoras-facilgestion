"""
core/services/email_sender.py — Envío de email con PDF adjunto.

API pública:
    enviar_calculo(to_email, calculadora, html_body, text_body, pdf_bytes)

Política:
    - multipart/alternative (text + html) con adjunto application/pdf
    - asunto fijo por calculadora (texto, no template del usuario)
    - NO logueamos el email ni el body (NoPIIFilter ayuda, pero por las
      dudas el log queda en boolean éxito/fracaso)
    - timeout corto (settings.EMAIL_TIMEOUT)
"""
import logging
from email.mime.base import MIMEBase
from email import encoders

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from calculadoras.constants import ASUNTOS_EMAIL  # ← creado al final de fase 2

logger = logging.getLogger(__name__)


def enviar_calculo(
    *,
    to_email: str,
    calculadora: str,
    html_body: str,
    text_body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> bool:
    """
    Envía un cálculo por email con el PDF adjunto.

    Args:
        to_email: destinatario (sólo se le envía, no se almacena).
        calculadora: clave en ASUNTOS_EMAIL ('iva', 'precio_venta', 'honorarios').
        html_body: cuerpo HTML completo (ya renderizado).
        text_body: cuerpo plain-text alternativo.
        pdf_bytes: bytes del PDF generado por core.services.pdf.render_pdf.
        pdf_filename: nombre del archivo adjunto (sin path).

    Returns:
        True si el SMTP aceptó el envío, False si falló.
        Nunca lanza excepción — captura y loguea sin PII.
    """
    asunto = ASUNTOS_EMAIL.get(
        calculadora,
        f"Tu cálculo · {settings.DEFAULT_FROM_EMAIL.split('<')[0].strip()}",
    )

    try:
        msg = EmailMultiAlternatives(
            subject=asunto,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
        )
        msg.attach_alternative(html_body, "text/html")

        # Adjuntar PDF como application/pdf con disposition inline=false
        adjunto = MIMEBase("application", "pdf")
        adjunto.set_payload(pdf_bytes)
        encoders.encode_base64(adjunto)
        adjunto.add_header(
            "Content-Disposition",
            f'attachment; filename="{pdf_filename}"',
        )
        msg.attach(adjunto)

        msg.send(fail_silently=False)
        logger.info("email enviado: calc=%s ok=True", calculadora)
        return True
    except Exception:
        # No registramos detalles; pueden contener email o asunto interpolado.
        logger.exception("email enviado: calc=%s ok=False", calculadora)
        return False

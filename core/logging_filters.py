"""
core/logging_filters.py — Filtro de PII para logs.

Detecta y reemplaza emails y RUTs chilenos antes de loguear.
"""
import logging
import re

# Email — patrón razonable, no exhaustivo (no necesitamos validar, solo redactar)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# RUT chileno con o sin puntos, con o sin guión, DV alfanumérico
_RUT_RE = re.compile(r"\b\d{1,2}[.\s]?\d{3}[.\s]?\d{3}[-\s]?[\dkK]\b")


class NoPIIFilter(logging.Filter):
    """
    Reemplaza emails y RUTs en log records por [REDACTED-EMAIL]/[REDACTED-RUT].

    Aplica a `record.msg` y a cualquier arg que sea string. No modifica el
    objeto original — devuelve True siempre para no descartar el record.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)

        if record.args:
            try:
                record.args = tuple(
                    _scrub(a) if isinstance(a, str) else a for a in record.args
                )
            except TypeError:
                # args puede ser un dict (formato `%(name)s`)
                if isinstance(record.args, dict):
                    record.args = {
                        k: _scrub(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
        return True


def _scrub(s: str) -> str:
    s = _EMAIL_RE.sub("[REDACTED-EMAIL]", s)
    s = _RUT_RE.sub("[REDACTED-RUT]", s)
    return s

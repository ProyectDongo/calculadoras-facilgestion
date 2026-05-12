"""
core/services/crypto.py — Cifrado simétrico de datos sensibles en reposo.

Usado principalmente para RUTs almacenados en la tabla `leads`. Cifra con
Fernet (AES-128-CBC + HMAC-SHA256 + IV aleatorio + timestamp).

La clave vive solo en `settings.RUT_ENCRYPTION_KEY`. Sin esa clave los datos
en la DB no se pueden descifrar — incluso para un atacante con acceso al
dump SQL.

NO usar para passwords (eso es bcrypt/argon2). NO usar para autenticación
(Fernet no es signature). Solo para datos sensibles que necesitamos descifrar
después (RUT que mostramos al equipo de ventas en su dashboard).
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CryptoError(Exception):
    """Falla genérica de cifrado/descifrado."""


def _cipher() -> Fernet:
    key = settings.RUT_ENCRYPTION_KEY
    if not key:
        raise CryptoError(
            "RUT_ENCRYPTION_KEY no está configurada. "
            "Generar con: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise CryptoError(f"RUT_ENCRYPTION_KEY inválida: {exc}") from exc


def encrypt_rut(rut: str) -> bytes:
    """Cifra un RUT (string) y devuelve bytes para guardar en BinaryField."""
    if not rut:
        return b""
    return _cipher().encrypt(rut.encode("utf-8"))


def decrypt_rut(token: bytes) -> str:
    """Descifra; devuelve "" si el token está vacío o no se puede descifrar."""
    if not token:
        return ""
    try:
        return _cipher().decrypt(token).decode("utf-8")
    except (InvalidToken, CryptoError):
        return ""

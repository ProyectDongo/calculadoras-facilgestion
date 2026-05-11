"""
core/services/ip_hash.py — Hash determinista de IP para rate limit.

NUNCA almacena la IP en claro. Sólo el digest se usa como clave de Redis.
Si se compromete Redis o los logs, no hay forma directa de recuperar la IP
sin conocer el salt (que vive sólo en `settings.IP_HASH_SALT`).
"""
import hashlib

from django.conf import settings


def get_client_ip(request) -> str:
    """
    Extrae la IP del cliente respetando Cloudflare.

    Prioridad:
        1. CF-Connecting-IP (Cloudflare envía la IP real del visitante).
        2. X-Forwarded-For (primer hop si hay proxy intermedio).
        3. REMOTE_ADDR (fallback local).

    Nota: estos headers son confiables sólo cuando el request entra por
    Cloudflare Tunnel; un atacante directo al puerto 8000 podría forjar
    los headers. En prod el container está bind a 127.0.0.1, por lo que
    no es alcanzable salvo via tunnel.
    """
    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return cf_ip.strip()

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def hash_ip(ip: str) -> str:
    """
    SHA-256(ip + salt) → hex digest (64 chars).

    El salt se rota sólo si se compromete. Rotarlo invalida todos los
    contadores de rate limit en Redis (que de todas formas tienen TTL corto).
    """
    if not ip:
        ip = "0.0.0.0"
    salt = settings.IP_HASH_SALT.encode("utf-8")
    digest = hashlib.sha256(ip.encode("utf-8") + salt).hexdigest()
    return digest


def request_ip_hash(request) -> str:
    """Atajo: obtener IP del request y devolver su hash."""
    return hash_ip(get_client_ip(request))

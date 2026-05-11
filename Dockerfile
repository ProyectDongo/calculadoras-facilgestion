# syntax=docker/dockerfile:1.7
# ─────────────────────────────────────────────────────────────────────────────
# calculadoras.facilgestion.cl — Imagen única, sin servicios extra.
# Stack: Python 3.12-slim + WeasyPrint deps + Gunicorn. Sin Node.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema:
#   - WeasyPrint: libpango, libcairo, libgdk-pixbuf, fonts
#   - psycopg / generic build: build-essential, libffi, libssl
#   - tini: PID 1 limpio para que SIGTERM llegue a gunicorn
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    libxml2 \
    libxslt1.1 \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root con UID/GID fijos (alineable con host si hace falta)
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --system --gid ${APP_GID} app \
 && useradd  --system --uid ${APP_UID} --gid ${APP_GID} \
             --shell /usr/sbin/nologin --home-dir /app app

WORKDIR /app

# Capa de dependencias (cacheable)
COPY --chown=app:app requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Código de la app
COPY --chown=app:app . .

# Quita binarios SUID que no necesitamos (defensa en profundidad)
RUN find / -xdev -perm -4000 -type f -exec chmod a-s {} + 2>/dev/null || true

# Static files (la app es stateless, collectstatic en build OK)
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
RUN DJANGO_SECRET_KEY=build-time-placeholder \
    IP_HASH_SALT=build-time-placeholder \
    python manage.py collectstatic --noinput

USER app
EXPOSE 8000

# tini → gunicorn (3 workers, sync, sin threads; el cálculo y PDF son CPU-bound corto)
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--access-logformat", "%({x-real-ip}i)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s %(M)sms"]

# Healthcheck simple — /healthz/ devuelve 200 OK sin info
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=3).status==200 else 1)"

# calculadoras.facilgestion.cl

Tres calculadoras públicas (Precio de venta, IVA, Boleta de honorarios) para PyMEs chilenas. Lead-gen del ERP FácilGestión. **Sin retención de datos**: la app es stateless, no persiste emails, RUTs ni payloads de cálculo.

> **Estado:** Fase 1 (setup) completada — 2026-05-11.
> **Próxima fase:** 2 (core services: rut.py, turnstile.py, pdf.py, email_sender.py).

---

## Stack

| Capa | Tecnología | Pin |
|---|---|---|
| Framework | Django LTS | 5.2.14 |
| Servidor | Gunicorn | 23.0.0 |
| Cache / rate limit | Redis 7 + django-redis | 5.4.0 |
| Anti-bot | Cloudflare Turnstile (managed) | — |
| CSP | django-csp 4.x | 4.0 |
| Rate limit decorators | django-ratelimit | 4.1.0 |
| PDF | WeasyPrint | 68.1 |
| Frontend | HTMX 2 + Alpine.js 3 (vendoreados) + Tailwind CDN | — |
| TLS | Cloudflare Tunnel (externo al compose) | — |
| Python | 3.12-slim | — |

## Características de diseño

- **Stateless**: ninguna tabla propia. Sin Postgres. Sessions = signed cookies (firmadas con SECRET_KEY, almacenadas en el navegador del usuario).
- **Cero PII server-side**: ni email, ni RUT, ni IP en claro. Si el usuario pide enviar PDF por correo, se envía y se descarta; nada queda persistido.
- **T&C obligatorios al entrar**: modal con aceptación, queda en cookie firmada (`calc_session`).
- **CSP por-vista, no global**: la política base es estricta; las vistas que necesitan `unsafe-inline` lo declaran con `@csp_update`.
- **Anti-bot en 4 capas**: Cloudflare Turnstile + honeypot + tiempo mínimo de submit + rate limit por endpoint.
- **PDFs con branding FácilGestión**: logo embebido, paleta `#2563eb` / `#0f172a` / `#475569`, fuentes del sistema.
- **Multi-ítem (lista)**: localStorage del navegador, exportable a PDF de lista en cliente → servidor solo recibe el JSON final para renderizar.

## Comandos

```bash
# Levantar dev
cp .env.example .env
# editar .env: DJANGO_SECRET_KEY, TURNSTILE_*, EMAIL_HOST_PASSWORD
docker compose up --build

# Generar requirements.txt (lockfile) la primera vez
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt requirements.in

# Producción (Cloudflare Tunnel externo apunta a 127.0.0.1:8000)
docker compose -f docker-compose.prod.yml up --build -d
```

## Estructura

```
calculadoras-facilgestion/
├── Dockerfile                       Python 3.12-slim + WeasyPrint deps
├── docker-compose.yml               dev (sin TLS, hot reload)
├── docker-compose.prod.yml          prod (read-only, cap_drop ALL)
├── .dockerignore .env.example .gitignore
├── requirements.in                  versiones pineadas (source)
├── manage.py
├── README.md SECURITY.md            ← SECURITY.md aún por escribir
├── config/
│   ├── __init__.py urls.py wsgi.py asgi.py
│   ├── tributario.py                IVA, retención honorarios, branding
│   └── settings/
│       ├── base.py                  configuración compartida
│       ├── dev.py                   DEBUG=True, email a consola
│       └── prod.py                  HSTS + SSL redirect + cookies SECURE
├── core/
│   ├── apps.py middleware.py
│   ├── context_processors.py        brand + turnstile en templates
│   ├── logging_filters.py           redacta email/RUT en logs
│   └── services/                    rut.py, pdf.py, etc. (← Fase 2)
├── calculadoras/
│   ├── apps.py
│   ├── static/calculadoras/
│   │   ├── logo.png                 ← copiado del ERP
│   │   ├── css/ js/ vendor/         ← Fase 3 (HTMX/Alpine vendored)
│   └── templates/calculadoras/
│       └── pdf/                     ← Fase 3
├── templates/                       404.html, 500.html, 429.html (← Fase 9)
└── deploy/
    └── cloudflared.example.yml      ← Fase 10
```

## Variables de entorno

Ver `.env.example`. Resumen:

- `DJANGO_SECRET_KEY` — requerido. Generar con `python -c "import secrets;print(secrets.token_urlsafe(50))"`.
- `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` — obtener en Cloudflare Dashboard.
- `EMAIL_HOST_PASSWORD` — app password de Gmail (reutilizar la del ERP).
- `REDIS_PASSWORD` — solo en prod.
- `IP_HASH_SALT` — salt fijo del proyecto para hashear keys efímeras del ratelimiter.

## Cloudflare (configuración externa)

Documentado en [SECURITY.md](SECURITY.md) (pendiente — Fase 10):

- Tunnel `calculadoras` → `127.0.0.1:8000` corriendo fuera del compose.
- WAF rule: 100 req/min por IP.
- Bot Fight Mode: ON.
- Security level: Medium.
- Turnstile widget en modo managed.

## Status de las fases

- [x] **Fase 1** — Setup (este commit)
- [ ] Fase 2 — Core services (rut, turnstile, pdf, email_sender)
- [ ] Fase 3 — Calc IVA completa (andamiaje)
- [ ] Fase 4 — Calc Precio Venta
- [ ] Fase 5 — Calc Honorarios
- [ ] Fase 6 — Lista multi-ítem (localStorage + PDF)
- [ ] Fase 7 — Política de privacidad pública
- [ ] Fase 8 — Tests + coverage ≥ 70%
- [ ] Fase 9 — Hardening final (`manage.py check --deploy`)
- [ ] Fase 10 — Documentación de deploy y Cloudflare

# calculadoras.facilgestion.cl

Cuatro calculadoras públicas para PyMEs chilenas (IVA, Precio de venta, Boleta de honorarios, Sueldo líquido) + cotizador multi-ítem exportable a PDF + glosario tributario. Lead-gen del ERP FácilGestión. **Sin retención de datos PII server-side**: la app es stateless, no persiste emails, RUTs ni payloads. Las listas viven en `localStorage` del navegador del usuario.

> **Estado:** Fases 1, 2, 3, 4 (Sueldo + Cotización + Glosario + FAQ + Lead-gen banner) completadas — 2026-05-11.
> **Pendiente:** Fase 5 (tests + coverage), Fase 6 (hardening final), Fase 7 (PWA + modo oscuro + calcs adicionales).

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
- **Anti-bot en 4 capas**: Cloudflare Turnstile + honeypot + tiempo mínimo de submit + rate limit por endpoint + middleware anti-flood global con Redis.
- **PDFs con branding FácilGestión**: logo embebido desde filesystem, paleta `#2563eb` / `#0f172a` / `#475569`, banner CTA al ERP integrado en cada PDF.
- **Multi-ítem (cotización)**: localStorage del navegador. Backend solo recibe el JSON al exportar PDF; re-totaliza server-side y descarta.
- **Lead-gen contextual**: tras 3 cálculos en una sesión, banner discreto al ERP. Descartable con cooldown de 7 días.

## Funcionalidad por página

| Ruta | Qué hace |
|---|---|
| `/calculadoras/` | Landing con 4 cards + accesos a Cotización y Glosario |
| `/calculadoras/iva/` | IVA 19% — Neto ↔ Bruto |
| `/calculadoras/precio-venta/` | Costo + flete + utilidad → precio con/sin IVA + botón "Agregar a cotización" |
| `/calculadoras/honorarios/` | Bruto ↔ Líquido (retención 15,25% Ley 21.133) |
| `/calculadoras/sueldo/` | Bruto → Líquido con AFP (selector 7 AFPs) + Fonasa/Isapre + cesantía + IGC 2026 |
| `/calculadoras/cotizacion/` | Lista multi-ítem desde `localStorage` → PDF profesional con emisor/cliente/items |
| `/calculadoras/glosario/` | 12 términos tributarios chilenos con links a sus calcs |
| `/calculadoras/privacidad/` | Política de privacidad (Ley 19.628) |
| `/calculadoras/api/calcular/{calc}/` | Endpoint HTMX que devuelve partial con resultado |
| `/calculadoras/api/pdf/` | Genera PDF de cálculo único |
| `/calculadoras/api/enviar/` | Envía PDF por email (sin almacenar) |
| `/calculadoras/api/cotizacion/pdf/` | Genera PDF de cotización multi-ítem |
| `/healthz/` | Health check para Cloudflare/Docker |

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

- [x] **Fase 1** — Setup base (Docker, settings split, dummy DB, signed cookies)
- [x] **Fase 2** — Core services (rut, turnstile, pdf, email_sender, honeypot, ip_hash, antiflood middleware)
- [x] **Fase 3** — Calc IVA + Precio Venta + Honorarios + landing diferenciada
- [x] **Fase 4** — Calc Sueldo Líquido + Lista multi-ítem + Cotización PDF + Glosario + FAQ + Banner ERP
- [ ] **Fase 5** — Suite de tests con pytest (≥ 70% coverage en `core/` y `calculadoras/`)
- [ ] **Fase 6** — Hardening final (CSP sin `unsafe-eval`/`unsafe-inline`, Tailwind build standalone, Alpine CSP-safe build, `manage.py check --deploy` limpio)
- [ ] **Fase 7** — Mejoras adicionales: PWA instalable, modo oscuro, calc Finiquito, UF/USD converter, F29 simplificada, embed widget

## Roadmap pendiente — calculadoras adicionales

- Finiquito laboral (años de servicio + vacaciones + indemnización)
- UF / USD / CLP converter con valor del día (cache Redis 15min, fuente `mindicador.cl`)
- Punto de equilibrio (costos fijos / margen unitario)
- F29 simplificada (IVA débito vs crédito + PPM)
- Precio inverso ("Quiero $X de utilidad, ¿a cuánto vendo?")
- Calendario tributario chileno (página estática SEO)

# SECURITY.md — Decisiones de seguridad de calculadoras.facilgestion.cl

> Fase 1 (setup). Este documento se completa en cada fase relevante.
> Última actualización: 2026-05-11.

---

## Resumen ejecutivo

| Mecanismo | Estado |
|---|---|
| Sin Postgres / sin persistencia de PII | ✅ DATABASES dummy + sessions signed_cookies |
| HSTS + SSL redirect | ✅ En `prod.py` (1 año, preload, subdomains) |
| Cookies SECURE / HttpOnly / SameSite=Lax | ✅ Sesión + CSRF |
| CSP estricta (django-csp 4.x dict API) | ✅ Política base + permite Tailwind CDN + Turnstile |
| X-Frame-Options DENY | ✅ |
| Permissions-Policy | ✅ Middleware (sin geo/mic/cam/payment) |
| Cross-Origin-Opener-Policy / Resource-Policy | ✅ same-origin |
| Cloudflare Turnstile | ✅ Verificación server-side fail-closed, 3s timeout |
| Rate limit por endpoint | ✅ django-ratelimit: 60/min calcular, 10/min PDF, 5/min enviar |
| Anti-flood middleware global | ✅ Redis-backed, 3 contadores con bloqueo 15min, fail-OPEN |
| Honeypot + tiempo mínimo submit | ✅ Campo `website` oculto + TimestampSigner 1.5s-30min |
| NoPIIFilter para logs | ✅ Redacta emails y RUTs con regex |
| Validación defensiva en cotización PDF | ✅ Max 50 items, longitudes capped, re-totaliza server-side |
| `manage.py check --deploy` sin warnings | 🟡 Pendiente fase 6 (al endurecer CSP) |
| Tests con coverage ≥ 70% | 🟡 Tests unitarios existen (IVA/honorarios/precio_venta/sueldo), pendiente integración |

---

## Decisiones arquitectónicas

### 1. Sin base de datos persistente

Razón: la app es **pública, anónima y stateless**. Los inputs (RUT, email) son PII en Chile bajo Ley 19.628. Al no almacenarlos:

- Reducimos a cero la superficie de breach.
- Eliminamos obligación de mantener "olvidame" / retención / borrado seguro.
- Simplificamos infraestructura (un container Redis ephemeral basta).

`DATABASES['default']['ENGINE'] = 'django.db.backends.dummy'` — Django no abre conexiones, ni hace migrations. Cualquier intento de `Model.objects.…` fallará en runtime.

### 2. Sessions en signed cookies

`SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'`. La sesión es un dict serializado y firmado con `SECRET_KEY`, almacenado en el navegador del usuario. Solo guardamos un flag boolean `tc_accepted_v1: True` cuando el usuario acepta los T&C.

- Sin storage server-side → cero PII en nuestros servidores.
- Cookie limitada a 4KB; jamás vamos a llenarla.
- Si rotamos `SECRET_KEY`, todas las cookies firmadas se invalidan (re-aceptación de T&C).

### 3. CSP por-vista, no global

`config/settings/base.py` define una política **estricta** como default (`default-src 'self'`, sólo Turnstile en `script-src`/`frame-src`).

Las vistas que necesiten relajación (ej: Tailwind inline) lo declararán con:

```python
from csp.decorators import csp_update
@csp_update(SCRIPT_SRC=("'unsafe-inline'",))
def mi_vista(request): ...
```

Razón: prevenir que una vulnerabilidad XSS futura tenga libertad para cargar scripts externos.

### 4. Cloudflare Tunnel termina TLS

El contenedor `web` expone HTTP puro en `127.0.0.1:8000`. Cloudflare valida certificado, agrega `X-Forwarded-Proto: https`, y Django confía vía `SECURE_PROXY_SSL_HEADER`. **El servidor nunca ve TLS** — sólo Cloudflare.

### 5. Container hardening (prod)

`docker-compose.prod.yml`:

- `read_only: true` — filesystem root inmutable.
- `tmpfs /tmp` para scratch space de WeasyPrint.
- `cap_drop: [ALL]` — sin capabilities Linux.
- `security_opt: no-new-privileges` — no escalada vía setuid.
- Usuario `app` UID 10001, no-root, sin shell (`/usr/sbin/nologin`).
- `SUID` bits removidos del filesystem en build.
- Puerto 8001 (no 8000) para coexistir con ERP en mismo VPS.

### 6. Lista multi-ítem y cotización — sin PII server-side

- La "lista de productos" vive 100% en `localStorage` del navegador. Cero base
  de datos, cero archivos del lado servidor.
- El backend SOLO recibe el JSON de la lista cuando el usuario hace click en
  "Descargar PDF". Inmediatamente después de generar el PDF, el JSON se
  descarta (no se loguea, no se cachea).
- `core/views.py:_sanitizar_cotizacion()` valida defensivamente:
    - Máximo 50 items por cotización.
    - `descripcion` cap a 200 caracteres.
    - `cantidad` y `precio_unitario` enteros positivos (cast forzado).
    - Strings sanitizados con `[:N].strip()` antes de meter en template.
- Re-totaliza server-side (`subtotal_neto = sum(items)`) — no confía en
  los totales que el cliente envía.
- El template del PDF auto-escapa (Django default) cualquier texto que venga
  del usuario; XSS via descripción de producto = no posible.

### 7. Engagement counter — solo localStorage

- `engagement.js` cuenta cálculos hechos en `localStorage` del navegador.
- Tras 3 cálculos muestra un toast al ERP.
- Sin tracking server-side. Sin cookies. Sin analytics externos.
- El usuario puede descartar; cooldown 7 días almacenado localmente.

---

## Pendiente (configurar a mano)

### Cloudflare Dashboard

> Acción manual del propietario del dominio.

1. **Tunnel**:
   - Crear tunnel `calculadoras` en https://one.dash.cloudflare.com/.
   - Apuntar hostname `calculadoras.facilgestion.cl` → `http://127.0.0.1:8000`.
   - Instalar `cloudflared` como servicio del host (no en el compose).

2. **Turnstile**:
   - Dashboard → Turnstile → Add site → dominio `calculadoras.facilgestion.cl`.
   - Modo "Managed" (invisible salvo challenge).
   - Copiar Site Key (público) y Secret Key (env del servidor).

3. **WAF rule en `calculadoras.facilgestion.cl`**:
   - `(http.request.method eq "POST") and (rate_limit_score > 100)` → Block 15min.
   - Rate limit: 100 req/min por IP.

4. **Bot Fight Mode**: ON.
5. **Security level**: Medium.

### `.env` antes del primer arranque

```bash
DJANGO_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(50))")
IP_HASH_SALT=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
REDIS_PASSWORD=$(python -c "import secrets;print(secrets.token_urlsafe(32))")
```

Las tres se generan ahora, una sola vez, y se rotan sólo en caso de compromiso.

---

## Amenazas modeladas

| Amenaza | Mitigación |
|---|---|
| Spam por formulario (bots) | Turnstile + honeypot + tiempo mínimo submit |
| Scraping intensivo / DDoS aplicativo | django-ratelimit + AntiFloodMiddleware + Cloudflare WAF |
| XSS via inputs en cálculo | Auto-escape Django + CSP estricta |
| CSRF | Token Django + SameSite=Lax + CSRF_TRUSTED_ORIGINS pinned |
| Clickjacking | `X-Frame-Options: DENY` + CSP `frame-ancestors: 'none'` |
| Email enumeration | No tenemos DB de emails — no aplica |
| Replay de PDFs | Cada PDF se genera on-demand, no se cachea |
| Privilege escalation en container | non-root + cap_drop ALL + no-new-privileges |
| Acceso al contenedor desde otros tenants | Cloudflare Tunnel termina en `127.0.0.1:8000` (no expuesto a internet) |
| Compromiso de SECRET_KEY | Rotación invalida sessions y CSRF tokens, sin pérdida de PII (no hay) |

## NO se mitigan (fuera de scope)

- Phishing dirigido contra la cuenta SMTP configurada en `.env`.
- Ataques contra Cloudflare como infraestructura.
- Compromiso del host físico donde corre Docker.

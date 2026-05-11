# SECURITY.md — Decisiones de seguridad de calculadoras.facilgestion.cl

> Fase 1 (setup). Este documento se completa en cada fase relevante.
> Última actualización: 2026-05-11.

---

## Resumen ejecutivo

| Mecanismo | Estado fase 1 |
|---|---|
| Sin Postgres / sin persistencia de PII | ✅ Implementado (DATABASES dummy, signed_cookies) |
| HSTS + SSL redirect | ✅ En `prod.py` |
| Cookies SECURE / HttpOnly / SameSite=Lax | ✅ Sesión + CSRF |
| CSP estricta (django-csp 4.x) | ✅ Base por-vista en `base.py` |
| X-Frame-Options DENY | ✅ |
| Permissions-Policy | ✅ Middleware |
| Cross-Origin-Opener-Policy / Resource-Policy | ✅ |
| Cloudflare Turnstile | 🟡 site_key/secret en env, verificación service pendiente (Fase 2) |
| Rate limit por endpoint | 🟡 django-ratelimit instalado, decoradores pendientes (Fase 3) |
| Anti-flood middleware global | 🟡 Stub, lógica pendiente (Fase 2) |
| Honeypot + tiempo mínimo submit | 🔴 Pendiente (Fase 3) |
| NoPIIFilter para logs | ✅ Implementado |
| `manage.py check --deploy` sin warnings | 🔴 Pendiente (Fase 9) |

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

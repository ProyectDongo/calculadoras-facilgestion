# DEPLOY.md — Despliegue en VPS compartido con FácilGestión ERP

Guía paso a paso para correr `calculadoras.facilgestion.cl` en el **mismo VPS** donde corre el ERP FácilGestión, sin afectarlo.

## Pre-condiciones

- VPS Linux con Docker + Docker Compose instalados.
- El ERP de FácilGestión ya está corriendo y usa `127.0.0.1:8000` para gunicorn.
- Cuenta de Cloudflare con el dominio `facilgestion.cl` ya gestionado.
- `cloudflared` instalado en el host (puede ser el mismo binario del Tunnel del ERP).
- Acceso SSH al VPS.

## Resumen de aislamiento

| Recurso | ERP | Calculadoras |
|---|---|---|
| Gunicorn puerto host | `127.0.0.1:8000` | `127.0.0.1:8001` |
| Container `web` | `web` | `calc_web` |
| Container `redis` | `redis` | `calc_redis` |
| Subdomain | `gestion.facilgestion.cl` | `calculadoras.facilgestion.cl` |
| DB Postgres | sí (compartida en el ERP) | **no usa** (signed cookies) |
| Volumen Docker | propios del ERP | propios (`calculadoras_*`) |

Cero solapamiento. Si tumbas el container de calc, el ERP sigue funcionando, y al revés.

---

## 1. Clonar el repo en el VPS

```bash
ssh tu-usuario@tu-vps
cd /opt   # o donde tengas tus proyectos
git clone https://github.com/<tu-org>/calculadoras-facilgestion.git
cd calculadoras-facilgestion
```

## 2. Crear el `.env` de producción

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Rellena con valores reales (NO commitear). Genera los 5 secretos con:

```bash
python3 -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50))"
python3 -c "import secrets; print('IP_HASH_SALT=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('REDIS_PASSWORD=' + secrets.token_urlsafe(32))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
python3 -c "from cryptography.fernet import Fernet; print('RUT_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

> El último comando requiere `pip install cryptography` o ejecutarlo dentro del container `calc_web`:
> `docker compose -f docker-compose.prod.yml run --rm web python -c '...'`

Variables que NO pueden quedar vacías:

- `DJANGO_SECRET_KEY` (generado arriba)
- `IP_HASH_SALT` (generado arriba)
- `REDIS_PASSWORD` (generado arriba)
- `POSTGRES_PASSWORD` (generado arriba) — Postgres dedicado para leads
- `RUT_ENCRYPTION_KEY` (generado arriba) — cifrado en reposo de los RUTs
- `DJANGO_ALLOWED_HOSTS=calculadoras.facilgestion.cl`
- `DJANGO_DEBUG=False`
- `DJANGO_SETTINGS_MODULE=config.settings.prod`
- `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` (Cloudflare Dashboard → Turnstile → Add site)
- `EMAIL_HOST` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` (puedes reusar las del ERP)
- `DEFAULT_FROM_EMAIL=FacilGestion Calculadoras <calculadoras@facilgestion.cl>`

### ⚠ Sobre `RUT_ENCRYPTION_KEY`

Esta clave **cifra los RUTs en la tabla `leads`**. Si la perdés, los RUTs ya
almacenados quedan ilegibles (los demás datos siguen accesibles). Reglas:

- Guardala fuera del repo (ya está en `.env`, que está gitignored).
- Si la rotás, los RUTs viejos quedan inaccesibles hasta que migres con la
  clave nueva. Para rotar en producción se necesita `MultiFernet` (no
  implementado todavía).
- Si la comprometés, generá una nueva, re-cifrá los RUTs y revocá la vieja.

## 3. Build + up con el compose de producción

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f web
```

El arranque hace `python manage.py migrate --noinput` automáticamente y
después gunicorn. La primera vez crea la tabla `leads`. Verifica que
gunicorn arranca sin errores. El container expone `127.0.0.1:8002:8000`
(puerto 8002 en el host — 8000 es ERP, 8001 es mail-facilgestion).

> **Si actualizás desde una versión sin Postgres**: borrá el volumen viejo
> de staticfiles para que el nuevo container con `migrate` arranque limpio:
> `docker volume rm calculadoras-facilgestion_static_volume`

## 4. Smoke test local en el VPS

```bash
# Healthcheck
curl -s http://127.0.0.1:8001/healthz/                       # debe responder "ok"

# Las 8 páginas públicas
for p in / iva/ precio-venta/ honorarios/ sueldo/ cotizacion/ glosario/ privacidad/; do
  printf "%-15s " "$p"
  curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8001/calculadoras$p"
done
# Deben responder todas 200.
```

## 5. Cloudflare Tunnel

Tienes dos opciones. Elige una:

### Opción A — Tunnel NUEVO sólo para calculadoras (recomendado)

```bash
cloudflared tunnel login                                  # browser para autenticar
cloudflared tunnel create calculadoras                    # crea el tunnel, devuelve UUID
sudo mkdir -p /etc/cloudflared
sudo mv ~/.cloudflared/<UUID>.json /etc/cloudflared/
```

Edita `/etc/cloudflared/config.yml` (créalo si no existe):

```yaml
tunnel: <UUID-DEL-TUNNEL-NUEVO>
credentials-file: /etc/cloudflared/<UUID-DEL-TUNNEL-NUEVO>.json

ingress:
  - hostname: calculadoras.facilgestion.cl
    service: http://127.0.0.1:8001
    originRequest:
      httpHostHeader: calculadoras.facilgestion.cl
      originServerName: calculadoras.facilgestion.cl
  - service: http_status:404
```

Crea el DNS record:

```bash
cloudflared tunnel route dns calculadoras calculadoras.facilgestion.cl
```

Arranca como servicio:

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
sudo systemctl status cloudflared
```

### Opción B — Reusar el Tunnel del ERP

Edita el `/etc/cloudflared/config.yml` existente, **agrega** una ingress regla ANTES del catch-all:

```yaml
ingress:
  - hostname: gestion.facilgestion.cl
    service: http://127.0.0.1:8000           # tu ERP existente
  - hostname: calculadoras.facilgestion.cl   # ← NUEVO
    service: http://127.0.0.1:8001
    originRequest:
      httpHostHeader: calculadoras.facilgestion.cl
  - service: http_status:404                  # mantener al final
```

Asigna DNS al mismo tunnel:

```bash
cloudflared tunnel route dns <tunnel-existente-name> calculadoras.facilgestion.cl
sudo systemctl restart cloudflared
```

Trade-off: si tumbas el tunnel para mantenimiento, ambas apps caen. La Opción A te da independencia.

## 6. Cloudflare Dashboard — protecciones

En https://dash.cloudflare.com → tu zona `facilgestion.cl`:

1. **Turnstile** (https://dash.cloudflare.com → Turnstile):
   - Add site → hostname `calculadoras.facilgestion.cl`
   - Widget mode: **Managed** (invisible salvo desafío)
   - Copia Site Key y Secret Key al `.env` del VPS y reinicia con `docker compose -f docker-compose.prod.yml restart web`.

2. **WAF → Rate limiting rules**:
   - Field: hostname → equals → `calculadoras.facilgestion.cl`
   - Action: Block
   - Threshold: 100 requests per 1 minute per IP

3. **Security → Bot Fight Mode**: ON.

4. **SSL/TLS → Edge Certificates**:
   - SSL/TLS encryption mode: **Full (strict)** (debe estar ya por el ERP).
   - HSTS: enable preload.

## 7. Verificar desde internet

```bash
curl -sI https://calculadoras.facilgestion.cl/healthz/
# Debe responder 200 OK, cabeceras de Cloudflare presentes.

curl -s https://calculadoras.facilgestion.cl/calculadoras/sueldo/ | grep -i "sueldo"
# Debe encontrar el título.
```

Abre en un navegador y valida cada calc:

```
https://calculadoras.facilgestion.cl/calculadoras/iva/
https://calculadoras.facilgestion.cl/calculadoras/precio-venta/
https://calculadoras.facilgestion.cl/calculadoras/honorarios/
https://calculadoras.facilgestion.cl/calculadoras/sueldo/
https://calculadoras.facilgestion.cl/calculadoras/cotizacion/
https://calculadoras.facilgestion.cl/calculadoras/glosario/
```

Checklist de validación:
- [ ] Modal de T&C aparece al primer load (cookie `tc_accepted_v1` persistente)
- [ ] Las 4 calcs reaccionan al escribir un monto (HTMX en vivo)
- [ ] Sin errores rojos en la consola del navegador
- [ ] Turnstile aparece al abrir modal de descargar/enviar
- [ ] "Descargar PDF" baja un PDF con logo + CTA al ERP
- [ ] "Enviar por correo" funciona si configuraste SMTP password real
- [ ] En `/precio-venta/`: botón "Agregar a cotización" suma al contador del header
- [ ] En `/cotizacion/`: la tabla se llena, exporta PDF cotización con branding completo
- [ ] Glosario muestra 12 términos
- [ ] Tras 3 cálculos en una sesión, aparece banner ERP bottom-right
- [ ] Footer muestra Cotización, Glosario y links externos

## 8. Mantenimiento

**Actualizar a la última versión del repo:**

```bash
cd /opt/calculadoras-facilgestion
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

**Ver logs:**

```bash
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f redis
```

**Rotación de secretos** (cuando un secreto se compromete):

1. Genera nuevo `DJANGO_SECRET_KEY` y reemplaza en `.env`.
2. `docker compose -f docker-compose.prod.yml restart web`.
3. Las cookies firmadas de sesión se invalidan → todos los usuarios verán el modal de T&C de nuevo. Sin pérdida de datos (no almacenamos).

**Backup**: la app no almacena nada. Sin DB, sin volúmenes con estado de usuario. El único "estado" es el config de Cloudflare y el `.env` del VPS.

## 9. Troubleshooting

| Síntoma | Probable causa | Fix |
|---|---|---|
| 502 en https://calculadoras.facilgestion.cl | `cloudflared` no llega al puerto 8001 | `docker ps` → verificar `calc_web` running, `ss -tlnp \| grep 8001` |
| Turnstile siempre falla | `TURNSTILE_SECRET_KEY` mal copiado | Revisar `.env`, reiniciar web |
| 429 inmediato | AntiFloodMiddleware con umbrales bajos | Ajustar `_LIMITS` en `core/middleware.py` y rebuild |
| Email no se envía | Gmail bloquea SMTP por IP del VPS | Crear app-password en Gmail y/o agregar VPS a IPs permitidas |
| CSP rompe Tailwind/Alpine | `script-src` no incluye CDN | Ver `config/settings/base.py:CONTENT_SECURITY_POLICY` |

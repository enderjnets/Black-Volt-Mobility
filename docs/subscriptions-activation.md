# Activación de Suscripciones de Drivers (`driver.blackvoltmobility.com`)

> El código de la Fase 3 está **completo y verificado en modo simulado/sandbox**
> en la rama `phase-3-subscriptions`. Esta es la checklist de **pasos manuales del
> dueño** para activarlo en vivo. Nada aquí toca código: son recursos externos
> (Square, DNS) + variables de entorno del VPS.

## Estado del código (ya hecho)

- **Backend**: alta de suscripción (`POST /api/v1/subscriptions`), planes Operator
  mensual + anual, entitlements (IA + perfil público), rate-limit, y **webhooks de
  Square** (`POST /api/v1/webhooks/square`) con verificación HMAC. 182 tests verdes,
  `ruff` limpio, sin drift de Alembic.
- **Frontend**: landing del driver en `/driver` (host-rewrite por `DRIVER_HOSTS`),
  checkout Square con toggle **mensual $29 / anual $290**, degradación a "contáctanos"
  si Square no está configurado. `tsc` + `next lint` + `build` limpios.
- **Guardrails respetados**: el token secreto de Square nunca llega al frontend (solo
  el `application_id`/`location_id` público + el nonce tokenizado); ninguna key en
  archivos commiteados; el webhook rechaza con 403 todo lo no verificado.

---

## Checklist de activación (dueño)

### 1. Square — crear el plan "Operator"
1. Square Dashboard → **Subscriptions → Plans → Create plan** → "Operator".
2. Añadir **dos variaciones**: mensual **$29** y anual **$290** (≈2 meses gratis).
3. Copiar el **plan variation ID** de cada una.
4. En el `.env` del VPS:
   ```
   SQUARE_PLAN_OPERATOR_MONTHLY=<id mensual>
   SQUARE_PLAN_OPERATOR_ANNUAL=<id anual>
   ```
   > Mientras `PAYMENTS_SIMULATED=true` un placeholder es válido (el flujo corre
   > simulado). Los ids reales solo hacen falta para cobrar de verdad.

### 2. DNS — subdominio `driver.`
1. En Cloudflare, apuntar `driver.blackvoltmobility.com` al **mismo túnel `blackvolt`**
   que ya sirve `app.` (ingress → frontend del VPS, puerto 3005). **No** crear un túnel
   nuevo ni reusar el de Realtors/Eko.
2. Confirmar `DRIVER_HOSTS=driver.blackvoltmobility.com` en el `.env` del VPS (ya es el
   default; se hornea en build → requiere rebuild del frontend si se cambia).

### 3. Square — webhook de suscripciones
1. Square Dashboard → **Developer → Webhooks → Add endpoint**.
2. URL: `https://driver.blackvoltmobility.com/api/v1/webhooks/square`
   (debe ser **exacta** — el HMAC se calcula sobre URL + body).
3. Suscribir los eventos: `subscription.updated`, `invoice.payment_made`,
   `invoice.scheduled_charge_failed`, `invoice.payment_failed`.
4. Copiar la **Signature Key** del endpoint. En el `.env` del VPS:
   ```
   SQUARE_WEBHOOK_SIGNATURE_KEY=<signature key>
   SQUARE_WEBHOOK_URL=https://driver.blackvoltmobility.com/api/v1/webhooks/square
   ```
   > Si ambas están vacías el endpoint responde 403 a todo (fail-closed por diseño).

### 4. Flip a producción
En el `.env` del VPS:
```
SQUARE_ENV=production
PAYMENTS_SIMULATED=false
SQUARE_ACCESS_TOKEN=<token de producción de Square>
SQUARE_LOCATION_ID=<location id de producción>
SQUARE_APPLICATION_ID=<application id de producción>
ENTITLEMENTS_ENFORCED=true   # opcional: empieza a cobrar features IA/perfil a no-pagos
```
> **Anti-patrón crítico**: nunca dejar un `*_SIMULATED=true` con
> `APP_ENV=production`. El backend loguea un WARN; investigar antes de green-light.

### 5. Rebuild del VPS
Los `NEXT_PUBLIC_*` y los rewrites de Next se hornean en **build time**:
```
docker compose build frontend backend
docker compose up -d
```

### 6. Prueba end-to-end (sandbox antes de producción)
1. Con `SQUARE_ENV=sandbox` + plan ids de sandbox + tarjeta `4111 1111 1111 1111`.
2. Abrir la landing en `driver.` → Operator → checkout → suscripción
   `simulated:false` → `status=active`.
3. Verificar que las features IA (`/rides/extract`) y el perfil público quedan
   desbloqueados para ese tenant.
4. Disparar un `invoice.payment_made` de prueba desde Square → confirmar que la fila
   local refleja `active` + `current_period_end`.

---

## Cierre de fase (cuando esté en vivo)

`phase-3-subscriptions` → `main`, luego:
- bump `frontend/lib/version.ts` + prepend `CHANGELOG.md`
- `git tag v0.X.0` + `gh release create` (protocolo checkmark Black Volt)

## Variables nuevas de esta fase (resumen)

| Var | Para qué |
|---|---|
| `SQUARE_PLAN_OPERATOR_MONTHLY` / `_ANNUAL` | plan variation ids del checkout |
| `SQUARE_WEBHOOK_SIGNATURE_KEY` | verificación HMAC del webhook |
| `SQUARE_WEBHOOK_URL` | URL exacta registrada (entra en el HMAC) |
| `CORS_ORIGINS` | incluye `driver.` por default; override por env |
| `DRIVER_HOSTS` | host-rewrite `/`→`/driver` (build-time) |
| `NEXT_PUBLIC_APP_URL` | destino del CTA "Free" (dashboard) |
| `NEXT_PUBLIC_SALES_EMAIL` | mailto del tier "Growth" |

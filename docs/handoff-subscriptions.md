# Handoff: Driver landing + Square Subscriptions (`driver.blackvoltmobility.com`)

> Brief para Claude Code. Lee primero `CLAUDE.md` (convenciones, anti-patrones, port map).
> Trabaja con TDD, modo simulado por defecto, y **no toques** los flujos de pago de rides.

## Objetivo

1. Servir la **página de marketing/pricing** para drivers (`driver.blackvoltmobility.com`).
2. Permitir que el driver **se suscriba al plan Operator** vía **Square Subscriptions**, conectado a la cuenta Square existente de Black Volt.
3. Free = registro (sin pago). Growth = ventas (mailto, sin autoservicio todavía).

## Prerrequisito del dueño (en el Dashboard de Square — hacer ANTES)

- Crear un **Subscription Plan** "Operator" con variación mensual **$29** (opcional: anual **$290**).
- Copiar el **plan variation ID** de cada variación → van en `.env`.
- Empezar en **sandbox** (`SQUARE_ENV=sandbox`) para probar; cambiar a producción al final.

## Archivos de diseño ya hechos (traer al repo)

- `driver-landing.html` — la página (pricing + checkout Square ya cableado al flujo correcto).
- `black-volt-one-pager.html` — one-pager para inversionistas (no es parte del producto; archivar en `docs/`).

---

## Tareas

### 1. Frontend — ruta de la landing del driver
- Portar `driver-landing.html` al Next.js (`frontend/`). Recomendado: ruta propia servida en el host `driver.` con un host-rewrite, **espejando** el patrón `app.` → `/dashboard` que ya existe.
- Mover el bloque `window.BV` a env: usar `NEXT_PUBLIC_API_URL` (ya existe) para `apiBase`; agregar `NEXT_PUBLIC_APP_URL` y `NEXT_PUBLIC_SALES_EMAIL`.
- Conservar el checkout: `GET /payments/config` → Web Payments SDK → `tokenize()` → `POST /subscriptions`.
- i18n EN+ES (la página está en ES; agregar EN siguiendo `lib/i18n.tsx`).

### 2. Backend — Square Subscriptions
Espeja la estructura de `app/services/payments_square.py`:

- **`app/services/subscriptions_square.py`** (adapter, async Square SDK):
  - `create_customer(email)`, `create_card(customer_id, source_id)`,
    `create_subscription(plan_variation_id, customer_id, card_id, location_id)`.
  - **Modo simulado** cuando `not settings.payments_live` → ids falsos (`SIMSUB-…`), para que el flujo corra sin Square.
- **`app/services/subscriptions.py`** (orquestación):
  - `plan_key` → `plan_variation_id` desde env.
  - Crea customer + card on file + subscription; persiste una fila `Subscription`.
  - Vincula al tenant del driver (auto-provisionar si no existe, reusando `tenancy.create_tenant_for`).
- **`app/api/v1/subscriptions.py`** (router): `POST /subscriptions`. Abierto (el driver nuevo aún no tiene sesión) o crea la cuenta aquí.
- **`app/models/subscription.py`** + migración `0013_subscriptions`:
  - `tenant_id`, `plan_key`, `status` (active|past_due|canceled), `square_subscription_id`,
    `square_customer_id`, `current_period_end`, `simulated`, timestamps.
  - Re-exportar en `app/models/__init__.py`.
- **`app/config.py`**: `SQUARE_PLAN_OPERATOR_MONTHLY`, `SQUARE_PLAN_OPERATOR_ANNUAL`,
  helper `subscription_plan(plan_key) -> plan_variation_id`.
- **Entitlements**: una suscripción Operator activa marca el tenant como plan pago →
  habilita features IA + perfil público (junto con la verificación de permiso del onboarding).

### 3. CORS + config
- Agregar `https://driver.blackvoltmobility.com` a `CORS_ORIGINS`.
- Agregar las nuevas vars a `.env.example`.

### 4. Webhooks (fase 2, después)
- `POST /subscriptions/webhook` con verificación de firma → sincroniza la fila local
  (`invoice.payment_made`, `subscription.updated`, `subscription.canceled` → paid/past_due/canceled).

### 5. Tests (TDD, simulado)
`backend/tests/test_subscriptions_api.py`:
- crear suscripción (simulado) → `status=active`, `simulated=true`.
- `plan_key` inválido → 400.
- idempotencia (mismo email/plan no duplica).
- entitlement: tras suscribir, el tenant queda en plan pago.

---

## Contrato del endpoint

```
POST /api/v1/subscriptions
req:  { "plan_key": "operator", "source_id": "<token Web SDK>", "email": "x@y.com" }
res:  { "status": "active", "subscription_id": "...", "simulated": true|false }
```

## Guardrails (de `CLAUDE.md`)

- El **token secreto de Square NUNCA** va al frontend. La página solo usa el app/location id público de `GET /payments/config`.
- Nada de keys en archivos commiteados — todo por `.env`.
- Simulado por defecto; **nunca** `*_SIMULATED=true` con `APP_ENV=production`.
- Growth es venta asistida (sin Square autoservicio) por ahora.
- No reusar recursos de Eko ni tocar los stacks `eko-*`.

## Orden sugerido

1. Tarea 2 (backend, simulado, con tests) — el núcleo.
2. Tarea 3 (CORS/env).
3. Tarea 1 (portar la landing + cablear al backend ya vivo).
4. Probar end-to-end en **sandbox** con tarjeta `4111 1111 1111 1111`.
5. Tarea 4 (webhooks) y cambio a producción.

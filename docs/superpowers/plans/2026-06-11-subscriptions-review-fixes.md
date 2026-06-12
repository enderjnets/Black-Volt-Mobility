# Subscriptions Hardening (10 code-review fixes) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 10 confirmed code-review findings in the Square Subscriptions backend (commit `1924193`, branch `phase-3-subscriptions`) so the subscribe flow is identity-linked, race-safe, abuse-guarded, and leaks nothing — without touching the ride one-off payment flow.

**Architecture:** The subscribe flow is reordered to "validate → resolve identity (AllowedUser) → Square calls → ONE atomic local transaction", with a partial-unique DB index owning the no-duplicate invariant and an IntegrityError recovery path that best-effort cancels the losing Square subscription. Entitlements are wired into the AI-extract and public-profile endpoints behind an `ENTITLEMENTS_ENFORCED` flag (default off — flipping it is a launch decision, and the default Black Volt tenant is always exempt). Errors become typed with sanitized public codes; a small in-memory rate limiter guards the public endpoint.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Postgres 16, pytest + pytest-asyncio, ruff. Dev gotcha: backend code is NOT bind-mounted — copy into `blackvolt-backend` with `docker cp` and run pytest/alembic inside the container.

**Branch:** work directly on `phase-3-subscriptions` (already checked out, clean tree). One commit per task.

**Test/verify loop used by every task** (run from repo root `~/Black-Volt-Mobility`):

```bash
# sync code into the container (image is COPY-built, not bind-mounted)
docker cp backend/app blackvolt-backend:/app/
docker cp backend/tests blackvolt-backend:/app/
docker cp backend/migrations blackvolt-backend:/app/
# run migrations (only needed after Task 3) and tests inside the container
docker exec blackvolt-backend alembic upgrade head
docker exec blackvolt-backend python -m pytest tests/test_subscriptions.py tests/test_subscriptions_api.py -q
# lint on the host
cd backend && ruff check app tests && cd ..
```

Findings → task map: #9 errors/leak → Task 1 · #4 email case → Task 2 · #5 empty plan id + prod gate → Task 3 · #3 race/unique → Task 4 (schema) + Task 6 (recovery) · #10 idempotency keys + #8 adapter half → Task 5 · #1 identity fork + #6 orphan tenants + #8 status → Task 6 · #2 entitlement unwired → Task 7 · #7 rate limit → Task 8 · cleanup `_client` copy → Task 5.

---

### Task 1: Typed errors + sanitized public error codes (finding #9)

**Files:**
- Modify: `backend/app/services/subscriptions_square.py` (SubscriptionError gains `public_code`; raises carry codes; module logger)
- Modify: `backend/app/services/subscriptions.py` (add `InvalidPlanError`)
- Modify: `backend/app/api/v1/subscriptions.py` (typed except clauses; sanitized detail; drop dead `str()` cast)
- Test: `backend/tests/test_subscriptions_api.py`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_subscriptions_api.py`:

```python
def test_square_error_detail_is_sanitized(monkeypatch):
    """A Square failure must NOT leak the raw API body to the (anonymous) caller —
    only the stable public code. The full message is for server logs."""
    from app.services import subscriptions_square

    async def boom(*, email, idempotency_seed=None, **kw):
        raise subscriptions_square.SubscriptionError(
            "square_customer:400:SECRET-SQUARE-BODY", public_code="square_customer"
        )

    monkeypatch.setattr(subscriptions_square, "create_customer", boom)
    r = _subscribe(_email())
    assert r.status_code == 402, r.text
    assert r.json()["detail"] == "square_customer"
    assert "SECRET-SQUARE-BODY" not in r.text
```

(Note: `idempotency_seed=None, **kw` keeps this test stable across Task 5's signature change.)

- [ ] **Step 2: Run to verify it fails**

Run: `docker cp backend/tests blackvolt-backend:/app/ && docker exec blackvolt-backend python -m pytest tests/test_subscriptions_api.py::test_square_error_detail_is_sanitized -q`
Expected: FAIL — `TypeError: SubscriptionError... unexpected keyword 'public_code'` (or detail contains the body).

- [ ] **Step 3: Implement.** In `backend/app/services/subscriptions_square.py` replace the error class and add a logger:

```python
import logging
...
logger = logging.getLogger("blackvolt.subscriptions")


class SubscriptionError(RuntimeError):
    """`public_code` is the ONLY detail safe to return to the unauthenticated
    caller; the full message (Square status + body) is log-only."""

    public_code = "subscription_failed"

    def __init__(self, message: str, *, public_code: str | None = None):
        super().__init__(message)
        if public_code is not None:
            self.public_code = public_code
```

Update the three raises to carry codes:

```python
raise SubscriptionError(
    f"square_customer:{e.status_code}:{e.body}", public_code="square_customer"
) from e
# ... same pattern: public_code="square_card" and public_code="square_subscription"
```

In `backend/app/services/subscriptions.py` add below the imports (replacing nothing yet):

```python
class InvalidPlanError(adapter.SubscriptionError):
    public_code = "invalid_plan"
```

and change the guard `raise adapter.SubscriptionError("invalid_plan")` → `raise InvalidPlanError(f"unknown plan_key: {plan_key}")`.

In `backend/app/api/v1/subscriptions.py` replace the handler body (and add `import logging` + `logger = logging.getLogger("blackvolt.api.subscriptions")`):

```python
    try:
        sub = await subscriptions.subscribe(
            db, plan_key=body.plan_key, email=body.email, source_id=body.source_id
        )
    except subscriptions.InvalidPlanError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=e.public_code
        ) from e
    except subscriptions_square.SubscriptionError as e:
        logger.error("subscribe failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=e.public_code
        ) from e
    return _out(sub)
```

(The old `if str(e) == "invalid_plan"` string match and the dead `str(body.email)` cast are gone.)

- [ ] **Step 4: Run the subscription tests**

Run: sync + `docker exec blackvolt-backend python -m pytest tests/test_subscriptions_api.py tests/test_subscriptions.py -q`
Expected: ALL PASS (the old `test_invalid_plan_key_400` still passes — detail is still `invalid_plan`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscriptions_square.py backend/app/services/subscriptions.py backend/app/api/v1/subscriptions.py backend/tests/test_subscriptions_api.py
git commit -m "fix(subscriptions): typed errors + sanitized public error codes

Square error bodies (status, internal ids) no longer reach anonymous
callers; the 402 detail is a stable public code and the full error is
log-only. invalid_plan routing is a typed exception, not a string match.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Email normalization — lowercase at the boundary (finding #4)

**Files:**
- Modify: `backend/app/api/v1/subscriptions.py:27-33` (validator lowercases)
- Modify: `backend/app/services/subscriptions.py` (service normalizes too — direct callers/webhooks stay safe)
- Test: `backend/tests/test_subscriptions.py`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_subscriptions.py`:

```python
async def test_email_is_normalized_and_idempotent_across_case(db):
    base = _email()
    mixed = base.replace("svc-", "SVC-").replace("@example.com", "@Example.COM")
    a = await subscriptions.subscribe(
        db, plan_key="operator", email=mixed, source_id="cnon:card-nonce-ok"
    )
    assert a.email == mixed.strip().lower()
    b = await subscriptions.subscribe(
        db, plan_key="operator", email=mixed.lower(), source_id="cnon:card-nonce-ok"
    )
    assert a.id == b.id
    assert await _count(db, mixed.lower()) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: sync + `docker exec blackvolt-backend python -m pytest tests/test_subscriptions.py::test_email_is_normalized_and_idempotent_across_case -q`
Expected: FAIL — `a.email` keeps the mixed case and two rows exist.

- [ ] **Step 3: Implement.** In `backend/app/api/v1/subscriptions.py` validator: `v = v.strip()` → `v = v.strip().lower()` (comment: the rest of the codebase compares emails lowercased — auth.py:131, team.py:73 — and the idempotency key depends on it). In `backend/app/services/subscriptions.py` `subscribe()`, first line of the body:

```python
    email = (email or "").strip().lower()
```

- [ ] **Step 4: Run** the two subscription test files. Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/subscriptions.py backend/app/services/subscriptions.py backend/tests/test_subscriptions.py
git commit -m "fix(subscriptions): normalize emails to lowercase at both boundaries

Case variants no longer defeat the (email, plan_key) idempotency key or
mismatch the lowercased allowed_users identities.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Plan guard for live mode + production availability gate (finding #5)

**Files:**
- Modify: `backend/app/services/subscriptions.py` (guards + `SubscriptionsUnavailableError`)
- Modify: `backend/app/main.py:63-64` area (startup warn parity)
- Modify: `backend/app/api/v1/subscriptions.py` (503 mapping)
- Test: `backend/tests/test_subscriptions.py`, `backend/tests/test_subscriptions_api.py`

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_subscriptions.py`:

```python
async def test_live_mode_rejects_unconfigured_plan(db, monkeypatch):
    """A known plan_key whose variation id env is unset must fail fast in live
    mode (before any Square call / card vaulting), not send '' to Square."""
    s = get_settings()
    monkeypatch.setattr(s, "PAYMENTS_SIMULATED", False)
    monkeypatch.setattr(s, "SQUARE_ACCESS_TOKEN", "fake-token")
    monkeypatch.setattr(s, "SQUARE_LOCATION_ID", "fake-loc")
    assert s.payments_live is True
    with pytest.raises(subscriptions.InvalidPlanError):
        await subscriptions.subscribe(
            db, plan_key="operator_annual", email=_email(), source_id="cnon:x"
        )


async def test_production_with_simulated_payments_is_unavailable(db, monkeypatch):
    """Anti-pattern guard: in production with payments simulated, the public
    endpoint must refuse instead of minting free ACTIVE subscriptions."""
    monkeypatch.setattr(get_settings(), "APP_ENV", "production")
    with pytest.raises(subscriptions.SubscriptionsUnavailableError):
        await subscriptions.subscribe(
            db, plan_key="operator", email=_email(), source_id="cnon:x"
        )
```

(`monkeypatch.setattr` works on the cached Settings instance — pydantic v2 models are mutable here and it restores values after each test.)

- [ ] **Step 2: Run to verify they fail**

Expected: first test — no exception (subscribe "succeeds" simulated? NO: payments_live is True so the adapter would try a real import/call — either way it does NOT raise InvalidPlanError, so FAIL). Second test — no exception → FAIL.

- [ ] **Step 3: Implement.** In `backend/app/services/subscriptions.py` add the error class and guards:

```python
class SubscriptionsUnavailableError(adapter.SubscriptionError):
    public_code = "subscriptions_unavailable"
```

Top of `subscribe()` (after the email normalization line):

```python
    settings = get_settings()
    # Anti-pattern #5 guard: NEVER serve simulated subscriptions in production —
    # they would mint free ACTIVE entitlements for anyone who POSTs.
    if settings.is_production and not settings.payments_live:
        raise SubscriptionsUnavailableError("production requires payments_live")

    plan_variation_id = settings.subscription_plan(plan_key)
    # None → unknown key. Empty string → known key whose variation id env is
    # unset: fine while simulated, but live it must fail BEFORE vaulting a card.
    if plan_variation_id is None or (settings.payments_live and not plan_variation_id):
        raise InvalidPlanError(f"plan not available: {plan_key}")
```

In `backend/app/api/v1/subscriptions.py`, add an except clause ABOVE `InvalidPlanError`:

```python
    except subscriptions.SubscriptionsUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=e.public_code
        ) from e
```

In `backend/app/main.py` lifespan, after the EMAIL_SIMULATED warn:

```python
    if settings.is_production and not settings.payments_live:
        logger.warning(
            "APP_ENV=production but payments not live — public subscriptions disabled (503)."
        )
```

- [ ] **Step 4: Run** both subscription test files. Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscriptions.py backend/app/api/v1/subscriptions.py backend/app/main.py backend/tests/test_subscriptions.py
git commit -m "fix(subscriptions): fail fast on unconfigured plan ids; 503 in prod while simulated

Live mode no longer vaults a card before discovering plan_variation_id is
empty, and production with simulated payments refuses (anti-pattern #5)
instead of minting free entitlements.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Schema owns the invariant — `pending` status + partial unique index (finding #3, schema half)

**Files:**
- Modify: `backend/app/models/subscription.py` (PENDING member; drop `index=True` on plan_key/status; `__table_args__` partial unique index)
- Create: `backend/migrations/versions/0014_subscriptions_hardening.py`
- Test: container `alembic upgrade head` + duplicate-insert probe + `alembic check`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_subscriptions.py`:

```python
async def test_db_enforces_one_open_subscription_per_email_plan(db):
    """The schema (not just app code) owns the no-duplicate invariant: inserting
    a second non-canceled row for the same email+plan violates the partial
    unique index."""
    from sqlalchemy.exc import IntegrityError

    from app.models import SubscriptionStatus

    email = _email()
    db.add(Subscription(tenant_id=1, email=email, plan_key="operator",
                        status=SubscriptionStatus.ACTIVE, simulated=True))
    await db.commit()
    db.add(Subscription(tenant_id=1, email=email, plan_key="operator",
                        status=SubscriptionStatus.PENDING, simulated=True))
    with pytest.raises(IntegrityError):
        await db.commit()
    await db.rollback()
```

(tenant_id=1 exists: the seeded Black Volt tenant.)

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `AttributeError: PENDING` (enum member missing), and without the index the second commit would succeed.

- [ ] **Step 3: Implement model.** `backend/app/models/subscription.py`:
  - Enum gains `PENDING = "pending"` declared LAST (matches Postgres `ADD VALUE` append order):

```python
class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    # Square returned the subscription but the first charge hasn't settled —
    # NOT yet entitled. Appended last to mirror ALTER TYPE ADD VALUE order.
    PENDING = "pending"
```

  - Remove `index=True` from `plan_key` and `status` columns (low-cardinality, never queried alone — replaced by the composite below).
  - Add imports `Index, text` from sqlalchemy and:

```python
    __table_args__ = (
        # One OPEN (non-canceled) subscription per email+plan — the DB enforces
        # idempotency under concurrency; app-level SELECT-then-INSERT can race.
        Index(
            "uq_subscriptions_email_plan_open",
            "email",
            "plan_key",
            unique=True,
            postgresql_where=text("status != 'canceled'"),
        ),
    )
```

- [ ] **Step 4: Write migration** `backend/migrations/versions/0014_subscriptions_hardening.py`:

```python
"""subscriptions hardening — pending status + open-subscription uniqueness

Adds the 'pending' enum value (Square create may return a not-yet-charged
subscription), normalizes existing emails to lowercase, replaces the
low-cardinality plan_key/status indexes with a partial UNIQUE index that makes
the database own the "one open subscription per email+plan" invariant.

Revision ID: 0014_subscriptions_hardening
Revises: 0013_subscriptions
Create Date: 2026-06-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_subscriptions_hardening"
down_revision: str | None = "0013_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Allowed in a transaction since PG12 as long as the new value isn't used
    # in the same transaction (we don't).
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'pending'")
    op.execute("UPDATE subscriptions SET email = lower(trim(email))")
    op.drop_index("ix_subscriptions_plan_key", table_name="subscriptions")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.create_index(
        "uq_subscriptions_email_plan_open",
        "subscriptions",
        ["email", "plan_key"],
        unique=True,
        postgresql_where=sa.text("status != 'canceled'"),
    )


def downgrade() -> None:
    op.drop_index("uq_subscriptions_email_plan_open", table_name="subscriptions")
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_plan_key", "subscriptions", ["plan_key"])
    # Postgres cannot remove an enum value; 'pending' stays behind (harmless).
```

- [ ] **Step 5: Apply + verify drift.** Sync, then:

```bash
docker exec blackvolt-backend alembic upgrade head
docker exec blackvolt-backend alembic check
```

Expected: upgrade applies; `alembic check` reports "No new upgrade operations detected." **If it flags the partial index where-clause** (text-comparison quirk on reflected predicates), adjust the model's `text(...)` literal to the exact reflected form shown in the diff (e.g. `text("status <> 'canceled'::subscription_status")`) and re-check. If existing dev rows violate uniqueness (duplicate open email+plan from old runs), delete the extras first: `docker exec blackvolt-db psql -U blackvolt -c "DELETE FROM subscriptions a USING subscriptions b WHERE a.id > b.id AND a.email=b.email AND a.plan_key=b.plan_key AND a.status != 'canceled' AND b.status != 'canceled'"`.

- [ ] **Step 6: Run the new test + both files.** Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/subscription.py backend/migrations/versions/0014_subscriptions_hardening.py backend/tests/test_subscriptions.py
git commit -m "feat(db): subscriptions pending status + partial unique open-subscription index

The DB now owns 'one open subscription per email+plan' (double-click race
can no longer double-charge), low-value indexes dropped, existing emails
normalized. Migration 0014.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Adapter — deterministic idempotency keys, charged_through_date, cancel, shared client (findings #10, #8-adapter, cleanup)

**Files:**
- Create: `backend/app/services/square_common.py`
- Modify: `backend/app/services/subscriptions_square.py`
- Modify: `backend/app/services/payments_square.py` (`_client` body → shared factory; NOTHING else)
- Test: `backend/tests/test_subscriptions.py`

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_subscriptions.py`:

```python
def test_idempotency_keys_are_deterministic_per_intent():
    """Retrying the SAME checkout (same nonce) must reuse the same Square
    idempotency keys so Square collapses duplicates; a NEW checkout (new nonce)
    gets fresh keys. A random-per-attempt key would double-bill on a lost
    response."""
    k1 = subscriptions_square._idempotency_key("subscription", "CUST1", "PLANVAR", "nonce-A")
    k2 = subscriptions_square._idempotency_key("subscription", "CUST1", "PLANVAR", "nonce-A")
    k3 = subscriptions_square._idempotency_key("subscription", "CUST1", "PLANVAR", "nonce-B")
    assert k1 == k2
    assert k1 != k3
    uuid.UUID(k1)  # valid uuid string


def test_parse_square_date():
    from datetime import UTC, datetime

    assert subscriptions_square._parse_square_date("2026-07-11") == datetime(
        2026, 7, 11, tzinfo=UTC
    )
    assert subscriptions_square._parse_square_date(None) is None
    assert subscriptions_square._parse_square_date("garbage") is None


async def test_cancel_subscription_simulated_is_noop():
    await subscriptions_square.cancel_subscription(subscription_id="SIMSUB-x")  # no raise
```

- [ ] **Step 2: Run to verify they fail**

Expected: FAIL — `AttributeError: _idempotency_key` / `_parse_square_date` / `cancel_subscription`.

- [ ] **Step 3: Implement.** Create `backend/app/services/square_common.py`:

```python
"""Shared Square client factory — ONE source of truth for the payments_live
simulation gate, token, and sandbox/production env, used by both the one-off
payments adapter and the subscriptions adapter (so a cutover change can never
apply to one and silently miss the other)."""
from __future__ import annotations

from app.config import get_settings


def square_client():
    """Async Square client for the configured environment, or None when simulated."""
    settings = get_settings()
    if not settings.payments_live:
        return None
    from square import AsyncSquare
    from square.environment import SquareEnvironment

    env = (
        SquareEnvironment.PRODUCTION
        if settings.SQUARE_ENV == "production"
        else SquareEnvironment.SANDBOX
    )
    return AsyncSquare(token=settings.SQUARE_ACCESS_TOKEN, environment=env)
```

In BOTH adapters replace the `_client()` body with (keep the `_client` name — it stays a local monkeypatch/seam):

```python
from app.services.square_common import square_client
...
def _client():
    return square_client()
```

In `backend/app/services/subscriptions_square.py` add helpers + rework the three calls:

```python
from datetime import UTC, datetime
...

def _idempotency_key(kind: str, *parts: str) -> str:
    """Deterministic per business intent (uuid5): the same checkout retried —
    same nonce — reuses the key so Square collapses duplicates instead of
    creating a second live subscription; a new checkout gets a fresh key."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "blackvolt:" + kind + ":" + ":".join(parts)))


def _parse_square_date(value) -> datetime | None:
    """Square's charged_through_date is 'YYYY-MM-DD'."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None
```

Signature/body changes:
- `async def create_customer(*, email: str, idempotency_seed: str) -> CustomerResult:` — live call uses `idempotency_key=_idempotency_key("customer", email, idempotency_seed)`.
- `create_card` — `idempotency_key=_idempotency_key("card", customer_id, source_id)`.
- `async def create_subscription(*, plan_variation_id, customer_id, card_id, location_id, idempotency_seed: str) -> SubscriptionResult:` — `idempotency_key=_idempotency_key("subscription", customer_id, plan_variation_id, idempotency_seed)`; live result becomes:

```python
    s = resp.subscription
    return SubscriptionResult(
        square_subscription_id=s.id,
        # A missing status must NOT default to ACTIVE — never grant entitlement
        # on absent data.
        status=s.status or "PENDING",
        current_period_end=_parse_square_date(getattr(s, "charged_through_date", None)),
        simulated=False,
    )
```

Add at the end:

```python
async def cancel_subscription(*, subscription_id: str) -> None:
    """Best-effort cancel — used when we lose the local insert race AFTER Square
    already created the subscription. Never raises: the caller is already on an
    error path; a failure here is logged for manual reconciliation in Square."""
    client = _client()
    if client is None:
        return
    try:
        await client.subscriptions.cancel(subscription_id=subscription_id)
    except Exception:
        logger.exception(
            "cancel_subscription failed — reconcile %s in the Square dashboard",
            subscription_id,
        )
```

Update the two call sites in `backend/app/services/subscriptions.py` to pass the seed (full rewrite lands in Task 6; for now keep the flow identical, just add args):

```python
    customer = await adapter.create_customer(email=email, idempotency_seed=source_id)
    ...
    result = await adapter.create_subscription(
        plan_variation_id=plan_variation_id,
        customer_id=customer.square_customer_id,
        card_id=card.square_card_id,
        location_id=settings.SQUARE_LOCATION_ID,
        idempotency_seed=source_id,
    )
```

- [ ] **Step 4: Run** both subscription files AND the payments tests (the `_client` hoist touches `payments_square.py`):

Run: sync + `docker exec blackvolt-backend python -m pytest tests/ -q -k "subscription or payment"`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/square_common.py backend/app/services/subscriptions_square.py backend/app/services/payments_square.py backend/app/services/subscriptions.py backend/tests/test_subscriptions.py
git commit -m "fix(subscriptions): deterministic Square idempotency keys + period-end parse + best-effort cancel

uuid5 keys per checkout intent collapse lost-response retries (no double
recurring billing); charged_through_date now persists; shared square_client()
factory so payments/subscriptions can't drift on cutover.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: subscribe() rewrite — identity link, atomic transaction, race recovery, real status (findings #1, #6, #3-service, #8-service)

**Files:**
- Modify: `backend/app/services/tenancy.py:69-81` (`create_tenant_for` gains `commit: bool = True`)
- Modify: `backend/app/services/subscriptions.py` (full rewrite of `subscribe` + `_active_for`→`_current_for`; drop `STATUS_ACTIVE`)
- Test: `backend/tests/test_subscriptions.py`

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_subscriptions.py`:

```python
from app.models import AllowedUser, SubscriptionStatus  # noqa: E402  (top of file)
from app.models.allowed_user import ROLE_DRIVER  # noqa: E402


async def _allowed_row(db, email: str) -> AllowedUser | None:
    return (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalars().first()


async def test_subscribe_creates_linked_allowed_user(db):
    """The paying driver must be able to LOG INTO the tenant they paid for:
    subscribe creates an active allowed_users row pinned to the same tenant."""
    email = _email()
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    row = await _allowed_row(db, email)
    assert row is not None
    assert row.active is True
    assert row.role == ROLE_DRIVER
    assert row.tenant_id == sub.tenant_id
    assert row.added_by == "subscription"


async def test_subscribe_reuses_existing_driver_tenant(db):
    """A driver who already signed in (allowed_users.tenant_id set) must get the
    subscription on THAT tenant — not a duplicate workspace."""
    from app.services.tenancy import create_tenant_for

    email = _email()
    tenant = await create_tenant_for(db, name=f"Pre {uuid.uuid4().hex[:6]}")
    db.add(AllowedUser(email=email, role=ROLE_DRIVER, active=True, tenant_id=tenant.id))
    await db.commit()
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert sub.tenant_id == tenant.id
    assert await subscriptions.tenant_is_paid(db, tenant_id=tenant.id) is True


async def test_subscribe_disabled_account_refused_before_charge(db, monkeypatch):
    """A deactivated allowed_user must be refused BEFORE any Square call."""
    email = _email()
    db.add(AllowedUser(email=email, role=ROLE_DRIVER, active=False))
    await db.commit()

    async def explode(**kw):
        raise AssertionError("Square must not be called for a disabled account")

    monkeypatch.setattr(subscriptions.adapter, "create_customer", explode)
    with pytest.raises(subscriptions.AccountDisabledError):
        await subscriptions.subscribe(
            db, plan_key="operator", email=email, source_id="cnon:x"
        )


async def test_tenant_slug_does_not_leak_email(db):
    from app.services.tenancy import get_tenant

    email = f"john.doe.{uuid.uuid4().hex[:8]}@private-domain.com"
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    tenant = await get_tenant(db, sub.tenant_id)
    assert "private-domain" not in tenant.slug


async def test_square_failure_leaves_no_rows(db, monkeypatch):
    """Finding #6: a declined card must leave NO orphan tenant/allowed_user/
    subscription rows — Square runs BEFORE any local write."""
    from app.models import Tenant

    email = _email()

    async def declined(**kw):
        raise subscriptions_square.SubscriptionError("square_card:400:declined",
                                                     public_code="square_card")

    monkeypatch.setattr(subscriptions.adapter, "create_card", declined)
    tenants_before = (
        await db.execute(select(func.count()).select_from(Tenant))
    ).scalar_one()
    with pytest.raises(subscriptions_square.SubscriptionError):
        await subscriptions.subscribe(
            db, plan_key="operator", email=email, source_id="cnon:x"
        )
    await db.rollback()
    tenants_after = (
        await db.execute(select(func.count()).select_from(Tenant))
    ).scalar_one()
    assert tenants_after == tenants_before
    assert await _count(db, email) == 0
    assert await _allowed_row(db, email) is None


async def test_pending_square_status_is_persisted_not_active(db, monkeypatch):
    """Finding #8: Square's returned status must be persisted; PENDING must not
    grant entitlement."""
    async def pending_sub(**kw):
        return subscriptions_square.SubscriptionResult(
            square_subscription_id=f"SIMSUB-{uuid.uuid4().hex[:18]}",
            status="PENDING", current_period_end=None, simulated=True,
        )

    monkeypatch.setattr(subscriptions.adapter, "create_subscription", pending_sub)
    email = _email()
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert sub.status == SubscriptionStatus.PENDING
    assert await subscriptions.tenant_is_paid(db, tenant_id=sub.tenant_id) is False
    # A pending row still blocks duplicates (idempotent on OPEN, not just active).
    again = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert again.id == sub.id


async def test_insert_race_recovers_and_cancels_duplicate(db, monkeypatch):
    """Finding #3 (service half): when two requests race past the existence
    check, the loser's commit hits the unique index → it must cancel its Square
    subscription (best-effort) and return the winner's row."""
    email = _email()
    real = subscriptions._current_for
    calls = {"n": 0}

    async def racy(db_, *, email, plan_key):
        calls["n"] += 1
        if calls["n"] <= 2:  # both "concurrent" checks miss
            return None
        return await real(db_, email=email, plan_key=plan_key)

    canceled = []

    async def fake_cancel(*, subscription_id):
        canceled.append(subscription_id)

    monkeypatch.setattr(subscriptions, "_current_for", racy)
    monkeypatch.setattr(subscriptions.adapter, "cancel_subscription", fake_cancel)
    a = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    b = await subscriptions.subscribe(
        db, plan_key="operator", email=email, source_id="cnon:card-nonce-ok"
    )
    assert a.id == b.id
    assert await _count(db, email) == 1
    assert len(canceled) == 1 and canceled[0] != a.square_subscription_id
```

Also UPDATE the existing `test_subscribe_simulated_creates_active_row`: `subscriptions.STATUS_ACTIVE` → `SubscriptionStatus.ACTIVE` (the alias is deleted).

- [ ] **Step 2: Run to verify the new tests fail** (no AllowedUser link, orphan tenants persist, status hardcoded, no `_current_for`).

- [ ] **Step 3: Implement `create_tenant_for(commit=...)`** in `backend/app/services/tenancy.py`:

```python
async def create_tenant_for(
    db: AsyncSession, *, name: str, slug: str | None = None, commit: bool = True
) -> Tenant:
    """Provision a brand-new driver tenant (their own workspace) + default rates.
    The slug is derived from the name (or `slug`) and de-duplicated. Called when
    an allow-listed driver signs in for the first time. With commit=False the
    rows are only flushed — the caller owns the transaction (atomic flows like
    subscribe must not persist a tenant before the payment succeeds)."""
    nm = (name or "").strip() or "Driver"
    uslug = await _unique_slug(db, slug or nm)
    t = Tenant(slug=uslug, name=nm)
    db.add(t)
    await db.flush()  # populate t.id for the RateConfig FK
    db.add(RateConfig(tenant_id=t.id, **DEFAULT_RATES))
    if commit:
        await db.commit()
        await db.refresh(t)
    return t
```

- [ ] **Step 4: Rewrite `backend/app/services/subscriptions.py`.** Full new content:

```python
"""Subscription orchestration: validate the plan, resolve the driver's identity
(allowed_users), drive the Square adapter, and persist atomically. Tenant-scoped.

Flow order is a security invariant: all Square calls happen BEFORE any local
write, and tenant + allowed_user + subscription land in ONE transaction — a
declined card leaves zero rows behind. The driver's identity is the lowercased
email: an existing allowed_user keeps their tenant (the subscription unlocks the
workspace they actually log into); a brand-new subscriber gets a tenant AND an
active allowed_users row so they can sign in with Google immediately."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AllowedUser, Subscription, SubscriptionStatus
from app.models.allowed_user import ROLE_DRIVER
from app.services import subscriptions_square as adapter
from app.services.tenancy import DEFAULT_TENANT_SLUG, create_tenant_for, get_tenant

logger = logging.getLogger("blackvolt.subscriptions")


class InvalidPlanError(adapter.SubscriptionError):
    public_code = "invalid_plan"


class AccountDisabledError(adapter.SubscriptionError):
    public_code = "account_disabled"


class SubscriptionsUnavailableError(adapter.SubscriptionError):
    public_code = "subscriptions_unavailable"


# Square statuses we trust to mean "money confirmed". Anything else (PENDING,
# unknown, missing) persists as PENDING — present but NOT entitled.
_STATUS_MAP = {"ACTIVE": SubscriptionStatus.ACTIVE, "PENDING": SubscriptionStatus.PENDING}


async def _current_for(db: AsyncSession, *, email: str, plan_key: str) -> Subscription | None:
    """The OPEN (non-canceled) subscription for email+plan, if any. Open — not
    just active — so a pending/past_due row also blocks a duplicate charge."""
    return (
        await db.execute(
            select(Subscription).where(
                Subscription.email == email,
                Subscription.plan_key == plan_key,
                Subscription.status != SubscriptionStatus.CANCELED,
            )
        )
    ).scalars().first()


async def subscribe(
    db: AsyncSession, *, plan_key: str, email: str, source_id: str
) -> Subscription:
    """Subscribe a driver to a plan. Idempotent on (email, plan_key) while open."""
    email = (email or "").strip().lower()
    settings = get_settings()
    # Anti-pattern #5 guard: NEVER serve simulated subscriptions in production —
    # they would mint free ACTIVE entitlements for anyone who POSTs.
    if settings.is_production and not settings.payments_live:
        raise SubscriptionsUnavailableError("production requires payments_live")

    plan_variation_id = settings.subscription_plan(plan_key)
    # None → unknown key. Empty string → known key whose variation id env is
    # unset: fine while simulated, but live it must fail BEFORE vaulting a card.
    if plan_variation_id is None or (settings.payments_live and not plan_variation_id):
        raise InvalidPlanError(f"plan not available: {plan_key}")

    existing = await _current_for(db, email=email, plan_key=plan_key)
    if existing is not None:
        return existing

    allowed = (
        await db.execute(select(AllowedUser).where(AllowedUser.email == email))
    ).scalar_one_or_none()
    if allowed is not None and not allowed.active:
        # Deactivated by the owner — refuse BEFORE charging the card.
        raise AccountDisabledError(f"allowed_user inactive: {email}")

    # ── Square first: a payment failure must leave NO local rows behind. ──
    customer = await adapter.create_customer(email=email, idempotency_seed=source_id)
    card = await adapter.create_card(
        customer_id=customer.square_customer_id, source_id=source_id
    )
    result = await adapter.create_subscription(
        plan_variation_id=plan_variation_id,
        customer_id=customer.square_customer_id,
        card_id=card.square_card_id,
        location_id=settings.SQUARE_LOCATION_ID,
        idempotency_seed=source_id,
    )

    # ── One atomic transaction: tenant + allowed_user + subscription. ──
    tenant_id = allowed.tenant_id if allowed is not None else None
    if tenant_id is None:
        # Name from the email's local part only — the full email must not leak
        # into the public tenant slug.
        tenant = await create_tenant_for(db, name=email.split("@", 1)[0], commit=False)
        tenant_id = tenant.id
        if allowed is None:
            allowed = AllowedUser(
                email=email, role=ROLE_DRIVER, active=True,
                tenant_id=tenant_id, added_by="subscription",
            )
            db.add(allowed)
        else:
            allowed.tenant_id = tenant_id

    sub = Subscription(
        tenant_id=tenant_id,
        email=email,
        plan_key=plan_key,
        status=_STATUS_MAP.get((result.status or "").upper(), SubscriptionStatus.PENDING),
        square_subscription_id=result.square_subscription_id,
        square_customer_id=customer.square_customer_id,
        current_period_end=result.current_period_end,
        simulated=result.simulated,
    )
    db.add(sub)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a concurrent race on uq_subscriptions_email_plan_open: undo our
        # local rows, cancel OUR duplicate Square subscription (best-effort),
        # and return the winner's.
        await db.rollback()
        await adapter.cancel_subscription(
            subscription_id=result.square_subscription_id
        )
        winner = await _current_for(db, email=email, plan_key=plan_key)
        if winner is not None:
            return winner
        raise adapter.SubscriptionError(
            f"subscription insert conflict without a winner row: {email}",
            public_code="subscription_conflict",
        ) from None
    await db.refresh(sub)
    return sub


async def tenant_is_paid(db: AsyncSession, *, tenant_id: int) -> bool:
    """Entitlement marker: the tenant has an ACTIVE subscription. In production
    simulated rows never count — only real Square money grants entitlement."""
    conditions = [
        Subscription.tenant_id == tenant_id,
        Subscription.status == SubscriptionStatus.ACTIVE,
    ]
    if get_settings().is_production:
        conditions.append(Subscription.simulated.is_(False))
    row = (await db.execute(select(Subscription.id).where(*conditions))).first()
    return row is not None
```

(Note `tenant_has_entitlements` is added in Task 7 — `get_tenant`/`DEFAULT_TENANT_SLUG` imports land here so Task 7 only appends.)

- [ ] **Step 5: Run** both subscription files. Expected: ALL PASS (including the Task 1-3 tests against the rewritten flow).

- [ ] **Step 6: Run the FULL suite** (tenancy signature change + auth flow share `create_tenant_for`):

Run: sync + `docker exec blackvolt-backend python -m pytest tests/ -q`
Expected: ALL PASS (~160).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/subscriptions.py backend/app/services/tenancy.py backend/tests/test_subscriptions.py
git commit -m "fix(subscriptions): link paid tenant to allowed_users + atomic no-orphan flow + race recovery

Square runs before any local write; tenant + allowed_user + subscription
commit in one transaction (declined card leaves zero rows). Existing
drivers keep their tenant; new subscribers can sign in immediately.
Square's real status is persisted (PENDING is not entitled) and an insert
race cancels the duplicate Square subscription.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire entitlements — `tenant_has_entitlements` + gates (finding #2)

**Files:**
- Modify: `backend/app/config.py` (`ENTITLEMENTS_ENFORCED`)
- Modify: `backend/app/services/subscriptions.py` (append helper)
- Modify: `backend/app/api/v1/rides.py:206-239` (`/rides/extract` gate)
- Modify: `backend/app/api/v1/tenant.py:172-179` (public profile gate)
- Modify: `docker-compose.yml` + `.env.example`
- Test: `backend/tests/test_subscriptions.py`

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_subscriptions.py`:

```python
async def test_entitlements_flag_off_everything_allowed(db):
    from app.services.tenancy import create_tenant_for

    tenant = await create_tenant_for(db, name=f"Free {uuid.uuid4().hex[:6]}")
    assert await subscriptions.tenant_has_entitlements(db, tenant_id=tenant.id) is True


async def test_entitlements_enforced_gates_unpaid_but_exempts_default(db, monkeypatch):
    from app.services.tenancy import create_tenant_for, get_default_tenant

    monkeypatch.setattr(get_settings(), "ENTITLEMENTS_ENFORCED", True)
    unpaid = await create_tenant_for(db, name=f"Unpaid {uuid.uuid4().hex[:6]}")
    assert await subscriptions.tenant_has_entitlements(db, tenant_id=unpaid.id) is False
    default = await get_default_tenant(db)
    assert await subscriptions.tenant_has_entitlements(db, tenant_id=default.id) is True
    paid = await subscriptions.subscribe(
        db, plan_key="operator", email=_email(), source_id="cnon:card-nonce-ok"
    )
    assert await subscriptions.tenant_has_entitlements(db, tenant_id=paid.tenant_id) is True


async def test_simulated_subscription_not_paid_in_production(db, monkeypatch):
    sub = await subscriptions.subscribe(
        db, plan_key="operator", email=_email(), source_id="cnon:card-nonce-ok"
    )
    assert await subscriptions.tenant_is_paid(db, tenant_id=sub.tenant_id) is True
    monkeypatch.setattr(get_settings(), "APP_ENV", "production")
    assert await subscriptions.tenant_is_paid(db, tenant_id=sub.tenant_id) is False
```

- [ ] **Step 2: Run to verify they fail** (`AttributeError: tenant_has_entitlements`; prod test fails on the un-hardened... already hardened in Task 6 — that one should PASS; keep it as a regression pin).

- [ ] **Step 3: Implement.** `backend/app/config.py`, after `SQUARE_PLAN_OPERATOR_ANNUAL`:

```python
    # Entitlement enforcement — when true, paid-plan features (AI extraction,
    # public profile) require an active subscription; the default Black Volt
    # tenant is always exempt (the owner doesn't subscribe to himself). Ships
    # false so flipping it is an explicit launch decision once billing is live.
    ENTITLEMENTS_ENFORCED: bool = False
```

Append to `backend/app/services/subscriptions.py`:

```python
async def tenant_has_entitlements(db: AsyncSession, *, tenant_id: int) -> bool:
    """Gate for paid-plan features. False only when enforcement is on AND the
    tenant is neither the default (owner) tenant nor actively subscribed."""
    if not get_settings().ENTITLEMENTS_ENFORCED:
        return True
    tenant = await get_tenant(db, tenant_id)
    if tenant is not None and tenant.slug == DEFAULT_TENANT_SLUG:
        return True
    return await tenant_is_paid(db, tenant_id=tenant_id)
```

`backend/app/api/v1/rides.py` — `/rides/extract` gains a db dep + gate (add `from app.services import subscriptions` to the existing services import line):

```python
@router.post("/rides/extract")
async def extract_reservation(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_staff),
):
    """... (keep existing docstring) ..."""
    tenant_id = await resolve_tenant_id(db, payload)
    if not await subscriptions.tenant_has_entitlements(db, tenant_id=tenant_id):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="subscription_required"
        )
    settings = get_settings()
    ...  # rest unchanged
```

`backend/app/api/v1/tenant.py` — public profile (404, never 402: don't reveal billing state publicly):

```python
@router.get("/tenants/{slug}")
async def get_public_profile(slug: str, db: AsyncSession = Depends(get_db)):
    t = await tenancy.get_tenant_by_slug(db, slug)
    if t is None or not await subscriptions.tenant_has_entitlements(db, tenant_id=t.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return await tenancy.public_profile(db, slug=slug)
```

(add `from app.services import subscriptions` to tenant.py imports.)

`docker-compose.yml` backend environment (the known gotcha — vars must be declared here):

```yaml
      ENTITLEMENTS_ENFORCED: ${ENTITLEMENTS_ENFORCED:-false}
```

`.env.example`:

```bash
# Paid-plan gating (AI extract + public profile). Flip to true at billing launch.
ENTITLEMENTS_ENFORCED=false
```

- [ ] **Step 4: Run the full suite** (the rides/tenant gates must not break existing smart/profile tests — flag defaults false). Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/subscriptions.py backend/app/api/v1/rides.py backend/app/api/v1/tenant.py docker-compose.yml .env.example backend/tests/test_subscriptions.py
git commit -m "feat(subscriptions): wire paid entitlements into AI extract + public profile

tenant_has_entitlements gates /rides/extract (402) and /tenants/{slug}
(404) behind ENTITLEMENTS_ENFORCED (default false — launch decision);
default tenant exempt; simulated rows never count in production.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Rate-limit the public endpoint (finding #7)

**Files:**
- Create: `backend/app/services/ratelimit.py`
- Modify: `backend/app/config.py`, `backend/app/api/v1/subscriptions.py`, `docker-compose.yml`, `.env.example`
- Test: `backend/tests/test_ratelimit.py` (new), `backend/tests/test_subscriptions_api.py`

- [ ] **Step 1: Write the failing tests.** Create `backend/tests/test_ratelimit.py`:

```python
"""Sliding-window limiter unit tests (injected clock — no sleeps)."""
from app.services import ratelimit


def setup_function():
    ratelimit.reset()


def test_allows_up_to_limit_then_blocks():
    for i in range(3):
        assert ratelimit.allow("k", limit=3, window_seconds=60, now=float(i)) is True
    assert ratelimit.allow("k", limit=3, window_seconds=60, now=3.0) is False


def test_window_slides():
    for i in range(3):
        assert ratelimit.allow("k", limit=3, window_seconds=60, now=float(i)) is True
    assert ratelimit.allow("k", limit=3, window_seconds=60, now=61.5) is True


def test_keys_are_independent():
    assert ratelimit.allow("a", limit=1, window_seconds=60, now=0.0) is True
    assert ratelimit.allow("b", limit=1, window_seconds=60, now=0.0) is True
    assert ratelimit.allow("a", limit=1, window_seconds=60, now=1.0) is False
```

Append to `backend/tests/test_subscriptions_api.py` (and add to the env block at the top, BEFORE `get_settings.cache_clear()`: `os.environ["SUBSCRIBE_RATE_PER_IP_HOURLY"] = "100000"` — every test in this module shares the TestClient IP, so only the per-email limit is exercised):

```python
def test_per_email_rate_limit_429():
    from app.services import ratelimit

    ratelimit.reset()
    email = _email()
    limit = get_settings().SUBSCRIBE_RATE_PER_EMAIL_HOURLY
    for _ in range(limit):
        assert _subscribe(email).status_code == 201
    r = _subscribe(email)
    assert r.status_code == 429, r.text
    assert r.json()["detail"] == "rate_limited"
```

(add `from app.config import get_settings` is already imported at module top.)

- [ ] **Step 2: Run to verify they fail** (`ModuleNotFoundError: app.services.ratelimit`).

- [ ] **Step 3: Implement.** Create `backend/app/services/ratelimit.py`:

```python
"""Tiny in-memory sliding-window rate limiter for abuse-prone public endpoints.

Single-process by design (the backend runs one uvicorn worker); swap for a
Redis-backed equivalent before scaling horizontally. The clock is injectable
so tests never sleep."""
from __future__ import annotations

import time

_hits: dict[str, list[float]] = {}


def allow(key: str, *, limit: int, window_seconds: float, now: float | None = None) -> bool:
    """Record an attempt under `key`; True while under `limit` per window."""
    ts = time.monotonic() if now is None else now
    bucket = [t for t in _hits.get(key, []) if ts - t < window_seconds]
    if len(bucket) >= limit:
        _hits[key] = bucket
        return False
    bucket.append(ts)
    _hits[key] = bucket
    return True


def reset() -> None:
    """Test hook: drop all counters."""
    _hits.clear()
```

`backend/app/config.py`, after `ENTITLEMENTS_ENFORCED`:

```python
    # Abuse guard for the PUBLIC subscribe endpoint (attempts/hour). Per-email
    # catches a stuck client; per-IP catches enumeration (Cloudflare passes the
    # real IP in cf-connecting-ip).
    SUBSCRIBE_RATE_PER_EMAIL_HOURLY: int = 5
    SUBSCRIBE_RATE_PER_IP_HOURLY: int = 30
```

`backend/app/api/v1/subscriptions.py` — add imports (`Request` from fastapi; `from app.config import get_settings`; `from app.services import ratelimit`) and at the top of the endpoint:

```python
@router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscribeBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    ip = request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown"
    )
    if not ratelimit.allow(
        f"sub:ip:{ip}", limit=settings.SUBSCRIBE_RATE_PER_IP_HOURLY, window_seconds=3600
    ) or not ratelimit.allow(
        f"sub:email:{body.email}",
        limit=settings.SUBSCRIBE_RATE_PER_EMAIL_HOURLY,
        window_seconds=3600,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited"
        )
    try:
        ...  # existing flow
```

`docker-compose.yml` backend environment + `.env.example`:

```yaml
      SUBSCRIBE_RATE_PER_EMAIL_HOURLY: ${SUBSCRIBE_RATE_PER_EMAIL_HOURLY:-5}
      SUBSCRIBE_RATE_PER_IP_HOURLY: ${SUBSCRIBE_RATE_PER_IP_HOURLY:-30}
```

- [ ] **Step 4: Run the full suite.** Expected: ALL PASS — if any pre-existing subscriptions_api test trips the email limit, it uses unique emails (max 2 calls per email), so only the new test reaches the cap.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ratelimit.py backend/app/config.py backend/app/api/v1/subscriptions.py docker-compose.yml .env.example backend/tests/test_ratelimit.py backend/tests/test_subscriptions_api.py
git commit -m "feat(subscriptions): rate-limit the public subscribe endpoint

Per-email (5/h) + per-IP (30/h, cf-connecting-ip aware) sliding window —
the only unauthenticated DB-writing endpoint no longer mints unbounded
tenants under abuse.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Final verification sweep

**Files:** none new — verification only.

- [ ] **Step 1: Full suite + lint + drift, fresh sync:**

```bash
docker cp backend/app blackvolt-backend:/app/ && docker cp backend/tests blackvolt-backend:/app/ && docker cp backend/migrations blackvolt-backend:/app/
docker exec blackvolt-backend alembic upgrade head
docker exec blackvolt-backend alembic check
docker exec blackvolt-backend python -m pytest tests/ -q
cd backend && ruff check app tests && cd ..
```

Expected: "No new upgrade operations detected", ALL tests pass, ruff clean.

- [ ] **Step 2: Migration cycle sanity:**

```bash
docker exec blackvolt-backend alembic downgrade -1 && docker exec blackvolt-backend alembic upgrade head
```

Expected: clean down/up of 0014.

- [ ] **Step 3: Show the user the consolidated diff:**

```bash
git log --oneline main..HEAD && git diff 1924193..HEAD --stat
```

- [ ] **Step 4: Confirm the worktree only holds the known untracked design assets** (`git status --porcelain` → only `docs/black-volt-one-pager.html`, `docs/handoff-subscriptions.md`, `frontend/driver-landing.html`, plus this plan file — commit the plan file under `docs/superpowers/plans/`).

```bash
git add docs/superpowers/plans/2026-06-11-subscriptions-review-fixes.md
git commit -m "docs: subscriptions hardening plan (10 review fixes)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage:** #1→T6, #2→T7, #3→T4+T6, #4→T2, #5→T3, #6→T6, #7→T8, #8→T5+T6, #9→T1, #10→T5, cleanup `_client`→T5. ✓
- **Type consistency:** `_current_for(db, *, email, plan_key)` used in T6 tests and impl; `idempotency_seed` kwarg consistent across T1 test shim, T5 adapter, T6 service; `public_code` defined T1, consumed T1/T3/T6. ✓
- **Known risk:** `alembic check` may flag the partial index where-clause text — handled explicitly in T4 Step 5.
- **Out of scope (deferred, documented):** webhooks (Tarea 4) own ongoing status sync; Redis-backed rate limiting if multi-worker; sim-id/error-wrap helper dedup (parametric, low value).

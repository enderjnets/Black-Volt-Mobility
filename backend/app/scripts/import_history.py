"""Import Black Volt's real history into the platform DB.

- Upserts the known recurring clients (Demetra, Rob, Michelle) — from the ROG
  `clients_riders.md` + Square customers.
- Pulls the REAL Square payment history (production) and records, per COMPLETED
  payment, a completed Ride + a captured Payment with the real amount + date,
  linked to the client when the Square customer maps to one of ours.

READ-ONLY against Square (lists customers + payments) — it never charges or
captures anything; it only mirrors existing history into our DB. Idempotent:
clients are matched by email/phone, payments skipped if already imported by
square_payment_id.

Run:  docker compose exec -T backend python -m app.scripts.import_history
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db.base import get_session_factory
from app.models import Client, Payment, PaymentMethod, PaymentStatus, Ride, RideStatus
from app.services.tenancy import get_default_tenant

SQUARE_VERSION = "2025-04-16"

# Known recurring clients (clients_riders.md + Square). square_ids map Square
# customer ids → this client so historical payments link correctly.
KNOWN_CLIENTS = [
    {
        "name": "Demetra Sullivan",
        "phone": "+12533803149",
        "email": "Demetra.Sullivan@gmail.com",
        "square_ids": ["0DV8ES34ZN51GTHC08AGXNRPMG"],
        "route": ("Parker, CO", "Denver Intl (DEN)"),
    },
    {
        "name": "Rob Humphries",
        "phone": "+17203226115",
        "email": None,
        "square_ids": [],
        "route": ("Boulder, CO", "Denver Intl (DEN)"),
    },
    {
        "name": "Michelle Hadley",
        "phone": "+16232102037",
        "email": "Michelle.Hadley@schomp.com",
        "square_ids": ["0FJ5GFM0FKQKT7TMR58KQZMRRG"],
        "route": ("Lone Tree, CO", "Denver Intl (DIA)"),
    },
]


def _base() -> str:
    s = get_settings()
    return (
        "https://connect.squareup.com"
        if s.SQUARE_ENV == "production"
        else "https://connect.squareupsandbox.com"
    )


def _headers() -> dict:
    return {
        "Square-Version": SQUARE_VERSION,
        "Authorization": f"Bearer {get_settings().SQUARE_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def fetch_square_payments() -> list[dict]:
    out: list[dict] = []
    cursor = None
    with httpx.Client(timeout=20.0) as http:
        while True:
            params = {"limit": 100, "sort_order": "ASC"}
            if cursor:
                params["cursor"] = cursor
            r = http.get(f"{_base()}/v2/payments", headers=_headers(), params=params)
            r.raise_for_status()
            data = r.json()
            out.extend(data.get("payments", []))
            cursor = data.get("cursor")
            if not cursor:
                break
    return out


def fetch_square_customers() -> dict[str, dict]:
    with httpx.Client(timeout=20.0) as http:
        r = http.get(f"{_base()}/v2/customers", headers=_headers(), params={"limit": 100})
        r.raise_for_status()
        return {c["id"]: c for c in r.json().get("customers", [])}


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _upsert_client(db, *, tenant_id: int, name, phone, email) -> Client:
    row = None
    if email:
        row = (
            await db.execute(
                select(Client).where(Client.tenant_id == tenant_id, Client.email == email)
            )
        ).scalar_one_or_none()
    if row is None and phone:
        row = (
            await db.execute(
                select(Client).where(Client.tenant_id == tenant_id, Client.phone == phone)
            )
        ).scalar_one_or_none()
    if row is None:
        row = Client(tenant_id=tenant_id, name=name, phone=phone, email=email)
        db.add(row)
        await db.flush()
    else:
        if name and not row.name:
            row.name = name
        if phone and not row.phone:
            row.phone = phone
        if email and not row.email:
            row.email = email
    return row


async def run() -> None:
    settings = get_settings()
    if not settings.SQUARE_ACCESS_TOKEN:
        print("No SQUARE_ACCESS_TOKEN configured — aborting.")
        return

    async with get_session_factory()() as db:
        tenant = await get_default_tenant(db)
        tid = tenant.id

        # 1) Upsert known clients + build Square customer_id → (client, route) map.
        sq_to_client: dict[str, tuple[Client, tuple[str, str]]] = {}
        for spec in KNOWN_CLIENTS:
            c = await _upsert_client(
                db, tenant_id=tid, name=spec["name"], phone=spec["phone"], email=spec["email"]
            )
            for sid in spec["square_ids"]:
                sq_to_client[sid] = (c, spec["route"])
        await db.commit()
        print(f"clients upserted: {[s['name'] for s in KNOWN_CLIENTS]}")

        # Also map any existing client by Square customer email (e.g. margie).
        sq_customers = fetch_square_customers()
        for sid, cust in sq_customers.items():
            if sid in sq_to_client:
                continue
            em = cust.get("email_address")
            if not em:
                continue
            existing = (
                await db.execute(
                    select(Client).where(Client.tenant_id == tid, Client.email == em)
                )
            ).scalar_one_or_none()
            if existing:
                sq_to_client[sid] = (existing, ("Black Volt ride", "—"))

        # 2) Import COMPLETED Square payments → completed rides + captured payments.
        payments = fetch_square_payments()
        imported = skipped = 0
        for p in payments:
            if p.get("status") != "COMPLETED":
                continue
            sq_id = p["id"]
            exists = (
                await db.execute(
                    select(Payment).where(
                        Payment.tenant_id == tid, Payment.square_payment_id == sq_id
                    )
                )
            ).scalar_one_or_none()
            if exists:
                skipped += 1
                continue
            amount = p.get("amount_money", {}).get("amount", 0)
            currency = p.get("amount_money", {}).get("currency", "USD")
            when = _parse_dt(p.get("created_at"))
            cust_id = p.get("customer_id")
            linked = sq_to_client.get(cust_id)
            client = linked[0] if linked else None
            pickup, dropoff = linked[1] if linked else ("Black Volt ride", "—")
            cust = sq_customers.get(cust_id or "", {})
            pax_name = None
            if client is None and cust:
                nm = " ".join(filter(None, [cust.get("given_name"), cust.get("family_name")]))
                pax_name = nm or None

            ride = Ride(
                tenant_id=tid,
                client_id=client.id if client else None,
                status=RideStatus.COMPLETED,
                pickup_text=pickup,
                dropoff_text=dropoff,
                scheduled_at=when,
                fare_total=round(amount / 100.0, 2),
                currency=currency,
                passenger_name=(client.name if client else pax_name),
                notes="Imported from Square history",
                payment_id=sq_id,
                payment_method=PaymentMethod.SQUARE,
                paid=True,
                paid_at=when,
                created_at=when,
            )
            db.add(ride)
            await db.flush()
            db.add(
                Payment(
                    tenant_id=tid,
                    ride_id=ride.id,
                    status=PaymentStatus.CAPTURED,
                    amount=amount,
                    currency=currency,
                    square_payment_id=sq_id,
                    simulated=False,
                    created_at=when,
                )
            )
            imported += 1
        await db.commit()
        print(f"payments imported: {imported}, skipped (already present): {skipped}")


if __name__ == "__main__":
    asyncio.run(run())

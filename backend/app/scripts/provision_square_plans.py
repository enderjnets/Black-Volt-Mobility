"""One-off: provision the Operator subscription plan (monthly + annual) in Square.

Idempotent via a deterministic idempotency key (re-running returns the same
catalog objects, never duplicates). Prints the two plan-variation ids to paste
into SQUARE_PLAN_OPERATOR_MONTHLY / SQUARE_PLAN_OPERATOR_ANNUAL.

Run inside the backend container with production env wired:

    docker exec blackvolt-backend python -m app.scripts.provision_square_plans

Requires PAYMENTS_SIMULATED=false + a Square access token with catalog write
scope (a Dashboard personal access token has it). Reuses the shared client
factory so it always targets the configured environment (sandbox/production).
"""
from __future__ import annotations

import asyncio
import uuid

from app.services.square_common import square_client

_NS = uuid.NAMESPACE_URL
PLAN_NAME = "Operator"
MONTHLY_AMOUNT = 2900  # $29.00
ANNUAL_AMOUNT = 29000  # $290.00


def _idem(parts: str) -> str:
    return str(uuid.uuid5(_NS, f"blackvolt:catalog:{parts}"))


def _variation(temp_id: str, name: str, cadence: str, amount: int) -> dict:
    return {
        "type": "SUBSCRIPTION_PLAN_VARIATION",
        "id": temp_id,
        "subscription_plan_variation_data": {
            "name": name,
            "phases": [
                {
                    "cadence": cadence,
                    "pricing": {
                        "type": "STATIC",
                        "price_money": {"amount": amount, "currency": "USD"},
                    },
                }
            ],
        },
    }


async def main() -> None:
    client = square_client()
    if client is None:
        raise SystemExit(
            "square_client() is None — needs PAYMENTS_SIMULATED=false "
            "+ SQUARE_ACCESS_TOKEN + SQUARE_LOCATION_ID"
        )

    plan = {
        "type": "SUBSCRIPTION_PLAN",
        "id": "#operator",
        "subscription_plan_data": {
            "name": PLAN_NAME,
            "subscription_plan_variations": [
                _variation("#operator-monthly", "Operator Monthly", "MONTHLY", MONTHLY_AMOUNT),
                _variation("#operator-annual", "Operator Annual", "ANNUAL", ANNUAL_AMOUNT),
            ],
        },
    }

    resp = await client.catalog.batch_upsert(
        idempotency_key=_idem("operator-plan-v1"),
        batches=[{"objects": [plan]}],
    )

    mappings = {m.client_object_id: m.object_id for m in (resp.id_mappings or [])}
    print("ID MAPPINGS:")
    for k, v in mappings.items():
        print(f"  {k} -> {v}")
    print()
    print(f"SQUARE_PLAN_OPERATOR_MONTHLY={mappings.get('#operator-monthly')}")
    print(f"SQUARE_PLAN_OPERATOR_ANNUAL={mappings.get('#operator-annual')}")


if __name__ == "__main__":
    asyncio.run(main())

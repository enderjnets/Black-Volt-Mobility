"""Backfill: push existing upcoming scheduled rides to Google Calendar.

Run once after configuring the service account (and optionally on a timer):
    docker compose exec -T backend python -m app.scripts.sync_calendar
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.base import get_session_factory
from app.models import Ride, RideStatus
from app.services import booking
from app.services.tenancy import get_default_tenant

_ACTIVE = (
    RideStatus.REQUESTED,
    RideStatus.QUOTED,
    RideStatus.CONFIRMED,
    RideStatus.ASSIGNED,
    RideStatus.EN_ROUTE,
)


async def run() -> None:
    async with get_session_factory()() as db:
        tenant = await get_default_tenant(db)
        now = datetime.now(UTC)
        rides = (
            await db.execute(
                select(Ride).where(
                    Ride.tenant_id == tenant.id,
                    Ride.scheduled_at >= now,
                    Ride.status.in_(_ACTIVE),
                    Ride.google_event_id.is_(None),
                )
            )
        ).scalars().all()
        print(f"upcoming scheduled rides to sync: {len(rides)}")
        synced = 0
        for ride in rides:
            await booking.sync_ride_to_calendar(db, ride)
            if ride.google_event_id:
                synced += 1
        print(f"synced to calendar: {synced}")


if __name__ == "__main__":
    asyncio.run(run())

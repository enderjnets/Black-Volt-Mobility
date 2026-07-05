"""Joules system-prompt builder: live zone-price override surfaces, upcoming
rides are serialized (cancelled excluded, capped at 3, Denver time), and the
language hint switches the reply-language instruction. Pure — no DB needed
(``build_system_prompt`` reads only its arguments).
"""
import asyncio
import datetime as dt
import os

os.environ["AUTH_SECRET"] = "api-test-secret"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.models import Client, RateConfig, Ride, RideStatus, Tenant  # noqa: E402
from app.services import joules  # noqa: E402

_UTC = dt.UTC


def _tenant() -> Tenant:
    return Tenant(
        id=1,
        slug="black-volt",
        name="Black Volt Mobility",
        vehicle="Kia EV9",
        city="Denver, CO",
        phone="+13035550000",
    )


def _client() -> Client:
    return Client(
        id=1, tenant_id=1, name="Ada Lovelace", first_name="Ada", email="ada@example.com", lang="en"
    )


def _ride(
    rid: int,
    status: RideStatus,
    when: dt.datetime | None,
    pickup="Aurora, CO",
    dropoff="DEN",
) -> Ride:
    return Ride(
        id=rid,
        tenant_id=1,
        client_id=1,
        status=status,
        pickup_text=pickup,
        dropoff_text=dropoff,
        scheduled_at=when,
        fare_total=110.0,
    )


def _build(rides, rc, lang="en") -> str:
    return asyncio.run(
        joules.build_system_prompt(
            None, tenant=_tenant(), client=_client(), rides=rides, rc=rc, lang_hint=lang
        )
    )


def test_live_zone_override_surfaces_in_pricing_block():
    rc = RateConfig(
        tenant_id=1, base=28.0, per_mile=2.4, minimum=90.0, zone_prices={"denver_metro": 105}
    )
    prompt = _build([], rc)
    assert "$105" in prompt  # override wins over the $110 code default
    assert "Denver metro" in prompt


def test_upcoming_ride_serialized_denver_time_cancelled_excluded():
    upcoming = _ride(10, RideStatus.CONFIRMED, dt.datetime(2030, 6, 1, 21, 0, tzinfo=_UTC))
    cancelled = _ride(11, RideStatus.CANCELLED, dt.datetime(2030, 6, 2, 21, 0, tzinfo=_UTC))
    rc = RateConfig(tenant_id=1, base=28, per_mile=2.4, minimum=90)
    prompt = _build([upcoming, cancelled], rc)
    assert "Ride #10" in prompt
    assert "Ride #11" not in prompt  # cancelled dropped
    assert "Denver time" in prompt


def test_rides_capped_at_three():
    rides = [
        _ride(i, RideStatus.CONFIRMED, dt.datetime(2030, 6, i, 21, 0, tzinfo=_UTC))
        for i in range(1, 5)
    ]
    prompt = _build(rides, RateConfig(tenant_id=1, base=28, per_mile=2.4, minimum=90))
    shown = [f"Ride #{i}" in prompt for i in range(1, 5)]
    assert sum(shown) == 3


def test_no_rides_message():
    prompt = _build([], RateConfig(tenant_id=1, base=28, per_mile=2.4, minimum=90))
    assert "no upcoming rides" in prompt.lower()


def test_reply_follows_the_passengers_latest_message_language():
    # Joules must mirror whatever language the passenger writes in, so a mid-chat
    # switch is honoured — the UI language only decides the tie-break default.
    for lang in ("en", "es"):
        prompt = _build([], RateConfig(tenant_id=1, base=28, per_mile=2.4, minimum=90), lang=lang)
        assert "same language the passenger's most recent message" in prompt.lower()


def test_language_default_tiebreak_follows_ui_hint():
    rc = RateConfig(tenant_id=1, base=28, per_mile=2.4, minimum=90)
    assert "use Spanish" in _build([], rc, lang="es")
    assert "use English" in _build([], rc, lang="en")
    # a Spanish variant tag still defaults to Spanish
    assert "use Spanish" in _build([], rc, lang="es-MX")


def test_serialize_rides_helper_direct():
    active = _ride(1, RideStatus.EN_ROUTE, dt.datetime(2030, 1, 1, 20, 0, tzinfo=_UTC))
    out = joules._serialize_rides([active], _tenant())
    assert "Ride #1" in out
    assert "en_route" in out
    # driver contact exposed for an active ride
    assert "+13035550000" in out

"""Passenger profile completeness + serialization.

A profile is "complete" once it has the data Google can't give us and that a
booking needs: first name, last name, and a phone the driver can reach. Shared
by the /me/profile endpoints and the auth session payloads so the frontend can
decide whether to show the onboarding gate.
"""
from __future__ import annotations

from app.models import Client


def is_complete(client: Client) -> bool:
    return bool(client.first_name) and bool(client.last_name) and bool(client.phone)


def serialize(client: Client) -> dict:
    return {
        "first_name": client.first_name,
        "last_name": client.last_name,
        "name": client.name,
        "email": client.email,
        "phone": client.phone,
        "home_address": client.home_address,
        "sms_consent": client.sms_consent,
        "profile_complete": is_complete(client),
    }

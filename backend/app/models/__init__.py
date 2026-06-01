"""Re-export every model so Alembic autogenerate + the app see them."""
from app.models.analytics import AnalyticsEvent
from app.models.client import Client
from app.models.payment import Payment, PaymentStatus
from app.models.rate_config import RateConfig
from app.models.ride import Ride, RideStatus
from app.models.tenant import Tenant

__all__ = [
    "Tenant",
    "Client",
    "RateConfig",
    "Ride",
    "RideStatus",
    "AnalyticsEvent",
    "Payment",
    "PaymentStatus",
]

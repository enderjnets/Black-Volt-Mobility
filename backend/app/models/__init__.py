"""Re-export every model so Alembic autogenerate + the app see them."""
from app.models.client import Client
from app.models.rate_config import RateConfig
from app.models.ride import Ride, RideStatus
from app.models.tenant import Tenant

__all__ = ["Tenant", "Client", "RateConfig", "Ride", "RideStatus"]

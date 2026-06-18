"""Re-export every model so Alembic autogenerate + the app see them."""
from app.models.allowed_user import AllowedUser
from app.models.analytics import AnalyticsEvent
from app.models.client import Client
from app.models.driver_funnel import DriverFunnelLog, DriverGoal
from app.models.payment import Payment, PaymentStatus
from app.models.platform_stat import PlatformStat
from app.models.rate_config import RateConfig
from app.models.ride import PaymentMethod, Ride, RideStatus
from app.models.social import SocialAccount, SocialInteraction, SocialPost
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant import Tenant

__all__ = [
    "Tenant",
    "Client",
    "RateConfig",
    "Ride",
    "RideStatus",
    "PaymentMethod",
    "AnalyticsEvent",
    "Payment",
    "PaymentStatus",
    "AllowedUser",
    "Subscription",
    "SubscriptionStatus",
    "DriverFunnelLog",
    "DriverGoal",
    "PlatformStat",
    "SocialAccount",
    "SocialPost",
    "SocialInteraction",
]

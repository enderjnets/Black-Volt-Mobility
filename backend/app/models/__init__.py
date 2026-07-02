"""Re-export every model so Alembic autogenerate + the app see them."""
from app.models.allowed_user import AllowedUser
from app.models.analytics import AnalyticsEvent
from app.models.calendar_credential import CalendarCredential
from app.models.client import Client
from app.models.client_address import ClientAddress
from app.models.discount import DiscountCampaign, DiscountCode
from app.models.document_consent import DocumentConsent
from app.models.driver_funnel import DriverFunnelLog, DriverGoal
from app.models.event import Event, EventSuggestion
from app.models.payment import Payment, PaymentStatus
from app.models.platform_stat import PlatformStat
from app.models.rate_config import RateConfig
from app.models.review import Review, ReviewInvite, ReviewStatus
from app.models.ride import PaymentMethod, Ride, RideStatus
from app.models.social import (
    SocialAccount,
    SocialFeedback,
    SocialInteraction,
    SocialPost,
)
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant import Tenant

__all__ = [
    "DiscountCampaign",
    "DiscountCode",
    "DocumentConsent",
    "Tenant",
    "Client",
    "ClientAddress",
    "RateConfig",
    "Review",
    "ReviewInvite",
    "ReviewStatus",
    "Ride",
    "RideStatus",
    "PaymentMethod",
    "AnalyticsEvent",
    "Payment",
    "PaymentStatus",
    "AllowedUser",
    "CalendarCredential",
    "Subscription",
    "SubscriptionStatus",
    "DriverFunnelLog",
    "DriverGoal",
    "Event",
    "EventSuggestion",
    "PlatformStat",
    "SocialAccount",
    "SocialPost",
    "SocialFeedback",
    "SocialInteraction",
]

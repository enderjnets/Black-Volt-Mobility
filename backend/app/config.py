"""Settings — read from env vars. Never put secrets in code."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "Black Volt Mobility"
    APP_VERSION: str = "0.0.1"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://blackvolt:blackvolt_local_pass@db:5432/blackvolt"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # ─── LLM ────────────────────────────────────────────────────────────
    # Both providers speak the `anthropic-messages` HTTP protocol → we use the
    # `anthropic` Python SDK with a custom `base_url` per provider. Fallback is
    # INLINE per request: if PRIMARY times out or errors, the same request
    # retries against FALLBACK before erroring out. NEVER use Anthropic OAuth here.
    LLM_PRIMARY: str = "kimi"  # "kimi" | "minimax"
    LLM_FALLBACK: str = "minimax"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_TOKENS_DEFAULT: int = 600

    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.kimi.com/coding"
    KIMI_MODEL: str = "kimi-for-coding"

    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimax.io/anthropic"
    MINIMAX_MODEL: str = "MiniMax-M2.7"

    # ─── Auth (Phase 1) ─────────────────────────────────────────────────
    # Driver/owner dashboard auth (shared password, HMAC-signed cookie) coexists
    # with Google Sign In for passengers. Default OFF for dev/demo; production
    # turns it on. Two audiences: owner/driver (dashboard) and passenger (portal).
    AUTH_ENABLED: bool = False
    DASHBOARD_PASSWORD: str = ""
    AUTH_SECRET: str = ""  # token signing key; derived from the password if empty
    AUTH_TTL_HOURS: int = 168  # 7 days

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_ADMIN_EMAILS: str = ""  # comma-separated; pinned owner/driver admins

    @property
    def google_admin_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.GOOGLE_ADMIN_EMAILS.split(",") if e.strip()]

    # ─── Maps (Phase 2) ─────────────────────────────────────────────────
    # Google Maps Platform powers route distance/duration + place autocomplete.
    # MAPS_SIMULATED (or a missing key) returns deterministic stub routes so the
    # booking flow works end-to-end in dev/demo without billing. NEVER ship
    # MAPS_SIMULATED=true with APP_ENV=production.
    MAPS_SIMULATED: bool = True
    GOOGLE_MAPS_API_KEY: str = ""
    # Airports treated as triggering the airport surcharge / flat handling.
    AIRPORT_KEYWORDS: str = "den,dia,denver intl,denver international,airport,aeropuerto"

    @property
    def airport_keywords_list(self) -> list[str]:
        return [k.strip().lower() for k in self.AIRPORT_KEYWORDS.split(",") if k.strip()]

    @property
    def maps_live(self) -> bool:
        """Real Google Maps calls require an explicit opt-out of simulation AND a key."""
        return not self.MAPS_SIMULATED and bool(self.GOOGLE_MAPS_API_KEY)

    # ─── Payments / Square (Phase 3) ────────────────────────────────────
    # Authorize at booking → capture on completion → refund on cancel. With
    # PAYMENTS_SIMULATED (or no token) the service fakes payment ids so the flow
    # works without Square. SQUARE_ENV picks sandbox vs production base URL.
    # NEVER ship PAYMENTS_SIMULATED=true with APP_ENV=production.
    PAYMENTS_SIMULATED: bool = True
    SQUARE_ENV: str = "sandbox"  # "sandbox" | "production"
    SQUARE_ACCESS_TOKEN: str = ""
    SQUARE_LOCATION_ID: str = ""
    SQUARE_APPLICATION_ID: str = ""

    @property
    def payments_live(self) -> bool:
        """Real Square calls require an explicit opt-out of simulation AND a token+location."""
        return (
            not self.PAYMENTS_SIMULATED
            and bool(self.SQUARE_ACCESS_TOKEN)
            and bool(self.SQUARE_LOCATION_ID)
        )

    # ─── Google Calendar (scheduled rides → Black Volt calendar) ────────
    # A service account (shared on the Black Volt calendar) pushes ride events.
    # CALENDAR_SIMULATED (or no creds) makes calendar writes a no-op so the
    # booking flow works without Google. NEVER ship simulated with prod intent.
    CALENDAR_SIMULATED: bool = True
    GOOGLE_CALENDAR_ID: str = ""  # e.g. blackvoltmobility@gmail.com
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""  # path to the mounted SA JSON
    CALENDAR_TIMEZONE: str = "America/Denver"

    @property
    def calendar_live(self) -> bool:
        return (
            not self.CALENDAR_SIMULATED
            and bool(self.GOOGLE_SERVICE_ACCOUNT_FILE)
            and bool(self.GOOGLE_CALENDAR_ID)
        )

    # Minimum gap (minutes) required between two rides before they count as a
    # scheduling conflict (travel + turnaround for the single driver).
    RIDE_BUFFER_MIN: int = 45

    # ─── Smart reservation (screenshot → reservation, vision) ───────────
    # The driver pastes screenshots of a client's SMS/WhatsApp/email; a vision
    # model reads them and pre-fills the reservation. Only MiniMax-M3 (not the
    # M2.x text models, not kimi-for-coding) accepts image content blocks over
    # the anthropic-compatible endpoint. SMART_SIMULATED (or a missing key)
    # returns a deterministic sample so the flow works without billing.
    # Uses a dedicated key so the vision model can differ from the chat LLM.
    # Two providers:
    #  - "minimax_coding_vlm": MiniMax Coding Plan (sk-cp key) → POST
    #    {host}/v1/coding_plan/vlm, one image per call (we merge). Subscription.
    #  - "minimax_anthropic": MiniMax-M3 over the anthropic endpoint (sk-api key,
    #    pay-as-you-go). Multiple images in one call.
    SMART_SIMULATED: bool = True
    SMART_VISION_PROVIDER: str = "minimax_coding_vlm"  # | "minimax_anthropic"
    SMART_VISION_API_KEY: str = ""
    SMART_MAX_IMAGES: int = 5
    SMART_VISION_TIMEOUT: float = 90.0  # vision is slower than chat
    # Coding-plan VLM
    SMART_VISION_HOST: str = "https://api.minimax.io"  # | https://api.minimaxi.com
    # Anthropic endpoint (MiniMax-M3)
    SMART_VISION_BASE_URL: str = "https://api.minimax.io/anthropic"
    SMART_VISION_MODEL: str = "MiniMax-M3"

    @property
    def smart_live(self) -> bool:
        """Real vision extraction requires opting out of simulation AND a key."""
        return not self.SMART_SIMULATED and bool(self.SMART_VISION_API_KEY)

    # ─── CORS ───────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3005"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

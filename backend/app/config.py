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

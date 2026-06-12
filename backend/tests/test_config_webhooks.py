"""Config-level guards for the subscription webhook + CORS wiring (Tarea A)."""
import os

os.environ.setdefault("DASHBOARD_PASSWORD", "test-pw")

from app.config import Settings, get_settings  # noqa: E402

get_settings.cache_clear()


def test_webhooks_live_false_without_key_or_url():
    s = Settings(SQUARE_WEBHOOK_SIGNATURE_KEY="", SQUARE_WEBHOOK_URL="")
    assert s.webhooks_live is False
    s = Settings(SQUARE_WEBHOOK_SIGNATURE_KEY="whsig", SQUARE_WEBHOOK_URL="")
    assert s.webhooks_live is False
    s = Settings(SQUARE_WEBHOOK_SIGNATURE_KEY="", SQUARE_WEBHOOK_URL="https://x/y")
    assert s.webhooks_live is False


def test_webhooks_live_true_with_key_and_url():
    s = Settings(
        SQUARE_WEBHOOK_SIGNATURE_KEY="whsig_abc",
        SQUARE_WEBHOOK_URL="https://driver.blackvoltmobility.com/api/v1/webhooks/square",
    )
    assert s.webhooks_live is True


def test_driver_origin_in_default_cors():
    s = Settings()
    assert "https://driver.blackvoltmobility.com" in s.cors_origins_list

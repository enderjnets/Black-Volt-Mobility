"""Buffer adapter + config tests (no network; GraphQL layer mocked)."""
import os

os.environ["BUFFER_API_KEY"] = "test-buffer-key"
os.environ["BUFFER_ORG_ID"] = "org-test"
os.environ["SOCIAL_PUBLISH_VIA_BUFFER"] = "true"
os.environ["SOCIAL_SIMULATED"] = "false"

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()


def test_is_buffer_live_true_when_configured():
    s = get_settings()
    assert s.is_buffer_live is True


def test_is_buffer_live_false_without_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "BUFFER_API_KEY", "", raising=False)
    # A fresh Settings with no key is not live.
    from app.config import Settings
    s = Settings(BUFFER_API_KEY="", BUFFER_ORG_ID="org", SOCIAL_PUBLISH_VIA_BUFFER=True)
    assert s.is_buffer_live is False

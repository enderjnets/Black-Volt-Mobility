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


from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

from app.services import social_buffer as B  # noqa: E402


@pytest.mark.asyncio
async def test_create_post_builds_ig_reel_sharenow(monkeypatch):
    captured = {}

    async def fake_gql(query, variables):
        captured["v"] = variables
        return {"createPost": {"id": "bufpost1", "status": "queued", "dueAt": None}}

    monkeypatch.setattr(B, "_gql", fake_gql)
    res = await B.create_post(
        channel_id="ch1", service="instagram", text="hi #x",
        video_url="https://app.blackvoltmobility.com/media/a.mp4", mode="shareNow",
    )
    assert res["id"] == "bufpost1"
    inp = captured["v"]["input"]
    assert inp["channelId"] == "ch1"
    assert inp["mode"] == "shareNow"
    assert inp["schedulingType"] == "automatic"
    assert inp["assets"] == [{"video": {"url": "https://app.blackvoltmobility.com/media/a.mp4"}}]
    assert inp["metadata"]["instagram"] == {"type": "reel", "shouldShareToFeed": True}
    assert "dueAt" not in inp


@pytest.mark.asyncio
async def test_create_post_scheduled_sets_dueat(monkeypatch):
    captured = {}

    async def fake_gql(query, variables):
        captured["v"] = variables
        return {"createPost": {"id": "p2", "status": "scheduled"}}

    monkeypatch.setattr(B, "_gql", fake_gql)
    dt = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    await B.create_post(
        channel_id="ch1", service="instagram", text="x",
        video_url="https://h/m.mp4", mode="customScheduled", due_at=dt,
    )
    assert captured["v"]["input"]["dueAt"] == dt.isoformat()


@pytest.mark.asyncio
async def test_list_channels_maps_connected(monkeypatch):
    async def fake_gql(query, variables):
        return {"channels": [
            {"id": "c1", "service": "instagram", "name": "bv",
             "displayName": "bv", "isDisconnected": False, "isLocked": False},
            {"id": "c2", "service": "facebook", "name": "fb",
             "displayName": "fb", "isDisconnected": True, "isLocked": False},
        ]}

    monkeypatch.setattr(B, "_gql", fake_gql)
    chans = await B.list_channels()
    by_id = {c["id"]: c for c in chans}
    assert by_id["c1"]["connected"] is True
    assert by_id["c1"]["display_name"] == "bv"
    assert by_id["c2"]["connected"] is False


@pytest.mark.asyncio
async def test_gql_raises_on_graphql_errors(monkeypatch):
    import httpx

    def handler(request):
        return httpx.Response(200, json={"errors": [{"message": "bad"}]})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)
    with pytest.raises(B.BufferError):
        await B._gql("query { x }", {})

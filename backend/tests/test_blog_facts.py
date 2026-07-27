"""The backend's copy of the route table must not drift from the pages it describes.

`frontend/lib/seoRoutes.ts` is the hand-written source of truth: eight landing pages whose
fares came from the live quote engine. The writer quotes those numbers in articles, so a
price changed on the site and not here would put a wrong fare in front of a customer.
Rather than couple the backend to a TypeScript file at runtime, this test parses it.
"""
import os
import re
from pathlib import Path

os.environ["DASHBOARD_PASSWORD"] = "test-pw"

from app.services import blog_facts  # noqa: E402

_TS = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "seoRoutes.ts"


def _parse_ts() -> dict[str, dict]:
    src = _TS.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for block in src.split("\n  {\n")[1:]:
        slug = re.search(r'slug: "([^"]+)"', block)
        if not slug:
            continue
        nums = {}
        for field in ("priceFrom", "distanceMi", "durationMin"):
            m = re.search(rf"{field}: (\d+),", block)
            if m:
                nums[field] = int(m.group(1))
        out[slug.group(1)] = nums
    return out


def test_the_route_table_is_parseable():
    """A guard on the guard: if the TS shape changes, fail loudly instead of passing empty."""
    parsed = _parse_ts()
    assert len(parsed) >= 8
    assert all(set(v) == {"priceFrom", "distanceMi", "durationMin"} for v in parsed.values())


def test_every_backend_route_matches_the_published_page():
    parsed = _parse_ts()
    for route in blog_facts.ROUTES:
        assert route.slug in parsed, f"{route.slug} is not a published page any more"
        page = parsed[route.slug]
        assert route.price_from == page["priceFrom"], f"{route.slug}: fare drifted"
        assert route.distance_mi == page["distanceMi"], f"{route.slug}: distance drifted"
        assert route.duration_min == page["durationMin"], f"{route.slug}: duration drifted"


def test_no_published_route_is_missing_from_the_backend():
    """A new landing page the writer is never told about is a page that gets no links."""
    assert set(_parse_ts()) == {r.slug for r in blog_facts.ROUTES}


def test_route_paths_are_link_shaped():
    assert blog_facts.route_paths() == {f"/rides/{r.slug}" for r in blog_facts.ROUTES}
    assert blog_facts.MONEY_PATHS >= blog_facts.route_paths()
    assert "/book" in blog_facts.MONEY_PATHS


def test_the_fare_table_reaches_the_prompt():
    block = blog_facts.routes_block()
    for route in blog_facts.ROUTES:
        assert route.path in block
        assert f"${route.price_from}" in block
        assert f"{route.duration_min} minutes" in block


def test_the_truth_block_forbids_a_fleet():
    truth = blog_facts.truth_block().lower()
    assert "fleet" in truth and "one" in truth
    assert blog_facts.VEHICLE.lower() in truth

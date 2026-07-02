"""Curated, factual per-venue knowledge for the event landing pages.

Drop-off/pickup spots, nearby eats and traffic tips belong to the *venue*, not the
individual event — Red Rocks always has the same rideshare zones and the same bars in
Morrison. We curate one profile per watchlist venue (owner reviews the copy before
launch) plus a `generic` fallback; every event at that venue reuses it.

This is a code constant on purpose (like `services/zones.py`): a handful of venues that
change rarely, no per-event cost, no DB round-trip on the public landing.
"""
from __future__ import annotations

# Substring aliases (matched against a lowercased venue name) → watchlist key.
_ALIASES: dict[str, tuple[str, ...]] = {
    "empower_field": ("empower field", "mile high"),
    "red_rocks": ("red rocks",),
    "ball_arena": ("ball arena",),
    "coors_field": ("coors field",),
    "fiddlers_green": ("fiddler",),
}

VENUE_PROFILES: dict[str, dict] = {
    "empower_field": {
        "name": "Empower Field at Mile High",
        "address": "1701 Bryant St, Denver, CO 80204",
        "coords": (39.7439, -105.0201),
        "dropoff": [
            "We drop you at the Bryant St / W 17th Ave side, closest to Gates 2 and 3, "
            "so you walk straight in.",
            "On concert and game nights we arrive at least 60 minutes before kickoff or "
            "doors — the streets around the stadium lock up fast.",
        ],
        "pickup": [
            "After the show we meet you two to three blocks off-site (along Federal Blvd "
            "or Old West Colfax) to skip the parking-lot gridlock.",
            "The first 30 minutes after the final whistle or encore are the worst — "
            "with a scheduled Black Volt pickup you walk to a calm corner instead of "
            "fighting for a rideshare.",
        ],
        "eats": [
            "LoHi is a five-minute ride away: Avanti Food & Beverage for a rooftop and "
            "a dozen kitchens under one roof.",
            "Little Man Ice Cream and the Highland bars are perfect for a pre-show bite.",
            "Jefferson Park sits right by the stadium for a quick drink before you walk over.",
        ],
        "parking_pain": "Stadium lots run $30–$60 and empty out at a crawl — one flat "
        "Black Volt fare each way beats parking plus the post-game standstill.",
    },
    "red_rocks": {
        "name": "Red Rocks Amphitheatre",
        "address": "18300 W Alameda Pkwy, Morrison, CO 80465",
        "coords": (39.6654, -105.2057),
        "dropoff": [
            "We use the Upper North Lot rideshare zone (Entrance 1) so you avoid the long "
            "climb from the lower lots.",
            "Arrive early — the two-lane road into the park backs up for miles before big "
            "shows.",
        ],
        "pickup": [
            "We meet you back at the Upper North Lot rideshare zone after the show.",
            "Cell service at Red Rocks is weak, so we lock in your pickup time in advance — "
            "no scrambling for signal to summon a car.",
            "Leave a song or two before the encore and you clear the canyon before the "
            "30-to-45-minute exit jam.",
        ],
        "eats": [
            "Downtown Morrison is minutes away: The Morrison Inn for margaritas and "
            "Mexican before the show.",
            "Red Rocks Beer Garden and the Bear Creek patios are great for a pre-show meal.",
            "Grab coffee or a bite in Morrison on the way up rather than the long venue lines.",
        ],
        "parking_pain": "Red Rocks parking is first-come and the canyon exit is legendary "
        "— a prepaid Black Volt round trip means no driving the dark mountain road tired.",
    },
    "ball_arena": {
        "name": "Ball Arena",
        "address": "1000 Chopper Cir, Denver, CO 80204",
        "coords": (39.7487, -105.0077),
        "dropoff": [
            "We drop you at the Chopper Circle rideshare zone, steps from the main "
            "entrances.",
            "For Nuggets and Avalanche nights we time the drop-off ahead of the downtown "
            "rush.",
        ],
        "pickup": [
            "We meet you at the Chopper Circle rideshare zone after the final buzzer.",
            "Prefer to skip the crowd? We can pick you up at Union Station, a 10-minute "
            "walk with zero gridlock.",
        ],
        "eats": [
            "LoDo and Larimer Square are a short ride away for dinner or drinks.",
            "Union Station's Great Hall has restaurants and bars under one roof.",
            "Tap Fourteen and the Ballpark-district rooftops are easy pre-game stops.",
        ],
        "parking_pain": "Downtown event parking spikes on game nights — a flat Black Volt "
        "fare each way is simpler than circling for a garage.",
    },
    "coors_field": {
        "name": "Coors Field",
        "address": "2001 Blake St, Denver, CO 80205",
        "coords": (39.7559, -104.9942),
        "dropoff": [
            "We drop you on Blake St between 20th and 22nd, right by the main gates.",
            "On weekend series and concerts we arrive early to beat the Ballpark-district "
            "crowds.",
        ],
        "pickup": [
            "We meet you two blocks northeast (around Larimer and 27th) — it clears far "
            "faster than the Blake St crawl.",
            "Text us when you leave your section and we time the pickup so you barely wait.",
        ],
        "eats": [
            "The Ballpark district is packed with rooftops: ViewHouse for a big patio.",
            "Larimer Square and RiNo are a quick ride for dinner before first pitch.",
            "Great Divide's taproom is a local favorite steps from the field.",
        ],
        "parking_pain": "Ballpark-district lots surge on game days — let Black Volt handle "
        "both legs so you can enjoy a drink without worrying about the drive.",
    },
    "fiddlers_green": {
        "name": "Fiddler's Green Amphitheatre",
        "address": "6350 Greenwood Plaza Blvd, Greenwood Village, CO 80111",
        "coords": (39.6013, -104.8961),
        "dropoff": [
            "Fiddler's Green is the closest big venue to our Aurora base, so response "
            "times are short and reliable.",
            "We drop you at the Greenwood Plaza Blvd rideshare area near the main entrance.",
        ],
        "pickup": [
            "We meet you at the Greenwood Plaza Blvd rideshare area after the show.",
            "The DTC streets empty quickly, so your ride home is fast once you reach us.",
        ],
        "eats": [
            "The Denver Tech Center along I-25 has plenty of options: Yard House and "
            "Ocean Prime for a sit-down dinner.",
            "Comida and the Landmark plaza restaurants are a short ride for pre-show plans.",
        ],
        "parking_pain": "Fiddler's Green lots fill early for sold-out shows — a flat Black "
        "Volt fare skips the wait to get out.",
    },
    "generic": {
        "name": "the venue",
        "address": "Denver, CO",
        "coords": (39.7392, -104.9903),
        "dropoff": [
            "We drop you right at the main entrance so you walk straight in.",
            "On busy nights we plan to arrive well ahead of doors — Denver event traffic "
            "builds fast.",
        ],
        "pickup": [
            "We meet you at a clear, agreed spot just off the main exit to avoid the "
            "post-event crush.",
            "Your pickup time is set in advance, so there's no scrambling for a rideshare "
            "when the show lets out.",
        ],
        "eats": [
            "Ask your driver — we know the best nearby spots for a pre-show meal or a "
            "drink afterward.",
        ],
        "parking_pain": "Event parking and post-show surge pricing add up — a flat Black "
        "Volt fare each way keeps the night simple.",
    },
}


def match_venue_key(venue_name: str) -> str | None:
    """Return the watchlist key for a venue name, or None if it is not on the watchlist."""
    if not venue_name:
        return None
    lowered = venue_name.lower()
    for key, aliases in _ALIASES.items():
        if any(alias in lowered for alias in aliases):
            return key
    return None


def get_profile(venue_key: str | None) -> dict:
    """Return the curated profile for a venue key, falling back to the generic profile."""
    return VENUE_PROFILES.get(venue_key or "", VENUE_PROFILES["generic"])

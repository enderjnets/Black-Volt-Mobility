"""One-time: obtain an OAuth refresh token for the Black Volt calendar OWNER
(blackvoltmobility@gmail.com) so the backend can invite attendees per event.
A service account cannot invite (403 forbiddenForServiceAccounts); OAuth can.

Run on a machine WITH a browser (e.g. your Mac):

    python -m app.scripts.calendar_oauth_setup /path/to/client_secret.json

Prerequisites (Google Cloud Console, same project as the service account):
  1. APIs & Services → OAuth consent screen: User type "External"; add scope
     .../auth/calendar.events; add blackvoltmobility@gmail.com (+ enderjnets) as
     users; set Publishing status to "In production" so the refresh token does
     NOT expire after 7 days (a "Testing" app expires it).
  2. Credentials → Create OAuth client ID → type "Desktop app" → download
     client_secret.json.

What it does:
  - Opens a browser; log in as blackvoltmobility@gmail.com and grant Calendar.
  - Writes gcal-oauth.json (authorized_user JSON with a refresh_token).
  - Upload it to the server's /secrets and set
    GOOGLE_OAUTH_TOKEN_FILE=/secrets/gcal-oauth.json.
"""
from __future__ import annotations

import sys

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "usage: python -m app.scripts.calendar_oauth_setup "
            "<client_secret.json> [out=gcal-oauth.json]"
        )
        raise SystemExit(2)
    client_secret = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "gcal-oauth.json"

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_secret, _SCOPES)
    # access_type=offline + prompt=consent → a refresh_token is always issued.
    try:
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    except Exception as e:  # browser closed, consent denied, port bind, etc.
        raise SystemExit(f"OAuth flow failed: {e}") from e
    if not creds.refresh_token:
        raise SystemExit(
            "No refresh_token returned. Set the OAuth consent screen to "
            "'In production' and retry (a 'Testing' app may omit/expire it)."
        )
    with open(out, "w") as f:
        f.write(creds.to_json())
    print(f"\nSaved {out} (contains a refresh_token).")
    print("Upload it to the server, e.g. secrets/gcal-oauth.json, then set")
    print("GOOGLE_OAUTH_TOKEN_FILE=/secrets/gcal-oauth.json and redeploy.")


if __name__ == "__main__":
    main()

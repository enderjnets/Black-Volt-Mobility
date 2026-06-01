# Setup: Passenger Google Sign-In

Passengers sign in to the portal with **Google Identity Services (GIS)**. The
backend verifies the Google ID token and find-or-creates a `Client` for the
tenant. Activation needs a Google OAuth **Web client** + two env vars.

## 1. Create the OAuth client (Google Cloud Console — your action)

1. https://console.cloud.google.com → create/select a project (e.g.
   `black-volt-mobility`).
2. **APIs & Services → OAuth consent screen**: User type **External**, app name
   **Black Volt Mobility**, support email = yours, developer email = yours.
   Scopes: the default `openid`, `email`, `profile` (non-sensitive — no Google
   verification needed). **Publish** the app (Publishing status → *In
   production*) so any passenger can sign in. (In *Testing* only listed test
   users can sign in.)
3. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Web application**. Name it "Black Volt Web".
   - **Authorized JavaScript origins** (exact):
     - `https://blackvoltmobility.com`
     - `https://www.blackvoltmobility.com`
     - `https://app.blackvoltmobility.com`
     - `http://localhost:3005` (dev)
   - **Authorized redirect URIs**: leave **empty** (GIS button uses the ID-token
     flow via JS origins — no redirect needed).
4. Copy the **Client ID** (ends with `.apps.googleusercontent.com`). It is
   **public** (safe to share); there is no client secret in this flow.

## 2. Wire it (the agent does this once you provide the Client ID)

In the ROG `~/Black-Volt-Mobility/.env`:

```
GOOGLE_CLIENT_ID=<the-client-id>.apps.googleusercontent.com
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<same-client-id>.apps.googleusercontent.com
```

Then rebuild both (backend reads `GOOGLE_CLIENT_ID` at runtime to verify the
token; the frontend bakes `NEXT_PUBLIC_GOOGLE_CLIENT_ID` into the GIS button at
build):

```bash
docker compose up -d --build backend frontend
```

## How it behaves

- **Configured** → the portal "Sign in" modal renders Google's real button;
  signing in creates a session + a `Client` row, and the header shows the
  passenger's account.
- **Not configured** → the modal shows a demo button (prototype only).
- The driver dashboard login (`app.blackvoltmobility.com` → password) is
  separate and unaffected.

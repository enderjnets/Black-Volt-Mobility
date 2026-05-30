# Setup: blackvoltmobility.com

Goal: serve the Black Volt app at **https://blackvoltmobility.com** (+ `www`).

## Why it needs a Cloudflare Tunnel

The app runs on the **ROG** (Linux, behind home NAT — not publicly reachable). The
proven pattern on this setup (same as `inmo-demo.ekoaiautomation.com`) is a
**Cloudflare Tunnel**: the ROG makes an outbound connection to Cloudflare's edge,
which terminates TLS for the real domain. A plain GoDaddy A/CNAME record can't
reach the ROG, so the domain's DNS must be managed by **Cloudflare**, which means
switching the nameservers at GoDaddy.

The Cloudflare account is **enderjnets@gmail.com** (already used for
`ekoaiautomation.com`; `cloudflared` is logged in on the ROG via `~/.cloudflared/cert.pem`).

## What needs YOU (credentials/actions an agent can't do)

1. **Add the zone to Cloudflare.** `cloudflared`'s cert can create *tunnels* but
   not a new *zone*. Either:
   - Dashboard: Cloudflare → **Add a site** → `blackvoltmobility.com` → Free plan →
     it shows **2 nameservers** (e.g. `xxx.ns.cloudflare.com`, `yyy.ns.cloudflare.com`); **or**
   - Give the agent a **Cloudflare API token** scoped `Zone:Edit` + `DNS:Edit` +
     account `Zone:Create`, and it will create the zone via the API.
2. **Switch the GoDaddy nameservers** (the screenshot's **Nameservers** tab):
   replace GoDaddy's NS with the 2 Cloudflare nameservers from step 1. Either do it
   in the GoDaddy dashboard, **or** give the agent a **GoDaddy API key+secret**
   (`developer.godaddy.com`, Domains write) to set them via the API.

Propagation is usually minutes (the eko migration was <30s).

## What the agent does (once the zone is ACTIVE + ROG deploy is authorized)

Run on the ROG:

```bash
bash ~/Black-Volt-Mobility/deploy/rog-deploy.sh
```

That script (idempotent, isolated from the eko stacks):
1. clones/updates the repo, `docker compose up -d --build` (frontend :3005, backend :8012);
2. creates a dedicated **`blackvolt`** Cloudflare Tunnel;
3. writes `~/.cloudflared/blackvolt.yml` (apex + `www` → `http://localhost:3005`);
4. `cloudflared tunnel route dns blackvolt blackvoltmobility.com` (+ `www`) — needs the zone active;
5. installs + starts `cloudflared-blackvolt.service` (systemd).

Ingress template: [`deploy/cloudflared/blackvolt.example.yml`](cloudflared/blackvolt.example.yml).

## Ports on the ROG (verified free, coexist with the 4 eko stacks)

| Service | Port | Container |
|---|---|---|
| Frontend | 3005 | blackvolt-frontend |
| Backend | 8012 | blackvolt-backend |
| Postgres | 5435 | blackvolt-db |
| Redis | 6382 | blackvolt-redis |

## Production note

The ROG tunnel is the fast live path (matches the eko demo). The eventual
production target is a dedicated **Linux VPS** (the current VPS `38.240.52.90` is
Windows). Migrating later = run the same stack on the VPS + point the tunnel (or a
direct A record) there; the domain/Cloudflare setup is unchanged.

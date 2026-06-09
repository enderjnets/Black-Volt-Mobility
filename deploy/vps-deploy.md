# Black Volt Mobility — VPS production deploy & migration runbook

Move the live stack from the ROG (home box behind NAT) to the InterServer VPS,
**reusing the same dedicated Cloudflare Tunnel** (`blackvolt`,
`73f0ae53-4138-4aa8-99dc-44ec2cd2ce96`) so there is **zero DNS change** — only the
machine running the tunnel connector changes.

Hosts: `ssh ender-vps` (target, Ubuntu 26.04, Docker+Compose ready) · `ssh pcrug`
(source ROG). Domain unchanged: `app.blackvoltmobility.com` (dashboard) + apex/`www`.

## Security model
- Backend (8012) + frontend (3005) bind to **127.0.0.1** via `docker-compose.prod.yml`
  (db/redis already loopback). Nothing app-facing is exposed; UFW stays at SSH-only.
- The tunnel connector runs on the host and reaches `127.0.0.1:3005` (outbound only).
- Secrets (`secrets/gcal-*.json`) are `chmod 600`, mounted read-only at `/secrets`.
- Rotate the VPS root password in `my.interserver.net` (password login is already off).

## 1. Repo + config on the VPS
```bash
ssh ender-vps
git clone https://github.com/enderjnets/Black-Volt-Mobility.git ~/Black-Volt-Mobility
cd ~/Black-Volt-Mobility && git checkout main      # = the released version
```
Copy `.env` **verbatim** from the ROG and the two Google secrets (relay via the Mac):
```bash
# .env (DATABASE_URL/REDIS_URL use docker service names → host-independent)
ssh pcrug 'cat ~/Black-Volt-Mobility/.env' | ssh ender-vps 'cat > ~/Black-Volt-Mobility/.env'
# secrets
ssh pcrug 'cat ~/Black-Volt-Mobility/secrets/gcal-oauth.json' | ssh ender-vps 'cat > ~/Black-Volt-Mobility/secrets/gcal-oauth.json'
ssh pcrug 'cat ~/Black-Volt-Mobility/secrets/gcal-sa.json'    | ssh ender-vps 'cat > ~/Black-Volt-Mobility/secrets/gcal-sa.json'
ssh ender-vps 'chmod 600 ~/Black-Volt-Mobility/secrets/gcal-*.json ~/Black-Volt-Mobility/.env'
```

## 2. Build + start privately (no public traffic yet)
```bash
cd ~/Black-Volt-Mobility
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# backend runs `alembic upgrade head` on boot; _seed_admin_users seeds admins
```
Smoke test locally (loopback): `curl -sf 127.0.0.1:8012/api/v1/health` and
`curl -sf 127.0.0.1:3005/ | head`. Verify `ss -tlnp` shows 3005/8012 only on 127.0.0.1.

## 3. Cutover (zero DNS change) — short window, no data loss
Order matters (stop writes BEFORE the authoritative dump):
```bash
# a. Stop the ROG tunnel connector (app goes unreachable → writes freeze) and
#    disable its autostart so it can't resurrect and split-brain the tunnel.
#    (Identify supervision first: ps/systemctl --user/cron; then stop + disable.)

# b. Authoritative dump ROG → restore VPS
ssh pcrug 'docker exec blackvolt-db pg_dump -U blackvolt -Fc blackvolt' > /tmp/bv-final.dump
cat /tmp/bv-final.dump | ssh ender-vps 'docker exec -i blackvolt-db pg_restore --clean --if-exists --no-owner -U blackvolt -d blackvolt'

# c. Restart VPS backend (alembic = no-op, already at head)
ssh ender-vps 'cd ~/Black-Volt-Mobility && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart backend'

# d. Install cloudflared + move the tunnel to the VPS
#    Copy ~/.cloudflared/{73f0ae53-...json, cert.pem, blackvolt.yml} from ROG → VPS,
#    point blackvolt.yml services at http://127.0.0.1:3005, then:
sudo cp deploy/cloudflared/blackvolt-vps.service /etc/systemd/system/cloudflared-blackvolt.service
sudo systemctl daemon-reload && sudo systemctl enable --now cloudflared-blackvolt
```

## 4. Verify live
- `curl -I https://app.blackvoltmobility.com` → 200, and the **VPS** backend logs show
  the request (not the ROG).
- Owner Google login works; `/dashboard` lists the real rides/clients; `/api/v1/health` 200.
- `cloudflared tunnel info blackvolt` shows the VPS connector (ROG has none).

## 5. Backups + standby
```bash
ssh ender-vps 'crontab -l 2>/dev/null; (crontab -l 2>/dev/null; echo "30 4 * * * /home/enderj/Black-Volt-Mobility/deploy/backup-db.sh >> /home/enderj/blackvolt-backup.log 2>&1") | crontab -'
ssh ender-vps '~/Black-Volt-Mobility/deploy/backup-db.sh'   # first backup now
```
Leave the ROG stack **stopped but intact** (containers + `~/.cloudflared/blackvolt.yml`)
as a hot standby for ~1 week. Its DB was only dumped, never modified.

## Rollback (instant)
```bash
ssh ender-vps 'sudo systemctl stop cloudflared-blackvolt'
ssh pcrug 'cd ~/Black-Volt-Mobility && docker compose up -d'   # if it was stopped
ssh pcrug 'cloudflared --no-autoupdate --config ~/.cloudflared/blackvolt.yml tunnel run blackvolt &'
```
Back on the ROG in <2 min. Only rides created on the VPS during the window are lost
(none expected; if any, re-dump VPS → ROG before switching back).

## Optional hardening (after verification)
Set `APP_ENV=production` + `DEBUG=false` in the VPS `.env` and `up -d` — only once
confirmed it doesn't change `is_production`-gated behavior.

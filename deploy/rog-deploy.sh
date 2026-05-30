#!/usr/bin/env bash
# One-shot deploy of Black Volt Mobility on the ROG behind a dedicated Cloudflare
# Tunnel for blackvoltmobility.com. Run ON the ROG (enderj@100.88.47.99).
#
# PREREQUISITE (done once, needs your action — see docs/setup-domain.md):
#   blackvoltmobility.com must already be an ACTIVE zone on the Cloudflare account
#   enderjnets@gmail.com (i.e. GoDaddy nameservers switched to Cloudflare's).
#   Until then the `route dns` step fails and the site won't resolve.
#
# Safe to re-run (idempotent). Does NOT touch the eko-landing / eko-realtors-demo
# tunnels or any eko-* containers. Ports used: 3005/8012/5435/6382 (verified free).
set -euo pipefail

REPO_SSH="git@github.com:enderjnets/Black-Volt-Mobility.git"
DIR="$HOME/Black-Volt-Mobility"
TUNNEL="blackvolt"
DOMAIN="blackvoltmobility.com"

echo "==> 1. Clone / update repo"
if [ -d "$DIR/.git" ]; then git -C "$DIR" pull --ff-only; else git clone "$REPO_SSH" "$DIR"; fi
cd "$DIR"
[ -f .env ] || cp .env.example .env

echo "==> 2. Build + start the stack (frontend :3005, backend :8012)"
docker compose up -d --build

echo "==> 3. Create the dedicated tunnel (if missing)"
if ! cloudflared tunnel list | grep -q " $TUNNEL "; then
  cloudflared tunnel create "$TUNNEL"
fi
UUID=$(cloudflared tunnel list | awk -v n="$TUNNEL" '$2==n {print $1}')
echo "    tunnel $TUNNEL = $UUID"

echo "==> 4. Write ingress config ~/.cloudflared/$TUNNEL.yml"
cat > "$HOME/.cloudflared/$TUNNEL.yml" <<YML
tunnel: $UUID
credentials-file: $HOME/.cloudflared/$UUID.json
ingress:
  - hostname: $DOMAIN
    service: http://localhost:3005
  - hostname: www.$DOMAIN
    service: http://localhost:3005
  - service: http_status:404
YML

echo "==> 5. Route DNS (requires the zone to be ACTIVE on Cloudflare)"
cloudflared tunnel route dns "$TUNNEL" "$DOMAIN"
cloudflared tunnel route dns "$TUNNEL" "www.$DOMAIN"

echo "==> 6. systemd service cloudflared-blackvolt.service"
sudo tee /etc/systemd/system/cloudflared-blackvolt.service >/dev/null <<UNIT
[Unit]
Description=cloudflared tunnel - blackvolt ($DOMAIN)
After=network.target
[Service]
User=$USER
ExecStart=/usr/local/bin/cloudflared --no-autoupdate --config $HOME/.cloudflared/$TUNNEL.yml tunnel run $TUNNEL
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared-blackvolt.service

echo "==> DONE. https://$DOMAIN should resolve once DNS propagates."

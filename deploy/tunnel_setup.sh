#!/usr/bin/env bash
# Creates/configures the walcert Cloudflare tunnel and runs it as a systemd service.
# Requires ~/.cloudflared/cert.pem (from `cloudflared tunnel login`).
set -eu

NAME=walcert
HOSTNAME=walcert.globalscoreagent.com
CFDIR="$HOME/.cloudflared"

echo "[1/6] create tunnel (idempotent)"
cloudflared tunnel create "$NAME" 2>/dev/null || echo "tunnel may already exist, continuing"

echo "[2/6] resolve tunnel UUID"
UUID=$(cloudflared tunnel list -o json | python3 -c "import sys,json;ts=json.load(sys.stdin);print(next(t['id'] for t in ts if t['name']=='$NAME'))")
echo "UUID=$UUID"

echo "[3/6] write config.yml"
cat > "$CFDIR/config.yml" <<CFG
tunnel: $UUID
credentials-file: $CFDIR/$UUID.json
ingress:
  - hostname: $HOSTNAME
    service: http://localhost:8000
  - service: http_status:404
CFG
cat "$CFDIR/config.yml"

echo "[4/6] route DNS (idempotent)"
cloudflared tunnel route dns "$NAME" "$HOSTNAME" 2>/dev/null || echo "DNS route may already exist, continuing"

echo "[5/6] systemd unit"
sudo tee /etc/systemd/system/cloudflared-walcert.service >/dev/null <<UNIT
[Unit]
Description=cloudflared tunnel for walcert
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
ExecStart=/usr/bin/cloudflared --no-autoupdate tunnel run $NAME
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable cloudflared-walcert >/dev/null 2>&1 || true
sudo systemctl restart cloudflared-walcert
sleep 5

echo "[6/6] status"
echo -n "cloudflared active: "; systemctl is-active cloudflared-walcert || true
echo -n "agent active: "; systemctl is-active walcert-agent || true
echo "DONE"

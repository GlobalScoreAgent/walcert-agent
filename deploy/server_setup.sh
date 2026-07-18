#!/usr/bin/env bash
# Idempotent server-side setup for the Walcert agent on Ubuntu 24.04.
# Run on the EC2 host: bash /tmp/server_setup.sh
set -euo pipefail

APP=/opt/walcert
PUBLIC_URL="https://walcert.globalscoreagent.com"

cd "$APP"

echo "[1/5] dependency + app import check"
./.venv/bin/python -c "import fastapi,uvicorn,httpx,pydantic,dotenv; from app.services import run_certificate; print('deps_ok')"

echo "[2/5] set PUBLIC_BASE_URL in .env"
touch .env
grep -v '^PUBLIC_BASE_URL=' .env > .env.tmp 2>/dev/null || true
mv .env.tmp .env
echo "PUBLIC_BASE_URL=${PUBLIC_URL}" >> .env
echo "PUBLIC_BASE_URL set to ${PUBLIC_URL}"

echo "[3/5] create systemd unit walcert-agent.service"
sudo tee /etc/systemd/system/walcert-agent.service >/dev/null <<'UNIT'
[Unit]
Description=Walcert Agent (FastAPI hot-analysis certificates)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/walcert
ExecStart=/opt/walcert/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

echo "[4/5] enable + (re)start service"
sudo systemctl daemon-reload
sudo systemctl enable walcert-agent >/dev/null 2>&1 || true
sudo systemctl restart walcert-agent
sleep 3
echo -n "service active: "; systemctl is-active walcert-agent || true

echo "[5/5] local smoke test (127.0.0.1:8000)"
./.venv/bin/python - <<'PY'
import urllib.request, json
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=10) as r:
        print("HTTP", r.status)
        body = r.read(400).decode("utf-8", "replace")
        print(body[:400])
except Exception as e:
    print("smoke test error:", e)
PY

echo "DONE"

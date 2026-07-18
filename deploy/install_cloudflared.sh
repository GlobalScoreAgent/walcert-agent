#!/usr/bin/env bash
# Installs cloudflared from Cloudflare's official apt repo on Ubuntu.
set -eu

echo "[1/3] ensure curl"
command -v curl >/dev/null 2>&1 || (sudo apt-get update -y >/dev/null 2>&1 && sudo apt-get install -y curl >/dev/null 2>&1)

echo "[2/3] add cloudflare apt repo + key"
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null

echo "[3/3] install cloudflared"
sudo apt-get update -y >/dev/null 2>&1
sudo apt-get install -y cloudflared >/dev/null 2>&1
cloudflared --version
echo "DONE"

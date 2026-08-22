# Deploy x402 BNB (Dexter Permit2) + receipt NFT voucher to EC2.
# Requires: SG allows TCP 22 from your current public IP.
# Usage: powershell -File deploy\push_x402_bnb.ps1
# Does not print secrets.

$ErrorActionPreference = "Stop"
$pem = Join-Path $env:USERPROFILE ".ssh\walcert.pem"
$host_ = "ubuntu@18.191.27.156"
$base = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $pem)) { throw "Missing $pem" }

Write-Host "Uploading BNB x402 + receipt files..."
scp -i $pem -o StrictHostKeyChecking=accept-new `
  "$base\app\config.py" `
  "$base\app\payments.py" `
  "$base\app\bnb_receipt.py" `
  "$base\app\onchain_log.py" `
  "$base\app\routes\certificates.py" `
  "$base\scripts\x402_buyer_test.py" `
  "${host_}:/tmp/"

Write-Host "Installing into /opt/walcert and restart..."
ssh -i $pem $host_ @"
sudo cp /tmp/config.py /opt/walcert/app/ &&
sudo cp /tmp/payments.py /opt/walcert/app/ &&
sudo cp /tmp/bnb_receipt.py /opt/walcert/app/ &&
sudo cp /tmp/onchain_log.py /opt/walcert/app/ &&
sudo mkdir -p /opt/walcert/app/routes &&
sudo cp /tmp/certificates.py /opt/walcert/app/routes/ &&
sudo cp /tmp/x402_buyer_test.py /opt/walcert/scripts/ &&
sudo chown -R ubuntu:ubuntu /opt/walcert/app /opt/walcert/scripts &&
sudo systemctl restart walcert-agent &&
sudo systemctl is-active walcert-agent
"@

Write-Host "Ensuring X402_BNB_* on EC2 .env (no overwrite of existing secrets)..."
ssh -i $pem $host_ @"
set -e
ENV=/opt/walcert/.env
sudo grep -q '^X402_BNB_ENABLED=' `$ENV && sudo sed -i 's/^X402_BNB_ENABLED=.*/X402_BNB_ENABLED=true/' `$ENV || echo 'X402_BNB_ENABLED=true' | sudo tee -a `$ENV >/dev/null
sudo grep -q '^X402_BNB_NETWORK=' `$ENV || echo 'X402_BNB_NETWORK=eip155:56' | sudo tee -a `$ENV >/dev/null
sudo grep -q '^X402_BNB_FACILITATOR_URL=' `$ENV || echo 'X402_BNB_FACILITATOR_URL=https://x402.dexter.cash' | sudo tee -a `$ENV >/dev/null
sudo grep -q '^BNB_RECEIPT_ENABLED=' `$ENV || echo 'BNB_RECEIPT_ENABLED=true' | sudo tee -a `$ENV >/dev/null
sudo grep -q '^BNB_RECEIPT_CONTRACT=' `$ENV && sudo sed -i 's|^BNB_RECEIPT_CONTRACT=.*|BNB_RECEIPT_CONTRACT=0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7|' `$ENV || echo 'BNB_RECEIPT_CONTRACT=0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7' | sudo tee -a `$ENV >/dev/null
sudo systemctl restart walcert-agent
sudo systemctl is-active walcert-agent
"@

Write-Host "Smoke: POST /v1/certificates/origins without payment (expect 402, last accept eip155:56)"
Write-Host "Done."

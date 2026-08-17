# Deploy CDP Bazaar discovery (Base-first accepts + extensions.bazaar) to EC2.
# Requires: SG allows TCP 22 from your current public IP.
# Usage: powershell -File deploy\push_cdp_bazaar.ps1
# Does not print secrets.

$ErrorActionPreference = "Stop"
$pem = Join-Path $env:USERPROFILE ".ssh\walcert.pem"
$host_ = "ubuntu@18.191.27.156"
$base = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $pem)) { throw "Missing $pem" }

Write-Host "Uploading payments.py, agent_card.py, requirements.txt..."
scp -i $pem -o StrictHostKeyChecking=accept-new `
  "$base\app\agent_card.py" `
  "$base\app\payments.py" `
  "$base\requirements.txt" `
  "${host_}:/tmp/"

Write-Host "Installing into /opt/walcert, pip jsonschema, restart..."
ssh -i $pem $host_ "sudo cp /tmp/agent_card.py /opt/walcert/app/ && sudo cp /tmp/payments.py /opt/walcert/app/ && sudo cp /tmp/requirements.txt /opt/walcert/ && sudo -u ubuntu /opt/walcert/.venv/bin/pip install -q 'jsonschema>=4.18.0' 'x402[fastapi,evm]>=2.16,<3' && sudo systemctl restart walcert-agent && sudo systemctl is-active walcert-agent"

Write-Host "Smoke: POST /v1/certificates/origins without payment (expect 402, accepts[0]=Base, extensions.bazaar)"
Write-Host "Then: POST https://api.cdp.coinbase.com/platform/v2/x402/validate for origins/activity/multichain/portfolio"
Write-Host "Done."

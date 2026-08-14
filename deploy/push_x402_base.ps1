# Deploy dual x402 (Celo + Base/CDP) to EC2 production.
# Requires: SG allows TCP 22 from your current public IP.
# Usage: powershell -File deploy\push_x402_base.ps1
# Does not print secrets. Copies COINBASE_* from local .env to EC2 if missing.

$ErrorActionPreference = "Stop"
$pem = Join-Path $env:USERPROFILE ".ssh\walcert.pem"
$host_ = "ubuntu@18.191.27.156"
$base = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $pem)) { throw "Missing $pem" }

Write-Host "Uploading files..."
scp -i $pem -o StrictHostKeyChecking=accept-new `
  "$base\app\agent_card.py" `
  "$base\app\config.py" `
  "$base\app\payments.py" `
  "$base\app\payment_log.py" `
  "$base\requirements.txt" `
  "${host_}:/tmp/"

Write-Host "Installing into /opt/walcert, pip cdp-sdk, restart..."
ssh -i $pem $host_ "sudo cp /tmp/agent_card.py /opt/walcert/app/ && sudo cp /tmp/config.py /opt/walcert/app/ && sudo cp /tmp/payments.py /opt/walcert/app/ && sudo cp /tmp/payment_log.py /opt/walcert/app/ && sudo cp /tmp/requirements.txt /opt/walcert/ && sudo -u ubuntu /opt/walcert/.venv/bin/pip install -q 'cdp-sdk>=1.32.0' && sudo systemctl restart walcert-agent && sudo systemctl is-active walcert-agent"

$localEnv = Join-Path $base ".env"
if (Test-Path $localEnv) {
  $keyLine = Select-String -Path $localEnv -Pattern '^COINBASE_API_KEY_BASE=' | Select-Object -First 1
  $secLine = Select-String -Path $localEnv -Pattern '^COINBASE_SECRET_BASE=' | Select-Object -First 1
  if ($keyLine -and $secLine) {
    Write-Host "Checking COINBASE_* on EC2 (values not printed)..."
    $remoteHas = ssh -i $pem $host_ "sudo grep -c '^COINBASE_API_KEY_BASE=.\+' /opt/walcert/.env || true"
    if ([int]$remoteHas -lt 1) {
      Write-Host "Appending COINBASE_* + X402_BASE_ENABLED to EC2 .env"
      $payload = @(
        "",
        "# x402 Base (CDP) added by push_x402_base.ps1",
        "X402_BASE_ENABLED=true",
        "X402_BASE_NETWORK=eip155:8453",
        $keyLine.Line,
        $secLine.Line
      ) -join "`n"
      $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($payload))
      ssh -i $pem $host_ "echo $b64 | base64 -d | sudo tee -a /opt/walcert/.env > /dev/null && sudo systemctl restart walcert-agent && sudo systemctl is-active walcert-agent"
    } else {
      Write-Host "EC2 .env already has COINBASE_API_KEY_BASE; not overwriting."
    }
  } else {
    Write-Host "Local .env missing COINBASE_API_KEY_BASE/SECRET; add them on EC2 manually."
  }
}

Write-Host "Smoke: POST /v1/certificates/origins without payment (expect 402 + Base accept)"
Write-Host "Done."

from __future__ import annotations

import asyncio
import sys

from app.services import run_certificate
from app.errors import MissingCredentials, ProviderError, QuotaExceeded

TYPES = ["origins", "activity", "multichain", "portfolio"]


async def main(wallet: str) -> None:
    for ct in TYPES:
        print(f"\n===== {ct} =====")
        try:
            result = await run_certificate(ct, wallet)
        except QuotaExceeded as exc:
            print(f"  QUOTA: {exc.provider} retry={exc.retry_after}")
            continue
        except MissingCredentials as exc:
            print(f"  MISSING_CREDENTIALS: {exc.provider}")
            continue
        except ProviderError as exc:
            print(f"  PROVIDER_ERROR: {exc.provider}: {exc.message}")
            continue

        cert = result.get("certificate")
        analysis = result.get("analysis") or {}
        print(f"  provider     : {result.get('provider')}")
        if ct == "origins":
            print(f"  senders      : {len(analysis.get('senders') or [])}")
        elif ct == "activity":
            print(f"  transfers    : {len(analysis.get('transfers') or [])}")
            print(f"  counterparties: {len(analysis.get('counterparties') or [])}")
        elif ct == "multichain":
            print(f"  chains       : {analysis.get('total_chains_with_activity')} celo_merged={analysis.get('celo_merged')}")
        elif ct == "portfolio":
            print(f"  positions    : {len(analysis.get('positions') or [])} total_usd={analysis.get('total_value_usd')}")

        if cert:
            print(f"  cert_id      : {cert.get('certificate_id')}")
            print(f"  grade        : {cert.get('grade')} ({cert.get('grade_label')})")
            print(f"  data_hash    : {cert.get('data_hash')}")
            print(f"  summary(esp) : {(cert.get('summary') or {}).get('esp')}")
        else:
            print("  NO CERTIFICATE returned")


if __name__ == "__main__":
    wallet = sys.argv[1] if len(sys.argv) > 1 else "0x2eFC66c0a78620Dd254443998BF2f11B685602E3"
    print(f"Wallet: {wallet}")
    asyncio.run(main(wallet))

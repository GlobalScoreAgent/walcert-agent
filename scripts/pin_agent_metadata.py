"""Pin the ERC-8004 agent logo and registration file to IPFS via Pinata.

Usage:
    python scripts/pin_agent_metadata.py [path/to/logo.png]

Requires PINATA_JWT in the environment (or .env at repo root).
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
REGISTRATION = ROOT / "agent" / "registration.json"
DEFAULT_LOGO = Path(
    r"C:\Global Score Agent\Desarrollo_Cursor\globalscoreagent-web\public\walcert_agent.png"
)

PIN_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PIN_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"


def _jwt() -> str:
    load_dotenv(ROOT / ".env")
    jwt = (os.getenv("PINATA_JWT") or "").strip()
    if not jwt:
        print("[-] Falta PINATA_JWT en el entorno / .env")
        sys.exit(1)
    return jwt


def pin_file(jwt: str, path: Path) -> str:
    if not path.exists():
        print(f"[-] No existe el logo: {path}")
        sys.exit(1)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        files = {"file": (path.name, fh, mime)}
        meta = {"pinataMetadata": json.dumps({"name": f"walcert-logo-{path.name}"})}
        with httpx.Client(timeout=120) as client:
            r = client.post(
                PIN_FILE_URL,
                headers={"Authorization": f"Bearer {jwt}"},
                files=files,
                data=meta,
            )
    if r.status_code >= 400:
        print(f"[-] pinFileToIPFS fallo HTTP {r.status_code}: {r.text[:300]}")
        sys.exit(1)
    cid = r.json()["IpfsHash"]
    print(f"[+] Logo pinneado: ipfs://{cid}")
    return cid


def pin_json(jwt: str, content: dict) -> str:
    body = {
        "pinataContent": content,
        "pinataMetadata": {"name": "walcert-agent-registration"},
    }
    with httpx.Client(timeout=120) as client:
        r = client.post(
            PIN_JSON_URL,
            headers={
                "Authorization": f"Bearer {jwt}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if r.status_code >= 400:
        print(f"[-] pinJSONToIPFS fallo HTTP {r.status_code}: {r.text[:300]}")
        sys.exit(1)
    cid = r.json()["IpfsHash"]
    print(f"[+] Metadata pinneado: ipfs://{cid}")
    return cid


def main() -> None:
    logo = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOGO
    jwt = _jwt()

    logo_cid = pin_file(jwt, logo)

    reg = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    reg["image"] = f"ipfs://{logo_cid}"
    reg["updatedAt"] = int(time.time())

    meta_cid = pin_json(jwt, reg)

    # Persist the resolved image + updatedAt back into the source file.
    REGISTRATION.write_text(
        json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("\n==================== RESULTADO ====================")
    print(f"logo      : ipfs://{logo_cid}")
    print(f"metadata  : ipfs://{meta_cid}")
    print("gateways  :")
    print(f"  https://gateway.pinata.cloud/ipfs/{meta_cid}")
    print(f"  https://ipfs.io/ipfs/{meta_cid}")
    print("\nagentURI para setAgentURI(9699, ...):")
    print(f"  ipfs://{meta_cid}")
    print("===================================================")


if __name__ == "__main__":
    main()

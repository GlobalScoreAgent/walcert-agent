"""Circuit-breaker quota for GoldRush analyses (not a billing cap)."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.models import PROVIDER_BY_TYPE
from app.providers.edge_scoring import EDGE_SLUGS
from app.providers.quota import QuotaManager


def test_public_multichain_uses_goldrush_v2_edge():
    assert PROVIDER_BY_TYPE["multichain"] == "goldrush"
    assert EDGE_SLUGS["multichain"] == "walcert-certificate-multichain-v2"
    assert EDGE_SLUGS["multichain_v2"] == "walcert-certificate-multichain-v2"


def test_goldrush_daily_limit_blocks(tmp_path: Path):
    settings = Settings()
    settings.goldrush_daily_limit = 2
    quota = QuotaManager(settings=settings, path=tmp_path / "quota.json")
    assert quota.can_consume_goldrush(1)[0] is True
    quota.record_goldrush(1)
    quota.record_goldrush(1)
    ok, retry = quota.can_consume_goldrush(1)
    assert ok is False
    assert retry == "next_day"
    snap = quota.snapshot()
    assert snap["goldrush"]["daily_used"] == 2
    assert snap["goldrush"]["daily_limit"] == 2
    assert snap["goldrush"]["unit"] == "analyses"


if __name__ == "__main__":
    test_public_multichain_uses_goldrush_v2_edge()
    print("ok")

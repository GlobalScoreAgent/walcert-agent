"""Offline tests mirroring iq-v1 → QualityHit mapping rules."""

from __future__ import annotations

KIND_PRIORITY = {
    "ofac": 0,
    "mixer": 1,
    "cex": 2,
    "bridge": 3,
    "airdrop": 4,
    "protocol": 5,
}

KLEROS_RISK_RE = (
    "scam|phish|hack|exploit|ransomware|darknet|mixer|tornado|"
    "sanction|ofac|fraud|rug|malware|stolen"
)


def pick_kind(categories: list[str] | None) -> str | None:
    if not categories:
        return None
    best = None
    best_pri = 999
    for raw in categories:
        k = str(raw or "").lower()
        if k not in KIND_PRIORITY:
            continue
        pri = KIND_PRIORITY[k]
        if pri < best_pri:
            best_pri = pri
            best = k
    return best


def kleros_risky(kleros) -> bool:
    import re

    if kleros is None:
        return False
    blob = str(kleros).lower()
    return re.search(KLEROS_RISK_RE, blob, re.I) is not None


def test_pick_kind_priority_ofac_over_cex():
    assert pick_kind(["cex", "ofac", "bridge"]) == "ofac"


def test_pick_kind_protocol():
    assert pick_kind(["protocol", "airdrop"]) == "airdrop"


def test_kleros_risk_scam_tag():
    assert kleros_risky({"tags": ["Scam", "Exchange"]}) is True


def test_kleros_risk_benign():
    assert kleros_risky({"tags": ["Exchange", "DeFi"]}) is False


def test_chunk_size_cap():
    items = list(range(250))
    chunks = [items[i : i + 100] for i in range(0, len(items), 100)]
    assert len(chunks) == 3
    assert len(chunks[0]) == 100
    assert len(chunks[-1]) == 50


if __name__ == "__main__":
    test_pick_kind_priority_ofac_over_cex()
    test_pick_kind_protocol()
    test_kleros_risk_scam_tag()
    test_kleros_risk_benign()
    test_chunk_size_cap()
    print("ok")

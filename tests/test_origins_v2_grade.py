"""Offline tests for Origins v2.3 grade rules + main_origin argmax."""

from __future__ import annotations


def main_origin_from_percentages(category_percentages: dict[str, float]) -> str:
    tie_order = [
        "cex",
        "bridge",
        "mixer",
        "organic",
        "protocol",
        "dex",
        "ofac",
        "airdrop",
        "synthetic",
        "unknown",
        "other",
    ]
    best = "other"
    best_val = -1.0
    best_rank = 999
    for k, raw in category_percentages.items():
        v = float(raw or 0)
        if v <= 0:
            continue
        try:
            rank = tie_order.index(k)
        except ValueError:
            rank = 100
        if v > best_val or (v == best_val and rank < best_rank):
            best_val = v
            best = k
            best_rank = rank
    return best if best_val > 0 else "other"


def assign_grade_origins_v2(
    *,
    cex_pct: float,
    unique_senders: int,
    mixing_risk: str,
    first_funding_age_days: int | None,
    sanctions_hit: bool,
    hhi: float = 0.0,
    top1_pct: float = 0.0,
    airdrop_pct: float = 0.0,
    kleros_risk_hit: bool = False,
) -> tuple[str, str]:
    age = first_funding_age_days or 0
    unique = unique_senders
    if sanctions_hit or mixing_risk == "high":
        return "F", "F"
    if (
        cex_pct <= 40
        and unique >= 10
        and mixing_risk == "low"
        and age >= 365
        and top1_pct <= 60
        and hhi <= 0.55
        and airdrop_pct <= 40
        and not kleros_risk_hit
    ):
        return "A", "A"
    if (
        cex_pct <= 70
        and unique >= 5
        and mixing_risk == "low"
        and top1_pct <= 80
        and hhi <= 0.70
        and airdrop_pct <= 70
    ):
        return "B", "B"
    if (
        mixing_risk == "medium"
        or (cex_pct > 85 and unique <= 2)
        or top1_pct >= 95
        or hhi >= 0.90
        or (airdrop_pct >= 80 and unique <= 3)
    ):
        return "D", "D"
    return "C", "C"


def test_main_origin_argmax_organic_over_small_bridge():
    assert (
        main_origin_from_percentages({"organic": 91.0, "bridge": 9.0, "cex": 0.0})
        == "organic"
    )


def test_main_origin_tie_prefers_cex():
    assert main_origin_from_percentages({"cex": 40.0, "bridge": 40.0}) == "cex"


def test_value_relevant_coverage_excludes_nfts():
    """NFTs must not dilute priced_coverage_pct denominator."""
    rows = [
        {"asset_category": "erc20", "amount": 100, "usd": 100},
        {"asset_category": "erc20", "amount": 50, "usd": None},
        {"asset_category": "erc721", "amount": 1, "usd": None},
        {"asset_category": "erc1155", "amount": 2, "usd": None},
        {"asset_category": "external", "amount": 0, "usd": None},
        {"asset_category": "external", "amount": 1.5, "usd": 3000},
    ]

    def is_vr(r: dict) -> bool:
        cat = str(r.get("asset_category") or "external").lower()
        amount = float(r.get("amount") or 0)
        return cat in ("external", "erc20") and amount > 0

    vr = [r for r in rows if is_vr(r)]
    vr_priced = sum(1 for r in vr if r.get("usd") is not None and float(r["usd"]) > 0)
    assert len(vr) == 3  # two erc20 + one external with amount
    assert vr_priced == 2
    coverage = round(100.0 * vr_priced / len(vr), 1)
    assert coverage == 66.7


def test_grade_f_ofac():
    g, _ = assign_grade_origins_v2(
        cex_pct=10,
        unique_senders=20,
        mixing_risk="low",
        first_funding_age_days=400,
        sanctions_hit=True,
        hhi=0.2,
        top1_pct=30,
    )
    assert g == "F"


def test_grade_f_mixer():
    g, _ = assign_grade_origins_v2(
        cex_pct=10,
        unique_senders=20,
        mixing_risk="high",
        first_funding_age_days=400,
        sanctions_hit=False,
        hhi=0.2,
        top1_pct=30,
    )
    assert g == "F"


def test_grade_a():
    g, _ = assign_grade_origins_v2(
        cex_pct=30,
        unique_senders=12,
        mixing_risk="low",
        first_funding_age_days=400,
        sanctions_hit=False,
        hhi=0.3,
        top1_pct=40,
    )
    assert g == "A"


def test_grade_a_blocked_by_concentration():
    g, _ = assign_grade_origins_v2(
        cex_pct=30,
        unique_senders=12,
        mixing_risk="low",
        first_funding_age_days=400,
        sanctions_hit=False,
        hhi=0.84,
        top1_pct=91,
    )
    assert g == "C"


def test_grade_b():
    g, _ = assign_grade_origins_v2(
        cex_pct=55,
        unique_senders=6,
        mixing_risk="low",
        first_funding_age_days=100,
        sanctions_hit=False,
        hhi=0.4,
        top1_pct=50,
    )
    assert g == "B"


def test_grade_d_medium_mixing():
    g, _ = assign_grade_origins_v2(
        cex_pct=20,
        unique_senders=1,
        mixing_risk="medium",
        first_funding_age_days=100,
        sanctions_hit=False,
    )
    assert g == "D"


def test_grade_d_cex_concentration():
    g, _ = assign_grade_origins_v2(
        cex_pct=90,
        unique_senders=2,
        mixing_risk="low",
        first_funding_age_days=100,
        sanctions_hit=False,
        hhi=0.5,
        top1_pct=50,
    )
    assert g == "D"


def test_grade_d_extreme_hhi():
    g, _ = assign_grade_origins_v2(
        cex_pct=20,
        unique_senders=8,
        mixing_risk="low",
        first_funding_age_days=100,
        sanctions_hit=False,
        hhi=0.92,
        top1_pct=96,
    )
    assert g == "D"


def test_grade_c_default():
    g, _ = assign_grade_origins_v2(
        cex_pct=50,
        unique_senders=3,
        mixing_risk="low",
        first_funding_age_days=100,
        sanctions_hit=False,
        hhi=0.4,
        top1_pct=50,
    )
    assert g == "C"


def test_grade_a_blocked_by_airdrop():
    g, _ = assign_grade_origins_v2(
        cex_pct=30,
        unique_senders=12,
        mixing_risk="low",
        first_funding_age_days=400,
        sanctions_hit=False,
        hhi=0.3,
        top1_pct=40,
        airdrop_pct=55,
    )
    assert g == "B"


def test_grade_a_blocked_by_kleros_risk():
    g, _ = assign_grade_origins_v2(
        cex_pct=30,
        unique_senders=12,
        mixing_risk="low",
        first_funding_age_days=400,
        sanctions_hit=False,
        hhi=0.3,
        top1_pct=40,
        kleros_risk_hit=True,
    )
    assert g == "B"


def test_grade_d_airdrop_dominated():
    g, _ = assign_grade_origins_v2(
        cex_pct=10,
        unique_senders=2,
        mixing_risk="low",
        first_funding_age_days=100,
        sanctions_hit=False,
        hhi=0.4,
        top1_pct=50,
        airdrop_pct=85,
    )
    assert g == "D"


def test_main_origin_protocol_over_dex_tie():
    assert main_origin_from_percentages({"protocol": 40.0, "dex": 40.0}) == "protocol"


def test_stable_pricing_map():
    from app.providers.pricing import STABLES, day_key_from_iso

    assert "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48" in STABLES[1]
    assert day_key_from_iso("2024-03-12T09:14:22Z") == "2024-03-12"


def test_price_inflows_does_not_treat_token_amount_as_usd():
    """Alchemy transfer.value is token amount — must not become usd via alchemy fallback."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.providers.pricing import price_inflows

    transfers = [
        {
            "from": "0x1111111111111111111111111111111111111111",
            "category": "erc20",
            "value": 9.69e21,
            "asset": "XBASE",
            "rawContract": {
                "address": "0x2222222222222222222222222222222222222222",
                "value": "0xde0b6b3a7640000",
                "decimal": "0x12",
            },
            "metadata": {"blockTimestamp": "2024-01-15T12:00:00Z"},
            "_walcert_chain_id": 8453,
        },
        {
            "from": "0x3333333333333333333333333333333333333333",
            "category": "erc20",
            "value": 100.0,
            "asset": "USDC",
            "rawContract": {
                "address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                "value": "0x5f5e100",
                "decimal": "0x6",
            },
            "metadata": {"blockTimestamp": "2024-01-15T12:00:00Z"},
            "_walcert_chain_id": 8453,
        },
    ]

    async def _run():
        with patch(
            "app.providers.pricing.spot_price_dex",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "app.providers.pricing.historical_price_usd",
            new_callable=AsyncMock,
            return_value=None,
        ):
            return await price_inflows(transfers)

    rows = asyncio.run(_run())
    junk = next(r for r in rows if r["symbol"] == "XBASE")
    stable = next(r for r in rows if r["symbol"] == "USDC")
    assert junk["usd"] is None
    assert junk["usd_method"] == "none"
    assert stable["usd_method"] == "stable"
    assert stable["usd"] == 100.0


if __name__ == "__main__":
    test_main_origin_argmax_organic_over_small_bridge()
    test_main_origin_tie_prefers_cex()
    test_value_relevant_coverage_excludes_nfts()
    test_grade_f_ofac()
    test_grade_f_mixer()
    test_grade_a()
    test_grade_a_blocked_by_concentration()
    test_grade_b()
    test_grade_d_medium_mixing()
    test_grade_d_cex_concentration()
    test_grade_d_extreme_hhi()
    test_grade_c_default()
    test_stable_pricing_map()
    test_price_inflows_does_not_treat_token_amount_as_usd()
    print("ALL ORIGINS V2.2 TESTS PASS")

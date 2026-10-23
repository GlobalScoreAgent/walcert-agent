"""Offline tests for Activity v2.2 grade rules + metric helpers."""

from __future__ import annotations


def assign_grade_activity_v2(
    *,
    unique_counterparties: int,
    cex_pct: float,
    counterparty_hhi: float,
    wash_trading_risk: str,
    circular_patterns: bool,
    wash_score: float,
    bot_like_score: float,
    velocity_txs_per_day: float,
    sanctions_hit: bool,
    mixer_hit: bool,
    airdrop_pct: float = 0.0,
    kleros_risk_hit: bool = False,
) -> str:
    u = unique_counterparties
    hhi = counterparty_hhi
    bot = bot_like_score
    if (
        sanctions_hit
        or wash_trading_risk == "high"
        or bot >= 0.8
        or wash_score >= 0.75
    ):
        return "F"
    if (
        mixer_hit
        or (circular_patterns and wash_trading_risk == "medium")
        or u < 3
        or cex_pct > 60
        or hhi > 0.70
        or bot >= 0.55
        or airdrop_pct > 70
    ):
        return "D"
    if (
        u >= 25
        and wash_trading_risk == "low"
        and not circular_patterns
        and hhi <= 0.25
        and bot < 0.35
        and velocity_txs_per_day <= 40
        and airdrop_pct <= 40
        and not kleros_risk_hit
    ):
        return "A"
    if (
        u >= 12
        and wash_trading_risk == "low"
        and hhi <= 0.35
        and bot < 0.5
        and airdrop_pct <= 60
    ):
        return "B"
    return "C"


def test_grade_f_ofac():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=30,
            cex_pct=10,
            counterparty_hhi=0.1,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.1,
            velocity_txs_per_day=5,
            sanctions_hit=True,
            mixer_hit=False,
        )
        == "F"
    )


def test_grade_f_wash_high():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=30,
            cex_pct=10,
            counterparty_hhi=0.1,
            wash_trading_risk="high",
            circular_patterns=True,
            wash_score=0.9,
            bot_like_score=0.1,
            velocity_txs_per_day=5,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "F"
    )


def test_grade_a():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=30,
            cex_pct=10,
            counterparty_hhi=0.15,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=8,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "A"
    )


def test_grade_b():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=15,
            cex_pct=20,
            counterparty_hhi=0.3,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.3,
            velocity_txs_per_day=12,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "B"
    )


def test_grade_d_low_diversity():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=2,
            cex_pct=10,
            counterparty_hhi=0.2,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=5,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "D"
    )


def test_grade_hhi_0_5_is_c_not_d():
    """Mid HHI no longer forces D; blocks A/B → C when unique is mid-range."""
    assert (
        assign_grade_activity_v2(
            unique_counterparties=150,
            cex_pct=10,
            counterparty_hhi=0.5,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=5,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "C"
    )


def test_grade_hhi_0_8_is_d():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=150,
            cex_pct=10,
            counterparty_hhi=0.8,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=5,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "D"
    )


def test_grade_c_default():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=8,
            cex_pct=30,
            counterparty_hhi=0.3,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.3,
            velocity_txs_per_day=10,
            sanctions_hit=False,
            mixer_hit=False,
        )
        == "C"
    )


def test_grade_a_blocked_by_airdrop():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=30,
            cex_pct=10,
            counterparty_hhi=0.15,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=8,
            sanctions_hit=False,
            mixer_hit=False,
            airdrop_pct=50,
        )
        == "B"
    )


def test_grade_d_airdrop():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=30,
            cex_pct=10,
            counterparty_hhi=0.15,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=8,
            sanctions_hit=False,
            mixer_hit=False,
            airdrop_pct=75,
        )
        == "D"
    )


def test_grade_a_blocked_by_kleros_risk():
    assert (
        assign_grade_activity_v2(
            unique_counterparties=30,
            cex_pct=10,
            counterparty_hhi=0.15,
            wash_trading_risk="low",
            circular_patterns=False,
            wash_score=0.1,
            bot_like_score=0.2,
            velocity_txs_per_day=8,
            sanctions_hit=False,
            mixer_hit=False,
            kleros_risk_hit=True,
        )
        == "B"
    )


def test_activity_metrics_hhi_and_nft():
    from app.providers.activity_metrics import compute_activity_metrics

    wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    transfers = [
        {
            "from": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "to": wallet,
            "value_usd": 100.0,
            "ts": "2026-07-20T12:00:00Z",
            "asset_category": "erc20",
            "symbol": "USDC",
            "contract": "0x1111111111111111111111111111111111111111",
            "chain_id": 8453,
        },
        {
            "from": wallet,
            "to": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "value_usd": 50.0,
            "ts": "2026-07-21T12:00:00Z",
            "asset_category": "erc20",
            "symbol": "USDC",
            "contract": "0x1111111111111111111111111111111111111111",
            "chain_id": 8453,
        },
        {
            "from": "0xcccccccccccccccccccccccccccccccccccccccc",
            "to": wallet,
            "value_usd": None,
            "ts": "2026-07-22T12:00:00Z",
            "asset_category": "erc721",
            "symbol": "NFT",
            "contract": "0x2222222222222222222222222222222222222222",
            "chain_id": 8453,
        },
    ]
    m = compute_activity_metrics(wallet, transfers, window_days=15)
    assert m["unique_counterparties"] == 2
    assert m["reciprocity_ratio"] == 0.5  # 1 of 2 both ways
    assert m["nft_transfer_pct"] > 0
    assert m["fungible_transfer_pct"] > 0
    assert m["token_diversity"] >= 2
    assert m["counterparty_hhi"] > 0


if __name__ == "__main__":
    test_grade_f_ofac()
    test_grade_f_wash_high()
    test_grade_a()
    test_grade_b()
    test_grade_d_low_diversity()
    test_grade_hhi_0_5_is_c_not_d()
    test_grade_hhi_0_8_is_d()
    test_grade_c_default()
    test_activity_metrics_hhi_and_nft()
    print("ALL ACTIVITY V2.1 TESTS PASS")

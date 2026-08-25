"""Offline tests for Multichain v2 GoldRush helpers + grade."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.providers.chain_families import ecosystem_family_from_chain_name
from app.providers.core_ecosystems import normalize_core_slug
from app.providers.multichain_v2_metrics import (
    compute_multichain_v2_signals,
    select_intensity_chains,
)


def assign_grade_multichain_v2(
    *,
    mainnets: int,
    ecosystems: int,
    span: int,
    consistency: float,
    recency: float,
    core: int,
    a30: int,
    dormant: float,
    total_tx: int,
    tx_hhi: float,
    testnets: int = 0,
) -> str:
    only_testnets = mainnets == 0 and testnets > 0
    if mainnets == 0 or only_testnets or (mainnets == 1 and span < 30 and total_tx < 5):
        return "F"
    if mainnets == 1 or (dormant > 0.75 and a30 == 0) or total_tx == 0:
        return "D"
    if (
        mainnets >= 5
        and ecosystems >= 3
        and span >= 365
        and consistency >= 0.5
        and recency >= 0.35
        and core >= 2
        and total_tx >= 50
        and tx_hhi <= 0.7
    ):
        return "A"
    if (
        mainnets >= 3
        and ecosystems >= 2
        and span >= 180
        and consistency >= 0.4
        and total_tx >= 15
    ):
        return "B"
    return "C"


def test_ecosystem_family_map():
    assert ecosystem_family_from_chain_name("eth-mainnet") == "ethereum"
    assert ecosystem_family_from_chain_name("base-mainnet") == "ethereum"
    assert ecosystem_family_from_chain_name("arbitrum-mainnet") == "ethereum"
    assert ecosystem_family_from_chain_name("matic-mainnet") == "polygon"
    assert ecosystem_family_from_chain_name("celo-mainnet") == "celo"
    assert ecosystem_family_from_chain_name("bsc-mainnet") == "bnb"


def test_core_goldrush_names():
    assert normalize_core_slug("eth-mainnet") == "eth"
    assert normalize_core_slug("base-mainnet") == "base"
    assert normalize_core_slug("matic-mainnet") == "polygon"


def test_select_intensity_priority():
    items = [
        {"name": "fantom-mainnet", "is_testnet": False, "last_seen_at": "2026-07-01T00:00:00Z", "first_seen_at": "2024-01-01T00:00:00Z"},
        {"name": "base-mainnet", "is_testnet": False, "last_seen_at": "2026-07-20T00:00:00Z", "first_seen_at": "2024-01-01T00:00:00Z"},
        {"name": "eth-mainnet", "is_testnet": False, "last_seen_at": "2026-07-25T00:00:00Z", "first_seen_at": "2020-01-01T00:00:00Z"},
        {"name": "sepolia-testnet", "is_testnet": True, "last_seen_at": "2026-07-25T00:00:00Z", "first_seen_at": "2026-01-01T00:00:00Z"},
    ]
    selected = select_intensity_chains(items, top_n=2)
    names = [c["name"] for c in selected]
    assert names[0] == "eth-mainnet"
    assert names[1] == "base-mainnet"


def test_grade_f_empty():
    assert (
        assign_grade_multichain_v2(
            mainnets=0,
            ecosystems=0,
            span=0,
            consistency=0,
            recency=0,
            core=0,
            a30=0,
            dormant=0,
            total_tx=0,
            tx_hhi=0,
        )
        == "F"
    )


def test_grade_d_no_tx():
    assert (
        assign_grade_multichain_v2(
            mainnets=4,
            ecosystems=2,
            span=400,
            consistency=0.6,
            recency=0.5,
            core=2,
            a30=2,
            dormant=0.1,
            total_tx=0,
            tx_hhi=0,
        )
        == "D"
    )


def test_grade_a():
    assert (
        assign_grade_multichain_v2(
            mainnets=6,
            ecosystems=4,
            span=500,
            consistency=0.6,
            recency=0.5,
            core=3,
            a30=3,
            dormant=0.1,
            total_tx=120,
            tx_hhi=0.4,
        )
        == "A"
    )


def test_grade_b():
    assert (
        assign_grade_multichain_v2(
            mainnets=3,
            ecosystems=2,
            span=200,
            consistency=0.45,
            recency=0.4,
            core=2,
            a30=1,
            dormant=0.2,
            total_tx=20,
            tx_hhi=0.5,
        )
        == "B"
    )


def test_signals_and_tx_hhi():
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    chains = [
        {
            "name": "eth-mainnet",
            "is_testnet": False,
            "category_label": "Ethereum",
            "first_seen_at": (now - timedelta(days=800)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_seen_at": (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tx_count": 100,
            "intensity_sampled": True,
        },
        {
            "name": "base-mainnet",
            "is_testnet": False,
            "is_appchain": False,
            "category_label": "Ethereum",
            "first_seen_at": (now - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_seen_at": (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tx_count": 50,
            "intensity_sampled": True,
        },
        {
            "name": "celo-mainnet",
            "is_testnet": False,
            "category_label": "Celo",
            "first_seen_at": (now - timedelta(days=300)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_seen_at": (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tx_count": 25,
            "intensity_sampled": True,
        },
    ]
    s = compute_multichain_v2_signals(
        chains,
        intensity_chain_names=["eth-mainnet", "base-mainnet", "celo-mainnet"],
        now=now,
    )
    assert s["total_chains_mainnet"] == 3
    assert s["intensity"]["total_tx_count"] == 175
    assert s["intensity"]["tx_hhi"] > 0
    assert s["core_ecosystem_count"] >= 2
    # eth + base share ethereum family; celo is separate → 2 ecosystems
    assert s["ecosystem_count"] == 2
    assert s["formula_hint"] == "multichain-v2.1"


if __name__ == "__main__":
    test_ecosystem_family_map()
    test_core_goldrush_names()
    test_select_intensity_priority()
    test_grade_f_empty()
    test_grade_d_no_tx()
    test_grade_a()
    test_grade_b()
    test_signals_and_tx_hhi()
    print("ALL MULTICHAIN V2.1 TESTS PASS")

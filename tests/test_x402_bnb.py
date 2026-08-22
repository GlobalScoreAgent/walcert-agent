from types import SimpleNamespace

import pytest

from app.bnb_receipt import is_bnb_network
from app.payments import facilitator_url_for_network, _payment_accepts


def _settings(**kwargs):
    defaults = dict(
        x402_network="eip155:42220",
        x402_facilitator_url="https://api.x402.celo.org",
        x402_base_network="eip155:8453",
        x402_base_facilitator_url="https://api.cdp.coinbase.com/platform/v2/x402",
        x402_bnb_network="eip155:56",
        x402_bnb_facilitator_url="https://x402.dexter.cash",
        x402_pay_to="0xF4D938200445B0Df0f028af6d90D016147AEd095",
        x402_base_pay_to="0xF4D938200445B0Df0f028af6d90D016147AEd095",
        x402_bnb_pay_to="0xF4D938200445B0Df0f028af6d90D016147AEd095",
        x402_price="$0.05",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_facilitator_url_bnb():
    s = _settings()
    assert facilitator_url_for_network(s, "eip155:56") == s.x402_bnb_facilitator_url
    assert facilitator_url_for_network(s, "bsc") == s.x402_bnb_facilitator_url


def test_accepts_bnb_last_base_first():
    pytest.importorskip("x402")
    s = _settings()
    nets = [
        opt.network
        for opt in _payment_accepts(s, include_base=True, include_bnb=True)
    ]
    assert nets[0] == "eip155:8453"
    assert "eip155:42220" in nets
    assert nets[-1] == "eip155:56"


def test_accepts_without_bnb_unchanged():
    pytest.importorskip("x402")
    s = _settings()
    nets = [opt.network for opt in _payment_accepts(s, include_base=True)]
    assert nets == ["eip155:8453", "eip155:42220"]


def test_is_bnb_network():
    assert is_bnb_network("eip155:56")
    assert is_bnb_network("bsc")
    assert not is_bnb_network("eip155:8453")
    assert not is_bnb_network("eip155:42220")

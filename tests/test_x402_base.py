from types import SimpleNamespace

from app.models import CERTIFICATE_TYPES
from app.payments import (
    BAZAAR_DESCRIPTIONS,
    _bazaar_extensions,
    _certificate_route_config,
    _payment_accepts,
    facilitator_url_for_network,
)


def _settings(**kwargs):
    defaults = dict(
        x402_network="eip155:42220",
        x402_facilitator_url="https://api.x402.celo.org",
        x402_base_network="eip155:8453",
        x402_base_facilitator_url="https://api.cdp.coinbase.com/platform/v2/x402",
        x402_pay_to="0xF4D938200445B0Df0f028af6d90D016147AEd095",
        x402_base_pay_to="0xF4D938200445B0Df0f028af6d90D016147AEd095",
        x402_price="$0.05",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_facilitator_url_celo_default():
    s = _settings()
    assert facilitator_url_for_network(s, None) == s.x402_facilitator_url
    assert facilitator_url_for_network(s, "eip155:42220") == s.x402_facilitator_url


def test_facilitator_url_base():
    s = _settings()
    assert (
        facilitator_url_for_network(s, "eip155:8453") == s.x402_base_facilitator_url
    )
    assert facilitator_url_for_network(s, "EIP155:8453") == s.x402_base_facilitator_url


def test_x402_base_ready_requires_keys(monkeypatch):
    monkeypatch.setenv("X402_BASE_ENABLED", "true")
    monkeypatch.setenv("COINBASE_API_KEY_BASE", "")
    monkeypatch.setenv("COINBASE_SECRET_BASE", "")
    monkeypatch.setenv("CDP_API_KEY_ID", "")
    monkeypatch.setenv("CDP_API_KEY_SECRET", "")
    from app.config import Settings

    s = Settings()
    assert s.x402_base_enabled is True
    assert s.x402_base_ready is False


def test_x402_base_ready_with_coinbase_env(monkeypatch):
    monkeypatch.setenv("X402_BASE_ENABLED", "true")
    monkeypatch.setenv("COINBASE_API_KEY_BASE", "key-id")
    monkeypatch.setenv("COINBASE_SECRET_BASE", "key-secret")
    from app.config import Settings

    s = Settings()
    assert s.x402_base_ready is True
    assert s.x402_base_network == "eip155:8453"
    assert s.x402_base_pay_to == s.x402_pay_to


def test_payment_accepts_base_first_when_include_base():
    s = _settings()
    nets = [opt.network for opt in _payment_accepts(s, include_base=True)]
    assert nets == ["eip155:8453", "eip155:42220"]


def test_payment_accepts_celo_only():
    s = _settings()
    nets = [opt.network for opt in _payment_accepts(s, include_base=False)]
    assert nets == ["eip155:42220"]


def test_bazaar_descriptions_within_cdp_limit():
    for cert_type, text in BAZAAR_DESCRIPTIONS.items():
        assert cert_type in CERTIFICATE_TYPES
        assert 0 < len(text) <= 500


def test_bazaar_extensions_on_all_paid_routes():
    s = _settings()
    accepts = _payment_accepts(s, include_base=True)
    for cert_type in CERTIFICATE_TYPES:
        ext = _bazaar_extensions(cert_type)
        assert "bazaar" in ext
        cfg = _certificate_route_config(cert_type, accepts, bazaar=True)
        assert cfg.extensions is not None
        assert "bazaar" in cfg.extensions
        assert cfg.description == BAZAAR_DESCRIPTIONS[cert_type]


def test_celo_only_route_has_no_bazaar_extension():
    s = _settings()
    accepts = _payment_accepts(s, include_base=False)
    cfg = _certificate_route_config("origins", accepts, bazaar=False)
    assert cfg.extensions is None

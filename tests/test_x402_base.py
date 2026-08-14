from types import SimpleNamespace

from app.payments import facilitator_url_for_network


def _settings(**kwargs):
    defaults = dict(
        x402_network="eip155:42220",
        x402_facilitator_url="https://api.x402.celo.org",
        x402_base_network="eip155:8453",
        x402_base_facilitator_url="https://api.cdp.coinbase.com/platform/v2/x402",
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

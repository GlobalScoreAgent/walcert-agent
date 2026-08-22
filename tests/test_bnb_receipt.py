from types import SimpleNamespace

from eth_account import Account

from app.bnb_receipt import (
    attach_receipt_if_bnb,
    build_claim_voucher,
    _extract_network_payer,
    payment_context_from_request,
)


def test_attach_skips_celo():
    cert = {"data_hash": "0x" + "ab" * 32, "type": "origins"}
    out = attach_receipt_if_bnb(
        cert, network="eip155:42220", payer="0x" + "11" * 20
    )
    assert "receipt" not in out


def test_voucher_uses_data_hash_as_delivery_hash(monkeypatch):
    key = "0x" + "11" * 32
    acct = Account.from_key(key)
    monkeypatch.setattr(
        "app.bnb_receipt.get_settings",
        lambda: SimpleNamespace(
            bnb_receipt_enabled=True,
            bnb_receipt_contract="0x" + "22" * 20,
            agent_signer_key=key,
            bnb_chain_id=56,
        ),
    )
    dh = "0x" + "cd" * 32
    v = build_claim_voucher(
        data_hash=dh, cert_type="origins", payer=acct.address
    )
    assert v is not None
    assert v["data_hash"] == dh
    assert v["delivery_hash"] == dh
    assert v["claim"]["args"][0] == dh
    assert v["signature"].startswith("0x")


def test_extract_network_payer_from_accepted_payload():
    payer = "0x" + "11" * 20
    obj = {
        "accepted": {"network": "eip155:56", "scheme": "exact"},
        "payload": {"permit2Authorization": {"from": payer}},
    }
    net, who = _extract_network_payer(obj)
    assert net == "eip155:56"
    assert who.lower() == payer.lower()


def test_context_from_payment_signature_header(monkeypatch):
    payer = "0x" + "aa" * 20
    payload = {
        "accepted": {"network": "eip155:56"},
        "payload": {"authorization": {"from": payer}},
    }
    monkeypatch.setattr(
        "app.bnb_receipt._payment_from_headers",
        lambda _req: payload,
    )
    req = SimpleNamespace(state=SimpleNamespace(), headers={})
    net, who = payment_context_from_request(req)
    assert net == "eip155:56"
    assert who.lower() == payer.lower()


def test_attach_uses_fallback_type(monkeypatch):
    key = "0x" + "11" * 32
    monkeypatch.setattr(
        "app.bnb_receipt.get_settings",
        lambda: SimpleNamespace(
            bnb_receipt_enabled=True,
            bnb_receipt_contract="0x" + "22" * 20,
            agent_signer_key=key,
            bnb_chain_id=56,
        ),
    )
    payer = Account.from_key(key).address
    cert = {"data_hash": "0x" + "cd" * 32}
    out = attach_receipt_if_bnb(
        cert,
        network="eip155:56",
        payer=payer,
        fallback_type="origins",
    )
    assert out.get("receipt")
    assert out["receipt"]["cert_type"] == "origins"

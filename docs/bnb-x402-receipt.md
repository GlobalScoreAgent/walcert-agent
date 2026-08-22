# BNB x402 (Permit2) + receipt NFT

Canonical certificate stays on **Celo** (EIP-712 + `giveFeedback`). Celo and Base x402 rails are unchanged (`accepts[0]` is still Base for CDP Bazaar).

**Live on production** (EC2, 2026-08-22): `POST /v1/certificates/{type}` lists three `accepts`: Base, Celo, `eip155:56`.

## Third rail

| | BNB |
| --- | --- |
| Network | `eip155:56` |
| Asset | Binance-Peg USDC `0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d` (18 decimals) |
| Method | Permit2 (`exact`) |
| Facilitator | [Dexter](https://x402.dexter.cash) |
| Price | `$0.05` (atomic `50000000000000000`) |
| First use | Payer `approve` USDC → Permit2 `0x000000000022D473030F116dDEE9F6B43aC78BA3` (once) |

## Receipt NFT (soulbound)

| | |
| --- | --- |
| Contract | [`0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7`](https://bscscan.com/address/0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7) |
| Source | `contracts/WalcertBnbReceipt.sol` |
| Owner | agent Owner EOA |
| Issuer | monitor (`AGENT_SIGNER_KEY`) — signs the voucher only |
| Who mints | **Payer** calls `claim` (`msg.sender` must be `payer`) |
| BscScan `From` | `0x000…000` (standard ERC-721 mint) |
| Gas | paid in **BNB by the claimant**, not from the $0.05 USDC. Smoke claim ≈ 133k gas ≈ **< $0.01** |

After a BNB settle the 200 includes `certificate.receipt` (EIP-712). The voucher is built from the incoming `PAYMENT-SIGNATURE` header (network + payer), not `request.state`.

`data_hash` == `delivery_hash` == future TermiX AACP `deliveryHash`. Celo/Base payments do **not** get a receipt.

DappBay should list **this** contract, not the ERC-8004 registry or TermiX escrow.

## Smoke (2026-08-22)

| Step | Tx |
| --- | --- |
| Permit2 approve | [0xda9fac6d…9084](https://bscscan.com/tx/0xda9fac6d5f409941d74f1842c561d6056bc7b8a9e6aff6efc9c873e482489084) |
| x402 settle (first, no voucher) | [0xe7b6ef65…a7ac](https://bscscan.com/tx/0xe7b6ef65bf5bc4a4414a8e05639c72bd4cda2bb661bc505388afce88724da7ac) |
| x402 settle + `receipt` | [0xef8d9dde…9bce](https://bscscan.com/tx/0xef8d9dde524d20524e2fe8f49480b59eda5624275c13d5ba9aa3a65a13a79bce) |
| NFT `claim` tokenId 1 | [0x1fab40e6…c00d](https://bscscan.com/tx/0x1fab40e6d5fb30b8665936bab00750492683de95f856a185e19f5d7e2f39c00d) |

Payer / NFT to: `0x475F589BD4bFe82b333b8006dcc278f393b8E124`. Certificate `origins` grade B, id `2cc54e41-c4c0-4cb5-a62d-58d60d9bf3dc`.

## Ops

1. Contract already deployed (address above).
2. EC2: `X402_BNB_ENABLED=true`, `BNB_RECEIPT_CONTRACT=0x4e430fB5…24c7`.
3. Buyer: `X402_NETWORK=eip155:56 python scripts/x402_buyer_test.py origins <wallet>`
4. Payer `claim` using `certificate.receipt.claim`.

SQL: `supabase/migrations/20260821_certificate_receipt_bnb.sql` (`receipt_bnb` jsonb). Deploy script: `deploy/push_x402_bnb.ps1`.

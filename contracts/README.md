# Walcert BNB receipt NFT

Soulbound ERC-721 on **BSC mainnet** (`chainId 56`). The paying wallet calls `claim`; `dataHash` is the certificate JSON keccak (same bytes as Celo `giveFeedback` / future TermiX AACP `deliveryHash`).

EIP-712:

- domain: `Walcert Receipt` / `1` / `chainId` / this contract
- type: `Claim(bytes32 dataHash,string certType,address payer,uint256 deadline)`

Compile in [Remix](https://remix.ethereum.org) (solc 0.8.24) and deploy with:

1. `owner_` — agent owner EOA (`0x475F…E124`)
2. `issuer_` — monitor / `AGENT_SIGNER_KEY` address
3. `baseURI_` — e.g. `https://walcert.globalscoreagent.com/v1/receipts/`

**Deployed BSC mainnet:** [`0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7`](https://bscscan.com/address/0x4e430fB5A5f26ED08eC123373Cd8AD3cE15C24c7) (2026-08-22, Owner signer). Set `BNB_RECEIPT_CONTRACT` on the agent host. Do not airdrop from the monitor: DappBay DAU is `msg.sender` on `claim`. First live mint: tokenId 1, [tx 0x1fab40e6…c00d](https://bscscan.com/tx/0x1fab40e6d5fb30b8665936bab00750492683de95f856a185e19f5d7e2f39c00d).

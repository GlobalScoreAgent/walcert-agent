-- BNB receipt NFT voucher (x402 Permit2). data_hash is the AACP deliveryHash.
ALTER TABLE walcert.certificate_requests
  ADD COLUMN IF NOT EXISTS receipt_bnb jsonb;

COMMENT ON COLUMN walcert.certificate_requests.receipt_bnb IS
  'EIP-712 claim voucher for the BNB soulbound receipt NFT; data_hash == future AACP deliveryHash.';

CREATE INDEX IF NOT EXISTS certificate_requests_receipt_bnb_payer_idx
  ON walcert.certificate_requests ((receipt_bnb->>'payer'))
  WHERE receipt_bnb IS NOT NULL;

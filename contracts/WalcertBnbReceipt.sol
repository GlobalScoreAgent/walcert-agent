// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Walcert BNB receipt (not the certificate)
/// @notice Payer claims an ERC-721 bound to certificate `dataHash` (keccak of canonical JSON).
///         Same bytes32 is the future TermiX AACP `deliveryHash`. Soulbound: no transfers.
/// @dev Deploy on BSC (chainId 56). EIP-712 domain: name "Walcert Receipt", version "1".
///      Issuer (monitor) is distinct from Ownable owner. OpenZeppelin not vendored —
///      compile in Remix/Foundry with OZ 5.x: ERC721, EIP712, ECDSA, Ownable, Strings.
interface IERC721Receiver {
    function onERC721Received(address, address, uint256, bytes calldata) external returns (bytes4);
}

contract WalcertBnbReceipt {
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Claimed(bytes32 indexed dataHash, address indexed payer, uint256 indexed tokenId, string certType);

    string public constant name = "Walcert Receipt";
    string public constant symbol = "WRECEIPT";
    bytes32 public constant CLAIM_TYPEHASH =
        keccak256("Claim(bytes32 dataHash,string certType,address payer,uint256 deadline)");

    address public owner;
    address public issuer;
    string public baseURI;
    uint256 public nextId = 1;

    mapping(uint256 => address) private _ownerOf;
    mapping(bytes32 => uint256) public tokenIdOf; // dataHash => tokenId (0 = unused)
    mapping(uint256 => bytes32) public dataHashOf;
    mapping(uint256 => string) public certTypeOf;

    bytes32 private immutable _CACHED_DOMAIN_SEPARATOR;
    uint256 private immutable _CACHED_CHAIN_ID;
    bytes32 private constant _TYPE_HASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    error NotOwner();
    error NotIssuer();
    error NotPayer();
    error Expired();
    error Used();
    error BadSig();
    error ZeroHash();
    error Soulbound();
    error Nonexistent();

    constructor(address owner_, address issuer_, string memory baseURI_) {
        require(owner_ != address(0) && issuer_ != address(0), "zero");
        owner = owner_;
        issuer = issuer_;
        baseURI = baseURI_;
        _CACHED_CHAIN_ID = block.chainid;
        _CACHED_DOMAIN_SEPARATOR = _buildDomainSeparator();
    }

    function DOMAIN_SEPARATOR() public view returns (bytes32) {
        return block.chainid == _CACHED_CHAIN_ID ? _CACHED_DOMAIN_SEPARATOR : _buildDomainSeparator();
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                _TYPE_HASH,
                keccak256(bytes("Walcert Receipt")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
    }

    function claim(
        bytes32 dataHash,
        string calldata certType,
        address payer,
        uint256 deadline,
        bytes calldata signature
    ) external returns (uint256 tokenId) {
        if (dataHash == bytes32(0)) revert ZeroHash();
        if (block.timestamp > deadline) revert Expired();
        if (msg.sender != payer) revert NotPayer();
        if (tokenIdOf[dataHash] != 0) revert Used();

        bytes32 structHash = keccak256(
            abi.encode(CLAIM_TYPEHASH, dataHash, keccak256(bytes(certType)), payer, deadline)
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR(), structHash));
        address recovered = _recover(digest, signature);
        if (recovered != issuer) revert BadSig();

        tokenId = nextId++;
        tokenIdOf[dataHash] = tokenId;
        dataHashOf[tokenId] = dataHash;
        certTypeOf[tokenId] = certType;
        _ownerOf[tokenId] = payer;
        emit Transfer(address(0), payer, tokenId);
        emit Claimed(dataHash, payer, tokenId, certType);
    }

    function ownerOf(uint256 tokenId) public view returns (address) {
        address o = _ownerOf[tokenId];
        if (o == address(0)) revert Nonexistent();
        return o;
    }

    function balanceOf(address account) public view returns (uint256 n) {
        // O(n) not provided; soulbound receipts are looked up by dataHash.
        account;
        return 0;
    }

    function tokenURI(uint256 tokenId) public view returns (string memory) {
        if (_ownerOf[tokenId] == address(0)) revert Nonexistent();
        return string.concat(baseURI, _toHex(dataHashOf[tokenId]));
    }

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x80ac58cd || interfaceId == 0x5b5e139f || interfaceId == 0x01ffc9a7;
    }

    function approve(address, uint256) external pure {
        revert Soulbound();
    }

    function setApprovalForAll(address, bool) external pure {
        revert Soulbound();
    }

    function getApproved(uint256) external pure returns (address) {
        return address(0);
    }

    function isApprovedForAll(address, address) external pure returns (bool) {
        return false;
    }

    function transferFrom(address, address, uint256) external pure {
        revert Soulbound();
    }

    function safeTransferFrom(address, address, uint256) external pure {
        revert Soulbound();
    }

    function safeTransferFrom(address, address, uint256, bytes calldata) external pure {
        revert Soulbound();
    }

    function setIssuer(address issuer_) external {
        if (msg.sender != owner) revert NotOwner();
        issuer = issuer_;
    }

    function setBaseURI(string calldata uri) external {
        if (msg.sender != owner) revert NotOwner();
        baseURI = uri;
    }

    function transferOwnership(address owner_) external {
        if (msg.sender != owner) revert NotOwner();
        owner = owner_;
    }

    function _recover(bytes32 digest, bytes calldata sig) private pure returns (address) {
        if (sig.length != 65) revert BadSig();
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (v < 27) v += 27;
        address recovered = ecrecover(digest, v, r, s);
        if (recovered == address(0)) revert BadSig();
        return recovered;
    }

    function _toHex(bytes32 w) private pure returns (string memory) {
        bytes16 hexSymbols = "0123456789abcdef";
        bytes memory o = new bytes(66);
        o[0] = "0";
        o[1] = "x";
        for (uint256 i = 0; i < 32; i++) {
            uint8 b = uint8(w[i]);
            o[2 + i * 2] = hexSymbols[b >> 4];
            o[3 + i * 2] = hexSymbols[b & 0x0f];
        }
        return string(o);
    }
}

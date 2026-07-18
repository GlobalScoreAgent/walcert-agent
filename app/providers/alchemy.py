from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import KNOWN_LABELS, Settings, get_settings
from app.errors import MissingCredentials, ProviderError, QuotaExceeded
from app.providers.quota import QuotaManager, get_quota

TRANSFER_CATEGORIES = ["external", "erc20", "erc721", "erc1155"]
MAX_PAGES_ORIGINS = 2
MAX_PAGES_ACTIVITY = 3
PAGE_SIZE = 100  # 0x64
ADDRESS_CAP = 1000
TRANSFERS_CAP = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hex_page_size() -> str:
    return hex(PAGE_SIZE)


def _label_for(address: str | None) -> tuple[str, str | None]:
    if not address:
        return "other", None
    known = KNOWN_LABELS.get(address.lower())
    if known:
        return known
    return "other", None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.isdigit():
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _transfer_value_usd(transfer: dict[str, Any]) -> float:
    raw = transfer.get("value")
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


class AlchemyProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        quota: QuotaManager | None = None,
    ):
        self.settings = settings or get_settings()
        self.quota = quota or get_quota()

    def _ensure_credentials(self) -> None:
        if not self.settings.alchemy_endpoints:
            raise MissingCredentials("alchemy")

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "alchemy_getAssetTransfers",
            "params": [params],
        }
        try:
            response = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError("alchemy", f"network error: {exc}") from exc

        cu = self.settings.alchemy_cu_per_transfer_call
        if response.status_code >= 400:
            raise ProviderError(
                "alchemy",
                f"HTTP {response.status_code}: {response.text[:300]}",
                status_code=response.status_code,
            )
        data = response.json()
        if "error" in data:
            raise ProviderError("alchemy", str(data["error"]))
        result = data.get("result") or {}
        return result, cu

    async def _fetch_pages_on_network(
        self,
        client: httpx.AsyncClient,
        endpoint: dict[str, str | int],
        wallet: str,
        *,
        from_block: str,
        max_pages: int,
        to_address: bool = True,
    ) -> list[dict[str, Any]]:
        transfers: list[dict[str, Any]] = []
        page_key: str | None = None
        pages = 0
        url = str(endpoint["url"])
        network = str(endpoint["network"])
        chain_id = int(endpoint["chain_id"])
        chain_name = str(endpoint["name"])

        while pages < max_pages:
            call_cu = self.settings.alchemy_cu_per_transfer_call
            ok, retry = self.quota.can_consume_alchemy(call_cu)
            if not ok:
                if pages == 0 and not transfers:
                    raise QuotaExceeded("alchemy", retry or "next_day")
                break

            params: dict[str, Any] = {
                "fromBlock": from_block,
                "toBlock": "latest",
                "category": TRANSFER_CATEGORIES,
                "withMetadata": True,
                "maxCount": _hex_page_size(),
                "order": "asc" if to_address else "desc",
            }
            if to_address:
                params["toAddress"] = wallet
            else:
                params["fromAddress"] = wallet
            if page_key:
                params["pageKey"] = page_key

            result, cu = await self._rpc(client, url, params)
            self.quota.record_alchemy(cu)
            pages += 1

            batch = result.get("transfers") or []
            for item in batch:
                item = dict(item)
                item["_walcert_network"] = network
                item["_walcert_chain"] = chain_name
                item["_walcert_chain_id"] = chain_id
                transfers.append(item)
            page_key = result.get("pageKey")
            if not page_key or not batch:
                break

        return transfers[: max_pages * PAGE_SIZE]

    async def _fetch_pages_all_networks(
        self,
        wallet: str,
        *,
        from_block: str,
        max_pages: int,
        to_address: bool = True,
    ) -> list[dict[str, Any]]:
        self._ensure_credentials()
        n_networks = len(self.settings.alchemy_endpoints)
        estimated = self.quota.estimate_alchemy_cu(max_pages * n_networks)
        ok, retry = self.quota.can_consume_alchemy(estimated)
        if not ok:
            raise QuotaExceeded("alchemy", retry or "next_day")

        all_transfers: list[dict[str, Any]] = []
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            for endpoint in self.settings.alchemy_endpoints:
                try:
                    batch = await self._fetch_pages_on_network(
                        client,
                        endpoint,
                        wallet,
                        from_block=from_block,
                        max_pages=max_pages,
                        to_address=to_address,
                    )
                    all_transfers.extend(batch)
                except QuotaExceeded:
                    raise
                except ProviderError as exc:
                    errors.append(f"{endpoint['network']}: {exc.message}")

        if not all_transfers and errors:
            raise ProviderError("alchemy", "; ".join(errors))
        return all_transfers

    def _chains_analyzed(self, transfers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, Any]] = {}
        for t in transfers:
            name = str(t.get("_walcert_chain") or "unknown")
            if name not in counts:
                counts[name] = {
                    "chain": name,
                    "chain_id": t.get("_walcert_chain_id"),
                    "network": t.get("_walcert_network"),
                    "transfers": 0,
                }
            counts[name]["transfers"] += 1
        return list(counts.values())

    def _build_origins(self, wallet: str, transfers: list[dict[str, Any]]) -> dict[str, Any]:
        senders: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_value_usd": 0.0,
                "tx_count": 0,
                "label": None,
                "category": "other",
                "chain": None,
                "chain_id": None,
            }
        )
        category_totals: dict[str, float] = defaultdict(float)
        first_funding = None
        earliest_ts: datetime | None = None

        for transfer in transfers:
            frm = (transfer.get("from") or "").lower() or None
            if not frm:
                continue
            usd = _transfer_value_usd(transfer)
            category, label = _label_for(frm)
            senders[frm]["total_value_usd"] += usd
            senders[frm]["tx_count"] += 1
            senders[frm]["label"] = label
            senders[frm]["category"] = category
            senders[frm]["chain"] = transfer.get("_walcert_chain")
            senders[frm]["chain_id"] = transfer.get("_walcert_chain_id")
            category_totals[category] += usd

            meta = transfer.get("metadata") or {}
            ts = _parse_timestamp(meta.get("blockTimestamp"))
            if ts and (earliest_ts is None or ts < earliest_ts):
                earliest_ts = ts
                first_funding = {
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "from": frm,
                    "value_usd_estimate": round(usd, 2),
                    "category": category,
                    "label": label,
                    "chain": transfer.get("_walcert_chain"),
                    "chain_id": transfer.get("_walcert_chain_id"),
                }

        total_usd = sum(category_totals.values()) or 0.0

        def pct(cat: str) -> float:
            if total_usd <= 0:
                return 0.0
            return round(100.0 * category_totals.get(cat, 0.0) / total_usd, 1)

        all_senders = sorted(
            (
                {
                    "address": addr,
                    "label": data["label"],
                    "total_value_usd": round(data["total_value_usd"], 2),
                    "tx_count": data["tx_count"],
                    "chain": data["chain"],
                    "chain_id": data["chain_id"],
                }
                for addr, data in senders.items()
            ),
            key=lambda x: x["total_value_usd"],
            reverse=True,
        )
        senders_list = all_senders[:ADDRESS_CAP]
        top_senders = all_senders[:10]

        unique_senders = len(senders)
        cex_dep = (category_totals.get("cex", 0.0) / total_usd) if total_usd else 0.0
        diversity = min(1.0, unique_senders / 20.0) if unique_senders else 0.0
        mixing = 0.15 if unique_senders >= 5 else 0.35 if unique_senders <= 1 else 0.25
        main_origin = max(
            ("cex", "bridge", "dex", "other"),
            key=lambda c: category_totals.get(c, 0.0),
            default="other",
        )
        if total_usd <= 0:
            main_origin = "other"

        return {
            "module": "origins",
            "wallet": wallet,
            "chains_analyzed": self._chains_analyzed(transfers),
            "networks": [e["network"] for e in self.settings.alchemy_endpoints],
            "analyzed_at": _now_iso(),
            "total_transfers_analyzed": len(transfers),
            "first_funding": first_funding,
            "origin_summary": {
                "cex_percentage": pct("cex"),
                "bridge_percentage": pct("bridge"),
                "dex_percentage": pct("dex"),
                "other_percentage": pct("other"),
                "unique_senders": unique_senders,
                "mixing_risk": "low" if mixing < 0.25 else "medium",
                "main_origin_type": main_origin,
            },
            "senders": senders_list,
            "top_senders": top_senders,
            "score_inputs": {
                "cex_dependency": round(cex_dep, 2),
                "sender_diversity": round(diversity, 2),
                "mixing_signals": round(mixing, 2),
            },
        }

    def _build_activity(self, wallet: str, transfers: list[dict[str, Any]]) -> dict[str, Any]:
        wallet_l = wallet.lower()
        counterparties: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "tx_count": 0,
                "direction": set(),
                "label": None,
                "chain": None,
                "chain_id": None,
                "total_value_usd": 0.0,
            }
        )
        inflow = outflow = 0
        cex_interactions = 0
        compact_transfers: list[dict[str, Any]] = []

        for transfer in transfers:
            frm = (transfer.get("from") or "").lower()
            to = (transfer.get("to") or "").lower()
            usd = _transfer_value_usd(transfer)
            meta = transfer.get("metadata") or {}
            ts = _parse_timestamp(meta.get("blockTimestamp"))
            if to == wallet_l:
                inflow += 1
                other = frm
                direction = "in"
            else:
                outflow += 1
                other = to
                direction = "out"
            compact_transfers.append(
                {
                    "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None,
                    "from": frm or None,
                    "to": to or None,
                    "value": round(usd, 6),
                    "chain": transfer.get("_walcert_chain"),
                }
            )
            if not other:
                continue
            category, label = _label_for(other)
            if category == "cex":
                cex_interactions += 1
            counterparties[other]["tx_count"] += 1
            counterparties[other]["direction"].add(direction)
            counterparties[other]["label"] = label
            counterparties[other]["chain"] = transfer.get("_walcert_chain")
            counterparties[other]["chain_id"] = transfer.get("_walcert_chain_id")
            counterparties[other]["total_value_usd"] += usd

        total = len(transfers) or 1
        unique = len(counterparties)
        cex_pct = round(100.0 * cex_interactions / total, 1)
        all_cp = sorted(
            (
                {
                    "address": addr,
                    "tx_count": data["tx_count"],
                    "direction": (
                        "both"
                        if data["direction"] == {"in", "out"}
                        else next(iter(data["direction"]), "unknown")
                    ),
                    "label": data["label"],
                    "chain": data["chain"],
                    "chain_id": data["chain_id"],
                    "total_value_usd": round(data["total_value_usd"], 2),
                }
                for addr, data in counterparties.items()
            ),
            key=lambda x: x["tx_count"],
            reverse=True,
        )
        counterparties_list = all_cp[:ADDRESS_CAP]
        top = all_cp[:10]

        diversity = min(1.0, unique / 30.0)
        cex_dep = cex_interactions / total
        natural = max(0.0, min(1.0, 0.5 * diversity + 0.5 * (1.0 - cex_dep)))

        return {
            "module": "activity",
            "wallet": wallet_l,
            "chains_analyzed": self._chains_analyzed(transfers),
            "networks": [e["network"] for e in self.settings.alchemy_endpoints],
            "analyzed_at": _now_iso(),
            "window_days": 7,
            "total_transfers": len(transfers),
            "inflow_count": inflow,
            "outflow_count": outflow,
            "unique_counterparties": unique,
            "cex_interaction_percentage": cex_pct,
            "behavior_signals": {
                # Edge Function recomputes wash/circular from transfers[]
                "wash_trading_risk": None,
                "circular_patterns": None,
                "bot_like_activity": len(transfers) > 80 and unique < 5,
                "high_frequency_trading": len(transfers) > 100,
            },
            "counterparties": counterparties_list,
            "top_counterparties": top,
            "transfers": compact_transfers[:TRANSFERS_CAP],
            "score_inputs": {
                "counterparty_diversity": round(diversity, 2),
                "cex_dependency": round(cex_dep, 2),
                "natural_flow_score": round(natural, 2),
            },
        }

    async def analyze_origins(self, wallet: str) -> dict[str, Any]:
        transfers = await self._fetch_pages_all_networks(
            wallet, from_block="0x0", max_pages=MAX_PAGES_ORIGINS, to_address=True
        )
        return self._build_origins(wallet, transfers)

    async def analyze_activity(self, wallet: str) -> dict[str, Any]:
        self._ensure_credentials()
        n = len(self.settings.alchemy_endpoints)
        estimated = self.quota.estimate_alchemy_cu(MAX_PAGES_ACTIVITY * 2 * n)
        ok, retry = self.quota.can_consume_alchemy(estimated)
        if not ok:
            raise QuotaExceeded("alchemy", retry or "next_day")

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        transfers = await self._fetch_recent_window(wallet, cutoff)
        return self._build_activity(wallet, transfers)

    async def _fetch_recent_window(
        self, wallet: str, cutoff: datetime
    ) -> list[dict[str, Any]]:
        """Fetch recent transfers for wallet (in + out) across all Alchemy networks."""
        self._ensure_credentials()
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            for endpoint in self.settings.alchemy_endpoints:
                url = str(endpoint["url"])
                network = str(endpoint["network"])
                chain_id = int(endpoint["chain_id"])
                chain_name = str(endpoint["name"])
                for direction in ("to", "from"):
                    page_key = None
                    for _ in range(MAX_PAGES_ACTIVITY):
                        call_cu = self.settings.alchemy_cu_per_transfer_call
                        ok, retry = self.quota.can_consume_alchemy(call_cu)
                        if not ok:
                            if not collected:
                                raise QuotaExceeded("alchemy", retry or "next_day")
                            return collected
                        params: dict[str, Any] = {
                            "fromBlock": "0x0",
                            "toBlock": "latest",
                            "category": TRANSFER_CATEGORIES,
                            "withMetadata": True,
                            "maxCount": _hex_page_size(),
                            "order": "desc",
                        }
                        if direction == "to":
                            params["toAddress"] = wallet
                        else:
                            params["fromAddress"] = wallet
                        if page_key:
                            params["pageKey"] = page_key
                        try:
                            result, cu = await self._rpc(client, url, params)
                        except ProviderError:
                            break
                        self.quota.record_alchemy(cu)
                        batch = result.get("transfers") or []
                        stop = False
                        for transfer in batch:
                            uniq = (
                                f"{network}-{transfer.get('hash')}-"
                                f"{transfer.get('uniqueId')}-"
                                f"{transfer.get('from')}-{transfer.get('to')}"
                            )
                            meta = transfer.get("metadata") or {}
                            ts = _parse_timestamp(meta.get("blockTimestamp"))
                            if ts and ts < cutoff:
                                stop = True
                                continue
                            if uniq in seen:
                                continue
                            seen.add(uniq)
                            item = dict(transfer)
                            item["_walcert_network"] = network
                            item["_walcert_chain"] = chain_name
                            item["_walcert_chain_id"] = chain_id
                            collected.append(item)
                        page_key = result.get("pageKey")
                        if stop or not page_key or not batch:
                            break
        return collected

    async def probe_celo_activity(self, wallet: str) -> dict[str, Any] | None:
        """Lightweight Celo presence check for multichain merge (1 page inbound)."""
        self._ensure_credentials()
        celo_eps = [
            e for e in self.settings.alchemy_endpoints if e.get("name") == "celo"
        ]
        if not celo_eps:
            # Try celo-mainnet network slug
            celo_eps = [
                e
                for e in self.settings.alchemy_endpoints
                if str(e.get("network", "")).startswith("celo")
            ]
        if not celo_eps:
            return None

        endpoint = celo_eps[0]
        call_cu = self.settings.alchemy_cu_per_transfer_call
        ok, retry = self.quota.can_consume_alchemy(call_cu)
        if not ok:
            return None

        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            try:
                batch = await self._fetch_pages_on_network(
                    client,
                    endpoint,
                    wallet,
                    from_block="0x0",
                    max_pages=1,
                    to_address=True,
                )
            except (ProviderError, QuotaExceeded):
                return None

        if not batch:
            return None

        first_ts: datetime | None = None
        last_ts: datetime | None = None
        for transfer in batch:
            meta = transfer.get("metadata") or {}
            ts = _parse_timestamp(meta.get("blockTimestamp"))
            if not ts:
                continue
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

        return {
            "chain": "celo",
            "chain_id": 42220,
            "first_transaction": (
                first_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if first_ts else None
            ),
            "last_transaction": (
                last_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if last_ts else None
            ),
        }

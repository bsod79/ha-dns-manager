"""Cloudflare DNS provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from ..const import (
    AUTH_MODE_GLOBAL_KEY,
    AUTH_MODE_TOKEN,
    CONF_API_EMAIL,
    CONF_API_KEY,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
)
from ..exceptions import ProviderAPIError, ProviderAuthError, RecordNotFoundError
from .base import AddressPair, DNSProvider, DnsRecord

CF_BASE_URL = "https://api.cloudflare.com/client/v4"


def _cloudflare_error_detail(payload: Any) -> str:
    """Best-effort human detail from a Cloudflare v4 JSON body."""
    if not isinstance(payload, dict):
        return ""
    errors = payload.get("errors") or []
    parts: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        msg = item.get("message")
        if msg:
            parts.append(str(msg))
            continue
        code = item.get("code")
        if code is not None:
            parts.append(str(code))
    return " ".join(parts).strip()


class CloudflareProvider(DNSProvider):
    """Cloudflare implementation using the v4 REST API."""

    def _headers(self) -> dict[str, str]:
        creds = self._config.credentials
        auth_mode = creds.get(CONF_AUTH_MODE)

        if auth_mode == AUTH_MODE_TOKEN and creds.get(CONF_API_TOKEN):
            return {"Authorization": f"Bearer {creds[CONF_API_TOKEN]}"}

        if (
            auth_mode == AUTH_MODE_GLOBAL_KEY
            and creds.get(CONF_API_EMAIL)
            and creds.get(CONF_API_KEY)
        ):
            return {
                "X-Auth-Email": creds[CONF_API_EMAIL],
                "X-Auth-Key": creds[CONF_API_KEY],
            }

        raise ProviderAuthError("Missing or invalid Cloudflare credentials")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{CF_BASE_URL}{path}"

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout, headers=self._headers()) as session:
            async with session.request(method, url, params=params, json=json) as resp:
                try:
                    payload = await resp.json(content_type=None)
                except Exception as err:  # noqa: BLE001
                    raise ProviderAPIError(f"Cloudflare returned invalid JSON ({resp.status})") from err

        detail = _cloudflare_error_detail(payload)

        if resp.status == 401:
            msg = "Invalid Cloudflare credentials or API token."
            if detail:
                msg = f"{msg} {detail}"
            raise ProviderAuthError(msg.strip())

        if resp.status == 403:
            # Common case: token can read DNS but lacks Zone: DNS: Edit for writes.
            msg = (
                "Cloudflare refused this request (HTTP 403). "
                "If you use an API token, grant DNS write access for this zone "
                "(permission: Zone — DNS — Edit, with the correct zone resource)."
            )
            if detail:
                msg = f"{msg} Cloudflare: {detail}"
            raise ProviderAPIError(msg.strip())

        if resp.status < 200 or resp.status >= 300:
            msg = f"Unexpected Cloudflare HTTP status {resp.status}"
            if detail:
                msg = f"{msg}: {detail}"
            raise ProviderAPIError(msg.strip())

        if not isinstance(payload, dict) or payload.get("success") is not True:
            errors = []
            if isinstance(payload, dict):
                errors = payload.get("errors") or []
            raise ProviderAPIError("Cloudflare API error", errors=errors)

        return payload.get("result")

    async def validate_credentials(self) -> bool:
        # A lightweight call that requires auth.
        await self.list_zones()
        return True

    async def list_zones(self) -> list[dict]:
        result = await self._request("GET", "/zones")
        if not isinstance(result, list):
            raise ProviderAPIError("Unexpected Cloudflare zones response")
        return [{"id": z["id"], "name": z["name"]} for z in result if "id" in z and "name" in z]

    async def list_a_records(self, zone_id: str) -> list[DnsRecord]:
        """List A and AAAA records (deduped by name for UI: prefer A id)."""
        by_name: dict[str, DnsRecord] = {}
        for rtype in ("A", "AAAA"):
            for rec in await self._list_records_by_type(zone_id, rtype):
                existing = by_name.get(rec.name)
                if existing is None:
                    by_name[rec.name] = rec
                elif rtype == "A":
                    # Prefer A record id as primary when both exist
                    by_name[rec.name] = rec
        return list(by_name.values())

    async def _list_records_by_type(self, zone_id: str, record_type: str) -> list[DnsRecord]:
        records: list[DnsRecord] = []
        page = 1
        per_page = 100
        while True:
            result = await self._request(
                "GET",
                f"/zones/{zone_id}/dns_records",
                params={"type": record_type, "page": str(page), "per_page": str(per_page)},
            )
            if not isinstance(result, list):
                raise ProviderAPIError("Unexpected Cloudflare records response")

            for r in result:
                if not isinstance(r, dict) or r.get("type") != record_type:
                    continue
                record_id = r.get("id")
                name = r.get("name")
                content = r.get("content")
                if not record_id or not name:
                    continue
                records.append(
                    DnsRecord(
                        record_id=str(record_id),
                        name=str(name),
                        current_ip=str(content or ""),
                        record_type=record_type,
                        proxied=bool(r.get("proxied", False)),
                        ttl=int(r.get("ttl", 1) or 1),
                    )
                )

            if len(result) < per_page:
                break
            page += 1
            await asyncio.sleep(0)
        return records

    async def find_record_by_name(
        self, zone_id: str, name: str, record_type: str
    ) -> DnsRecord | None:
        for rec in await self._list_records_by_type(zone_id, record_type):
            if rec.name.lower() == name.lower():
                return rec
        return None

    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        result = await self._request("GET", f"/zones/{zone_id}/dns_records/{record_id}")
        if not isinstance(result, dict):
            raise ProviderAPIError("Unexpected Cloudflare record response")
        if result.get("id") is None:
            raise RecordNotFoundError(record_id)
        rtype = str(result.get("type", "A"))
        if rtype not in ("A", "AAAA"):
            raise ProviderAPIError(f"Unsupported record type: {rtype}")

        return DnsRecord(
            record_id=str(result["id"]),
            name=str(result.get("name", "")),
            current_ip=str(result.get("content", "")),
            record_type=rtype,
            proxied=bool(result.get("proxied", False)),
            ttl=int(result.get("ttl", 1) or 1),
        )

    async def update_record(self, zone_id: str, record: DnsRecord, new_ip: str) -> DnsRecord:
        body: dict[str, Any] = {
            "type": record.record_type,
            "name": record.name,
            "content": new_ip,
            "ttl": record.ttl,
            "proxied": record.proxied,
        }

        result = await self._request(
            "PUT",
            f"/zones/{zone_id}/dns_records/{record.record_id}",
            json=body,
        )
        if not isinstance(result, dict):
            raise ProviderAPIError("Unexpected Cloudflare update response")

        return DnsRecord(
            record_id=str(result.get("id", record.record_id)),
            name=str(result.get("name", record.name)),
            current_ip=str(result.get("content", new_ip)),
            record_type=str(result.get("type", record.record_type)),
            proxied=bool(result.get("proxied", record.proxied)),
            ttl=int(result.get("ttl", record.ttl) or record.ttl),
        )

    async def _create_record(
        self,
        zone_id: str,
        *,
        name: str,
        record_type: str,
        content: str,
        proxied: bool,
        ttl: int,
    ) -> DnsRecord:
        body = {
            "type": record_type,
            "name": name,
            "content": content,
            "ttl": ttl,
            "proxied": proxied if record_type == "A" else False,
        }
        result = await self._request("POST", f"/zones/{zone_id}/dns_records", json=body)
        if not isinstance(result, dict):
            raise ProviderAPIError("Unexpected Cloudflare create response")
        return DnsRecord(
            record_id=str(result.get("id", "")),
            name=str(result.get("name", name)),
            current_ip=str(result.get("content", content)),
            record_type=str(result.get("type", record_type)),
            proxied=bool(result.get("proxied", False)),
            ttl=int(result.get("ttl", ttl) or ttl),
        )

    async def get_addresses(
        self,
        zone_id: str,
        *,
        name: str,
        record_id: str = "",
        record_id_aaaa: str = "",
    ) -> AddressPair:
        ipv4 = ""
        ipv6 = ""
        if record_id:
            try:
                rec = await self.get_record(zone_id, record_id)
                ipv4 = rec.current_ip
                name = name or rec.name
            except RecordNotFoundError:
                pass
        elif name:
            found = await self.find_record_by_name(zone_id, name, "A")
            if found:
                ipv4 = found.current_ip

        if record_id_aaaa:
            try:
                rec6 = await self.get_record(zone_id, record_id_aaaa)
                ipv6 = rec6.current_ip
            except RecordNotFoundError:
                pass
        elif name:
            found6 = await self.find_record_by_name(zone_id, name, "AAAA")
            if found6:
                ipv6 = found6.current_ip
        return AddressPair(ipv4=ipv4, ipv6=ipv6)

    async def update_addresses(
        self,
        zone_id: str,
        *,
        name: str,
        record_id: str = "",
        record_id_aaaa: str = "",
        ipv4: str | None = None,
        ipv6: str | None = None,
        proxied: bool = False,
        ttl: int = 1,
    ) -> AddressPair:
        out = AddressPair()
        host = name

        if ipv4 is not None:
            if record_id:
                current = await self.get_record(zone_id, record_id)
                host = host or current.name
                updated = await self.update_record(zone_id, current, ipv4)
                out.ipv4 = updated.current_ip
            else:
                existing = await self.find_record_by_name(zone_id, host, "A") if host else None
                if existing:
                    updated = await self.update_record(zone_id, existing, ipv4)
                    out.ipv4 = updated.current_ip
                elif host:
                    created = await self._create_record(
                        zone_id,
                        name=host,
                        record_type="A",
                        content=ipv4,
                        proxied=proxied,
                        ttl=ttl,
                    )
                    out.ipv4 = created.current_ip

        if ipv6 is not None:
            if record_id_aaaa:
                current = await self.get_record(zone_id, record_id_aaaa)
                host = host or current.name
                updated = await self.update_record(zone_id, current, ipv6)
                out.ipv6 = updated.current_ip
            else:
                existing = await self.find_record_by_name(zone_id, host, "AAAA") if host else None
                if existing:
                    updated = await self.update_record(zone_id, existing, ipv6)
                    out.ipv6 = updated.current_ip
                elif host:
                    created = await self._create_record(
                        zone_id,
                        name=host,
                        record_type="AAAA",
                        content=ipv6,
                        proxied=False,
                        ttl=ttl,
                    )
                    out.ipv6 = created.current_ip

        return out


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
from .base import DNSProvider, DnsRecord

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
        records: list[DnsRecord] = []

        page = 1
        per_page = 100

        # Cloudflare paginates; stop when fewer than per_page.
        while True:
            result = await self._request(
                "GET",
                f"/zones/{zone_id}/dns_records",
                params={"type": "A", "page": str(page), "per_page": str(per_page)},
            )
            if not isinstance(result, list):
                raise ProviderAPIError("Unexpected Cloudflare records response")

            for r in result:
                if not isinstance(r, dict):
                    continue
                if r.get("type") != "A":
                    continue
                record_id = r.get("id")
                name = r.get("name")
                content = r.get("content")
                if not record_id or not name or not content:
                    continue
                records.append(
                    DnsRecord(
                        record_id=str(record_id),
                        name=str(name),
                        current_ip=str(content),
                        record_type=str(r.get("type", "A")),
                        proxied=bool(r.get("proxied", False)),
                        ttl=int(r.get("ttl", 1) or 1),
                    )
                )

            if len(result) < per_page:
                break
            page += 1
            await asyncio.sleep(0)

        return records

    async def get_record(self, zone_id: str, record_id: str) -> DnsRecord:
        result = await self._request("GET", f"/zones/{zone_id}/dns_records/{record_id}")
        if not isinstance(result, dict):
            raise ProviderAPIError("Unexpected Cloudflare record response")
        if result.get("id") is None:
            raise RecordNotFoundError(record_id)
        if result.get("type") != "A":
            raise ProviderAPIError("Record is not type A")

        return DnsRecord(
            record_id=str(result["id"]),
            name=str(result.get("name", "")),
            current_ip=str(result.get("content", "")),
            record_type=str(result.get("type", "A")),
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


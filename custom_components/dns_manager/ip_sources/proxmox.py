"""Proxmox VE client for reading guest interface addresses."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from ..const import (
    CONF_PVE_HOST,
    CONF_PVE_TOKEN_ID,
    CONF_PVE_TOKEN_SECRET,
    CONF_PVE_VERIFY_SSL,
    PROXMOX_KIND_LXC,
    PROXMOX_KIND_QEMU,
)
from ..exceptions import IPDetectionError, ProviderAPIError, ProviderAuthError

_LOGGER = logging.getLogger(__name__)


def _normalize_host(host: str) -> str:
    value = host.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


def _strip_cidr(value: str) -> str:
    return value.split("/", 1)[0].strip()


def _is_link_local(ip: str) -> bool:
    lower = ip.lower()
    return lower.startswith("fe80:") or lower.startswith("169.254.")


class ProxmoxIpClient:
    """Read-only Proxmox API helper (API token auth)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        host: str,
        token_id: str,
        token_secret: str,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        self._host = _normalize_host(host)
        self._token_id = token_id.strip()
        self._token_secret = token_secret.strip()
        self._verify_ssl = verify_ssl

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"PVEAPIToken={self._token_id}={self._token_secret}",
            "Accept": "application/json",
        }

    async def _request(self, path: str) -> Any:
        url = f"{self._host}{path}"
        try:
            async with self._session.get(
                url,
                headers=self._headers(),
                ssl=self._verify_ssl if self._host.startswith("https://") else None,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                if resp.status == 401:
                    raise ProviderAuthError(
                        "Proxmox authentication failed (HTTP 401). Check token id and secret."
                    )
                if resp.status == 403:
                    raise ProviderAPIError(
                        "Proxmox forbidden (HTTP 403). Grant the API token at least "
                        "VM.Audit on the target guest (and Sys.Audit if listing nodes fails)."
                    )
                if resp.status >= 400:
                    raise ProviderAPIError(f"Proxmox HTTP {resp.status}: {text[:200]}")
                try:
                    payload = await resp.json(content_type=None)
                except Exception as err:  # noqa: BLE001
                    raise ProviderAPIError(f"Proxmox returned non-JSON: {text[:120]}") from err
        except (ProviderAuthError, ProviderAPIError):
            raise
        except aiohttp.ClientError as err:
            raise ProviderAPIError(f"Cannot reach Proxmox at {self._host}") from err

        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    async def validate_credentials(self) -> bool:
        """Lightweight check: GET /api2/json/version."""
        await self._request("/api2/json/version")
        return True

    async def list_nodes(self) -> list[str]:
        data = await self._request("/api2/json/nodes")
        nodes: list[str] = []
        for row in data or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("node") or "").strip()
            if name:
                nodes.append(name)
        return sorted(nodes)

    async def list_guests(self, node: str, kind: str) -> list[dict[str, str]]:
        """Return [{vmid, name, status}, ...] for LXC or QEMU on a node."""
        if kind == PROXMOX_KIND_LXC:
            path = f"/api2/json/nodes/{node}/lxc"
        elif kind == PROXMOX_KIND_QEMU:
            path = f"/api2/json/nodes/{node}/qemu"
        else:
            raise ProviderAPIError(f"Unsupported Proxmox kind: {kind}")

        data = await self._request(path)
        guests: list[dict[str, str]] = []
        for row in data or []:
            if not isinstance(row, dict):
                continue
            vmid = str(row.get("vmid") or "").strip()
            if not vmid:
                continue
            name = str(row.get("name") or vmid).strip()
            status = str(row.get("status") or "").strip()
            guests.append({"vmid": vmid, "name": name, "status": status})
        guests.sort(key=lambda g: int(g["vmid"]) if g["vmid"].isdigit() else g["vmid"])
        return guests

    async def get_guest_ip(
        self,
        *,
        node: str,
        kind: str,
        vmid: str,
        family: str = "ipv4",
        iface: str | None = None,
    ) -> str:
        """Return first usable address for the guest, or raise IPDetectionError."""
        if kind == PROXMOX_KIND_LXC:
            return await self._ip_from_lxc(node, vmid, family=family, iface=iface)
        if kind == PROXMOX_KIND_QEMU:
            return await self._ip_from_qemu(node, vmid, family=family, iface=iface)
        raise IPDetectionError(f"Unsupported Proxmox kind: {kind}")

    async def _ip_from_lxc(
        self, node: str, vmid: str, *, family: str, iface: str | None
    ) -> str:
        data = await self._request(f"/api2/json/nodes/{node}/lxc/{vmid}/interfaces")
        key = "inet" if family == "ipv4" else "inet6"
        for row in data or []:
            if not isinstance(row, dict):
                continue
            if iface and str(row.get("name") or "") != iface:
                continue
            raw = row.get(key)
            for candidate in _iter_addr_values(raw):
                ip = _strip_cidr(candidate)
                if ip and not _is_link_local(ip):
                    return ip
        raise IPDetectionError(
            f"No {family} on LXC {vmid}@{node} (running? correct iface?)"
        )

    async def _ip_from_qemu(
        self, node: str, vmid: str, *, family: str, iface: str | None
    ) -> str:
        data = await self._request(
            f"/api2/json/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces"
        )
        # Agent responses are often {"result": [ ... ]} nested under data.
        result = data
        if isinstance(data, dict):
            result = data.get("result", data)
        wanted = "ipv4" if family == "ipv4" else "ipv6"
        for row in result or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "")
            if name in ("lo", "lo0"):
                continue
            if iface and name != iface:
                continue
            for addr in row.get("ip-addresses") or []:
                if not isinstance(addr, dict):
                    continue
                if str(addr.get("ip-address-type") or "") != wanted:
                    continue
                ip = str(addr.get("ip-address") or "").strip()
                if ip and not _is_link_local(ip):
                    return ip
        raise IPDetectionError(
            f"No {family} on VM {vmid}@{node} (guest agent installed and running?)"
        )


def _iter_addr_values(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    return [text] if text else []


def proxmox_client_from_config(
    session: aiohttp.ClientSession, config: dict[str, Any]
) -> ProxmoxIpClient:
    return ProxmoxIpClient(
        session,
        host=str(config.get(CONF_PVE_HOST) or ""),
        token_id=str(config.get(CONF_PVE_TOKEN_ID) or ""),
        token_secret=str(config.get(CONF_PVE_TOKEN_SECRET) or ""),
        verify_ssl=bool(config.get(CONF_PVE_VERIFY_SSL, True)),
    )

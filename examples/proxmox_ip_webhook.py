#!/usr/bin/env python3
"""Tiny Proxmox → IP webhook for DNS Manager (From URL).

Returns JSON: {"ip": "1.2.3.4"}  (plain text IP also works).

Setup
-----
1. Create a Proxmox API token (Datacenter → Permissions → API Tokens)
   with at least VM.Audit on the target CT/VM.
2. Export env vars (or pass CLI flags):

     export PVE_HOST=https://192.168.1.10:8006
     export PVE_TOKEN_ID=dns@pve!dns-manager   # user@realm!tokenname
     export PVE_TOKEN_SECRET=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
     export PVE_NODE=pve
     export PVE_VMID=101
     export PVE_KIND=lxc                      # lxc | qemu
     export BIND=0.0.0.0
     export PORT=8787

3. Run:  python3 proxmox_ip_webhook.py
4. In DNS Manager → record IP strategy → From URL:
     http://<host>:8787/ip
     or per-container: http://<host>:8787/ip/lxc/pve/101

Security: bind to LAN only, put behind reverse proxy + auth if exposed.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise SystemExit(f"Missing required env: {name}")
    return value


PVE_HOST = os.environ.get("PVE_HOST", "https://127.0.0.1:8006").rstrip("/")
PVE_TOKEN_ID = os.environ.get("PVE_TOKEN_ID", "")
PVE_TOKEN_SECRET = os.environ.get("PVE_TOKEN_SECRET", "")
PVE_VERIFY_SSL = os.environ.get("PVE_VERIFY_SSL", "0") not in ("0", "false", "False")
DEFAULT_NODE = os.environ.get("PVE_NODE", "")
DEFAULT_VMID = os.environ.get("PVE_VMID", "")
DEFAULT_KIND = os.environ.get("PVE_KIND", "lxc")  # lxc | qemu
DEFAULT_IFACE = os.environ.get("PVE_IFACE", "")  # e.g. eth0 / ens18; empty = first with IP
FAMILY = os.environ.get("PVE_FAMILY", "ipv4")  # ipv4 | ipv6
BIND = os.environ.get("BIND", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8787"))


def _ssl_context() -> ssl.SSLContext | None:
    if PVE_HOST.startswith("https://") and not PVE_VERIFY_SSL:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def pve_get(path: str) -> dict:
    if not PVE_TOKEN_ID or not PVE_TOKEN_SECRET:
        raise RuntimeError("Set PVE_TOKEN_ID and PVE_TOKEN_SECRET")
    url = f"{PVE_HOST}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"PVEAPIToken={PVE_TOKEN_ID}={PVE_TOKEN_SECRET}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        raise RuntimeError(f"Proxmox HTTP {err.code}: {body}") from err


def _strip_cidr(value: str) -> str:
    return value.split("/", 1)[0].strip()


def _usable(ip: str) -> bool:
    lower = ip.lower()
    if not ip or lower == "::1" or lower.startswith("127."):
        return False
    if lower.startswith("fe80:") or lower.startswith("169.254."):
        return False
    return True


def ip_from_lxc(node: str, vmid: str, *, iface: str, family: str) -> str:
    data = pve_get(f"/api2/json/nodes/{node}/lxc/{vmid}/interfaces").get("data") or []
    key = "inet" if family == "ipv4" else "inet6"
    for row in data:
        name = row.get("name") or ""
        if name in ("lo", "lo0"):
            continue
        if iface and name != iface:
            continue
        raw = row.get(key)
        if not raw:
            continue
        # may be "1.2.3.4/24" or a list of CIDRs on newer PVE
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        ip = _strip_cidr(str(raw))
        if _usable(ip):
            return ip
    raise RuntimeError(f"No {family} on CT {vmid} (running? correct iface?)")


def ip_from_qemu(node: str, vmid: str, *, iface: str, family: str) -> str:
    # Requires qemu-guest-agent installed + enabled in the VM.
    data = pve_get(
        f"/api2/json/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces"
    ).get("data") or {}
    result = data.get("result") or data
    if isinstance(result, dict):
        result = result.get("result") or []
    wanted = "ipv4" if family == "ipv4" else "ipv6"
    for row in result or []:
        name = row.get("name") or ""
        if name in ("lo", "lo0"):
            continue
        if iface and name != iface:
            continue
        for addr in row.get("ip-addresses") or []:
            if addr.get("ip-address-type") != wanted:
                continue
            ip = str(addr.get("ip-address") or "").strip()
            if _usable(ip):
                return ip
    raise RuntimeError(f"No {family} on VM {vmid} (guest agent running?)")


def resolve_ip(kind: str, node: str, vmid: str, *, iface: str, family: str) -> str:
    if kind == "lxc":
        return ip_from_lxc(node, vmid, iface=iface, family=family)
    if kind == "qemu":
        return ip_from_qemu(node, vmid, iface=iface, family=family)
    raise RuntimeError("kind must be lxc or qemu")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quieter
        print(f"{self.address_string()} - {fmt % args}")

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        try:
            if path == "/health":
                self._send(200, {"ok": True})
                return

            # /ip  → defaults from env
            # /ip/{kind}/{node}/{vmid}
            kind, node, vmid = DEFAULT_KIND, DEFAULT_NODE, DEFAULT_VMID
            parts = [p for p in path.split("/") if p]
            if parts and parts[0] == "ip":
                if len(parts) == 4:
                    kind, node, vmid = parts[1], parts[2], parts[3]
                elif len(parts) != 1:
                    raise RuntimeError("Use /ip or /ip/{lxc|qemu}/{node}/{vmid}")
            else:
                raise RuntimeError("Not found (try /ip or /health)")

            if not node or not vmid:
                raise RuntimeError("Set PVE_NODE + PVE_VMID or use /ip/{kind}/{node}/{vmid}")

            iface = qs.get("iface", [DEFAULT_IFACE])[0]
            family = qs.get("family", [FAMILY])[0]
            if family not in ("ipv4", "ipv6"):
                raise RuntimeError("family must be ipv4 or ipv6")

            ip = resolve_ip(kind, node, vmid, iface=iface, family=family)
            self._send(200, {"ip": ip})
        except Exception as err:  # noqa: BLE001
            self._send(502, {"error": str(err)})


def main() -> None:
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"Listening on http://{BIND}:{PORT}  (GET /ip)")
    server.serve_forever()


if __name__ == "__main__":
    main()

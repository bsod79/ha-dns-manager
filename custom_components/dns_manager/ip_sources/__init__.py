"""IP source backends (read addresses; do not write DNS)."""

from __future__ import annotations

from .proxmox import ProxmoxIpClient, proxmox_client_from_config

__all__ = ["ProxmoxIpClient", "proxmox_client_from_config"]

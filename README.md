# DNS Manager for Home Assistant

Custom integration to **manage DNS A/AAAA records from Home Assistant**, with multiple providers and flexible IP strategies — without juggling one add-on / integration per DNS host.

Built for a real home-lab need: keep DNS in sync when public IP, LAN hosts, or Proxmox guests change, without the usual fragmentation (Cloudflare-only, DuckDNS-only, etc.).

**Repository:** [github.com/bsod79/ha-dns-manager](https://github.com/bsod79/ha-dns-manager)  
**Version:** see `custom_components/dns_manager/manifest.json` (currently **0.8.5**)

---

## Why this exists

Home Assistant has many “update my DNS” pieces, but they are usually:

- tied to **one** provider, or  
- limited to **public WAN IP** only  

DNS Manager separates three ideas:

1. **Where to write DNS** → providers (credentials saved once)  
2. **Where the expected IP comes from** → strategy per record (and per IPv4/IPv6)  
3. **What is managed** → list of records you care about  

So one HA instance can update Cloudflare for `home.example.com` from your WAN IP, DuckDNS for a subdomain from a Proxmox LXC, and another hostname from a `device_tracker` attribute — side by side.

---

## Features

- **Multiple DNS providers** in one integration  
  Cloudflare · DuckDNS · No-IP · DynDNS · dynv6  
- **Per-record IP strategy** (IPv4 and optionally IPv6):  
  Auto (public IP) · From URL · Static · From entity (+ optional attribute) · From Proxmox · Off  
- **IP sources** (optional): save a **Proxmox VE** API token once, then attach LXC/QEMU guests as the expected address  
- **IPv6** optional (global switch; off by default)  
- **Monitor vs write**: poll status without updating DNS until you enable auto sync / buttons / services  
- **Sensors** per record: sync status + current IPv4/IPv6 on DNS  
- **Problem** binary sensor when any record is out of sync  
- **Events** for automations (`record_out_of_sync`, `record_synced`, `sync_error`)  
- **Services** to force update / refresh  
- Config flow + Options UI (no YAML required)  
- Diagnostics download  

---

## Requirements

- Home Assistant **2024.x+** (config flow / entity selectors)  
- HACS (recommended) or manual copy of `custom_components/dns_manager`  
- Provider credentials (API token / username+password depending on provider)  
- For Proxmox: API token with at least **VM.Audit** on the guests you read (and **Sys.Audit** if listing nodes fails)

---

## Installation

### HACS (recommended)

1. HACS → **⋯** → **Custom repositories**  
2. URL: `https://github.com/bsod79/ha-dns-manager`  
3. Category: **Integration**  
4. Download **DNS Manager**, then **restart Home Assistant**  
5. Settings → Devices & services → **Add integration** → **DNS Manager**

### Manual

1. Copy `custom_components/dns_manager` into your HA `custom_components/` folder  
2. Restart Home Assistant  
3. Add the integration as above  

---

## Quick start

1. **Add DNS Manager** (give the instance a name).  
2. **Options → Providers → Add provider** (e.g. Cloudflare zone token, or DuckDNS account token).  
3. Optional: **Options → IP sources → Add IP source** (Proxmox host + token).  
4. **Options → Managed records → Add record**  
   - pick provider + DNS record  
   - choose IPv4 strategy (and IPv6 if enabled)  
5. Optional under **General settings**: Enable IPv6, public IP URLs, `auto_sync`, `sync_on_start`, `write_cooldown`.

### Options menu

```
General settings
Providers         → Add · Remove · Back
IP sources        → Add · Remove · Back
Managed records   → Add · Edit · Remove · Back
```

---

## Mental model

| Piece | Role |
|--------|------|
| **Provider** | How HA authenticates and writes DNS (Cloudflare, DuckDNS, …) |
| **IP source** | Optional helper that only **reads** addresses (today: Proxmox). Not a DNS provider. |
| **Managed record** | One DNS name you monitor/update, with its own IP strategy |

**DuckDNS:** one provider = one account token. Each managed record is a subdomain under that token.

**Proxmox:** save once under IP sources → on a record choose **From Proxmox** → pick node / LXC or QEMU / optional interface (`eth0`, …). Empty interface = first usable IP (skips loopback and link-local). QEMU needs the **guest agent**. Docker IPs *inside* a VM are not visible via Proxmox.

---

## IP strategy (per record)

IPv6 is **off by default**. Enable under **Options → General settings → Enable IPv6**.

| Mode | Expected address |
|------|------------------|
| **Auto** | Instance public IPv4 / IPv6 detection URL |
| **From URL** | Custom HTTP(S) endpoint (plain text or JSON with `ip`) |
| **Static** | Fixed address you type |
| **From entity** | Any HA entity **state**, or an **attribute** (e.g. `ip`, `ip_address`) |
| **From Proxmox** | Guest IP via saved Proxmox IP source |
| **Off** | Do not manage that family (A or AAAA) |

---

## Polling vs DNS writes

- **Polling** compares expected IP vs what the provider currently has.  
- **Writes** happen only if you enable **auto_sync** / **sync_on_start**, press **Update** buttons, or call services.  
- **write_cooldown** limits *automatic* writes per record. Manual updates and services bypass it.

---

## Entities

| Entity | Meaning |
|--------|---------|
| Public IPv4 / IPv6 | Detected WAN address for Auto mode |
| `{record} — {provider}` | `ready` / `not_ready` / `unknown` (in sync?) |
| `{record} IPv4` | Current A value on DNS (`expected_ipv4` in attributes) |
| `{record} IPv6` | Current AAAA when IPv6 is managed |
| Problem | On if any managed record is out of sync |

---

## Events (automations)

| Event | When |
|-------|------|
| `dns_manager.record_out_of_sync` | Record becomes out of sync (edge) |
| `dns_manager.record_synced` | Successful write (`trigger`: `auto` / `manual` / `startup`) |
| `dns_manager.sync_error` | Write failed |

Payload includes `config_entry_id`, `record_uid`, `record_name`, and IP fields where relevant.

---

## Services

| Service | Purpose |
|---------|---------|
| `dns_manager.update_all_records` | Force-update all managed records |
| `dns_manager.update_record` | Force-update one record (optional IP overrides) |
| `dns_manager.refresh_status` | Re-poll status without writing |

---

## Example use cases

- Update Cloudflare when the **home WAN IP** changes  
- Point a hostname at a **Proxmox LXC/VM** LAN IP  
- Sync DNS from a **UniFi / router / tracker** entity attribute without a template sensor  
- Mix providers: Cloudflare for the domain, DuckDNS for a quick public subdomain  

---

## Limitations

- Does **not** create DNS zones or delete remote records on remove (only stops managing them in HA)  
- Proxmox reads **guest NIC** addresses, not Docker container IPs inside a VM  
- Provider coverage is the list above; more can be added later  
- Still evolving — feedback and issues welcome  

---

## Diagnostics & support

- **Settings → Devices & services → DNS Manager → ⋮ → Download diagnostics** (secrets redacted)  
- Issues: [github.com/bsod79/ha-dns-manager/issues](https://github.com/bsod79/ha-dns-manager/issues)  
- Changelog: [CHANGELOG.md](CHANGELOG.md)  

---

## Development

```text
custom_components/dns_manager/   # integration
tests/                           # pytest (needs Home Assistant test deps)
examples/proxmox_ip_webhook.py   # optional standalone Proxmox→IP helper
```

---

## Contributing

Issues and PRs welcome. Please include HA version, provider type, and diagnostics when reporting bugs.

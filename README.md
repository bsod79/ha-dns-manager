# HACS DNS Manager

Home Assistant custom integration to manage DNS records across multiple providers.

## Model

1. **Providers** (saved once) — Cloudflare zone, DuckDNS account token, No-IP, DynDNS, dynv6  
2. **Managed records** — pick a saved provider, then choose IPv4/IPv6 strategy  

Each record can use a different provider. Credentials are not re-entered when adding records.

**DuckDNS:** one provider = one account token. Each managed record is a subdomain under that token.

## IP strategy (per record, per family)

IPv6 is **off by default**. Enable it under **Options → General settings → Enable IPv6** (optionally set the public IPv6 URL). Until then, add/edit record only shows IPv4 strategy.

| Mode | IPv4 (A) | IPv6 (AAAA) — only if enabled |
|------|----------|-------------------------------|
| **Auto** | Instance public IPv4 URL | Instance public IPv6 URL |
| **From URL** | Custom URL | Custom URL |
| **Static** | Fixed IPv4 | Fixed IPv6 |
| **From entity** | Entity state (sensor / input_text / text) | Entity state |
| **Off** | Do not manage | Do not manage |

Default after migration: IPv4 Auto, IPv6 Off (and global Enable IPv6 off, unless you already had an IPv6 URL or managed AAAA).

## Setup

1. Add **DNS Manager** (name the instance).
2. **Options → Providers → Add provider**.
3. **Options → Managed records → Add record** → select provider → (Cloudflare: pick record / DuckDNS: enter subdomain) → IP strategy.
4. Optional under **Options → General settings**: **Enable IPv6**, IPv6 detection URL, **auto_sync**, **sync_on_start**, **write_cooldown**.

Options menu structure:

```
General settings
Providers         → Add provider · Remove provider · Back
Managed records   → Add record · Edit record · Remove record · Back
```

## Polling vs updates

- **Polling** checks expected vs DNS for each enabled IP family.
- **Writes** only with **auto_sync**, **sync_on_start**, Update buttons, or services.
- **write_cooldown** limits automatic writes per record (auto_sync / sync_on_start). Manual Update buttons and services bypass it.

## Events (for automations)

| Event | When |
|-------|------|
| `dns_manager.record_out_of_sync` | Record becomes out of sync (edge, not every poll) |
| `dns_manager.record_synced` | Successful DNS write (`trigger`: `auto` / `manual` / `startup`) |
| `dns_manager.sync_error` | Write failed |

Payload includes `config_entry_id`, `record_uid`, `record_name`, and IP fields where relevant.

## Problem binary sensor

One **Problem** binary sensor per instance: on when any managed record is out of sync. Attribute `out_of_sync_records` lists names.

## Diagnostics

**Settings → Devices & services → DNS Manager → ⋮ → Download diagnostics**

## Development

- Integration: `custom_components/dns_manager/`
- Tests: `tests/`

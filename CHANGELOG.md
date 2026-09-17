# Changelog

## 0.5.2

- Options UI restructured for consistency: `General settings` / `Providers` / `Managed records`, each sub-menu with Add/Edit/Remove and a Back entry.
- Uniform step titles (`Add provider — …`, `Add record — …`, `Edit record — …`) and contextual descriptions (selected provider, record, IP strategy, counts).
- `translations/en.json` fully synced with `strings.json` (previously most option steps had no translations); `it.json` completed.
- Error strings added under `options.error`.

## 0.5.1

- Removed unused provider name field; all option forms use sections.

## 0.5.0

- Saved providers: configure each provider once, attach records to it.

## 0.4.0

- Per-record IP source: Auto, From URL, Static.

## 0.3.0

- Multi-provider support: Cloudflare, DuckDNS, No-IP, DynDNS, dynv6.

## 0.2.0

- Diagnostics download with activity log; `auto_sync` option.

## 0.1.0

- Initial scaffold.

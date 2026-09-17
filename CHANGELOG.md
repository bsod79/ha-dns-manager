# Changelog

## 0.6.1

- Fix Italian translations: remove UTF-8 BOM that prevented HA from parsing `it.json`.

## 0.6.0

- DuckDNS account model: provider stores only the account token; each managed record is a subdomain (legacy subdomain+token providers are migrated automatically).
- IPv6 support: per-record IPv4/IPv6 strategies (Auto / From URL / Static / Off), optional global IPv6 detection URL, A+AAAA updates (Cloudflare, DuckDNS, dynv6).
- Public IPv6 sensor; diagnostics and services accept IPv6 overrides.

## 0.5.4

- Fix DuckDNS credential validation: the API returns plain text `OK`/`KO`, not JSON — this was causing "Cannot connect" when adding a DuckDNS provider.
- Fix translation `UNCLOSED_TAG` on the DuckDNS add-provider step (angle brackets around `<subdomain>` were parsed as HTML).

## 0.5.3

- Fix duplicate providers: adding a provider for a zone/hostname that already exists now updates its credentials in place instead of creating a second entry.
- Existing duplicates (e.g. legacy-migrated Cloudflare zone + manually re-added one) are merged automatically on load; records are re-linked to the surviving provider.
- Provider labels no longer repeat the zone/hostname (`Cloudflare — example.com` instead of `Cloudflare — example.com (Cloudflare: example.com)`).

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

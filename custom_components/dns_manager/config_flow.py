"""Config flow for DNS Manager."""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    AUTH_MODE_GLOBAL_KEY,
    AUTH_MODE_TOKEN,
    CONF_API_EMAIL,
    CONF_API_KEY,
    CONF_API_TOKEN,
    CONF_AUTH_MODE,
    CONF_AUTO_SYNC,
    CONF_ENABLED,
    CONF_HOSTNAME,
    CONF_IP_DETECTION_URL,
    CONF_IP_ENTITY,
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_DETECTION_URL,
    CONF_IPV6_ENABLED,
    CONF_IPV6_ENTITY,
    CONF_IPV6_MODE,
    CONF_IPV6_PROXMOX_IFACE,
    CONF_IPV6_PROXMOX_KIND,
    CONF_IPV6_PROXMOX_NODE,
    CONF_IPV6_PROXMOX_SOURCE_ID,
    CONF_IPV6_PROXMOX_VMID,
    CONF_IPV6_URL,
    CONF_PASSWORD,
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_ID,
    CONF_PROVIDER_TYPE,
    CONF_PROXMOX_IFACE,
    CONF_PROXMOX_KIND,
    CONF_PROXMOX_NODE,
    CONF_PROXMOX_SOURCE_ID,
    CONF_PROXMOX_VMID,
    CONF_PVE_DEFAULT_NODE,
    CONF_PVE_HOST,
    CONF_PVE_TOKEN_ID,
    CONF_PVE_TOKEN_SECRET,
    CONF_PVE_VERIFY_SSL,
    CONF_RECORD_ID,
    CONF_RECORD_ID_AAAA,
    CONF_RECORD_NAME,
    CONF_RECORD_TYPE,
    CONF_RECORD_UID,
    CONF_SCAN_INTERVAL,
    CONF_SOURCE_CONFIG,
    CONF_SOURCE_ID,
    CONF_SOURCE_TYPE,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    CONF_SUBDOMAIN,
    CONF_SYNC_ON_START,
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_WRITE_COOLDOWN,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DEFAULT_AUTO_SYNC,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_IPV6_DETECTION_URL,
    DEFAULT_IPV6_ENABLED,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SYNC_ON_START,
    DEFAULT_WRITE_COOLDOWN,
    ENTITY_IP_DOMAINS,
    IP_MODE_AUTO,
    IP_MODE_ENTITY,
    IP_MODE_OFF,
    IP_MODE_PROXMOX,
    IP_MODE_STATIC,
    IP_MODE_URL,
    IP_SOURCE_LABELS,
    IP_SOURCE_PROXMOX,
    IPV4_MODE_LABELS,
    IPV6_MODE_LABELS,
    PROXMOX_KIND_LABELS,
    PROXMOX_KIND_LXC,
    PROVIDER_CLOUDFLARE,
    PROVIDER_DUCKDNS,
    PROVIDER_DYNDNS,
    PROVIDER_DYNV6,
    PROVIDER_LABELS,
    PROVIDER_NOIP,
)
from .exceptions import ProviderAPIError, ProviderAuthError
from .ip_sources.proxmox import proxmox_client_from_config
from .options_model import (
    build_options_payload,
    ddns_hostname_from_provider,
    default_options,
    default_proxmox_source_name,
    find_ip_source,
    find_provider_in_list,
    get_ip_sources,
    infer_ipv6_enabled,
    ip_source_display_label,
    is_account_provider,
    is_zone_provider,
    migrate_options,
    provider_display_label,
    provider_uid,
    source_uid,
    upsert_ip_source,
    upsert_provider,
)
from .providers import get_provider
from .providers.base import DnsRecord, ProviderConfig
from .providers.ddns import duckdns_hostname, duckdns_subdomain
from .providers.duckdns import DuckDNSProvider
from .providers.record_context import normalize_record, record_display_label, record_uid


def _validate_ipv4(value: str) -> str:
    return str(ipaddress.IPv4Address(value))


def _validate_ipv6(value: str) -> str:
    return str(ipaddress.IPv6Address(value))


def _section(schema: vol.Schema, *, collapsed: bool = False):
    return section(schema, {"collapsed": collapsed})


def _sectioned(key: str, fields: dict[Any, Any]) -> vol.Schema:
    return vol.Schema({vol.Required(key): _section(vol.Schema(fields), collapsed=False)})


def _from_section(user_input: dict[str, Any], key: str) -> dict[str, Any]:
    nested = user_input.get(key)
    if isinstance(nested, dict):
        return nested
    return user_input


def _entity_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=list(ENTITY_IP_DOMAINS))
    )


def _needs_ip_details(ipv4_mode: str, ipv6_mode: str) -> bool:
    detail_modes = (IP_MODE_STATIC, IP_MODE_URL, IP_MODE_ENTITY)
    return ipv4_mode in detail_modes or ipv6_mode in detail_modes


def _needs_proxmox(ipv4_mode: str, ipv6_mode: str) -> bool:
    return ipv4_mode == IP_MODE_PROXMOX or ipv6_mode == IP_MODE_PROXMOX


def _empty_proxmox_fields() -> dict[str, Any]:
    return {
        CONF_PROXMOX_SOURCE_ID: None,
        CONF_PROXMOX_KIND: None,
        CONF_PROXMOX_NODE: None,
        CONF_PROXMOX_VMID: None,
        CONF_PROXMOX_IFACE: None,
        CONF_IPV6_PROXMOX_SOURCE_ID: None,
        CONF_IPV6_PROXMOX_KIND: None,
        CONF_IPV6_PROXMOX_NODE: None,
        CONF_IPV6_PROXMOX_VMID: None,
        CONF_IPV6_PROXMOX_IFACE: None,
    }


def _apply_proxmox_target(
    *,
    ipv4_mode: str,
    ipv6_mode: str,
    target: dict[str, Any] | None,
) -> dict[str, Any]:
    fields = _empty_proxmox_fields()
    if not target:
        return fields
    if ipv4_mode == IP_MODE_PROXMOX:
        fields[CONF_PROXMOX_SOURCE_ID] = target.get(CONF_PROXMOX_SOURCE_ID)
        fields[CONF_PROXMOX_KIND] = target.get(CONF_PROXMOX_KIND)
        fields[CONF_PROXMOX_NODE] = target.get(CONF_PROXMOX_NODE)
        fields[CONF_PROXMOX_VMID] = target.get(CONF_PROXMOX_VMID)
        fields[CONF_PROXMOX_IFACE] = target.get(CONF_PROXMOX_IFACE)
    if ipv6_mode == IP_MODE_PROXMOX:
        fields[CONF_IPV6_PROXMOX_SOURCE_ID] = target.get(CONF_PROXMOX_SOURCE_ID)
        fields[CONF_IPV6_PROXMOX_KIND] = target.get(CONF_PROXMOX_KIND)
        fields[CONF_IPV6_PROXMOX_NODE] = target.get(CONF_PROXMOX_NODE)
        fields[CONF_IPV6_PROXMOX_VMID] = target.get(CONF_PROXMOX_VMID)
        fields[CONF_IPV6_PROXMOX_IFACE] = target.get(CONF_PROXMOX_IFACE)
    return fields

class DnsManagerConfigFlow(config_entries.ConfigFlow, domain="dns_manager"):
    VERSION = 3

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            data = _from_section(user_input, "setup")
            title = str(data.get("instance_name", "DNS Manager")).strip() or "DNS Manager"
            return self.async_create_entry(title=title, data={}, options=default_options())

        return self.async_show_form(
            step_id="user",
            data_schema=_sectioned(
                "setup",
                {vol.Optional("instance_name", default="DNS Manager"): str},
            ),
        )

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return DnsManagerOptionsFlow()


class DnsManagerOptionsFlow(config_entries.OptionsFlow):
    """Options: manage saved providers, then attach records to them."""

    def __init__(self) -> None:
        self._scan_interval = DEFAULT_SCAN_INTERVAL
        self._ip_url = DEFAULT_IP_DETECTION_URL
        self._ipv6_enabled = DEFAULT_IPV6_ENABLED
        self._ipv6_url = DEFAULT_IPV6_DETECTION_URL
        self._auto_sync = DEFAULT_AUTO_SYNC
        self._sync_on_start = DEFAULT_SYNC_ON_START
        self._write_cooldown = DEFAULT_WRITE_COOLDOWN
        self._providers: list[dict[str, Any]] = []
        self._ip_sources: list[dict[str, Any]] = []
        self._records: list[dict[str, Any]] = []

        self._adding_provider_type: str | None = None
        self._adding_provider_config: dict[str, Any] = {}
        self._cf_client = None
        self._zones: list[dict] = []

        self._selected_provider_id: str | None = None
        self._adding_record_id: str = ""
        self._adding_record_id_aaaa: str = ""
        self._adding_record_name: str = ""
        self._adding_record_type: str = "A"
        self._cf_records: list[DnsRecord] = []
        self._ip_mode_choice: str = IP_MODE_AUTO
        self._ipv6_mode_choice: str = IP_MODE_OFF
        self._editing_record_uid: str | None = None
        self._edit_enabled: bool = True
        self._proxmox_target: dict[str, Any] | None = None
        self._pve_source_id: str | None = None
        self._pve_kind: str = PROXMOX_KIND_LXC
        self._pve_node: str = ""
        self._pve_nodes: list[str] = []
        self._pve_guests: list[dict[str, str]] = []
        self._flow_context: str = "add"  # add | edit

    def _load_state(self) -> None:
        self._scan_interval = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._ip_url = str(
            self.config_entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
        )
        self._ipv6_enabled = infer_ipv6_enabled(self.config_entry.options)
        self._ipv6_url = str(
            self.config_entry.options.get(CONF_IPV6_DETECTION_URL, DEFAULT_IPV6_DETECTION_URL) or ""
        )
        self._auto_sync = bool(self.config_entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC))
        self._sync_on_start = bool(
            self.config_entry.options.get(CONF_SYNC_ON_START, DEFAULT_SYNC_ON_START)
        )
        self._write_cooldown = int(
            self.config_entry.options.get(CONF_WRITE_COOLDOWN, DEFAULT_WRITE_COOLDOWN)
        )
        providers, records, _ = migrate_options(self.config_entry)
        self._providers = providers
        self._records = records
        self._ip_sources = get_ip_sources(self.config_entry)

    def _payload(self) -> dict[str, Any]:
        return build_options_payload(
            scan_interval=self._scan_interval,
            ip_detection_url=self._ip_url,
            ipv6_enabled=self._ipv6_enabled,
            ipv6_detection_url=self._ipv6_url,
            auto_sync=self._auto_sync,
            sync_on_start=self._sync_on_start,
            write_cooldown=self._write_cooldown,
            providers=self._providers,
            ip_sources=self._ip_sources,
            records=self._records,
        )

    def _save(self) -> FlowResult:
        return self.async_create_entry(title="", data=self._payload())

    def _record_already_managed(self, name: str, provider_id: str) -> bool:
        key = name.lower()
        for rec in self._records:
            if str(rec.get(CONF_RECORD_NAME, "")).lower() != key:
                continue
            if str(rec.get(CONF_PROVIDER_ID, "")) == provider_id:
                return True
        return False

    def _provider_map(self) -> dict[str, str]:
        return {provider_uid(p): provider_display_label(p) for p in self._providers}

    def _record_map(self) -> dict[str, str]:
        return {
            record_uid(r): record_display_label(normalize_record(r, self.config_entry), self.config_entry)
            for r in self._records
        }

    def _counts(self) -> dict[str, str]:
        return {
            "providers_count": str(len(self._providers)),
            "ip_sources_count": str(len(self._ip_sources)),
            "records_count": str(len(self._records)),
        }

    def _ip_source_map(self) -> dict[str, str]:
        return {source_uid(s): ip_source_display_label(s) for s in self._ip_sources}

    def _selected_provider_label(self) -> str:
        prov = find_provider_in_list(self._providers, str(self._selected_provider_id))
        return provider_display_label(prov) if prov else ""

    def _adding_record_label(self) -> str:
        return f"{self._adding_record_name} ({self._adding_record_type})"

    def _editing_record_label(self) -> str:
        rec = next((r for r in self._records if record_uid(r) == str(self._editing_record_uid)), None)
        if rec is None:
            return ""
        return record_display_label(normalize_record(rec, self.config_entry), self.config_entry)

    def _pve_client_for_source(self, source_id: str):
        src = find_ip_source(self._ip_sources, source_id)
        if src is None:
            raise ProviderAPIError("IP source not found")
        session = async_get_clientsession(self.hass)
        return proxmox_client_from_config(session, dict(src.get(CONF_SOURCE_CONFIG) or {}))

    # --- Menus ---

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._load_state()
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "providers_menu", "ip_sources_menu", "records_menu"],
            description_placeholders=self._counts(),
        )

    async def async_step_providers_menu(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="providers_menu",
            menu_options=["add_provider_type", "remove_provider_select", "init"],
            description_placeholders=self._counts(),
        )

    async def async_step_ip_sources_menu(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="ip_sources_menu",
            menu_options=["add_ip_source_type", "remove_ip_source_select", "init"],
            description_placeholders=self._counts(),
        )

    async def async_step_records_menu(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="records_menu",
            menu_options=[
                "add_record_select_provider",
                "edit_record_select",
                "remove_record_select",
                "init",
            ],
            description_placeholders=self._counts(),
        )

    # --- General ---

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            polling = _from_section(user_input, "polling")
            self._scan_interval = int(polling[CONF_SCAN_INTERVAL])
            self._ip_url = str(polling[CONF_IP_DETECTION_URL])
            self._ipv6_enabled = bool(polling.get(CONF_IPV6_ENABLED, DEFAULT_IPV6_ENABLED))
            self._ipv6_url = str(polling.get(CONF_IPV6_DETECTION_URL, "") or "").strip()
            self._auto_sync = bool(polling.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC))
            self._sync_on_start = bool(polling.get(CONF_SYNC_ON_START, DEFAULT_SYNC_ON_START))
            self._write_cooldown = max(
                0, int(polling.get(CONF_WRITE_COOLDOWN, DEFAULT_WRITE_COOLDOWN))
            )
            return self._save()

        return self.async_show_form(
            step_id="general",
            data_schema=_sectioned(
                "polling",
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.Coerce(int),
                    vol.Required(CONF_IP_DETECTION_URL, default=self._ip_url): str,
                    vol.Optional(CONF_IPV6_ENABLED, default=self._ipv6_enabled): bool,
                    vol.Optional(CONF_IPV6_DETECTION_URL, default=self._ipv6_url): str,
                    vol.Optional(CONF_AUTO_SYNC, default=self._auto_sync): bool,
                    vol.Optional(CONF_SYNC_ON_START, default=self._sync_on_start): bool,
                    vol.Optional(
                        CONF_WRITE_COOLDOWN, default=self._write_cooldown
                    ): vol.Coerce(int),
                },
            ),
        )

    # --- Providers ---

    async def async_step_add_provider_type(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            nested = _from_section(user_input, "provider")
            self._adding_provider_type = str(nested[CONF_PROVIDER_TYPE])
            if self._adding_provider_type == PROVIDER_CLOUDFLARE:
                return await self.async_step_add_provider_cloudflare_credentials()
            if self._adding_provider_type == PROVIDER_DUCKDNS:
                return await self.async_step_add_provider_duckdns()
            if self._adding_provider_type in (PROVIDER_NOIP, PROVIDER_DYNDNS):
                return await self.async_step_add_provider_hostname_auth()
            return await self.async_step_add_provider_dynv6()

        return self.async_show_form(
            step_id="add_provider_type",
            data_schema=_sectioned(
                "provider",
                {vol.Required(CONF_PROVIDER_TYPE): vol.In(PROVIDER_LABELS)},
            ),
        )

    async def async_step_add_provider_cloudflare_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                auth = _from_section(user_input, "auth")
                auth_mode = auth[CONF_AUTH_MODE]
                credentials: dict[str, Any] = {CONF_AUTH_MODE: auth_mode}
                if auth_mode == AUTH_MODE_TOKEN:
                    credentials[CONF_API_TOKEN] = auth[CONF_API_TOKEN]
                else:
                    credentials[CONF_API_EMAIL] = auth[CONF_API_EMAIL]
                    credentials[CONF_API_KEY] = auth[CONF_API_KEY]
                self._adding_provider_config = credentials
                self._cf_client = get_provider(
                    ProviderConfig(provider_type=PROVIDER_CLOUDFLARE, credentials=credentials)
                )
                await self._cf_client.validate_credentials()
                return await self.async_step_add_provider_cloudflare_zone()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        auth_modes = {AUTH_MODE_TOKEN: "API Token", AUTH_MODE_GLOBAL_KEY: "Global API Key"}
        auth_mode = AUTH_MODE_TOKEN
        if user_input:
            auth = _from_section(user_input, "auth")
            auth_mode = auth.get(CONF_AUTH_MODE, AUTH_MODE_TOKEN)

        fields: dict[Any, Any] = {vol.Required(CONF_AUTH_MODE, default=auth_mode): vol.In(auth_modes)}
        if auth_mode == AUTH_MODE_TOKEN:
            fields[vol.Required(CONF_API_TOKEN)] = str
        else:
            fields[vol.Required(CONF_API_EMAIL)] = str
            fields[vol.Required(CONF_API_KEY)] = str

        return self.async_show_form(
            step_id="add_provider_cloudflare_credentials",
            data_schema=_sectioned("auth", fields),
            errors=errors,
        )

    async def async_step_add_provider_cloudflare_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            zone = _from_section(user_input, "zone")
            zone_id = str(zone[CONF_ZONE_ID])
            zone_name = next((z["name"] for z in self._zones if z["id"] == zone_id), zone_id)
            self._adding_provider_config = {
                **self._adding_provider_config,
                CONF_ZONE_ID: zone_id,
                CONF_ZONE_NAME: zone_name,
            }
            upsert_provider(
                self._providers,
                provider_type=PROVIDER_CLOUDFLARE,
                name=f"Cloudflare — {zone_name}",
                config=self._adding_provider_config,
            )
            return self._save()

        try:
            self._zones = await self._cf_client.list_zones()
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        zones_map = {z["id"]: z["name"] for z in self._zones}
        return self.async_show_form(
            step_id="add_provider_cloudflare_zone",
            data_schema=_sectioned("zone", {vol.Required(CONF_ZONE_ID): vol.In(zones_map)}),
            errors=errors,
            description_placeholders={"zones_count": str(len(self._zones))},
        )

    async def async_step_add_provider_duckdns(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _from_section(user_input, "duckdns")
                token = str(data[CONF_TOKEN]).strip()
                verify_sub = duckdns_subdomain(str(data.get(CONF_SUBDOMAIN) or ""))
                provider = DuckDNSProvider(
                    ProviderConfig(
                        provider_type=PROVIDER_DUCKDNS,
                        credentials={CONF_TOKEN: token},
                    )
                )
                await provider.validate_credentials()
                if verify_sub:
                    await provider.validate_with_subdomain(verify_sub)
                upsert_provider(
                    self._providers,
                    provider_type=PROVIDER_DUCKDNS,
                    name="DuckDNS",
                    config={CONF_TOKEN: token},
                )
                return self._save()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="add_provider_duckdns",
            data_schema=_sectioned(
                "duckdns",
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Optional(CONF_SUBDOMAIN): str,
                },
            ),
            errors=errors,
        )

    async def async_step_add_provider_hostname_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        provider_type = str(self._adding_provider_type)
        label = PROVIDER_LABELS.get(provider_type, provider_type)
        if user_input is not None:
            try:
                data = _from_section(user_input, "account")
                username = str(data[CONF_USERNAME]).strip()
                password = str(data[CONF_PASSWORD])
                verify_host = str(data.get(CONF_HOSTNAME) or "").strip().lower()
                provider = get_provider(
                    ProviderConfig(
                        provider_type=provider_type,
                        credentials={CONF_USERNAME: username, CONF_PASSWORD: password},
                    )
                )
                await provider.validate_credentials()
                if verify_host and hasattr(provider, "validate_with_hostname"):
                    await provider.validate_with_hostname(verify_host)
                upsert_provider(
                    self._providers,
                    provider_type=provider_type,
                    name=f"{label} — {username}",
                    config={CONF_USERNAME: username, CONF_PASSWORD: password},
                )
                return self._save()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="add_provider_hostname_auth",
            data_schema=_sectioned(
                "account",
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_HOSTNAME): str,
                },
            ),
            errors=errors,
            description_placeholders={"provider": label},
        )

    async def async_step_add_provider_dynv6(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _from_section(user_input, "dynv6")
                token = str(data[CONF_TOKEN]).strip()
                verify_host = str(data.get(CONF_HOSTNAME) or "").strip().lower()
                provider = get_provider(
                    ProviderConfig(
                        provider_type=PROVIDER_DYNV6,
                        credentials={CONF_TOKEN: token},
                    )
                )
                await provider.validate_credentials()
                if verify_host and hasattr(provider, "validate_with_hostname"):
                    await provider.validate_with_hostname(verify_host)
                upsert_provider(
                    self._providers,
                    provider_type=PROVIDER_DYNV6,
                    name="dynv6",
                    config={CONF_TOKEN: token},
                )
                return self._save()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="add_provider_dynv6",
            data_schema=_sectioned(
                "dynv6",
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Optional(CONF_HOSTNAME): str,
                },
            ),
            errors=errors,
        )

    def _provider_select_schema(self) -> vol.Schema:
        return _sectioned("selection", {vol.Required(CONF_PROVIDER_ID): vol.In(self._provider_map())})

    async def async_step_remove_provider_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._providers:
            return self.async_abort(reason="no_providers")

        if user_input is not None:
            pid = str(_from_section(user_input, "selection")[CONF_PROVIDER_ID])
            if any(str(r.get(CONF_PROVIDER_ID)) == pid for r in self._records):
                return self.async_abort(reason="provider_in_use")
            self._providers = [p for p in self._providers if provider_uid(p) != pid]
            return self._save()

        return self.async_show_form(
            step_id="remove_provider_select",
            data_schema=self._provider_select_schema(),
            description_placeholders=self._counts(),
        )

    # --- IP sources (Proxmox, …) ---

    async def async_step_add_ip_source_type(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            stype = str(_from_section(user_input, "source")[CONF_SOURCE_TYPE])
            if stype == IP_SOURCE_PROXMOX:
                return await self.async_step_add_ip_source_proxmox()
            return self.async_abort(reason="unknown")

        return self.async_show_form(
            step_id="add_ip_source_type",
            data_schema=_sectioned(
                "source",
                {vol.Required(CONF_SOURCE_TYPE): vol.In(IP_SOURCE_LABELS)},
            ),
        )

    async def async_step_add_ip_source_proxmox(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _from_section(user_input, "proxmox")
                host = str(data[CONF_PVE_HOST]).strip()
                if not host.startswith(("http://", "https://")):
                    host = f"https://{host}"
                config = {
                    CONF_PVE_HOST: host,
                    CONF_PVE_TOKEN_ID: str(data[CONF_PVE_TOKEN_ID]).strip(),
                    CONF_PVE_TOKEN_SECRET: str(data[CONF_PVE_TOKEN_SECRET]).strip(),
                    CONF_PVE_VERIFY_SSL: bool(data.get(CONF_PVE_VERIFY_SSL, True)),
                    CONF_PVE_DEFAULT_NODE: str(data.get(CONF_PVE_DEFAULT_NODE) or "").strip() or None,
                }
                session = async_get_clientsession(self.hass)
                client = proxmox_client_from_config(session, config)
                await client.validate_credentials()
                upsert_ip_source(
                    self._ip_sources,
                    source_type=IP_SOURCE_PROXMOX,
                    name=default_proxmox_source_name(config),
                    config=config,
                )
                return self._save()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="add_ip_source_proxmox",
            data_schema=_sectioned(
                "proxmox",
                {
                    vol.Required(CONF_PVE_HOST): str,
                    vol.Required(CONF_PVE_TOKEN_ID): str,
                    vol.Required(CONF_PVE_TOKEN_SECRET): str,
                    vol.Optional(CONF_PVE_VERIFY_SSL, default=True): bool,
                    vol.Optional(CONF_PVE_DEFAULT_NODE, default=""): str,
                },
            ),
            errors=errors,
        )

    async def async_step_remove_ip_source_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._ip_sources:
            return self.async_abort(reason="no_ip_sources")

        if user_input is not None:
            sid = str(_from_section(user_input, "selection")[CONF_SOURCE_ID])
            in_use = any(
                str(r.get(CONF_PROXMOX_SOURCE_ID) or "") == sid
                or str(r.get(CONF_IPV6_PROXMOX_SOURCE_ID) or "") == sid
                for r in self._records
            )
            if in_use:
                return self.async_abort(reason="ip_source_in_use")
            self._ip_sources = [s for s in self._ip_sources if source_uid(s) != sid]
            return self._save()

        return self.async_show_form(
            step_id="remove_ip_source_select",
            data_schema=_sectioned(
                "selection", {vol.Required(CONF_SOURCE_ID): vol.In(self._ip_source_map())}
            ),
            description_placeholders=self._counts(),
        )

    # --- Records ---

    async def async_step_add_record_select_provider(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not self._providers:
            return self.async_abort(reason="no_providers")

        if user_input is not None:
            self._selected_provider_id = str(_from_section(user_input, "selection")[CONF_PROVIDER_ID])
            prov = find_provider_in_list(self._providers, self._selected_provider_id)
            if prov is None:
                return self.async_abort(reason="no_providers")
            ptype = str(prov[CONF_PROVIDER_TYPE])
            if is_zone_provider(ptype):
                return await self.async_step_add_record_cloudflare_select()
            if ptype == PROVIDER_DUCKDNS:
                return await self.async_step_add_record_duckdns_subdomain()
            if is_account_provider(ptype):
                return await self.async_step_add_record_hostname()
            hostname = ddns_hostname_from_provider(prov)
            if not hostname:
                return self.async_abort(reason="no_providers")
            if self._record_already_managed(hostname, self._selected_provider_id):
                return self.async_show_form(
                    step_id="add_record_select_provider",
                    data_schema=self._provider_select_schema(),
                    errors={"base": "record_already_managed"},
                    description_placeholders=self._counts(),
                )
            self._adding_record_id = hostname
            self._adding_record_id_aaaa = ""
            self._adding_record_name = hostname
            self._adding_record_type = "A"
            return await self.async_step_add_record_ip_mode()

        return self.async_show_form(
            step_id="add_record_select_provider",
            data_schema=self._provider_select_schema(),
            description_placeholders=self._counts(),
        )

    async def async_step_add_record_duckdns_subdomain(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        prov = find_provider_in_list(self._providers, str(self._selected_provider_id))
        if prov is None:
            return self.async_abort(reason="no_providers")

        if user_input is not None:
            try:
                data = _from_section(user_input, "subdomain")
                sub = duckdns_subdomain(str(data[CONF_SUBDOMAIN]))
                if not sub:
                    raise ValueError("empty")
                host = duckdns_hostname(sub)
                if self._record_already_managed(host, str(self._selected_provider_id)):
                    errors["base"] = "record_already_managed"
                else:
                    cfg = dict(prov.get(CONF_PROVIDER_CONFIG) or {})
                    client = DuckDNSProvider(
                        ProviderConfig(provider_type=PROVIDER_DUCKDNS, credentials=cfg)
                    )
                    await client.validate_with_subdomain(sub)
                    self._adding_record_id = sub
                    self._adding_record_id_aaaa = ""
                    self._adding_record_name = host
                    self._adding_record_type = "A"
                    return await self.async_step_add_record_ip_mode()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        return self.async_show_form(
            step_id="add_record_duckdns_subdomain",
            data_schema=_sectioned(
                "subdomain",
                {vol.Required(CONF_SUBDOMAIN): str},
            ),
            errors=errors,
            description_placeholders={"provider": self._selected_provider_label()},
        )

    async def async_step_add_record_hostname(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a hostname for No-IP / DynDNS / dynv6 account providers."""
        errors: dict[str, str] = {}
        prov = find_provider_in_list(self._providers, str(self._selected_provider_id))
        if prov is None:
            return self.async_abort(reason="no_providers")
        ptype = str(prov[CONF_PROVIDER_TYPE])
        label = PROVIDER_LABELS.get(ptype, ptype)

        if user_input is not None:
            try:
                data = _from_section(user_input, "hostname")
                host = str(data[CONF_HOSTNAME]).strip().lower()
                if not host:
                    raise ValueError("empty")
                if self._record_already_managed(host, str(self._selected_provider_id)):
                    errors["base"] = "record_already_managed"
                else:
                    cfg = dict(prov.get(CONF_PROVIDER_CONFIG) or {})
                    client = get_provider(ProviderConfig(provider_type=ptype, credentials=cfg))
                    if hasattr(client, "validate_with_hostname"):
                        await client.validate_with_hostname(host)
                    self._adding_record_id = host
                    self._adding_record_id_aaaa = ""
                    self._adding_record_name = host
                    self._adding_record_type = "A"
                    return await self.async_step_add_record_ip_mode()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        return self.async_show_form(
            step_id="add_record_hostname",
            data_schema=_sectioned(
                "hostname",
                {vol.Required(CONF_HOSTNAME): str},
            ),
            errors=errors,
            description_placeholders={
                "provider": self._selected_provider_label() or label,
            },
        )

    async def async_step_add_record_cloudflare_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        prov = find_provider_in_list(self._providers, str(self._selected_provider_id))
        if prov is None:
            return self.async_abort(reason="no_providers")
        cfg = dict(prov.get(CONF_PROVIDER_CONFIG) or {})
        zone_id = str(cfg.get(CONF_ZONE_ID, ""))
        client = get_provider(
            ProviderConfig(provider_type=PROVIDER_CLOUDFLARE, credentials=cfg)
        )

        if user_input is not None:
            cf_record_id = str(_from_section(user_input, "record")[CONF_RECORD_ID])
            record = next((r for r in self._cf_records if r.record_id == cf_record_id), None)
            name = record.name if record else cf_record_id
            if self._record_already_managed(name, str(self._selected_provider_id)):
                errors["base"] = "record_already_managed"
            else:
                self._adding_record_id = cf_record_id if (record and record.record_type == "A") else ""
                self._adding_record_id_aaaa = (
                    cf_record_id if (record and record.record_type == "AAAA") else ""
                )
                # If UI picked A, try to find sibling AAAA id later at runtime; store name
                if record and record.record_type == "A":
                    self._adding_record_id = record.record_id
                    self._adding_record_id_aaaa = ""
                self._adding_record_name = name
                self._adding_record_type = "A"
                return await self.async_step_add_record_ip_mode()

        try:
            self._cf_records = await client.list_a_records(zone_id)
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        rec_map = {r.record_id: f"{r.name} ({r.record_type})" for r in self._cf_records}
        return self.async_show_form(
            step_id="add_record_cloudflare_select",
            data_schema=_sectioned("record", {vol.Required(CONF_RECORD_ID): vol.In(rec_map)}),
            errors=errors,
            description_placeholders={"provider": self._selected_provider_label()},
        )

    async def async_step_add_record_ip_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._flow_context = "add"
        if user_input is not None:
            data = _from_section(user_input, "strategy")
            self._ip_mode_choice = str(data[CONF_IP_MODE])
            self._ipv6_mode_choice = (
                str(data.get(CONF_IPV6_MODE, IP_MODE_OFF)) if self._ipv6_enabled else IP_MODE_OFF
            )
            if self._ip_mode_choice == IP_MODE_OFF and self._ipv6_mode_choice == IP_MODE_OFF:
                return self.async_show_form(
                    step_id="add_record_ip_mode",
                    data_schema=self._ip_strategy_schema(
                        self._ip_mode_choice, self._ipv6_mode_choice
                    ),
                    errors={"base": "invalid_ip"},
                    description_placeholders={
                        "record": self._adding_record_label(),
                        "provider": self._selected_provider_label(),
                    },
                )
            if _needs_proxmox(self._ip_mode_choice, self._ipv6_mode_choice):
                if not self._ip_sources:
                    return self.async_abort(reason="no_ip_sources")
                return await self.async_step_add_record_proxmox_source()
            if _needs_ip_details(self._ip_mode_choice, self._ipv6_mode_choice):
                return await self.async_step_add_record_ip_details()
            return self._finish_add_record(
                self._ip_mode_choice, None, None, None, self._ipv6_mode_choice, None, None, None
            )

        return self.async_show_form(
            step_id="add_record_ip_mode",
            data_schema=self._ip_strategy_schema(IP_MODE_AUTO, IP_MODE_OFF),
            description_placeholders={
                "record": self._adding_record_label(),
                "provider": self._selected_provider_label(),
            },
        )

    async def async_step_add_record_proxmox_source(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._pve_source_id = str(_from_section(user_input, "proxmox")[CONF_SOURCE_ID])
            self._pve_nodes = []
            self._pve_guests = []
            return await self.async_step_add_record_proxmox_node()

        return self.async_show_form(
            step_id="add_record_proxmox_source",
            data_schema=_sectioned(
                "proxmox",
                {vol.Required(CONF_SOURCE_ID): vol.In(self._ip_source_map())},
            ),
            description_placeholders={
                "record": self._adding_record_label()
                if self._flow_context == "add"
                else self._editing_record_label(),
            },
        )

    async def async_step_add_record_proxmox_node(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        source_id = str(self._pve_source_id or "")

        if user_input is not None:
            data = _from_section(user_input, "node")
            self._pve_kind = str(data[CONF_PROXMOX_KIND])
            self._pve_node = str(data[CONF_PROXMOX_NODE])
            self._pve_guests = []
            return await self.async_step_add_record_proxmox_guest()

        try:
            client = self._pve_client_for_source(source_id)
            self._pve_nodes = await client.list_nodes()
            src = find_ip_source(self._ip_sources, source_id)
            cfg = (src or {}).get(CONF_SOURCE_CONFIG) or {}
            default_node = str(cfg.get(CONF_PVE_DEFAULT_NODE) or "")
            if default_node and default_node in self._pve_nodes:
                self._pve_node = default_node
            elif self._pve_nodes and not self._pve_node:
                self._pve_node = self._pve_nodes[0]
        except ProviderAuthError:
            errors["base"] = "invalid_auth"
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        nodes_map = {n: n for n in self._pve_nodes}
        if not nodes_map:
            errors.setdefault("base", "no_proxmox_nodes")
            nodes_map = {}

        schema_fields: dict[Any, Any] = {
            vol.Required(CONF_PROXMOX_KIND, default=self._pve_kind): vol.In(PROXMOX_KIND_LABELS),
        }
        if nodes_map:
            schema_fields[
                vol.Required(
                    CONF_PROXMOX_NODE, default=self._pve_node or next(iter(nodes_map))
                )
            ] = vol.In(nodes_map)

        return self.async_show_form(
            step_id="add_record_proxmox_node",
            data_schema=_sectioned("node", schema_fields),
            errors=errors,
            description_placeholders={
                "record": self._adding_record_label()
                if self._flow_context == "add"
                else self._editing_record_label(),
            },
        )

    async def async_step_add_record_proxmox_guest(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        source_id = str(self._pve_source_id or "")

        if user_input is not None:
            try:
                data = _from_section(user_input, "guest")
                vmid = str(data[CONF_PROXMOX_VMID]).strip()
                if not vmid.isdigit():
                    raise ValueError("invalid_vmid")
                iface = str(data.get(CONF_PROXMOX_IFACE) or "").strip() or None
                self._proxmox_target = {
                    CONF_PROXMOX_SOURCE_ID: source_id,
                    CONF_PROXMOX_KIND: self._pve_kind,
                    CONF_PROXMOX_NODE: self._pve_node,
                    CONF_PROXMOX_VMID: vmid,
                    CONF_PROXMOX_IFACE: iface,
                }
                if _needs_ip_details(self._ip_mode_choice, self._ipv6_mode_choice):
                    if self._flow_context == "edit":
                        return await self.async_step_edit_record_ip_details()
                    return await self.async_step_add_record_ip_details()
                if self._flow_context == "edit":
                    return self._finish_edit_record(
                        self._ip_mode_choice, None, None, None, None, None, None
                    )
                return self._finish_add_record(
                    self._ip_mode_choice,
                    None,
                    None,
                    None,
                    self._ipv6_mode_choice,
                    None,
                    None,
                    None,
                )
            except ValueError:
                errors["base"] = "no_proxmox_guests"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        try:
            client = self._pve_client_for_source(source_id)
            self._pve_guests = await client.list_guests(self._pve_node, self._pve_kind)
        except ProviderAuthError:
            errors["base"] = "invalid_auth"
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        guests_map = {
            g["vmid"]: f"{g['vmid']} — {g['name']}"
            + (f" ({g['status']})" if g.get("status") else "")
            for g in self._pve_guests
            if str(g.get("vmid") or "").isdigit()
        }
        if not guests_map:
            errors.setdefault("base", "no_proxmox_guests")

        schema_fields: dict[Any, Any] = {}
        if guests_map:
            schema_fields[vol.Required(CONF_PROXMOX_VMID)] = vol.In(guests_map)
        schema_fields[vol.Optional(CONF_PROXMOX_IFACE, default="")] = str

        return self.async_show_form(
            step_id="add_record_proxmox_guest",
            data_schema=_sectioned("guest", schema_fields),
            errors=errors,
            description_placeholders={
                "record": self._adding_record_label()
                if self._flow_context == "add"
                else self._editing_record_label(),
                "guests_count": str(len(guests_map)),
                "node": self._pve_node,
                "kind": PROXMOX_KIND_LABELS.get(self._pve_kind, self._pve_kind),
            },
        )
    def _ip_strategy_schema(self, ipv4_default: str, ipv6_default: str) -> vol.Schema:
        fields: dict[Any, Any] = {
            vol.Required(CONF_IP_MODE, default=ipv4_default): vol.In(IPV4_MODE_LABELS),
        }
        if self._ipv6_enabled:
            fields[vol.Required(CONF_IPV6_MODE, default=ipv6_default)] = vol.In(IPV6_MODE_LABELS)
        return _sectioned("strategy", fields)

    def _strategy_mode_label(self) -> str:
        label = f"IPv4={IPV4_MODE_LABELS.get(self._ip_mode_choice, self._ip_mode_choice)}"
        if self._ipv6_enabled:
            label += (
                f"; IPv6={IPV6_MODE_LABELS.get(self._ipv6_mode_choice, self._ipv6_mode_choice)}"
            )
        return label

    async def async_step_add_record_ip_details(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _from_section(user_input, "details")
                static_ip = None
                ip_url = None
                ip_entity = None
                static_ipv6 = None
                ipv6_url = None
                ipv6_entity = None
                if self._ip_mode_choice == IP_MODE_STATIC:
                    static_ip = _validate_ipv4(str(data[CONF_STATIC_IP]).strip())
                elif self._ip_mode_choice == IP_MODE_URL:
                    ip_url = str(data[CONF_IP_URL]).strip()
                    if not ip_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                elif self._ip_mode_choice == IP_MODE_ENTITY:
                    ip_entity = str(data[CONF_IP_ENTITY]).strip()
                    if not ip_entity:
                        raise ValueError("invalid_entity")
                if self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_STATIC:
                    static_ipv6 = _validate_ipv6(str(data[CONF_STATIC_IPV6]).strip())
                elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_URL:
                    ipv6_url = str(data[CONF_IPV6_URL]).strip()
                    if not ipv6_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_ENTITY:
                    ipv6_entity = str(data[CONF_IPV6_ENTITY]).strip()
                    if not ipv6_entity:
                        raise ValueError("invalid_entity")
                return self._finish_add_record(
                    self._ip_mode_choice,
                    static_ip,
                    ip_url,
                    ip_entity,
                    self._ipv6_mode_choice,
                    static_ipv6,
                    ipv6_url,
                    ipv6_entity,
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        fields: dict[Any, Any] = {}
        if self._ip_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IP)] = str
        elif self._ip_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IP_URL)] = str
        elif self._ip_mode_choice == IP_MODE_ENTITY:
            fields[vol.Required(CONF_IP_ENTITY)] = _entity_selector()
        if self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IPV6)] = str
        elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IPV6_URL)] = str
        elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_ENTITY:
            fields[vol.Required(CONF_IPV6_ENTITY)] = _entity_selector()

        return self.async_show_form(
            step_id="add_record_ip_details",
            data_schema=_sectioned("details", fields),
            errors=errors,
            description_placeholders={
                "record": self._adding_record_label(),
                "provider": self._selected_provider_label(),
                "mode": self._strategy_mode_label(),
            },
        )

    def _finish_add_record(
        self,
        ip_mode: str,
        static_ip: str | None,
        ip_url: str | None,
        ip_entity: str | None,
        ipv6_mode: str,
        static_ipv6: str | None,
        ipv6_url: str | None,
        ipv6_entity: str | None,
    ) -> FlowResult:
        proxmox_fields = _apply_proxmox_target(
            ipv4_mode=ip_mode, ipv6_mode=ipv6_mode, target=self._proxmox_target
        )
        self._records.append(
            {
                CONF_RECORD_UID: str(uuid.uuid4()),
                CONF_PROVIDER_ID: str(self._selected_provider_id),
                CONF_RECORD_ID: self._adding_record_id,
                CONF_RECORD_ID_AAAA: self._adding_record_id_aaaa or None,
                CONF_RECORD_NAME: self._adding_record_name,
                CONF_RECORD_TYPE: self._adding_record_type,
                CONF_IP_MODE: ip_mode,
                CONF_STATIC_IP: static_ip,
                CONF_IP_URL: ip_url,
                CONF_IP_ENTITY: ip_entity,
                CONF_IPV6_MODE: ipv6_mode,
                CONF_STATIC_IPV6: static_ipv6,
                CONF_IPV6_URL: ipv6_url,
                CONF_IPV6_ENTITY: ipv6_entity,
                CONF_ENABLED: True,
                **proxmox_fields,
            }
        )
        self._proxmox_target = None
        return self._save()
    async def async_step_edit_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._records:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            self._editing_record_uid = str(_from_section(user_input, "selection")[CONF_RECORD_UID])
            rec = next((r for r in self._records if record_uid(r) == self._editing_record_uid), None)
            if rec is None:
                return self.async_abort(reason="no_managed_records")
            self._flow_context = "edit"
            self._edit_enabled = bool(rec.get(CONF_ENABLED, True))
            self._ip_mode_choice = str(rec.get(CONF_IP_MODE, IP_MODE_AUTO))
            self._ipv6_mode_choice = str(rec.get(CONF_IPV6_MODE, IP_MODE_OFF))
            self._proxmox_target = None
            if rec.get(CONF_PROXMOX_SOURCE_ID) or rec.get(CONF_IPV6_PROXMOX_SOURCE_ID):
                self._proxmox_target = {
                    CONF_PROXMOX_SOURCE_ID: rec.get(CONF_PROXMOX_SOURCE_ID)
                    or rec.get(CONF_IPV6_PROXMOX_SOURCE_ID),
                    CONF_PROXMOX_KIND: rec.get(CONF_PROXMOX_KIND) or rec.get(CONF_IPV6_PROXMOX_KIND),
                    CONF_PROXMOX_NODE: rec.get(CONF_PROXMOX_NODE) or rec.get(CONF_IPV6_PROXMOX_NODE),
                    CONF_PROXMOX_VMID: rec.get(CONF_PROXMOX_VMID) or rec.get(CONF_IPV6_PROXMOX_VMID),
                    CONF_PROXMOX_IFACE: rec.get(CONF_PROXMOX_IFACE) or rec.get(CONF_IPV6_PROXMOX_IFACE),
                }
            return await self.async_step_edit_record_ip_mode()

        return self.async_show_form(
            step_id="edit_record_select",
            data_schema=_sectioned("selection", {vol.Required(CONF_RECORD_UID): vol.In(self._record_map())}),
            description_placeholders=self._counts(),
        )

    async def async_step_edit_record_ip_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._flow_context = "edit"
        if user_input is not None:
            data = _from_section(user_input, "strategy")
            self._ip_mode_choice = str(data[CONF_IP_MODE])
            if self._ipv6_enabled:
                self._ipv6_mode_choice = str(data.get(CONF_IPV6_MODE, IP_MODE_OFF))
            self._edit_enabled = bool(data.get(CONF_ENABLED, True))
            if self._ip_mode_choice == IP_MODE_OFF and (
                not self._ipv6_enabled or self._ipv6_mode_choice == IP_MODE_OFF
            ):
                return self.async_show_form(
                    step_id="edit_record_ip_mode",
                    data_schema=self._edit_strategy_schema(),
                    errors={"base": "invalid_ip"},
                    description_placeholders={"record": self._editing_record_label()},
                )
            effective_v6 = self._ipv6_mode_choice if self._ipv6_enabled else IP_MODE_OFF
            if _needs_proxmox(self._ip_mode_choice, effective_v6):
                if not self._ip_sources:
                    return self.async_abort(reason="no_ip_sources")
                return await self.async_step_add_record_proxmox_source()
            if _needs_ip_details(self._ip_mode_choice, effective_v6):
                return await self.async_step_edit_record_ip_details()
            return self._finish_edit_record(
                self._ip_mode_choice, None, None, None, None, None, None
            )

        return self.async_show_form(
            step_id="edit_record_ip_mode",
            data_schema=self._edit_strategy_schema(),
            description_placeholders={"record": self._editing_record_label()},
        )

    def _edit_strategy_schema(self) -> vol.Schema:
        fields: dict[Any, Any] = {
            vol.Required(CONF_IP_MODE, default=self._ip_mode_choice): vol.In(IPV4_MODE_LABELS),
        }
        if self._ipv6_enabled:
            fields[vol.Required(CONF_IPV6_MODE, default=self._ipv6_mode_choice)] = vol.In(
                IPV6_MODE_LABELS
            )
        fields[vol.Optional(CONF_ENABLED, default=self._edit_enabled)] = bool
        return _sectioned("strategy", fields)

    async def async_step_edit_record_ip_details(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        rec = next((r for r in self._records if record_uid(r) == str(self._editing_record_uid)), None)
        if rec is None:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            try:
                data = _from_section(user_input, "details")
                static_ip = None
                ip_url = None
                ip_entity = None
                static_ipv6 = None
                ipv6_url = None
                ipv6_entity = None
                if self._ip_mode_choice == IP_MODE_STATIC:
                    static_ip = _validate_ipv4(str(data[CONF_STATIC_IP]).strip())
                elif self._ip_mode_choice == IP_MODE_URL:
                    ip_url = str(data[CONF_IP_URL]).strip()
                    if not ip_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                elif self._ip_mode_choice == IP_MODE_ENTITY:
                    ip_entity = str(data[CONF_IP_ENTITY]).strip()
                    if not ip_entity:
                        raise ValueError("invalid_entity")
                if self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_STATIC:
                    static_ipv6 = _validate_ipv6(str(data[CONF_STATIC_IPV6]).strip())
                elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_URL:
                    ipv6_url = str(data[CONF_IPV6_URL]).strip()
                    if not ipv6_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_ENTITY:
                    ipv6_entity = str(data[CONF_IPV6_ENTITY]).strip()
                    if not ipv6_entity:
                        raise ValueError("invalid_entity")
                return self._finish_edit_record(
                    self._ip_mode_choice,
                    static_ip,
                    ip_url,
                    ip_entity,
                    static_ipv6,
                    ipv6_url,
                    ipv6_entity,
                    update_ipv6=self._ipv6_enabled,
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        fields: dict[Any, Any] = {}
        if self._ip_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IP, default=str(rec.get(CONF_STATIC_IP) or ""))] = str
        elif self._ip_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IP_URL, default=str(rec.get(CONF_IP_URL) or ""))] = str
        elif self._ip_mode_choice == IP_MODE_ENTITY:
            default_ent = str(rec.get(CONF_IP_ENTITY) or "")
            fields[
                vol.Required(CONF_IP_ENTITY, default=default_ent) if default_ent else vol.Required(CONF_IP_ENTITY)
            ] = _entity_selector()
        if self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IPV6, default=str(rec.get(CONF_STATIC_IPV6) or ""))] = str
        elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IPV6_URL, default=str(rec.get(CONF_IPV6_URL) or ""))] = str
        elif self._ipv6_enabled and self._ipv6_mode_choice == IP_MODE_ENTITY:
            default_ent6 = str(rec.get(CONF_IPV6_ENTITY) or "")
            fields[
                vol.Required(CONF_IPV6_ENTITY, default=default_ent6)
                if default_ent6
                else vol.Required(CONF_IPV6_ENTITY)
            ] = _entity_selector()

        return self.async_show_form(
            step_id="edit_record_ip_details",
            data_schema=_sectioned("details", fields),
            errors=errors,
            description_placeholders={
                "record": self._editing_record_label(),
                "mode": self._strategy_mode_label(),
            },
        )

    def _finish_edit_record(
        self,
        ip_mode: str,
        static_ip: str | None,
        ip_url: str | None,
        ip_entity: str | None,
        static_ipv6: str | None,
        ipv6_url: str | None,
        ipv6_entity: str | None,
        *,
        update_ipv6: bool | None = None,
    ) -> FlowResult:
        apply_ipv6 = self._ipv6_enabled if update_ipv6 is None else update_ipv6
        effective_v6 = self._ipv6_mode_choice if apply_ipv6 else IP_MODE_OFF
        proxmox_fields = _apply_proxmox_target(
            ipv4_mode=ip_mode, ipv6_mode=effective_v6, target=self._proxmox_target
        )
        new_records: list[dict[str, Any]] = []
        for r in self._records:
            if record_uid(r) != str(self._editing_record_uid):
                new_records.append(r)
                continue
            updated = dict(r)
            updated[CONF_IP_MODE] = ip_mode
            updated[CONF_STATIC_IP] = static_ip
            updated[CONF_IP_URL] = ip_url
            updated[CONF_IP_ENTITY] = ip_entity
            if apply_ipv6:
                updated[CONF_IPV6_MODE] = self._ipv6_mode_choice
                updated[CONF_STATIC_IPV6] = static_ipv6
                updated[CONF_IPV6_URL] = ipv6_url
                updated[CONF_IPV6_ENTITY] = ipv6_entity
            # Always refresh IPv4 proxmox fields from target/mode; preserve ipv6
            # proxmox when global IPv6 is off.
            for key, value in proxmox_fields.items():
                if not apply_ipv6 and key.startswith("ipv6_"):
                    continue
                updated[key] = value
            updated[CONF_ENABLED] = self._edit_enabled
            new_records.append(updated)
        self._records = new_records
        self._proxmox_target = None
        return self._save()
    async def async_step_remove_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._records:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            uid = str(_from_section(user_input, "selection")[CONF_RECORD_UID])
            self._records = [r for r in self._records if record_uid(r) != uid]
            return self._save()

        return self.async_show_form(
            step_id="remove_record_select",
            data_schema=_sectioned("selection", {vol.Required(CONF_RECORD_UID): vol.In(self._record_map())}),
            description_placeholders=self._counts(),
        )

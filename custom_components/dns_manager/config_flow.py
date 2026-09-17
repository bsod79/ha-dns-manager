"""Config flow for DNS Manager."""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult, section

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
    CONF_IP_MODE,
    CONF_IP_URL,
    CONF_IPV6_DETECTION_URL,
    CONF_IPV6_MODE,
    CONF_IPV6_URL,
    CONF_PASSWORD,
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_ID,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_ID,
    CONF_RECORD_ID_AAAA,
    CONF_RECORD_NAME,
    CONF_RECORD_TYPE,
    CONF_RECORD_UID,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_IP,
    CONF_STATIC_IPV6,
    CONF_SUBDOMAIN,
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DEFAULT_AUTO_SYNC,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_IPV6_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
    IP_MODE_AUTO,
    IP_MODE_OFF,
    IP_MODE_STATIC,
    IP_MODE_URL,
    IPV4_MODE_LABELS,
    IPV6_MODE_LABELS,
    PROVIDER_CLOUDFLARE,
    PROVIDER_DUCKDNS,
    PROVIDER_DYNDNS,
    PROVIDER_DYNV6,
    PROVIDER_LABELS,
    PROVIDER_NOIP,
)
from .exceptions import ProviderAPIError, ProviderAuthError
from .options_model import (
    build_options_payload,
    ddns_hostname_from_provider,
    default_options,
    find_provider_in_list,
    is_account_provider,
    is_zone_provider,
    migrate_options,
    provider_display_label,
    provider_uid,
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
        self._ipv6_url = DEFAULT_IPV6_DETECTION_URL
        self._auto_sync = DEFAULT_AUTO_SYNC
        self._providers: list[dict[str, Any]] = []
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

    def _load_state(self) -> None:
        self._scan_interval = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._ip_url = str(
            self.config_entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
        )
        self._ipv6_url = str(
            self.config_entry.options.get(CONF_IPV6_DETECTION_URL, DEFAULT_IPV6_DETECTION_URL) or ""
        )
        self._auto_sync = bool(self.config_entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC))
        providers, records, _ = migrate_options(self.config_entry)
        self._providers = providers
        self._records = records

    def _payload(self) -> dict[str, Any]:
        return build_options_payload(
            scan_interval=self._scan_interval,
            ip_detection_url=self._ip_url,
            ipv6_detection_url=self._ipv6_url,
            auto_sync=self._auto_sync,
            providers=self._providers,
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
            "records_count": str(len(self._records)),
        }

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

    # --- Menus ---

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._load_state()
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "providers_menu", "records_menu"],
            description_placeholders=self._counts(),
        )

    async def async_step_providers_menu(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="providers_menu",
            menu_options=["add_provider_type", "remove_provider_select", "init"],
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
            self._ipv6_url = str(polling.get(CONF_IPV6_DETECTION_URL, "") or "").strip()
            self._auto_sync = bool(polling.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC))
            return self._save()

        return self.async_show_form(
            step_id="general",
            data_schema=_sectioned(
                "polling",
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.Coerce(int),
                    vol.Required(CONF_IP_DETECTION_URL, default=self._ip_url): str,
                    vol.Optional(CONF_IPV6_DETECTION_URL, default=self._ipv6_url): str,
                    vol.Optional(CONF_AUTO_SYNC, default=self._auto_sync): bool,
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
        if user_input is not None:
            try:
                data = _from_section(user_input, "account")
                hostname = str(data[CONF_HOSTNAME]).strip().lower()
                username = str(data[CONF_USERNAME]).strip()
                password = str(data[CONF_PASSWORD])
                provider = get_provider(
                    ProviderConfig(
                        provider_type=provider_type,
                        credentials={
                            CONF_HOSTNAME: hostname,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                        },
                    )
                )
                await provider.validate_credentials()
                label = PROVIDER_LABELS.get(provider_type, provider_type)
                upsert_provider(
                    self._providers,
                    provider_type=provider_type,
                    name=f"{label} — {hostname}",
                    config={
                        CONF_HOSTNAME: hostname,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
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
                    vol.Required(CONF_HOSTNAME): str,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                },
            ),
            errors=errors,
            description_placeholders={"provider": PROVIDER_LABELS.get(provider_type, provider_type)},
        )

    async def async_step_add_provider_dynv6(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _from_section(user_input, "dynv6")
                hostname = str(data[CONF_HOSTNAME]).strip().lower()
                token = str(data[CONF_TOKEN]).strip()
                provider = get_provider(
                    ProviderConfig(
                        provider_type=PROVIDER_DYNV6,
                        credentials={CONF_HOSTNAME: hostname, CONF_TOKEN: token},
                    )
                )
                await provider.validate_credentials()
                upsert_provider(
                    self._providers,
                    provider_type=PROVIDER_DYNV6,
                    name=f"dynv6 — {hostname}",
                    config={CONF_HOSTNAME: hostname, CONF_TOKEN: token},
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
                    vol.Required(CONF_HOSTNAME): str,
                    vol.Required(CONF_TOKEN): str,
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
            if is_account_provider(ptype):
                return await self.async_step_add_record_duckdns_subdomain()
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
        if user_input is not None:
            data = _from_section(user_input, "strategy")
            self._ip_mode_choice = str(data[CONF_IP_MODE])
            self._ipv6_mode_choice = str(data.get(CONF_IPV6_MODE, IP_MODE_OFF))
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
            needs_details = self._ip_mode_choice in (IP_MODE_STATIC, IP_MODE_URL) or (
                self._ipv6_mode_choice in (IP_MODE_STATIC, IP_MODE_URL)
            )
            if needs_details:
                return await self.async_step_add_record_ip_details()
            return self._finish_add_record(
                self._ip_mode_choice, None, None, self._ipv6_mode_choice, None, None
            )

        return self.async_show_form(
            step_id="add_record_ip_mode",
            data_schema=self._ip_strategy_schema(IP_MODE_AUTO, IP_MODE_OFF),
            description_placeholders={
                "record": self._adding_record_label(),
                "provider": self._selected_provider_label(),
            },
        )

    def _ip_strategy_schema(self, ipv4_default: str, ipv6_default: str) -> vol.Schema:
        return _sectioned(
            "strategy",
            {
                vol.Required(CONF_IP_MODE, default=ipv4_default): vol.In(IPV4_MODE_LABELS),
                vol.Required(CONF_IPV6_MODE, default=ipv6_default): vol.In(IPV6_MODE_LABELS),
            },
        )

    async def async_step_add_record_ip_details(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _from_section(user_input, "details")
                static_ip = None
                ip_url = None
                static_ipv6 = None
                ipv6_url = None
                if self._ip_mode_choice == IP_MODE_STATIC:
                    static_ip = _validate_ipv4(str(data[CONF_STATIC_IP]).strip())
                elif self._ip_mode_choice == IP_MODE_URL:
                    ip_url = str(data[CONF_IP_URL]).strip()
                    if not ip_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                if self._ipv6_mode_choice == IP_MODE_STATIC:
                    static_ipv6 = _validate_ipv6(str(data[CONF_STATIC_IPV6]).strip())
                elif self._ipv6_mode_choice == IP_MODE_URL:
                    ipv6_url = str(data[CONF_IPV6_URL]).strip()
                    if not ipv6_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                return self._finish_add_record(
                    self._ip_mode_choice,
                    static_ip,
                    ip_url,
                    self._ipv6_mode_choice,
                    static_ipv6,
                    ipv6_url,
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        fields: dict[Any, Any] = {}
        if self._ip_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IP)] = str
        elif self._ip_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IP_URL)] = str
        if self._ipv6_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IPV6)] = str
        elif self._ipv6_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IPV6_URL)] = str

        return self.async_show_form(
            step_id="add_record_ip_details",
            data_schema=_sectioned("details", fields),
            errors=errors,
            description_placeholders={
                "record": self._adding_record_label(),
                "provider": self._selected_provider_label(),
                "mode": f"IPv4={IPV4_MODE_LABELS.get(self._ip_mode_choice, self._ip_mode_choice)}; "
                f"IPv6={IPV6_MODE_LABELS.get(self._ipv6_mode_choice, self._ipv6_mode_choice)}",
            },
        )

    def _finish_add_record(
        self,
        ip_mode: str,
        static_ip: str | None,
        ip_url: str | None,
        ipv6_mode: str,
        static_ipv6: str | None,
        ipv6_url: str | None,
    ) -> FlowResult:
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
                CONF_IPV6_MODE: ipv6_mode,
                CONF_STATIC_IPV6: static_ipv6,
                CONF_IPV6_URL: ipv6_url,
                CONF_ENABLED: True,
            }
        )
        return self._save()

    async def async_step_edit_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if not self._records:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            self._editing_record_uid = str(_from_section(user_input, "selection")[CONF_RECORD_UID])
            rec = next((r for r in self._records if record_uid(r) == self._editing_record_uid), None)
            if rec is None:
                return self.async_abort(reason="no_managed_records")
            self._edit_enabled = bool(rec.get(CONF_ENABLED, True))
            self._ip_mode_choice = str(rec.get(CONF_IP_MODE, IP_MODE_AUTO))
            self._ipv6_mode_choice = str(rec.get(CONF_IPV6_MODE, IP_MODE_OFF))
            return await self.async_step_edit_record_ip_mode()

        return self.async_show_form(
            step_id="edit_record_select",
            data_schema=_sectioned("selection", {vol.Required(CONF_RECORD_UID): vol.In(self._record_map())}),
            description_placeholders=self._counts(),
        )

    async def async_step_edit_record_ip_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            data = _from_section(user_input, "strategy")
            self._ip_mode_choice = str(data[CONF_IP_MODE])
            self._ipv6_mode_choice = str(data.get(CONF_IPV6_MODE, IP_MODE_OFF))
            self._edit_enabled = bool(data.get(CONF_ENABLED, True))
            if self._ip_mode_choice == IP_MODE_OFF and self._ipv6_mode_choice == IP_MODE_OFF:
                return self.async_show_form(
                    step_id="edit_record_ip_mode",
                    data_schema=self._edit_strategy_schema(),
                    errors={"base": "invalid_ip"},
                    description_placeholders={"record": self._editing_record_label()},
                )
            needs_details = self._ip_mode_choice in (IP_MODE_STATIC, IP_MODE_URL) or (
                self._ipv6_mode_choice in (IP_MODE_STATIC, IP_MODE_URL)
            )
            if needs_details:
                return await self.async_step_edit_record_ip_details()
            return self._finish_edit_record(
                self._ip_mode_choice, None, None, self._ipv6_mode_choice, None, None
            )

        return self.async_show_form(
            step_id="edit_record_ip_mode",
            data_schema=self._edit_strategy_schema(),
            description_placeholders={"record": self._editing_record_label()},
        )

    def _edit_strategy_schema(self) -> vol.Schema:
        return _sectioned(
            "strategy",
            {
                vol.Required(CONF_IP_MODE, default=self._ip_mode_choice): vol.In(IPV4_MODE_LABELS),
                vol.Required(CONF_IPV6_MODE, default=self._ipv6_mode_choice): vol.In(IPV6_MODE_LABELS),
                vol.Optional(CONF_ENABLED, default=self._edit_enabled): bool,
            },
        )

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
                static_ipv6 = None
                ipv6_url = None
                if self._ip_mode_choice == IP_MODE_STATIC:
                    static_ip = _validate_ipv4(str(data[CONF_STATIC_IP]).strip())
                elif self._ip_mode_choice == IP_MODE_URL:
                    ip_url = str(data[CONF_IP_URL]).strip()
                    if not ip_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                if self._ipv6_mode_choice == IP_MODE_STATIC:
                    static_ipv6 = _validate_ipv6(str(data[CONF_STATIC_IPV6]).strip())
                elif self._ipv6_mode_choice == IP_MODE_URL:
                    ipv6_url = str(data[CONF_IPV6_URL]).strip()
                    if not ipv6_url.startswith(("http://", "https://")):
                        raise ValueError("invalid_url")
                return self._finish_edit_record(
                    self._ip_mode_choice,
                    static_ip,
                    ip_url,
                    self._ipv6_mode_choice,
                    static_ipv6,
                    ipv6_url,
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        fields: dict[Any, Any] = {}
        if self._ip_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IP, default=str(rec.get(CONF_STATIC_IP) or ""))] = str
        elif self._ip_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IP_URL, default=str(rec.get(CONF_IP_URL) or ""))] = str
        if self._ipv6_mode_choice == IP_MODE_STATIC:
            fields[vol.Required(CONF_STATIC_IPV6, default=str(rec.get(CONF_STATIC_IPV6) or ""))] = str
        elif self._ipv6_mode_choice == IP_MODE_URL:
            fields[vol.Required(CONF_IPV6_URL, default=str(rec.get(CONF_IPV6_URL) or ""))] = str

        return self.async_show_form(
            step_id="edit_record_ip_details",
            data_schema=_sectioned("details", fields),
            errors=errors,
            description_placeholders={
                "record": self._editing_record_label(),
                "mode": f"IPv4={IPV4_MODE_LABELS.get(self._ip_mode_choice, self._ip_mode_choice)}; "
                f"IPv6={IPV6_MODE_LABELS.get(self._ipv6_mode_choice, self._ipv6_mode_choice)}",
            },
        )

    def _finish_edit_record(
        self,
        ip_mode: str,
        static_ip: str | None,
        ip_url: str | None,
        ipv6_mode: str,
        static_ipv6: str | None,
        ipv6_url: str | None,
    ) -> FlowResult:
        new_records: list[dict[str, Any]] = []
        for r in self._records:
            if record_uid(r) != str(self._editing_record_uid):
                new_records.append(r)
                continue
            updated = dict(r)
            updated[CONF_IP_MODE] = ip_mode
            updated[CONF_STATIC_IP] = static_ip
            updated[CONF_IP_URL] = ip_url
            updated[CONF_IPV6_MODE] = ipv6_mode
            updated[CONF_STATIC_IPV6] = static_ipv6
            updated[CONF_IPV6_URL] = ipv6_url
            updated[CONF_ENABLED] = self._edit_enabled
            new_records.append(updated)
        self._records = new_records
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

"""Config flow for DNS Manager."""

from __future__ import annotations

import ipaddress
import uuid
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

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
    CONF_PASSWORD,
    CONF_PROVIDER_CONFIG,
    CONF_PROVIDER_TYPE,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_RECORD_TYPE,
    CONF_RECORD_UID,
    CONF_RECORDS,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_IP,
    CONF_SUBDOMAIN,
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DEFAULT_AUTO_SYNC,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
    IP_MODE_AUTO,
    IP_MODE_LABELS,
    IP_MODE_STATIC,
    IP_MODE_URL,
    PROVIDER_CLOUDFLARE,
    PROVIDER_DUCKDNS,
    PROVIDER_DYNV6,
    PROVIDER_DYNDNS,
    PROVIDER_LABELS,
    PROVIDER_NOIP,
)
from .exceptions import ProviderAPIError, ProviderAuthError
from .providers import get_provider
from .providers.base import DnsRecord, ProviderConfig
from .providers.duckdns import DuckDNSProvider
from .providers.record_context import normalize_record, record_display_label, record_uid


def _validate_ipv4(value: str) -> str:
    return str(ipaddress.IPv4Address(value))


def _parse_ip_strategy(user_input: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Validate and normalize ip_mode / static_ip / ip_url from a form."""
    ip_mode = str(user_input[CONF_IP_MODE])
    static_ip: str | None = None
    ip_url: str | None = None

    if ip_mode == IP_MODE_STATIC:
        static_ip = _validate_ipv4(str(user_input.get(CONF_STATIC_IP, "")).strip())
    elif ip_mode == IP_MODE_URL:
        ip_url = str(user_input.get(CONF_IP_URL, "")).strip()
        if not ip_url.startswith(("http://", "https://")):
            raise ValueError("invalid_url")
    elif ip_mode != IP_MODE_AUTO:
        raise ValueError("invalid_ip_mode")

    return ip_mode, static_ip, ip_url


def _ip_strategy_schema(
    *,
    default_mode: str = IP_MODE_AUTO,
    default_static: str = "",
    default_url: str = "",
    include_enabled: bool = False,
    enabled_default: bool = True,
) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_IP_MODE, default=default_mode): vol.In(IP_MODE_LABELS),
        vol.Optional(CONF_STATIC_IP, default=default_static): str,
        vol.Optional(CONF_IP_URL, default=default_url): str,
    }
    if include_enabled:
        fields[vol.Optional(CONF_ENABLED, default=enabled_default)] = bool
    return vol.Schema(fields)


class DnsManagerConfigFlow(config_entries.ConfigFlow, domain="dns_manager"):
    """Handle a config flow for DNS Manager."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Create a DNS Manager instance; add records via Options."""
        if user_input is not None:
            title = str(user_input.get("instance_name", "DNS Manager")).strip() or "DNS Manager"
            return self.async_create_entry(
                title=title,
                data={},
                options={
                    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    CONF_IP_DETECTION_URL: DEFAULT_IP_DETECTION_URL,
                    CONF_AUTO_SYNC: DEFAULT_AUTO_SYNC,
                    CONF_RECORDS: [],
                },
            )

        schema = vol.Schema({vol.Optional("instance_name", default="DNS Manager"): str})
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return DnsManagerOptionsFlow()


class DnsManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle options — each managed record can use a different provider."""

    def __init__(self) -> None:
        self._scan_interval: int = DEFAULT_SCAN_INTERVAL
        self._ip_url: str = DEFAULT_IP_DETECTION_URL
        self._auto_sync: bool = DEFAULT_AUTO_SYNC

        # Add-record wizard state
        self._adding_provider_type: str | None = None
        self._adding_provider_config: dict[str, Any] = {}
        self._adding_record_name: str = ""
        self._adding_record_id: str = ""
        self._adding_record_type: str = "A"
        self._cf_provider = None
        self._zones: list[dict] = []
        self._cf_records: list[DnsRecord] = []
        self._selected_cf_record_id: str | None = None
        self._editing_record_uid: str | None = None

    def _options_payload(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            CONF_SCAN_INTERVAL: self._scan_interval,
            CONF_IP_DETECTION_URL: self._ip_url,
            CONF_AUTO_SYNC: self._auto_sync,
            CONF_RECORDS: records,
        }

    def _load_general_options(self) -> None:
        self._scan_interval = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._ip_url = str(
            self.config_entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
        )
        self._auto_sync = bool(self.config_entry.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC))

    def _managed_records(self) -> list[dict[str, Any]]:
        return [
            normalize_record(r, self.config_entry)
            for r in self.config_entry.options.get(CONF_RECORDS, [])
        ]

    def _record_already_managed(self, name: str, provider_type: str) -> bool:
        key = name.lower()
        for rec in self._managed_records():
            if str(rec.get(CONF_RECORD_NAME, "")).lower() == key and str(rec.get(CONF_PROVIDER_TYPE)) == provider_type:
                return True
        return False

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._load_general_options()
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "add_record_provider",
                "edit_record_select",
                "remove_record_select",
            ],
        )

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._scan_interval = int(user_input[CONF_SCAN_INTERVAL])
            self._ip_url = str(user_input[CONF_IP_DETECTION_URL])
            self._auto_sync = bool(user_input.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC))
            return self.async_create_entry(
                title="",
                data=self._options_payload(self._managed_records()),
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.Coerce(int),
                vol.Required(CONF_IP_DETECTION_URL, default=self._ip_url): str,
                vol.Optional(CONF_AUTO_SYNC, default=self._auto_sync): bool,
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    async def async_step_add_record_provider(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._adding_provider_type = str(user_input[CONF_PROVIDER_TYPE])
            if self._adding_provider_type == PROVIDER_CLOUDFLARE:
                return await self.async_step_add_record_cloudflare_credentials()
            if self._adding_provider_type == PROVIDER_DUCKDNS:
                return await self.async_step_add_record_duckdns()
            if self._adding_provider_type == PROVIDER_NOIP:
                return await self.async_step_add_record_noip()
            if self._adding_provider_type == PROVIDER_DYNDNS:
                return await self.async_step_add_record_dyndns()
            if self._adding_provider_type == PROVIDER_DYNV6:
                return await self.async_step_add_record_dynv6()

        schema = vol.Schema({vol.Required(CONF_PROVIDER_TYPE): vol.In(PROVIDER_LABELS)})
        return self.async_show_form(step_id="add_record_provider", data_schema=schema)

    async def async_step_add_record_duckdns(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                subdomain = str(user_input[CONF_SUBDOMAIN]).strip().lower()
                token = str(user_input[CONF_TOKEN]).strip()
                hostname = f"{subdomain}.duckdns.org"
                if self._record_already_managed(hostname, PROVIDER_DUCKDNS):
                    errors["base"] = "record_already_managed"
                else:
                    provider = DuckDNSProvider(
                        ProviderConfig(
                            provider_type=PROVIDER_DUCKDNS,
                            credentials={CONF_SUBDOMAIN: subdomain, CONF_TOKEN: token},
                        )
                    )
                    await provider.validate_credentials()
                    self._adding_provider_config = {CONF_SUBDOMAIN: subdomain, CONF_TOKEN: token}
                    self._adding_record_name = hostname
                    self._adding_record_id = hostname
                    self._adding_record_type = "A"
                    return await self.async_step_add_record_strategy()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_SUBDOMAIN): str,
                vol.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="add_record_duckdns", data_schema=schema, errors=errors)

    async def async_step_add_record_noip(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_add_record_hostname_auth(
            step_id="add_record_noip",
            provider_type=PROVIDER_NOIP,
            user_input=user_input,
        )

    async def async_step_add_record_dyndns(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._async_step_add_record_hostname_auth(
            step_id="add_record_dyndns",
            provider_type=PROVIDER_DYNDNS,
            user_input=user_input,
        )

    async def _async_step_add_record_hostname_auth(
        self,
        *,
        step_id: str,
        provider_type: str,
        user_input: dict[str, Any] | None,
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                hostname = str(user_input[CONF_HOSTNAME]).strip().lower()
                username = str(user_input[CONF_USERNAME]).strip()
                password = str(user_input[CONF_PASSWORD])
                if self._record_already_managed(hostname, provider_type):
                    errors["base"] = "record_already_managed"
                else:
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
                    self._adding_provider_config = {
                        CONF_HOSTNAME: hostname,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    }
                    self._adding_record_name = hostname
                    self._adding_record_id = hostname
                    self._adding_record_type = "A"
                    return await self.async_step_add_record_strategy()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOSTNAME): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors)

    async def async_step_add_record_dynv6(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                hostname = str(user_input[CONF_HOSTNAME]).strip().lower()
                token = str(user_input[CONF_TOKEN]).strip()
                if self._record_already_managed(hostname, PROVIDER_DYNV6):
                    errors["base"] = "record_already_managed"
                else:
                    provider = get_provider(
                        ProviderConfig(
                            provider_type=PROVIDER_DYNV6,
                            credentials={CONF_HOSTNAME: hostname, CONF_TOKEN: token},
                        )
                    )
                    await provider.validate_credentials()
                    self._adding_provider_config = {CONF_HOSTNAME: hostname, CONF_TOKEN: token}
                    self._adding_record_name = hostname
                    self._adding_record_id = hostname
                    self._adding_record_type = "A"
                    return await self.async_step_add_record_strategy()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOSTNAME): str,
                vol.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="add_record_dynv6", data_schema=schema, errors=errors)

    async def async_step_add_record_cloudflare_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                auth_mode = user_input[CONF_AUTH_MODE]
                credentials: dict[str, Any] = {CONF_AUTH_MODE: auth_mode}
                if auth_mode == AUTH_MODE_TOKEN:
                    credentials[CONF_API_TOKEN] = user_input[CONF_API_TOKEN]
                else:
                    credentials[CONF_API_EMAIL] = user_input[CONF_API_EMAIL]
                    credentials[CONF_API_KEY] = user_input[CONF_API_KEY]
                self._adding_provider_config = credentials
                self._cf_provider = get_provider(
                    ProviderConfig(provider_type=PROVIDER_CLOUDFLARE, credentials=credentials)
                )
                await self._cf_provider.validate_credentials()
                return await self.async_step_add_record_cloudflare_zone()
            except ProviderAuthError:
                errors["base"] = "invalid_auth"
            except ProviderAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        auth_modes = {AUTH_MODE_TOKEN: "API Token", AUTH_MODE_GLOBAL_KEY: "Global API Key"}
        auth_mode = (user_input or {}).get(CONF_AUTH_MODE, AUTH_MODE_TOKEN)
        fields: dict[Any, Any] = {vol.Required(CONF_AUTH_MODE, default=auth_mode): vol.In(auth_modes)}
        if auth_mode == AUTH_MODE_TOKEN:
            fields[vol.Required(CONF_API_TOKEN)] = str
        else:
            fields[vol.Required(CONF_API_EMAIL)] = str
            fields[vol.Required(CONF_API_KEY)] = str

        return self.async_show_form(
            step_id="add_record_cloudflare_credentials",
            data_schema=vol.Schema(fields),
            errors=errors,
        )

    async def async_step_add_record_cloudflare_zone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            zone_id = str(user_input[CONF_ZONE_ID])
            zone_name = next((z["name"] for z in self._zones if z["id"] == zone_id), zone_id)
            self._adding_provider_config = {
                **self._adding_provider_config,
                CONF_ZONE_ID: zone_id,
                CONF_ZONE_NAME: zone_name,
            }
            return await self.async_step_add_record_cloudflare_select()

        try:
            self._zones = await self._cf_provider.list_zones()
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        zones_map = {z["id"]: z["name"] for z in self._zones}
        schema = vol.Schema({vol.Required(CONF_ZONE_ID): vol.In(zones_map)})
        return self.async_show_form(step_id="add_record_cloudflare_zone", data_schema=schema, errors=errors)

    async def async_step_add_record_cloudflare_select(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        zone_id = str(self._adding_provider_config[CONF_ZONE_ID])

        if user_input is not None:
            cf_record_id = str(user_input[CONF_RECORD_ID])
            record = next((r for r in self._cf_records if r.record_id == cf_record_id), None)
            if record and self._record_already_managed(record.name, PROVIDER_CLOUDFLARE):
                errors["base"] = "record_already_managed"
            else:
                self._selected_cf_record_id = cf_record_id
                self._adding_record_id = cf_record_id
                self._adding_record_name = record.name if record else cf_record_id
                self._adding_record_type = record.record_type if record else "A"
                return await self.async_step_add_record_strategy()

        try:
            self._cf_records = await self._cf_provider.list_a_records(zone_id)
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        rec_map = {r.record_id: f"{r.name} ({r.record_type})" for r in self._cf_records}
        schema = vol.Schema({vol.Required(CONF_RECORD_ID): vol.In(rec_map)})
        return self.async_show_form(step_id="add_record_cloudflare_select", data_schema=schema, errors=errors)

    async def async_step_add_record_strategy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                ip_mode, static_ip, ip_url = _parse_ip_strategy(user_input)

                new_record = {
                    CONF_RECORD_UID: str(uuid.uuid4()),
                    CONF_PROVIDER_TYPE: str(self._adding_provider_type),
                    CONF_PROVIDER_CONFIG: dict(self._adding_provider_config),
                    CONF_RECORD_ID: self._adding_record_id,
                    CONF_RECORD_NAME: self._adding_record_name,
                    CONF_RECORD_TYPE: self._adding_record_type,
                    CONF_IP_MODE: ip_mode,
                    CONF_STATIC_IP: static_ip,
                    CONF_IP_URL: ip_url,
                    CONF_ENABLED: True,
                }
                new_records = self._managed_records()
                new_records.append(new_record)
                return self.async_create_entry(title="", data=self._options_payload(new_records))
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        return self.async_show_form(
            step_id="add_record_strategy",
            data_schema=_ip_strategy_schema(),
            errors=errors,
        )

    async def async_step_edit_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        managed = self._managed_records()
        if not managed:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            self._editing_record_uid = str(user_input[CONF_RECORD_UID])
            return await self.async_step_edit_record_strategy()

        schema = vol.Schema(
            {
                vol.Required(CONF_RECORD_UID): vol.In(
                    {record_uid(r): record_display_label(r) for r in managed}
                )
            }
        )
        return self.async_show_form(step_id="edit_record_select", data_schema=schema)

    async def async_step_edit_record_strategy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        managed = self._managed_records()
        rec = next((r for r in managed if record_uid(r) == str(self._editing_record_uid)), None)
        if rec is None:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            try:
                ip_mode, static_ip, ip_url = _parse_ip_strategy(user_input)
                enabled = bool(user_input.get(CONF_ENABLED, True))

                new_records: list[dict[str, Any]] = []
                for r in managed:
                    if record_uid(r) != str(self._editing_record_uid):
                        new_records.append(r)
                        continue
                    updated = dict(r)
                    updated[CONF_IP_MODE] = ip_mode
                    updated[CONF_STATIC_IP] = static_ip
                    updated[CONF_IP_URL] = ip_url
                    updated[CONF_ENABLED] = enabled
                    new_records.append(updated)

                return self.async_create_entry(title="", data=self._options_payload(new_records))
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        return self.async_show_form(
            step_id="edit_record_strategy",
            data_schema=_ip_strategy_schema(
                default_mode=str(rec.get(CONF_IP_MODE, IP_MODE_AUTO)),
                default_static=str(rec.get(CONF_STATIC_IP) or ""),
                default_url=str(rec.get(CONF_IP_URL) or ""),
                include_enabled=True,
                enabled_default=bool(rec.get(CONF_ENABLED, True)),
            ),
            errors=errors,
        )

    async def async_step_remove_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        managed = self._managed_records()
        if not managed:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            uid = str(user_input[CONF_RECORD_UID])
            new_records = [r for r in managed if record_uid(r) != uid]
            return self.async_create_entry(title="", data=self._options_payload(new_records))

        schema = vol.Schema(
            {
                vol.Required(CONF_RECORD_UID): vol.In(
                    {record_uid(r): record_display_label(r) for r in managed}
                )
            }
        )
        return self.async_show_form(step_id="remove_record_select", data_schema=schema)

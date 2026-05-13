"""Config flow for DNS Manager."""

from __future__ import annotations

import ipaddress
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
    CONF_CREDENTIALS,
    CONF_ENABLED,
    CONF_IP_DETECTION_URL,
    CONF_IP_MODE,
    CONF_PROVIDER_TYPE,
    CONF_RECORDS,
    CONF_RECORD_ID,
    CONF_RECORD_NAME,
    CONF_SCAN_INTERVAL,
    CONF_STATIC_IP,
    CONF_ZONE_ID,
    CONF_ZONE_NAME,
    DEFAULT_IP_DETECTION_URL,
    DEFAULT_SCAN_INTERVAL,
    IP_MODE_AUTO,
    IP_MODE_STATIC,
)
from .exceptions import ProviderAPIError, ProviderAuthError
from .providers import get_provider
from .providers.base import DnsRecord, ProviderConfig


def _validate_ipv4(value: str) -> str:
    return str(ipaddress.IPv4Address(value))


class DnsManagerConfigFlow(config_entries.ConfigFlow, domain="dns_manager"):
    """Handle a config flow for DNS Manager."""

    VERSION = 1

    def __init__(self) -> None:
        self._provider_type: str | None = None
        self._credentials: dict[str, Any] = {}
        self._provider = None
        self._zones: list[dict] = []
        self._zone_id: str | None = None
        self._zone_name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_provider(user_input)

    async def async_step_provider(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._provider_type = user_input[CONF_PROVIDER_TYPE]
            return await self.async_step_credentials()

        schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER_TYPE): vol.In(
                    {
                        "cloudflare": "Cloudflare",
                    }
                )
            }
        )
        return self.async_show_form(step_id="provider", data_schema=schema)

    async def async_step_credentials(self, user_input: dict[str, Any] | None = None) -> FlowResult:
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

                self._credentials = credentials
                self._provider = get_provider(
                    ProviderConfig(provider_type=str(self._provider_type), credentials=credentials)
                )
                await self._provider.validate_credentials()
                return await self.async_step_zone()
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

        return self.async_show_form(step_id="credentials", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_zone(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._zone_id = user_input[CONF_ZONE_ID]
            self._zone_name = next((z["name"] for z in self._zones if z["id"] == self._zone_id), self._zone_id)
            title = self._zone_name or "DNS Manager"
            data = {
                CONF_PROVIDER_TYPE: str(self._provider_type),
                CONF_CREDENTIALS: self._credentials,
                CONF_ZONE_ID: str(self._zone_id),
                CONF_ZONE_NAME: str(self._zone_name),
            }
            options = {
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                CONF_IP_DETECTION_URL: DEFAULT_IP_DETECTION_URL,
                CONF_RECORDS: [],
            }
            return self.async_create_entry(title=title, data=data, options=options)

        try:
            self._zones = await self._provider.list_zones()
        except Exception:  # noqa: BLE001
            errors["base"] = "cannot_connect"

        zones_map = {z["id"]: z["name"] for z in self._zones}
        schema = vol.Schema({vol.Required(CONF_ZONE_ID): vol.In(zones_map)})
        return self.async_show_form(step_id="zone", data_schema=schema, errors=errors)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return DnsManagerOptionsFlow()


class DnsManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self) -> None:
        self._provider = None
        self._records: list[DnsRecord] = []
        self._selected_record_id: str | None = None
        self._editing_record_id: str | None = None
        self._scan_interval: int = DEFAULT_SCAN_INTERVAL
        self._ip_url: str = DEFAULT_IP_DETECTION_URL

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        self._scan_interval = int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._ip_url = str(
            self.config_entry.options.get(CONF_IP_DETECTION_URL, DEFAULT_IP_DETECTION_URL)
        )
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "add_record_select", "edit_record_select", "remove_record_select"],
        )

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._scan_interval = int(user_input[CONF_SCAN_INTERVAL])
            self._ip_url = str(user_input[CONF_IP_DETECTION_URL])
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: self._scan_interval,
                    CONF_IP_DETECTION_URL: self._ip_url,
                    CONF_RECORDS: list(self.config_entry.options.get(CONF_RECORDS, [])),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=self._scan_interval): vol.Coerce(int),
                vol.Required(CONF_IP_DETECTION_URL, default=self._ip_url): str,
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    async def _ensure_provider_and_records(self) -> None:
        if self._provider is None:
            self._provider = get_provider(
                ProviderConfig(
                    provider_type=self.config_entry.data[CONF_PROVIDER_TYPE],
                    credentials=self.config_entry.data[CONF_CREDENTIALS],
                )
            )

        self._records = await self._provider.list_a_records(self.config_entry.data[CONF_ZONE_ID])

    def _managed_records(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_RECORDS, []))

    async def async_step_add_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        await self._ensure_provider_and_records()
        errors: dict[str, str] = {}

        if user_input is not None:
            self._selected_record_id = str(user_input[CONF_RECORD_ID])
            if any(r.get(CONF_RECORD_ID) == self._selected_record_id for r in self._managed_records()):
                errors["base"] = "record_already_managed"
            else:
                return await self.async_step_add_record_strategy()

        rec_map = {r.record_id: r.name for r in self._records}
        schema = vol.Schema({vol.Required(CONF_RECORD_ID): vol.In(rec_map)})
        return self.async_show_form(step_id="add_record_select", data_schema=schema, errors=errors)

    async def async_step_add_record_strategy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        await self._ensure_provider_and_records()
        errors: dict[str, str] = {}

        record_id = str(self._selected_record_id)
        record = next((r for r in self._records if r.record_id == record_id), None)
        record_name = record.name if record else record_id

        if user_input is not None:
            try:
                ip_mode = user_input[CONF_IP_MODE]
                static_ip = None
                if ip_mode == IP_MODE_STATIC:
                    static_ip = _validate_ipv4(str(user_input[CONF_STATIC_IP]))

                new_records = self._managed_records()
                new_records.append(
                    {
                        CONF_RECORD_ID: record_id,
                        CONF_RECORD_NAME: record_name,
                        CONF_IP_MODE: ip_mode,
                        CONF_STATIC_IP: static_ip,
                        CONF_ENABLED: True,
                    }
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: self._scan_interval,
                        CONF_IP_DETECTION_URL: self._ip_url,
                        CONF_RECORDS: new_records,
                    },
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        schema = vol.Schema(
            {
                vol.Required(CONF_IP_MODE, default=IP_MODE_AUTO): vol.In(
                    {IP_MODE_AUTO: "Auto (public IP)", IP_MODE_STATIC: "Static IP"}
                ),
                vol.Optional(CONF_STATIC_IP): str,
            }
        )
        return self.async_show_form(step_id="add_record_strategy", data_schema=schema, errors=errors)

    async def async_step_edit_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        managed = self._managed_records()
        if not managed:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            self._editing_record_id = str(user_input[CONF_RECORD_ID])
            return await self.async_step_edit_record_strategy()

        schema = vol.Schema(
            {vol.Required(CONF_RECORD_ID): vol.In({r[CONF_RECORD_ID]: r[CONF_RECORD_NAME] for r in managed})}
        )
        return self.async_show_form(step_id="edit_record_select", data_schema=schema)

    async def async_step_edit_record_strategy(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        managed = self._managed_records()
        rec = next((r for r in managed if str(r.get(CONF_RECORD_ID)) == str(self._editing_record_id)), None)
        if rec is None:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            try:
                ip_mode = user_input[CONF_IP_MODE]
                static_ip = None
                if ip_mode == IP_MODE_STATIC:
                    static_ip = _validate_ipv4(str(user_input[CONF_STATIC_IP]))
                enabled = bool(user_input.get(CONF_ENABLED, True))

                new_records: list[dict[str, Any]] = []
                for r in managed:
                    if str(r.get(CONF_RECORD_ID)) != str(self._editing_record_id):
                        new_records.append(r)
                        continue
                    new_records.append(
                        {
                            CONF_RECORD_ID: r[CONF_RECORD_ID],
                            CONF_RECORD_NAME: r.get(CONF_RECORD_NAME),
                            CONF_IP_MODE: ip_mode,
                            CONF_STATIC_IP: static_ip,
                            CONF_ENABLED: enabled,
                        }
                    )

                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SCAN_INTERVAL: self._scan_interval,
                        CONF_IP_DETECTION_URL: self._ip_url,
                        CONF_RECORDS: new_records,
                    },
                )
            except Exception:  # noqa: BLE001
                errors["base"] = "invalid_ip"

        schema = vol.Schema(
            {
                vol.Required(CONF_IP_MODE, default=rec.get(CONF_IP_MODE, IP_MODE_AUTO)): vol.In(
                    {IP_MODE_AUTO: "Auto (public IP)", IP_MODE_STATIC: "Static IP"}
                ),
                vol.Optional(CONF_STATIC_IP, default=rec.get(CONF_STATIC_IP) or ""): str,
                vol.Optional(CONF_ENABLED, default=bool(rec.get(CONF_ENABLED, True))): bool,
            }
        )
        return self.async_show_form(step_id="edit_record_strategy", data_schema=schema, errors=errors)

    async def async_step_remove_record_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        managed = self._managed_records()
        if not managed:
            return self.async_abort(reason="no_managed_records")

        if user_input is not None:
            record_id = str(user_input[CONF_RECORD_ID])
            new_records = [r for r in managed if str(r.get(CONF_RECORD_ID)) != record_id]
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: self._scan_interval,
                    CONF_IP_DETECTION_URL: self._ip_url,
                    CONF_RECORDS: new_records,
                },
            )

        schema = vol.Schema(
            {vol.Required(CONF_RECORD_ID): vol.In({r[CONF_RECORD_ID]: r[CONF_RECORD_NAME] for r in managed})}
        )
        return self.async_show_form(step_id="remove_record_select", data_schema=schema)


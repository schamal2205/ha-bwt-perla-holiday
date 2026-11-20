"""Config flow for BWT Perla Holiday Mode."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PerlaApi, PerlaApiError, PerlaAuthError
from .const import (
    CONF_CODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .vnc import PerlaVnc, VncError


async def _validate(hass: HomeAssistant, host: str, code: str) -> dict[str, str]:
    """Check API login and VNC access. Returns a form error dict."""
    try:
        await PerlaApi(async_get_clientsession(hass), host, code).current_data()
    except PerlaAuthError:
        return {"base": "invalid_auth"}
    except PerlaApiError:
        return {"base": "cannot_connect"}
    try:
        async with PerlaVnc(host) as vnc:
            if (vnc.width, vnc.height) != (800, 480):
                return {"base": "unsupported_display"}
    except VncError:
        return {"base": "vnc_unavailable"}
    return {}


class PerlaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            errors = await _validate(self.hass, host, user_input[CONF_CODE])
            if not errors:
                return self.async_create_entry(
                    title=f"BWT Perla ({host})",
                    data={CONF_HOST: host, CONF_CODE: user_input[CONF_CODE]},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST): str, vol.Required(CONF_CODE): str}
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            errors = await _validate(
                self.hass, entry.data[CONF_HOST], user_input[CONF_CODE]
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_CODE: user_input[CONF_CODE]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_CODE): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return PerlaOptionsFlow()


class PerlaOptionsFlow(OptionsFlow):
    """Options: polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                    )
                }
            ),
        )

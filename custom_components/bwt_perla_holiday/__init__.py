"""BWT Perla Holiday Mode integration.

Reads the holiday mode state from the local Perla API and switches it by
operating the device's touch display over its (unauthenticated) VNC server.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PerlaApi
from .const import CONF_CODE, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import PerlaConfigEntry, PerlaCoordinator, PerlaRuntimeData

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: PerlaConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    host = entry.data[CONF_HOST]
    api = PerlaApi(async_get_clientsession(hass), host, entry.data[CONF_CODE])
    interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    coordinator = PerlaCoordinator(hass, entry, api, host, interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = PerlaRuntimeData(coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PerlaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PerlaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

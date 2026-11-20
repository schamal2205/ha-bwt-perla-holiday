"""Data coordinator and display controller for the BWT Perla."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PerlaApi, PerlaApiError, PerlaAuthError, holiday_active
from .const import DOMAIN, VERIFY_ATTEMPTS, VERIFY_DELAY
from .navigator import NavigationError, set_holiday_mode
from .vnc import Frame, PerlaVnc, VncError

_LOGGER = logging.getLogger(__name__)


@dataclass
class PerlaRuntimeData:
    """Runtime data stored on the config entry."""

    coordinator: PerlaCoordinator


type PerlaConfigEntry = ConfigEntry[PerlaRuntimeData]


class PerlaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls GetCurrentData and drives the touch display over VNC."""

    config_entry: PerlaConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: PerlaConfigEntry,
        api: PerlaApi,
        host: str,
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=interval,
        )
        self.api = api
        self.host = host
        # Only one VNC session at a time drives the display.
        self.display_lock = asyncio.Lock()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.current_data()
        except PerlaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PerlaApiError as err:
            raise UpdateFailed(f"Error talking to Perla API: {err}") from err

    @property
    def holiday_mode(self) -> bool | None:
        """Holiday mode as reported by the API."""
        if self.data is None:
            return None
        return holiday_active(self.data)

    async def async_set_holiday_mode(self, enabled: bool) -> None:
        """Switch holiday mode via the display and verify via the API."""
        async with self.display_lock:
            try:
                async with PerlaVnc(self.host) as vnc:
                    await set_holiday_mode(vnc, enabled)
            except (VncError, NavigationError) as err:
                raise PerlaControlError(str(err)) from err

        for _ in range(VERIFY_ATTEMPTS):
            await self.async_refresh()
            if self.holiday_mode is enabled:
                return
            await asyncio.sleep(VERIFY_DELAY)
        _LOGGER.warning(
            "Display reports holiday mode %s but the API does not confirm it yet",
            "on" if enabled else "off",
        )

    async def async_capture_display(self) -> Frame:
        """Grab the current display content."""
        async with self.display_lock:
            async with PerlaVnc(self.host) as vnc:
                return await vnc.capture()


class PerlaControlError(Exception):
    """Switching via the display failed."""

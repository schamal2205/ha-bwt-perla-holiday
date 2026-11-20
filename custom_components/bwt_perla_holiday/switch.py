"""Holiday mode switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import PerlaConfigEntry, PerlaControlError
from .entity import PerlaEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PerlaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch."""
    async_add_entities([PerlaHolidaySwitch(entry.runtime_data.coordinator)])


class PerlaHolidaySwitch(PerlaEntity, SwitchEntity):
    """Holiday mode: when on, the Perla shuts off the water supply."""

    _attr_translation_key = "holiday_mode"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "holiday_mode")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.holiday_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.async_set_holiday_mode(enabled)
        except PerlaControlError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="switch_failed",
                translation_placeholders={"error": str(err)},
            ) from err

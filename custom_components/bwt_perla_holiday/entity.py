"""Base entity for the BWT Perla."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import PerlaCoordinator


class PerlaEntity(CoordinatorEntity[PerlaCoordinator]):
    """Common device info."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PerlaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        data = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            model="Perla",
            name="BWT Perla",
            sw_version=str(data.get("FirmwareVersion", "")) or None,
            configuration_url=f"http://{coordinator.host}/",
        )

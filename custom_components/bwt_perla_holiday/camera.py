"""Camera entity mirroring the Perla touch display (useful for debugging)."""

from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PerlaConfigEntry, PerlaCoordinator
from .entity import PerlaEntity
from .vnc import VncError

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PerlaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the display camera."""
    async_add_entities([PerlaDisplayCamera(entry.runtime_data.coordinator)])


class PerlaDisplayCamera(PerlaEntity, Camera):
    """Still image of the device display, fetched over VNC on demand."""

    _attr_translation_key = "display"
    _attr_entity_registry_enabled_default = False
    _attr_frame_interval = 10

    def __init__(self, coordinator: PerlaCoordinator) -> None:
        PerlaEntity.__init__(self, coordinator, "display")
        Camera.__init__(self)
        self.content_type = "image/png"

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            frame = await self.coordinator.async_capture_display()
        except (VncError, OSError):
            return None
        return await self.hass.async_add_executor_job(frame.to_png)

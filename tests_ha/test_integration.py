"""Home Assistant tests (config flow, switch).

Run with:
    pip install pytest-homeassistant-custom-component PyTurboJPEG
    pytest -p pytest_homeassistant_custom_component tests_ha
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bwt_perla_holiday.api import PerlaAuthError
from custom_components.bwt_perla_holiday.const import DOMAIN
from custom_components.bwt_perla_holiday.navigator import NavigationError

PKG = "custom_components.bwt_perla_holiday"
DATA = {"host": "192.0.2.10", "code": "secret"}
OFF = {"FirmwareVersion": "2.0212", "HolidayModeStartTime": 0}
ON = {"FirmwareVersion": "2.0212", "HolidayModeStartTime": 1}


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


class FakeVnc:
    width, height, name = 800, 480, "fake"

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


async def test_config_flow_success(hass: HomeAssistant) -> None:
    with (
        patch(f"{PKG}.api.PerlaApi.current_data", AsyncMock(return_value=OFF)),
        patch(f"{PKG}.config_flow.PerlaVnc", FakeVnc),
        patch(f"{PKG}.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], DATA
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA


async def test_config_flow_invalid_auth(hass: HomeAssistant) -> None:
    with patch(
        f"{PKG}.api.PerlaApi.current_data",
        AsyncMock(side_effect=PerlaAuthError("nope")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], DATA
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def _setup(hass: HomeAssistant, api_mock: AsyncMock) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id=DATA["host"])
    entry.add_to_hass(hass)
    with patch(f"{PKG}.api.PerlaApi.current_data", api_mock):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_switch_turn_on(hass: HomeAssistant) -> None:
    api = AsyncMock(return_value=OFF)
    await _setup(hass, api)
    state = hass.states.get("switch.bwt_perla_holiday_mode")
    assert state is not None and state.state == "off"

    async def fake_set(vnc, enabled, **kwargs):
        api.return_value = ON if enabled else OFF
        return enabled

    with (
        patch(f"{PKG}.api.PerlaApi.current_data", api),
        patch(f"{PKG}.coordinator.PerlaVnc", FakeVnc),
        patch(f"{PKG}.coordinator.set_holiday_mode", side_effect=fake_set) as nav,
    ):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.bwt_perla_holiday_mode"},
            blocking=True,
        )
    nav.assert_awaited_once()
    assert nav.await_args.args[1] is True
    assert hass.states.get("switch.bwt_perla_holiday_mode").state == "on"


async def test_switch_failure_raises(hass: HomeAssistant) -> None:
    api = AsyncMock(return_value=OFF)
    await _setup(hass, api)
    with (
        patch(f"{PKG}.api.PerlaApi.current_data", api),
        patch(f"{PKG}.coordinator.PerlaVnc", FakeVnc),
        patch(
            f"{PKG}.coordinator.set_holiday_mode",
            AsyncMock(side_effect=NavigationError("unknown screen")),
        ),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.bwt_perla_holiday_mode"},
            blocking=True,
        )

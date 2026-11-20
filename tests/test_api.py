"""Tests for interpreting HolidayModeStartTime."""

from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
_pkg = types.ModuleType("perla")
_pkg.__path__ = [str(ROOT / "custom_components" / "bwt_perla_holiday")]
sys.modules.setdefault("perla", _pkg)

from perla.api import holiday_active, holiday_scheduled_start  # noqa: E402

NOW = 1_800_000_000


def test_off() -> None:
    assert holiday_active({"HolidayModeStartTime": 0}, NOW) is False
    assert holiday_scheduled_start({"HolidayModeStartTime": 0}, NOW) is None


def test_on_immediately() -> None:
    assert holiday_active({"HolidayModeStartTime": 1}, NOW) is True
    assert holiday_scheduled_start({"HolidayModeStartTime": 1}, NOW) is None


def test_scheduled_in_future() -> None:
    data = {"HolidayModeStartTime": NOW + 3600}
    assert holiday_active(data, NOW) is False
    assert holiday_scheduled_start(data, NOW).timestamp() == NOW + 3600


def test_scheduled_start_passed() -> None:
    data = {"HolidayModeStartTime": NOW - 60}
    assert holiday_active(data, NOW) is True
    assert holiday_scheduled_start(data, NOW) is None


def test_garbage() -> None:
    assert holiday_active({"HolidayModeStartTime": "x"}, NOW) is False
    assert holiday_active({}, NOW) is False

"""Screen recognition and navigation on the Perla touch display.

Screens are recognised by colours at fixed, text-free positions, so the
logic does not depend on the display language.

Navigation path (800x480 display):
    Home --(hamburger 55,35)--> Menu --(Functions 627,148)--> Functions
    --(Holiday mode row 560,358)--> Holiday mode page --(toggle 728,111)
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from .vnc import Frame, PerlaVnc

_LOGGER = logging.getLogger(__name__)

Color = tuple[int, int, int]

GREY_BG: Color = (243, 245, 247)
WHITE: Color = (255, 255, 255)
SEPARATOR: Color = (234, 234, 233)
BLUE: Color = (25, 118, 210)
TOGGLE_OFF: Color = (214, 215, 213)

TAP_BACK = (50, 37)
TAP_MENU = (55, 35)
TAP_FUNCTIONS = (627, 148)
TAP_HOLIDAY_ENTRY = (560, 358)
TAP_TOGGLE = (728, 111)
TAP_WAKE = (400, 10)  # inert title area on every known screen

EXPECTED_SIZE = (800, 480)


class Screen(Enum):
    """Known screens."""

    HOME = "home"
    MENU = "menu"
    FUNCTIONS = "functions"
    HOLIDAY = "holiday"
    DARK = "dark"
    UNKNOWN = "unknown"


class NavigationError(Exception):
    """Raised when the holiday mode page cannot be reached or switched."""


def _near(c: Color, ref: Color, tol: int = 5) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(c, ref))


def _line_at(frame: Frame, x: int, y: int) -> bool:
    """True if a thin separator line is at (x, y +- 2)."""
    return any(
        _near(frame.pixel(x, yy), SEPARATOR, 6)
        for yy in range(y - 2, y + 3)
        if 0 <= yy < frame.height
    )


def toggle_state(frame: Frame) -> bool | None:
    """Return the holiday toggle state on the holiday page (None if unclear)."""
    knob = frame.pixel(740, 111)
    if _near(knob, BLUE, 30):
        return True
    if _near(knob, TOGGLE_OFF, 20):
        return False
    return None


def has_header(frame: Frame) -> bool:
    """Sub pages have a grey header bar and a white body."""
    return _near(frame.pixel(400, 37), GREY_BG) and _near(frame.pixel(400, 80), WHITE)


def classify(frame: Frame) -> Screen:
    """Identify the current screen."""
    if (frame.width, frame.height) != EXPECTED_SIZE:
        return Screen.UNKNOWN
    px = frame.pixel
    samples = [px(x, y) for x, y in ((400, 37), (400, 240), (100, 400), (700, 400))]
    if all(max(c) < 40 for c in samples):
        return Screen.DARK
    if _near(px(173, 148), BLUE) and _near(px(627, 148), BLUE):
        return Screen.MENU
    if (
        _near(px(400, 37), GREY_BG)
        and _near(px(400, 80), GREY_BG)
        and _near(px(100, 250), GREY_BG)
    ):
        return Screen.HOME
    if has_header(frame):
        if (
            _line_at(frame, 100, 151)
            and _line_at(frame, 600, 151)
            and toggle_state(frame) is not None
        ):
            return Screen.HOLIDAY
        if _near(px(100, 250), WHITE) and all(
            _line_at(frame, 600, y) for y in (153, 235, 316, 398)
        ):
            return Screen.FUNCTIONS
    return Screen.UNKNOWN


async def set_holiday_mode(
    vnc: PerlaVnc,
    enabled: bool,
    *,
    max_steps: int = 14,
    settle: float = 1.5,
    return_home: bool = True,
) -> bool:
    """Navigate to the holiday mode page and set the toggle.

    Returns the toggle state read from the display afterwards.
    """
    unknown = 0
    toggles = 0
    for step in range(max_steps):
        frame = await vnc.capture()
        screen = classify(frame)
        _LOGGER.debug("Step %s: screen %s", step, screen.value)

        if screen is Screen.HOLIDAY:
            state = toggle_state(frame)
            _LOGGER.debug("Holiday toggle is %s, want %s", state, enabled)
            if state is enabled:
                break
            if toggles >= 3:
                raise NavigationError("Toggle did not change after 3 taps")
            toggles += 1
            await vnc.tap(*TAP_TOGGLE)
            if await _wait_for_toggle(vnc, enabled):
                break
            continue
        elif screen is Screen.HOME:
            await vnc.tap(*TAP_MENU)
        elif screen is Screen.MENU:
            await vnc.tap(*TAP_FUNCTIONS)
        elif screen is Screen.FUNCTIONS:
            await vnc.tap(*TAP_HOLIDAY_ENTRY)
        elif screen is Screen.DARK:
            await vnc.tap(*TAP_WAKE)
        else:
            unknown += 1
            if unknown > 4:
                raise NavigationError("Display shows an unknown screen")
            await vnc.tap(*(TAP_BACK if has_header(frame) else TAP_WAKE))
        await asyncio.sleep(settle)
    else:
        raise NavigationError(f"Holiday mode page not reached in {max_steps} steps")

    if return_home:
        try:
            await go_home(vnc, settle=settle)
        except Exception:  # noqa: BLE001 - cosmetic only
            _LOGGER.debug("Could not return display to home screen", exc_info=True)
    return enabled


async def _wait_for_toggle(
    vnc: PerlaVnc, enabled: bool, *, timeout: float = 8.0, interval: float = 1.0
) -> bool:
    """After a toggle tap, only observe (never tap) until the state is reached.

    Intermediate frames (animation, short busy overlays) are ignored so that
    no stray "back" tap can leave the page while the device reacts.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        await asyncio.sleep(interval)
        frame = await vnc.capture()
        screen = classify(frame)
        state = toggle_state(frame) if screen is Screen.HOLIDAY else None
        _LOGGER.debug("After toggle tap: screen %s, toggle %s", screen.value, state)
        if state is enabled:
            return True
        if screen is Screen.HOLIDAY and state is (not enabled):
            # Settled in the old position: tap was not accepted.
            return False
    return False


async def go_home(vnc: PerlaVnc, *, settle: float = 1.5, max_steps: int = 5) -> None:
    """Return the display to the home screen."""
    for _ in range(max_steps):
        frame = await vnc.capture()
        screen = classify(frame)
        if screen is Screen.HOME:
            return
        if screen is Screen.MENU:
            await vnc.tap(173, 148)
        elif has_header(frame):
            await vnc.tap(*TAP_BACK)
        else:
            return
        await asyncio.sleep(settle)

"""Screen classification tests against real Perla screenshots.

Run with: pytest tests
These tests do not need Home Assistant installed.
"""

from __future__ import annotations

import pathlib
import struct
import sys
import types
import zlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "bwt_perla_holiday"
# Import the HA-independent modules without running the package __init__.
_pkg = types.ModuleType("perla")
_pkg.__path__ = [str(PKG)]
sys.modules.setdefault("perla", _pkg)

from perla import navigator  # noqa: E402
from perla.vnc import Frame  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


def load_png(path: pathlib.Path) -> Frame:
    """Decode an 8-bit RGB PNG (filter types 0-4) into a Frame."""
    data = path.read_bytes()
    pos, idat, width, height = 8, b"", 0, 0
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        tag = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height = struct.unpack(">II", body[:8])
            assert body[8:10] == b"\x08\x02", "only 8-bit RGB supported"
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * 3
    prev = bytearray(stride)
    rgb = bytearray()
    for r in range(height):
        ftype = raw[r * (stride + 1)]
        line = bytearray(raw[r * (stride + 1) + 1 : (r + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
                line[i] = (line[i] + pred) & 0xFF
        rgb += line
        prev = line
    bgrx = bytearray(width * height * 4)
    bgrx[2::4] = rgb[0::3]
    bgrx[1::4] = rgb[1::3]
    bgrx[0::4] = rgb[2::3]
    return Frame(width, height, bytes(bgrx))


@pytest.mark.parametrize(
    ("fixture", "screen"),
    [
        ("home.png", navigator.Screen.HOME),
        ("menu.png", navigator.Screen.MENU),
        ("functions.png", navigator.Screen.FUNCTIONS),
        ("holiday_off.png", navigator.Screen.HOLIDAY),
        ("holiday_on.png", navigator.Screen.HOLIDAY),
        ("login.png", navigator.Screen.LOGIN),
        ("login_keyboard.png", navigator.Screen.LOGIN),
    ],
)
def test_classify(fixture: str, screen: navigator.Screen) -> None:
    assert navigator.classify(load_png(FIXTURES / fixture)) is screen


@pytest.mark.parametrize(
    ("fixture", "state"), [("holiday_off.png", False), ("holiday_on.png", True)]
)
def test_toggle_state(fixture: str, state: bool) -> None:
    assert navigator.toggle_state(load_png(FIXTURES / fixture)) is state


def test_dark_screen() -> None:
    frame = Frame(800, 480, bytes(800 * 480 * 4))
    assert navigator.classify(frame) is navigator.Screen.DARK


def test_png_roundtrip() -> None:
    frame = load_png(FIXTURES / "menu.png")
    tmp = FIXTURES.parent / "_roundtrip.png"
    try:
        tmp.write_bytes(frame.to_png())
        assert load_png(tmp).bgrx == frame.bgrx
    finally:
        tmp.unlink(missing_ok=True)


def _run(coro):
    """Run a coroutine on a private loop (keeps pytest-asyncio's loop intact)."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class FakeVnc:
    """Replays frames; records taps."""

    def __init__(self, frames: list[Frame]) -> None:
        self.frames = frames
        self.taps: list[tuple[int, int]] = []

    async def capture(self) -> Frame:
        return self.frames.pop(0) if len(self.frames) > 1 else self.frames[0]

    async def tap(self, x: int, y: int, hold: float = 0.15) -> None:
        self.taps.append((x, y))


def test_no_back_tap_during_toggle_animation() -> None:
    off = load_png(FIXTURES / "holiday_off.png")
    on = load_png(FIXTURES / "holiday_on.png")
    # Mid-animation frame: knob neither clearly on nor off -> unknown screen.
    mid = bytearray(off.bgrx)
    o = (111 * 800 + 740) * 4
    mid[o : o + 3] = bytes((128, 128, 128))
    mid_frame = Frame(800, 480, bytes(mid))
    assert navigator.classify(mid_frame) is navigator.Screen.UNKNOWN

    home = load_png(FIXTURES / "home.png")
    vnc = FakeVnc([off, off, mid_frame, on, home])
    result = _run(
        navigator.set_holiday_mode(vnc, True, settle=0, return_home=True)
    )
    assert result is True
    assert vnc.taps == [navigator.TAP_TOGGLE]


def test_login_screen_aborts_without_tapping() -> None:
    login = load_png(FIXTURES / "login.png")
    vnc = FakeVnc([login])
    with pytest.raises(navigator.NavigationError, match="login"):
        _run(navigator.set_holiday_mode(vnc, True, settle=0))
    assert vnc.taps == []


def test_no_action_on_unstable_frame() -> None:
    """A single transitional frame must not trigger a tap for that screen."""
    menu = load_png(FIXTURES / "menu.png")
    functions = load_png(FIXTURES / "functions.png")
    holiday = load_png(FIXTURES / "holiday_on.png")
    home = load_png(FIXTURES / "home.png")
    # Stale "functions" frame directly followed by the real menu: the
    # navigator must tap "Functions" (menu), never the holiday row.
    vnc = FakeVnc([functions, menu, menu, functions, functions, holiday, holiday, home])
    _run(navigator.set_holiday_mode(vnc, True, settle=0))
    assert vnc.taps[0] == navigator.TAP_FUNCTIONS


def test_keyboard_layout_positions() -> None:
    assert navigator.LETTER_KEYS["q"] == (49, 193)
    assert navigator.LETTER_KEYS["a"] == (49, 271)
    assert navigator.LETTER_KEYS["m"] == (609, 350)
    assert navigator.NUMERIC_KEYS["0"] == (679, 193)
    assert navigator.unsupported_code_chars("abc123") == set()
    assert navigator.unsupported_code_chars("ab#") == {"#"}


def test_keyboard_screens_detected() -> None:
    assert navigator.keyboard_open(load_png(FIXTURES / "login_keyboard.png"))
    assert navigator.keyboard_open(load_png(FIXTURES / "login_keyboard_numeric.png"))
    assert navigator.login_form_shown(load_png(FIXTURES / "login.png"))
    assert not navigator.login_form_shown(load_png(FIXTURES / "home.png"))


def test_unlock_types_code_and_presses_login() -> None:
    login = load_png(FIXTURES / "login.png")
    kbd = load_png(FIXTURES / "login_keyboard.png")
    home = load_png(FIXTURES / "home.png")
    vnc = FakeVnc([kbd, login, home])
    _run(navigator.unlock(vnc, "aB1", settle=0))
    taps = vnc.taps
    assert taps[0] == navigator.TAP_CODE_FIELD
    typed = [t for t in taps[1:] if t != navigator.TAP_KBD_BACKSPACE]
    assert typed == [
        navigator.LETTER_KEYS["a"],
        navigator.TAP_KBD_SHIFT,
        navigator.LETTER_KEYS["b"],
        navigator.TAP_KBD_SWITCH,
        navigator.NUMERIC_KEYS["1"],
        navigator.TAP_KBD_DONE,
        navigator.TAP_LOGIN_BUTTON,
    ]


def test_rejected_code_is_tried_only_once() -> None:
    login = load_png(FIXTURES / "login.png")
    kbd = load_png(FIXTURES / "login_keyboard.png")
    vnc = FakeVnc([login, login, kbd, login])
    with pytest.raises(navigator.NavigationError, match="not accepted"):
        _run(navigator.set_holiday_mode(vnc, True, settle=0, code="abc"))
    assert vnc.taps.count(navigator.TAP_LOGIN_BUTTON) == 1
    assert navigator.TAP_TOGGLE not in vnc.taps

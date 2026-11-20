"""Test the integration logic against a Perla without Home Assistant.

Usage:
    python scripts/perla_cli.py HOST status          (needs PERLA_CODE env var)
    python scripts/perla_cli.py HOST screen          (classify current screen)
    python scripts/perla_cli.py HOST screenshot out.png
    python scripts/perla_cli.py HOST on|off          (switch holiday mode!)
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import types

PKG = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "bwt_perla_holiday"
_pkg = types.ModuleType("perla")
_pkg.__path__ = [str(PKG)]
sys.modules["perla"] = _pkg

from perla import navigator  # noqa: E402
from perla.vnc import PerlaVnc  # noqa: E402


async def status(host: str) -> None:
    import aiohttp

    from perla.api import PerlaApi, holiday_active

    code = os.environ.get("PERLA_CODE")
    if not code:
        sys.exit("Set PERLA_CODE to the device login code")
    async with aiohttp.ClientSession() as session:
        data = await PerlaApi(session, host, code).current_data()
    print("firmware:", data.get("FirmwareVersion"))
    print("HolidayModeStartTime:", data.get("HolidayModeStartTime"))
    print("holiday mode active:", holiday_active(data))


async def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    host, cmd = sys.argv[1], sys.argv[2]
    if cmd == "status":
        await status(host)
        return
    async with PerlaVnc(host) as vnc:
        print(f"VNC: {vnc.name} {vnc.width}x{vnc.height}")
        if cmd == "screen":
            frame = await vnc.capture()
            print("screen:", navigator.classify(frame).value)
            if navigator.classify(frame) is navigator.Screen.HOLIDAY:
                print("toggle:", navigator.toggle_state(frame))
        elif cmd == "screenshot":
            frame = await vnc.capture()
            pathlib.Path(sys.argv[3]).write_bytes(frame.to_png())
            print("saved", sys.argv[3])
        elif cmd in ("on", "off"):
            result = await navigator.set_holiday_mode(vnc, cmd == "on")
            print("holiday mode now:", "on" if result else "off")
        else:
            sys.exit(__doc__)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO)
    asyncio.run(main())

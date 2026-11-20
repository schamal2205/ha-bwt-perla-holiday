"""Client for the read-only local BWT Perla HTTP API (port 8080)."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import aiohttp

DEFAULT_API_PORT = 8080


class PerlaApiError(Exception):
    """Generic API error."""


class PerlaAuthError(PerlaApiError):
    """Wrong login code or local API disabled."""


class PerlaApi:
    """Read current data from the Perla.

    The firmware answers unauthenticated requests with an empty 404, so a
    wrong code and a disabled API look the same.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        code: str,
        port: int = DEFAULT_API_PORT,
    ) -> None:
        self._session = session
        self._base = f"http://{host}:{port}/api/"
        self._auth = aiohttp.BasicAuth("user", code)

    async def _get(self, endpoint: str) -> dict[str, Any]:
        try:
            async with self._session.get(
                self._base + endpoint,
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (401, 403, 404):
                    raise PerlaAuthError(
                        f"HTTP {resp.status}: wrong login code or local API disabled"
                    )
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except PerlaApiError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise PerlaApiError(str(err)) from err

    async def current_data(self) -> dict[str, Any]:
        """Return GetCurrentData."""
        return await self._get("GetCurrentData")


def _start_value(data: dict[str, Any]) -> int:
    try:
        return int(data.get("HolidayModeStartTime", 0))
    except (TypeError, ValueError):
        return 0


def holiday_active(data: dict[str, Any], now: float | None = None) -> bool:
    """Whether holiday mode (water shut-off) is active right now.

    HolidayModeStartTime is 0 when off, 1 when switched on immediately, and
    a Unix timestamp when a start was scheduled (e.g. in the BWT app).
    """
    value = _start_value(data)
    if value <= 0:
        return False
    if value == 1:
        return True
    return value <= (time.time() if now is None else now)


def holiday_scheduled_start(
    data: dict[str, Any], now: float | None = None
) -> datetime | None:
    """Return the scheduled (future) start of holiday mode, if any."""
    value = _start_value(data)
    if value > 1 and value > (time.time() if now is None else now):
        return datetime.fromtimestamp(value, tz=UTC)
    return None

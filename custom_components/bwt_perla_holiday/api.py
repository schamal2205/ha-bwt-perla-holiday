"""Client for the read-only local BWT Perla HTTP API (port 8080)."""

from __future__ import annotations

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


def holiday_active(data: dict[str, Any]) -> bool:
    """Holiday mode is active when HolidayModeStartTime is non-zero."""
    try:
        return int(data.get("HolidayModeStartTime", 0)) != 0
    except (TypeError, ValueError):
        return False

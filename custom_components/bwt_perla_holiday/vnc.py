"""Minimal asyncio RFB (VNC) client for the BWT Perla touch display.

The Perla runs a "Qt for Embedded Linux VNC Server" on port 5900 without
authentication. This client only implements what is needed to read the
framebuffer (Raw encoding, 32 bpp) and to send pointer (touch) events.
It has no third-party dependencies.
"""

from __future__ import annotations

import asyncio
import struct
import zlib
from dataclasses import dataclass

DEFAULT_VNC_PORT = 5900

# RFB message types (server -> client)
_MSG_FB_UPDATE = 0
_MSG_COLORMAP = 1
_MSG_BELL = 2
_MSG_CUT_TEXT = 3

_SEC_NONE = 1


class VncError(Exception):
    """Raised when the VNC connection or protocol fails."""


@dataclass(slots=True)
class Frame:
    """A captured framebuffer in BGRX byte order (32 bpp, little endian)."""

    width: int
    height: int
    bgrx: bytes

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        """Return the (r, g, b) value of a pixel."""
        o = (y * self.width + x) * 4
        b = self.bgrx
        return b[o + 2], b[o + 1], b[o]

    def to_rgb(self) -> bytes:
        """Return the frame as packed RGB888."""
        n = self.width * self.height
        rgb = bytearray(n * 3)
        rgb[0::3] = self.bgrx[2::4]
        rgb[1::3] = self.bgrx[1::4]
        rgb[2::3] = self.bgrx[0::4]
        return bytes(rgb)

    def to_png(self) -> bytes:
        """Encode the frame as PNG (CPU bound, run in an executor)."""
        rgb = self.to_rgb()
        stride = self.width * 3
        raw = b"".join(
            b"\x00" + rgb[r * stride : (r + 1) * stride] for r in range(self.height)
        )

        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b"")
        )


class PerlaVnc:
    """Async VNC session. Use as ``async with PerlaVnc(host) as vnc:``."""

    def __init__(
        self, host: str, port: int = DEFAULT_VNC_PORT, timeout: float = 10.0
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.width = 0
        self.height = 0
        self.name = ""
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def __aenter__(self) -> PerlaVnc:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _read(self, n: int) -> bytes:
        assert self._reader is not None
        try:
            return await asyncio.wait_for(
                self._reader.readexactly(n), timeout=self.timeout
            )
        except asyncio.IncompleteReadError as err:
            raise VncError("Connection closed by VNC server") from err
        except TimeoutError as err:
            raise VncError("Timeout while reading from VNC server") from err

    async def _send(self, data: bytes) -> None:
        assert self._writer is not None
        self._writer.write(data)
        await self._writer.drain()

    async def connect(self) -> None:
        """Open the connection and perform the RFB handshake."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout
            )
        except (OSError, TimeoutError) as err:
            raise VncError(f"Cannot connect to {self.host}:{self.port}: {err}") from err

        version = await self._read(12)
        if not version.startswith(b"RFB "):
            raise VncError(f"Not a VNC server: {version!r}")
        try:
            minor = int(version[8:11])
            major = int(version[4:7])
        except ValueError as err:
            raise VncError(f"Bad RFB version {version!r}") from err

        if (major, minor) >= (3, 7):
            use_minor = 8 if minor >= 8 else 7
            await self._send(b"RFB 003.%03d\n" % use_minor)
            count = (await self._read(1))[0]
            if count == 0:
                reason_len = struct.unpack(">I", await self._read(4))[0]
                reason = await self._read(reason_len)
                raise VncError(f"VNC server refused connection: {reason!r}")
            types = list(await self._read(count))
            if _SEC_NONE not in types:
                raise VncError(
                    f"VNC server requires authentication (types {types}); "
                    "only unauthenticated VNC is supported"
                )
            await self._send(bytes([_SEC_NONE]))
            if use_minor >= 8:
                result = struct.unpack(">I", await self._read(4))[0]
                if result != 0:
                    raise VncError("VNC security handshake failed")
        else:
            await self._send(b"RFB 003.003\n")
            sec = struct.unpack(">I", await self._read(4))[0]
            if sec != _SEC_NONE:
                raise VncError(
                    f"VNC server requires authentication (type {sec}); "
                    "only unauthenticated VNC is supported"
                )

        await self._send(b"\x01")  # ClientInit: shared session
        init = await self._read(24)
        self.width, self.height = struct.unpack(">HH", init[:4])
        name_len = struct.unpack(">I", init[20:24])[0]
        self.name = (await self._read(name_len)).decode(errors="replace")

        # SetPixelFormat: 32bpp, depth 24, little endian, true colour, R<<16 G<<8 B
        await self._send(
            struct.pack(
                ">BxxxBBBBHHHBBBxxx", 0, 32, 24, 0, 1, 255, 255, 255, 16, 8, 0
            )
        )
        # SetEncodings: Raw only
        await self._send(struct.pack(">BxHi", 2, 1, 0))

    async def close(self) -> None:
        """Close the connection."""
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        self._reader = self._writer = None

    async def capture(self) -> Frame:
        """Request and return a full framebuffer."""
        w, h = self.width, self.height
        await self._send(struct.pack(">BBHHHH", 3, 0, 0, 0, w, h))
        buf = bytearray(w * h * 4)
        covered = 0
        while covered < w * h:
            msg_type = (await self._read(1))[0]
            if msg_type == _MSG_FB_UPDATE:
                await self._read(1)
                rects = struct.unpack(">H", await self._read(2))[0]
                for _ in range(rects):
                    x, y, rw, rh, enc = struct.unpack(">HHHHi", await self._read(12))
                    if enc != 0:
                        raise VncError(f"Unexpected encoding {enc}")
                    data = await self._read(rw * rh * 4)
                    row = rw * 4
                    for r in range(rh):
                        o = ((y + r) * w + x) * 4
                        buf[o : o + row] = data[r * row : (r + 1) * row]
                    covered += rw * rh
            elif msg_type == _MSG_BELL:
                continue
            elif msg_type == _MSG_CUT_TEXT:
                await self._read(3)
                length = struct.unpack(">I", await self._read(4))[0]
                await self._read(length)
            elif msg_type == _MSG_COLORMAP:
                await self._read(1)
                _first, count = struct.unpack(">HH", await self._read(4))
                await self._read(count * 6)
            else:
                raise VncError(f"Unknown server message type {msg_type}")
        return Frame(w, h, bytes(buf))

    async def tap(self, x: int, y: int, hold: float = 0.15) -> None:
        """Simulate a short touch at (x, y)."""
        await self._send(struct.pack(">BBHH", 5, 0, x, y))
        await asyncio.sleep(0.05)
        await self._send(struct.pack(">BBHH", 5, 1, x, y))
        await asyncio.sleep(hold)
        await self._send(struct.pack(">BBHH", 5, 0, x, y))

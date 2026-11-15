"""A fake camera: what a printer without a video stream serves its images on."""

from __future__ import annotations

import asyncio
import contextlib
import struct
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import ssl
    from types import TracebackType

LOGIN_SIZE = 80


def jpeg(content: bytes) -> bytes:
    """Return something that starts and ends like a JPEG image."""
    return b"\xff\xd8\xff\xe0" + content + b"\xff\xd9"


def frame(image: bytes) -> bytes:
    """Return an image the way the camera sends it."""
    return struct.pack("<IIII", len(image), 0, 1, 0) + image


class FakeCamera:
    """A camera that listens on localhost."""

    def __init__(
        self,
        access_code: str,
        ssl_context: ssl.SSLContext,
        *,
        frames: list[bytes],
        interval: float = 0.01,
    ) -> None:
        """Initialize the camera, which sends the frames over and over."""
        self.access_code = access_code
        self.frames = frames
        self.interval = interval
        self.connections = 0
        self.clients = 0
        self.port = 0
        self._ssl_context = ssl_context
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> Self:
        """Start the camera."""
        self._server = await asyncio.start_server(
            self._handle_client, "127.0.0.1", 0, ssl=self._ssl_context
        )
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the camera."""
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Send images to a client that logs in, until it leaves."""
        self.connections += 1
        self.clients += 1
        try:
            login = await reader.readexactly(LOGIN_SIZE)
            size, kind, username, password = struct.unpack("<II8x32s32s", login)
            accepted = (
                (size, kind) == (0x40, 0x3000)
                and username.rstrip(b"\x00") == b"bblp"
                and password.rstrip(b"\x00") == self.access_code.encode()
            )
            # Like a printer, send nothing when the frames ran out.
            while accepted and not reader.at_eof():
                for data in self.frames:
                    writer.write(data)
                    await writer.drain()
                    await asyncio.sleep(self.interval)
                await asyncio.sleep(self.interval)
        except (asyncio.IncompleteReadError, OSError):
            pass
        finally:
            self.clients -= 1
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

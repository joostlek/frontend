"""Images of the camera of a printer that has no video stream.

These printers send JPEG images over a connection of their own, one every
second or two. The connection takes a while to set up, so it stays open for as
long as images are asked for.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import struct
from typing import TYPE_CHECKING, Final

from .const import CAMERA_IDLE_TIMEOUT, CAMERA_PORT, MQTT_USERNAME
from .exceptions import (
    BambuLabCertificateError,
    BambuLabConnectionError,
    BambuLabError,
    BambuLabSerialMismatchError,
)
from .tls import VERIFY_CODE_HOSTNAME_MISMATCH

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)

_HEADER_SIZE: Final = 16
# An image is about 100 kB. Anything far beyond that is not an image.
_MAX_IMAGE_SIZE: Final = 10_000_000
_JPEG_START: Final = b"\xff\xd8"
_JPEG_END: Final = b"\xff\xd9"


def _login(access_code: str) -> bytes:
    """Return the packet that opens the stream of images."""
    return struct.pack(
        "<IIII32s32s",
        0x40,
        0x3000,
        0,
        0,
        MQTT_USERNAME.encode(),
        access_code.encode(),
    )


class CameraImages:
    """The images of the camera of a printer."""

    def __init__(
        self,
        host: str,
        serial: str,
        access_code: str,
        get_ssl_context: Callable[[], Awaitable[ssl.SSLContext]],
        timeout: float,
    ) -> None:
        """Initialize the images. Nothing connects until one is asked for."""
        self._host = host
        self._serial = serial
        self._access_code = access_code
        self._get_ssl_context = get_ssl_context
        self._timeout = timeout

        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._image: bytes | None = None
        self._error: BambuLabError | None = None
        self._last_request = 0.0

    async def image(self) -> bytes:
        """Return the most recent image, and connect when that is needed."""
        loop = asyncio.get_running_loop()
        self._last_request = loop.time()
        if self._task is None or self._task.done():
            self._image = None
            self._error = None
            self._ready.clear()
            self._task = loop.create_task(
                self._run(), name=f"aiobambulab camera {self._serial}"
            )
        await self._ready.wait()
        if self._image is None:
            raise self._error or BambuLabConnectionError("The camera sent no image")
        return self._image

    async def close(self) -> None:
        """Close the connection to the camera."""
        if (task := self._task) is None:
            return
        self._task = None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        """Receive images, until nobody asks for them anymore."""
        error: BambuLabError = BambuLabConnectionError(
            "The printer closed the connection to the camera"
        )
        try:
            await self._receive()
        except ssl.SSLCertVerificationError as err:
            if err.verify_code == VERIFY_CODE_HOSTNAME_MISMATCH:
                error = BambuLabSerialMismatchError(
                    "The certificate of the printer is for another serial number"
                )
            else:
                error = BambuLabCertificateError(
                    f"The certificate is not issued by Bambu Lab: {err.verify_message}"
                )
        except TimeoutError:
            error = BambuLabConnectionError("The camera did not answer in time")
        except asyncio.IncompleteReadError:
            # The printer closes the connection, also for a wrong access code.
            pass
        except (OSError, ValueError) as err:
            error = BambuLabConnectionError(str(err))
        finally:
            _LOGGER.debug("Camera of printer %s stopped: %s", self._serial, error)
            self._image = None
            self._error = error
            # Never leave the caller of image() waiting.
            self._ready.set()

    async def _receive(self) -> None:
        """Connect to the camera, and keep the most recent image."""
        loop = asyncio.get_running_loop()
        context = await self._get_ssl_context()
        async with asyncio.timeout(self._timeout):
            reader, writer = await asyncio.open_connection(
                self._host, CAMERA_PORT, ssl=context, server_hostname=self._serial
            )
        try:
            writer.write(_login(self._access_code))
            while loop.time() - self._last_request < CAMERA_IDLE_TIMEOUT:
                async with asyncio.timeout(self._timeout):
                    header = await reader.readexactly(_HEADER_SIZE)
                    size = int.from_bytes(header[:4], "little")
                    if size > _MAX_IMAGE_SIZE:
                        msg = f"The camera announced an image of {size} bytes"
                        raise ValueError(msg)
                    image = await reader.readexactly(size)
                if image.startswith(_JPEG_START) and image.endswith(_JPEG_END):
                    self._image = image
                    self._ready.set()
        finally:
            writer.close()

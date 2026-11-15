"""Tests for the camera of a printer, against a fake camera."""

from __future__ import annotations

import asyncio
import struct
from typing import TYPE_CHECKING

import pytest

from aiobambulab import (
    BambuLabCertificateError,
    BambuLabClient,
    BambuLabConnectionError,
    BambuLabSerialMismatchError,
)

from .conftest import (
    ACCESS_CODE,
    SERIAL,
    CertificateAuthority,
    client_ssl_context,
    load_fixture,
)
from .fake_camera import FakeCamera, frame, jpeg
from .test_client import status, wait_for

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    import ssl

    from .fake_printer import FakePrinter

FIRST = jpeg(b"first")
SECOND = jpeg(b"second")


@pytest.fixture
async def camera(
    printer_ssl_context: ssl.SSLContext, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FakeCamera]:
    """Return a running camera that sends one image."""
    async with FakeCamera(
        ACCESS_CODE, printer_ssl_context, frames=[frame(FIRST)]
    ) as camera:
        monkeypatch.setattr("aiobambulab.camera.CAMERA_PORT", camera.port)
        yield camera


async def test_camera_image(camera: FakeCamera, client: BambuLabClient) -> None:
    """The client returns the most recent image, over one connection."""
    assert await client.camera_image() == FIRST

    camera.frames = [frame(SECOND)]
    await wait_for(lambda: client._camera._image == SECOND)

    assert await client.camera_image() == SECOND
    assert camera.connections == 1


async def test_camera_image_without_the_printer(
    camera: FakeCamera, ssl_context: ssl.SSLContext
) -> None:
    """An image does not need the connection that follows the printer."""
    client = BambuLabClient("127.0.0.1", SERIAL, ACCESS_CODE, ssl_context=ssl_context)

    assert await client.camera_image() == FIRST

    await client.disconnect()
    await wait_for(lambda: camera.clients == 0)


async def test_camera_images_at_the_same_time(
    camera: FakeCamera, client: BambuLabClient
) -> None:
    """Two requests at the same time share one connection."""
    images = await asyncio.gather(client.camera_image(), client.camera_image())

    assert list(images) == [FIRST, FIRST]
    assert camera.connections == 1


async def test_camera_skips_what_is_not_an_image(
    camera: FakeCamera, client: BambuLabClient
) -> None:
    """The client only keeps what looks like a JPEG image."""
    camera.frames = [frame(b"not an image"), frame(FIRST), frame(b"\xff\xd8 cut off")]

    assert await client.camera_image() == FIRST
    await asyncio.sleep(0.1)
    assert await client.camera_image() == FIRST


async def test_camera_closes_when_idle(
    camera: FakeCamera, client: BambuLabClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The connection closes when nobody asks for images, and opens again."""
    monkeypatch.setattr("aiobambulab.camera.CAMERA_IDLE_TIMEOUT", 0.05)

    assert await client.camera_image() == FIRST
    await wait_for(lambda: camera.clients == 0)

    camera.frames = [frame(SECOND)]

    assert await client.camera_image() == SECOND
    assert camera.connections == 2


async def test_camera_closes_on_disconnect(
    camera: FakeCamera, printer: FakePrinter, client: BambuLabClient
) -> None:
    """Disconnecting from the printer also closes the connection to the camera."""
    await client.connect()
    await client.camera_image()
    assert camera.clients == 1

    await client.disconnect()

    await wait_for(lambda: camera.clients == 0)
    assert printer.connections == 1


async def test_camera_with_wrong_access_code(
    camera: FakeCamera, ssl_context: ssl.SSLContext
) -> None:
    """A printer closes the connection to a client with a wrong access code."""
    client = BambuLabClient("127.0.0.1", SERIAL, "87654321", ssl_context=ssl_context)

    with pytest.raises(BambuLabConnectionError, match="closed the connection"):
        await client.camera_image()

    # The next request tries again.
    with pytest.raises(BambuLabConnectionError):
        await client.camera_image()
    assert camera.connections == 2


async def test_camera_that_sends_nothing(
    camera: FakeCamera, ssl_context: ssl.SSLContext
) -> None:
    """The client gives up on a camera that sends no image."""
    camera.frames = []
    client = BambuLabClient(
        "127.0.0.1", SERIAL, ACCESS_CODE, ssl_context=ssl_context, timeout=0.2
    )

    with pytest.raises(BambuLabConnectionError, match="did not answer in time"):
        await client.camera_image()


async def test_camera_that_sends_nonsense(
    camera: FakeCamera, client: BambuLabClient
) -> None:
    """The client does not wait for an image that is impossibly large."""
    camera.frames = [struct.pack("<IIII", 0x7FFFFFFF, 0, 1, 0)]

    with pytest.raises(BambuLabConnectionError, match="2147483647 bytes"):
        await client.camera_image()


async def test_camera_that_is_not_there(
    printer_ssl_context: ssl.SSLContext,
    client: BambuLabClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client tells when nothing listens where the camera should be."""
    async with FakeCamera(ACCESS_CODE, printer_ssl_context, frames=[]) as camera:
        port = camera.port
    monkeypatch.setattr("aiobambulab.camera.CAMERA_PORT", port)

    with pytest.raises(BambuLabConnectionError):
        await client.camera_image()


async def test_camera_of_another_printer(
    camera: FakeCamera, ca: CertificateAuthority
) -> None:
    """The client does not send the access code to the camera of another printer."""
    client = BambuLabClient(
        "127.0.0.1",
        "01P00A999999999",
        ACCESS_CODE,
        ssl_context=client_ssl_context(ca, "01P00A999999999"),
    )

    with pytest.raises(BambuLabSerialMismatchError):
        await client.camera_image()

    assert camera.clients == 0


async def test_camera_with_untrusted_certificate(
    other_ca: CertificateAuthority,
    ssl_context: ssl.SSLContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client does not talk to a camera with a certificate of someone else."""
    async with FakeCamera(
        ACCESS_CODE, other_ca.issue(SERIAL), frames=[frame(FIRST)]
    ) as camera:
        monkeypatch.setattr("aiobambulab.camera.CAMERA_PORT", camera.port)
        client = BambuLabClient(
            "127.0.0.1", SERIAL, ACCESS_CODE, ssl_context=ssl_context
        )

        with pytest.raises(BambuLabCertificateError) as exc_info:
            await client.camera_image()

    assert not isinstance(exc_info.value, BambuLabSerialMismatchError)


@pytest.mark.usefixtures("camera")
async def test_camera_with_the_default_tls_context(
    ca: CertificateAuthority, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a TLS context, the client creates one for the serial number."""
    monkeypatch.setattr("aiobambulab.tls.CA_FILE", ca.path)
    client = BambuLabClient("127.0.0.1", SERIAL, ACCESS_CODE)

    assert await client.camera_image() == FIRST

    await client.disconnect()


@pytest.mark.usefixtures("printer")
async def test_supports_camera_images(client: BambuLabClient) -> None:
    """A printer without a video stream sends images of its camera."""
    assert not client.supports_camera_images

    await client.connect()

    assert client.supports_camera_images
    assert client.state.camera_stream_enabled is None
    assert client.camera_stream_url is None


async def test_camera_stream(printer: FakePrinter, client: BambuLabClient) -> None:
    """A printer with a video stream tells whether it serves it."""
    printer.version = load_fixture("h2d_version.json")
    printer.status = load_fixture("h2d_status.json")
    printer.status["print"]["ipcam"] = {"ipcam_dev": "1", "rtsp_url": "disable"}
    await client.connect()

    assert not client.supports_camera_images
    assert client.state.camera_stream_enabled is False
    assert client.camera_stream_url is None

    printer.push(
        status(ipcam={"rtsp_url": "rtsps://192.168.1.50:322/streaming/live/1"})
    )
    await wait_for(lambda: client.state.camera_stream_enabled is True)

    assert (
        client.camera_stream_url
        == "rtsps://bblp:12345678@127.0.0.1:322/streaming/live/1"
    )


@pytest.mark.parametrize(
    ("host", "access_code", "url"),
    [
        (
            "printer.local",
            "ab/c@d:e",
            "rtsps://bblp:ab%2Fc%40d%3Ae@printer.local:322/streaming/live/1",
        ),
        (
            "fd00::50",
            "12345678",
            "rtsps://bblp:12345678@[fd00::50]:322/streaming/live/1",
        ),
    ],
)
def test_camera_stream_url(host: str, access_code: str, url: str) -> None:
    """The address of the stream is one that can be used as it is."""
    client = BambuLabClient(host, SERIAL, access_code)
    client._state = client._state.from_report(
        {"ipcam": {"rtsp_url": "rtsps://192.168.1.50/streaming/live/1"}}
    )

    assert client.camera_stream_url == url

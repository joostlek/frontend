"""Tests for finding printers on the network."""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING

import pytest

from aiobambulab import BambuLabConnectionError, DiscoveredPrinter, discover

from .conftest import SERIAL

if TYPE_CHECKING:
    from collections.abc import Iterator

ANNOUNCEMENT = (
    "NOTIFY * HTTP/1.1\r\n"
    "HOST: 239.255.255.250:1990\r\n"
    "Server: UPnP/1.0\r\n"
    "Location: {host}\r\n"
    "NT: urn:bambulab-com:device:3dprinter:1\r\n"
    "NTS: ssdp:alive\r\n"
    "USN: {serial}\r\n"
    "Cache-Control: max-age=1800\r\n"
    "DevModel.bambu.com: C12\r\n"
    "DevName.bambu.com: {name}\r\n"
    "DevConnect.bambu.com: lan\r\n"
    "DevBind.bambu.com: free\r\n"
    "\r\n"
)


def announcement(
    serial: str = SERIAL, host: str = "192.168.1.50", name: str = "3DP-01P-001"
) -> bytes:
    """Return what a printer announces itself with."""
    return ANNOUNCEMENT.format(serial=serial, host=host, name=name).encode()


@pytest.fixture
def port(monkeypatch: pytest.MonkeyPatch) -> int:
    """Return a free port to listen for printers on."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
    monkeypatch.setattr("aiobambulab.discovery.DISCOVERY_PORT", port)
    return port


@pytest.fixture
def sender() -> Iterator[socket.socket]:
    """Return a socket to announce printers with."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        yield sock


async def listening() -> None:
    """Give the listener a moment to start."""
    await asyncio.sleep(0.05)


async def test_discover(port: int, sender: socket.socket) -> None:
    """The printers that announce themselves are found."""
    discovery = asyncio.create_task(discover(2, settle=0.1))
    await listening()

    sender.sendto(announcement(), ("127.0.0.1", port))
    sender.sendto(
        announcement("01p00a000000002", "192.168.1.51", "Workshop"),
        ("127.0.0.1", port),
    )
    # A printer keeps announcing itself.
    sender.sendto(announcement(), ("127.0.0.1", port))

    assert await discovery == [
        DiscoveredPrinter(serial=SERIAL, host="192.168.1.50", name="3DP-01P-001"),
        DiscoveredPrinter(
            serial="01P00A000000002", host="192.168.1.51", name="Workshop"
        ),
    ]


async def test_discover_stops_after_the_last_printer(
    port: int, sender: socket.socket
) -> None:
    """Listening does not take the full time once a printer is found."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    discovery = asyncio.create_task(discover(30, settle=0.1))
    await listening()

    sender.sendto(announcement(), ("127.0.0.1", port))

    assert len(await discovery) == 1
    assert loop.time() - started < 5


@pytest.mark.usefixtures("port")
async def test_discover_nothing() -> None:
    """Listening ends at the timeout when no printer announces itself."""
    assert await discover(0.1) == []


async def test_discover_takes_the_new_address(port: int, sender: socket.socket) -> None:
    """A printer that moved is found at its new address."""
    discovery = asyncio.create_task(discover(2, settle=0.1))
    await listening()

    sender.sendto(announcement(host="192.168.1.50"), ("127.0.0.1", port))
    sender.sendto(announcement(host="192.168.1.99"), ("127.0.0.1", port))

    assert [printer.host for printer in await discovery] == ["192.168.1.99"]


@pytest.mark.parametrize(
    ("data", "printer"),
    [
        pytest.param(
            announcement(host="not an address", name=""),
            DiscoveredPrinter(serial=SERIAL, host="127.0.0.1"),
            id="uses_the_sender_without_a_usable_address",
        ),
        pytest.param(
            b"NOTIFY * HTTP/1.1\r\nNT: urn:bambulab-com:device:3dprinter:1\r\n"
            b"USN: " + SERIAL.encode() + b"\r\n\r\n",
            DiscoveredPrinter(serial=SERIAL, host="127.0.0.1"),
            id="only_what_is_needed",
        ),
    ],
)
async def test_discover_lenient(
    port: int, sender: socket.socket, data: bytes, printer: DiscoveredPrinter
) -> None:
    """A printer that tells less about itself is still found."""
    discovery = asyncio.create_task(discover(2, settle=0.1))
    await listening()

    sender.sendto(data, ("127.0.0.1", port))

    assert await discovery == [printer]


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\xff\xfe\x00", id="not_text"),
        pytest.param(b"hello", id="no_headers"),
        pytest.param(
            b"NOTIFY * HTTP/1.1\r\nNT: upnp:rootdevice\r\nUSN: uuid:1234\r\n\r\n",
            id="another_device",
        ),
        pytest.param(
            b"NOTIFY * HTTP/1.1\r\nNT: urn:bambulab-com:device:3dprinter:1\r\n\r\n",
            id="no_serial",
        ),
    ],
)
async def test_discover_ignores_other_messages(
    port: int, sender: socket.socket, data: bytes
) -> None:
    """What is not the announcement of a printer is ignored."""
    discovery = asyncio.create_task(discover(0.3, settle=0.1))
    await listening()

    sender.sendto(data, ("127.0.0.1", port))

    assert await discovery == []


async def test_discover_twice_at_the_same_time(port: int) -> None:
    """Two can listen at the same time, like a slicer next to this library."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        other.bind(("", port))

        assert await discover(0.1) == []


async def test_discover_when_the_port_is_taken(port: int) -> None:
    """Listening fails when another program keeps the port to itself."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
        other.bind(("", port))

        with pytest.raises(BambuLabConnectionError, match="Cannot listen for printers"):
            await discover(0.1)

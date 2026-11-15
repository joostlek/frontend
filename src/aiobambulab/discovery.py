"""Find Bambu Lab printers on the local network.

A printer announces itself every few seconds, with a message that looks like
SSDP. It is not: it goes to a port of its own, and it lacks what SSDP clients
need to accept it. So this module listens for it itself.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import ipaddress
import logging
import socket
from typing import Final

from .const import DISCOVERY_PORT
from .exceptions import BambuLabConnectionError

_LOGGER = logging.getLogger(__name__)

_NOTIFICATION_TYPE: Final = "urn:bambulab-com:device:3dprinter:1"


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveredPrinter:
    """A printer that announced itself on the network."""

    serial: str
    host: str
    name: str | None = None


def _parse(data: bytes, source: str) -> DiscoveredPrinter | None:
    """Return the printer that sent an announcement, or None if it is not one."""
    headers: dict[str, str] = {}
    for line in data.decode(errors="replace").splitlines()[1:]:
        key, separator, value = line.partition(":")
        if separator:
            headers[key.strip().lower()] = value.strip()
    if headers.get("nt") != _NOTIFICATION_TYPE or not (serial := headers.get("usn")):
        return None
    # The printer tells its address. Trust it only when it is one.
    host = headers.get("location", "")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        host = source
    return DiscoveredPrinter(
        serial=serial.upper(),
        host=host,
        name=headers.get("devname.bambu.com") or None,
    )


class _Listener(asyncio.DatagramProtocol):
    """Collect the printers that announce themselves."""

    def __init__(self) -> None:
        self.printers: dict[str, DiscoveredPrinter] = {}
        self.found = asyncio.Event()

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle an announcement."""
        printer = _parse(data, addr[0])
        if printer is None or self.printers.get(printer.serial) == printer:
            return
        _LOGGER.debug("Found printer %s at %s", printer.serial, printer.host)
        self.printers[printer.serial] = printer
        self.found.set()


def _open_socket() -> socket.socket:
    """Open the socket that announcements arrive on."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Other programs listen for printers as well, like a slicer.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):  # pragma: no branch
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setblocking(False)  # noqa: FBT003
        sock.bind(("", DISCOVERY_PORT))
    except OSError:
        sock.close()
        raise
    return sock


async def discover(
    timeout: float = 15.0,  # noqa: ASYNC109
    *,
    settle: float = 2.0,
) -> list[DiscoveredPrinter]:
    """Listen for printers that announce themselves, and return them.

    Listening stops at the timeout, or earlier, when no new printer showed up
    for `settle` seconds after the first one was found.

    Raises:
        BambuLabConnectionError: The port that printers announce themselves on
            cannot be listened on.

    """
    loop = asyncio.get_running_loop()
    listener = _Listener()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: listener, sock=_open_socket()
        )
    except OSError as err:
        msg = f"Cannot listen for printers: {err}"
        raise BambuLabConnectionError(msg) from err
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(timeout):
                await listener.found.wait()
                while True:
                    listener.found.clear()
                    try:
                        async with asyncio.timeout(settle):
                            await listener.found.wait()
                    except TimeoutError:
                        break
    finally:
        transport.close()
    return list(listener.printers.values())

"""A fake printer: a tiny MQTT broker over TLS that answers like a printer."""

from __future__ import annotations

import asyncio
import contextlib
import json
import struct
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    import ssl
    from types import TracebackType

CONNECT = 1
CONNACK = 2
PUBLISH = 3
SUBSCRIBE = 8
SUBACK = 9
PINGREQ = 12
PINGRESP = 13

CONNACK_ACCEPTED = 0
CONNACK_BAD_CREDENTIALS = 4
CONNACK_NOT_AUTHORIZED = 5


def _packet(kind: int, body: bytes, flags: int = 0) -> bytes:
    """Build an MQTT packet."""
    length = len(body)
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        encoded.append(digit | 0x80 if length else digit)
        if not length:
            break
    return bytes([kind << 4 | flags]) + bytes(encoded) + body


def _text(body: bytes, offset: int) -> tuple[str, int]:
    """Read a length-prefixed text from the body of an MQTT packet."""
    (length,) = struct.unpack_from("!H", body, offset)
    start = offset + 2
    return body[start : start + length].decode(), start + length


class FakePrinter:
    """A printer that listens on localhost."""

    def __init__(
        self,
        serial: str,
        access_code: str,
        ssl_context: ssl.SSLContext,
        *,
        version: dict[str, Any] | None,
        status: dict[str, Any] | None,
        refuse_code: int = CONNACK_NOT_AUTHORIZED,
    ) -> None:
        """Initialize the printer.

        The printer answers a version request with `version`, and a request
        for its status with `status`. It ignores a request when that is None.
        """
        self.serial = serial
        self.access_code = access_code
        self.version = version
        self.status = status
        self.refuse_code = refuse_code
        # Like a printer that is not in developer mode, when False.
        self.accepts_commands = True
        self.requests: list[dict[str, Any]] = []
        self.client_ids: list[str] = []
        self.connections = 0
        self.port = 0
        self._ssl_context = ssl_context
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        """Start to listen, on the port used before if there is one."""
        self._server = await asyncio.start_server(
            self._handle_client, "127.0.0.1", self.port, ssl=self._ssl_context
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop to listen, and drop the clients."""
        if self._server is None:
            return
        self._server.close()
        await self.drop_clients()
        await self._server.wait_closed()
        self._server = None

    async def drop_clients(self) -> None:
        """Close the connections of all clients, like a printer that restarts."""
        for writer in list(self._clients):
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def push(self, message: dict[str, Any] | bytes) -> None:
        """Send a message to the clients, as a report of the printer."""
        payload = message if isinstance(message, bytes) else json.dumps(message)
        if isinstance(payload, str):
            payload = payload.encode()
        topic = f"device/{self.serial}/report".encode()
        packet = _packet(PUBLISH, struct.pack("!H", len(topic)) + topic + payload)
        for writer in self._clients:
            writer.write(packet)

    async def __aenter__(self) -> Self:
        """Start the printer."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stop the printer."""
        await self.stop()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Talk MQTT to a client, until it leaves."""
        self.connections += 1
        try:
            while True:
                kind, flags, body = await self._read_packet(reader)
                if kind == CONNECT:
                    accepted = self._handle_connect(body, writer)
                    await writer.drain()
                    if not accepted:
                        break
                    self._clients.add(writer)
                elif kind == SUBSCRIBE:
                    # Grant QoS 0 for every topic. Only one is ever asked for.
                    writer.write(_packet(SUBACK, body[:2] + b"\x00"))
                elif kind == PUBLISH:
                    self._handle_publish(flags, body)
                elif kind == PINGREQ:
                    writer.write(_packet(PINGRESP, b""))
                else:
                    # DISCONNECT, or something a printer does not support.
                    break
        except (asyncio.IncompleteReadError, OSError):
            pass
        finally:
            self._clients.discard(writer)
            writer.close()

    @staticmethod
    async def _read_packet(reader: asyncio.StreamReader) -> tuple[int, int, bytes]:
        """Read one MQTT packet."""
        (header,) = await reader.readexactly(1)
        length = 0
        shift = 0
        while True:
            (digit,) = await reader.readexactly(1)
            length |= (digit & 0x7F) << shift
            shift += 7
            if not digit & 0x80:
                break
        return header >> 4, header & 0x0F, await reader.readexactly(length)

    def _handle_connect(self, body: bytes, writer: asyncio.StreamWriter) -> bool:
        """Check the credentials of a client, and answer."""
        _, offset = _text(body, 0)
        # Skip the protocol level, the connect flags, and the keep alive.
        offset += 4
        client_id, offset = _text(body, offset)
        self.client_ids.append(client_id)
        username, offset = _text(body, offset)
        password, offset = _text(body, offset)
        accepted = username == "bblp" and password == self.access_code
        code = CONNACK_ACCEPTED if accepted else self.refuse_code
        writer.write(_packet(CONNACK, bytes([0, code])))
        return accepted

    def _handle_publish(self, flags: int, body: bytes) -> None:
        """Handle a request of a client."""
        topic, offset = _text(body, 0)
        if flags & 0x06:
            # Skip the packet identifier of a message with QoS 1 or 2.
            offset += 2
        if topic != f"device/{self.serial}/request":
            return
        request = json.loads(body[offset:])
        self.requests.append(request)
        if "info" in request and self.version is not None:
            self.push(self.version)
        if "pushing" in request and self.status is not None:
            self.push(self.status)
        if (change := self._handle_command(request)) is not None:
            self.push({"print": {"command": "push_status", "msg": 1, **change}})

    def _handle_command(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Do what a command asks, and return what changed."""
        system = request.get("system", {})
        if system.get("command") == "ledctrl":
            light = {"node": system["led_node"], "mode": system["led_mode"]}
            return {"lights_report": [light]}
        if not self.accepts_commands:
            return None
        camera = request.get("camera", {})
        settings = {"ipcam_timelapse": "timelapse", "ipcam_record_set": "ipcam_record"}
        if (setting := settings.get(camera.get("command"))) is not None:
            return {"ipcam": {setting: camera["control"]}}
        command = request.get("print", {})
        if command.get("command") == "gcode_line":
            return self._handle_gcode(command["param"])
        if command.get("command") == "print_speed":
            return {"spd_lvl": int(command["param"])}
        states = {"pause": "PAUSE", "resume": "RUNNING", "stop": "FAILED"}
        if (state := states.get(command.get("command"))) is not None:
            return {"gcode_state": state}
        return None

    @staticmethod
    def _handle_gcode(gcode: str) -> dict[str, Any] | None:
        """Do what a line of G-code asks, for the few codes a test needs."""
        code, *parameters = gcode.split()
        values = {parameter[0]: int(parameter[1:]) for parameter in parameters}
        if code == "M104":
            return {"nozzle_target_temper": values["S"]}
        if code == "M140":
            return {"bed_target_temper": values["S"]}
        if code == "M106":
            fans = {1: "cooling_fan_speed", 2: "big_fan1_speed", 3: "big_fan2_speed"}
            return {fans[values["P"]]: str(round(values["S"] / 255 * 15))}
        return None

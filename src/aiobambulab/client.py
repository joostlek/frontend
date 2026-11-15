"""Client to talk to a Bambu Lab printer on the local network."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
from typing import TYPE_CHECKING, Any, Self

import aiomqtt
from aiomqtt.exceptions import MqttConnectError
from paho.mqtt.reasoncodes import ReasonCode

from .const import (
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    MQTT_KEEPALIVE,
    MQTT_USERNAME,
    RECONNECT_MAX_DELAY,
    RECONNECT_MIN_DELAY,
)
from .exceptions import (
    BambuLabAuthenticationError,
    BambuLabCertificateError,
    BambuLabConnectionError,
    BambuLabError,
    BambuLabSerialMismatchError,
)
from .models import PrinterInfo, PrinterState
from .tls import VERIFY_CODE_HOSTNAME_MISMATCH, create_ssl_context

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

_LOGGER = logging.getLogger(__name__)

# The codes a printer can refuse the access code with: "bad user name or
# password" and "not authorized", as MQTT 3.1.1 and as MQTT 5 reason codes.
_AUTHENTICATION_CODES = frozenset({4, 5, 134, 135})


def _convert_error(err: aiomqtt.MqttError) -> BambuLabError:
    """Convert an error of the MQTT client to an error of this library."""
    if isinstance(err, MqttConnectError):
        code = err.rc.value if isinstance(err.rc, ReasonCode) else err.rc
        if code in _AUTHENTICATION_CODES:
            return BambuLabAuthenticationError("The printer rejected the access code")
    # The MQTT client hides the error of the TLS handshake as the context.
    cause = err.__cause__ or err.__context__
    if isinstance(cause, ssl.SSLCertVerificationError):
        if cause.verify_code == VERIFY_CODE_HOSTNAME_MISMATCH:
            return BambuLabSerialMismatchError(
                "The certificate of the printer is for another serial number"
            )
        return BambuLabCertificateError(
            f"The certificate is not issued by Bambu Lab: {cause.verify_message}"
        )
    return BambuLabConnectionError(str(err))


def _merge(target: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge an update into a report, object by object."""
    for key, value in update.items():
        current = target.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            _merge(current, value)
        else:
            target[key] = value


class BambuLabClient:
    """Client that follows a Bambu Lab printer on the local network.

    The printer pushes its status over MQTT. The client keeps the connection
    open, connects again when it is lost, and tells its listeners when the
    state of the printer changes.
    """

    def __init__(  # noqa: PLR0913
        self,
        host: str,
        serial: str,
        access_code: str,
        *,
        port: int = DEFAULT_PORT,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the client.

        The serial number is not case sensitive: printers use capitals, and
        so does the client. Without `ssl_context`, the client only accepts a
        certificate that Bambu Lab issued to this serial number.
        """
        self._host = host
        self._serial = serial.upper()
        self._access_code = access_code
        self._port = port
        self._ssl_context = ssl_context
        self._timeout = timeout

        self._info = PrinterInfo(serial=self._serial)
        self._state = PrinterState()
        self._available = False
        self._listeners: list[Callable[[], None]] = []

        self._task: asyncio.Task[None] | None = None
        self._first_attempt = asyncio.Event()
        self._error: BambuLabError | None = None
        self._report: dict[str, Any] = {}
        self._has_info = False
        self._has_report = False
        self._sequence_id = 0

    @property
    def serial(self) -> str:
        """Return the serial number of the printer."""
        return self._serial

    @property
    def available(self) -> bool:
        """Return whether the printer is connected and its state is known."""
        return self._available

    @property
    def info(self) -> PrinterInfo:
        """Return what the printer is: its model and its versions."""
        return self._info

    @property
    def state(self) -> PrinterState:
        """Return the last known state of the printer."""
        return self._state

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call the listener when the state or availability of the printer changes.

        Returns a function that removes the listener.
        """
        self._listeners.append(listener)

        def remove_listener() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return remove_listener

    async def connect(self) -> None:
        """Connect to the printer, and wait until its state is known.

        The client then keeps following the printer until `disconnect`.

        Raises:
            BambuLabAuthenticationError: The printer rejected the access code.
            BambuLabSerialMismatchError: The printer has another serial number.
            BambuLabCertificateError: The device is not a Bambu Lab printer.
            BambuLabConnectionError: The printer could not be reached, or it
                did not report its state in time.

        """
        if self._task is not None:
            return
        loop = asyncio.get_running_loop()
        if self._ssl_context is None:
            self._ssl_context = await loop.run_in_executor(
                None, create_ssl_context, self._serial
            )
        self._first_attempt.clear()
        self._error = None
        self._task = loop.create_task(self._run(), name=f"aiobambulab {self._serial}")
        self._task.add_done_callback(self._handle_task_done)
        try:
            async with asyncio.timeout(self._timeout):
                await self._first_attempt.wait()
        except TimeoutError:
            self._error = self._timeout_error()
        except asyncio.CancelledError:
            await self.disconnect()
            raise
        if self._available:
            return
        await self.disconnect()
        raise self._error or BambuLabError(
            "Unexpected error while connecting to the printer"
        )

    def _timeout_error(self) -> BambuLabConnectionError:
        """Return the error for a printer that did not get available in time."""
        if self._has_info:
            return BambuLabConnectionError(
                "The printer did not report its status in time"
            )
        if self._has_report:
            return BambuLabConnectionError(
                "The printer did not report its version in time"
            )
        return BambuLabConnectionError("The printer did not answer in time")

    async def disconnect(self) -> None:
        """Disconnect from the printer."""
        if (task := self._task) is None:
            return
        self._task = None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def __aenter__(self) -> Self:
        """Connect to the printer."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Disconnect from the printer."""
        await self.disconnect()

    async def _run(self) -> None:
        """Keep a connection to the printer open, until cancelled."""
        loop = asyncio.get_running_loop()
        delay = RECONNECT_MIN_DELAY
        try:
            while True:
                started = loop.time()
                error: BambuLabError = BambuLabConnectionError(
                    "The printer closed the connection"
                )
                try:
                    await self._listen()
                except aiomqtt.MqttError as err:
                    error = _convert_error(err)
                self._error = error
                self._set_available(available=False)
                if not self._first_attempt.is_set():
                    # The caller of connect() decides if and when to try again.
                    _LOGGER.debug(
                        "Could not connect to printer %s: %s", self._serial, error
                    )
                    return
                if loop.time() - started > RECONNECT_MAX_DELAY:
                    # The connection held for a while: start over.
                    delay = RECONNECT_MIN_DELAY
                _LOGGER.debug(
                    "Lost the connection to printer %s, next attempt in %.0f s: %s",
                    self._serial,
                    delay,
                    error,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
        finally:
            self._set_available(available=False)
            # Never leave connect() waiting, whatever happened.
            self._first_attempt.set()

    def _handle_task_done(self, task: asyncio.Task[None]) -> None:
        """Report it when the connection ended in a way it never should."""
        if task.cancelled() or (err := task.exception()) is None:
            return
        if self._task is task:
            self._task = None
        _LOGGER.error(
            "Unexpected error in the connection to printer %s",
            self._serial,
            exc_info=err,
        )

    async def _listen(self) -> None:
        """Connect to the printer, and handle what it reports."""
        self._report = {}
        self._has_info = False
        self._has_report = False
        async with aiomqtt.Client(
            hostname=self._host,
            port=self._port,
            username=MQTT_USERNAME,
            password=self._access_code,
            protocol=aiomqtt.ProtocolVersion.V311,
            tls_context=self._ssl_context,
            keepalive=MQTT_KEEPALIVE,
            timeout=self._timeout,
            logger=_LOGGER.getChild("mqtt"),
        ) as mqtt:
            _LOGGER.debug("Connected to printer %s", self._serial)
            await mqtt.subscribe(f"device/{self._serial}/report")
            await self._request(mqtt, "info", {"command": "get_version"})
            await self._request(
                mqtt, "pushing", {"command": "pushall", "version": 1, "push_target": 1}
            )
            async for message in mqtt.messages:
                self._handle_message(message.payload)

    async def _request(
        self, mqtt: aiomqtt.Client, kind: str, request: dict[str, Any]
    ) -> None:
        """Send a request to the printer."""
        self._sequence_id += 1
        payload = {kind: {"sequence_id": str(self._sequence_id), **request}}
        await mqtt.publish(f"device/{self._serial}/request", json.dumps(payload))

    def _handle_message(self, payload: Any) -> None:
        """Handle a message of the printer."""
        try:
            message = json.loads(payload)
        except (TypeError, ValueError):
            _LOGGER.debug("Ignoring a message of %s that is not JSON", self._serial)
            return
        if not isinstance(message, dict):
            return

        info_changed = False
        version = message.get("info")
        if isinstance(version, dict) and version.get("command") == "get_version":
            info = PrinterInfo.from_modules(self._serial, version.get("module"))
            info_changed = info != self._info
            self._info = info
            self._has_info = True
            _LOGGER.debug("Printer %s reported its version: %s", self._serial, info)

        report = message.get("print")
        if isinstance(report, dict) and report.get("command") == "push_status":
            # Some printers only report what changed, so keep what is known.
            _merge(self._report, report)
            # A report without "msg", or with 0, is a complete one.
            if not report.get("msg"):
                self._has_report = True

        if not (self._has_info and self._has_report):
            return
        state = PrinterState.from_report(self._report, self._info.model)
        if self._available and state == self._state and not info_changed:
            return
        self._state = state
        self._error = None
        self._available = True
        self._first_attempt.set()
        self._notify()

    def _set_available(self, *, available: bool) -> None:
        """Set whether the printer is available, and tell the listeners."""
        if self._available == available:
            return
        self._available = available
        self._notify()

    def _notify(self) -> None:
        """Tell the listeners that the printer changed."""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                # A listener that fails must not end the connection.
                _LOGGER.exception("Error in a listener of printer %s", self._serial)

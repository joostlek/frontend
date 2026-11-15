"""Tests for the client of aiobambulab, against a fake printer."""

from __future__ import annotations

import asyncio
import ssl
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock, patch

import aiomqtt
import pytest

from aiobambulab import (
    BambuLabAuthenticationError,
    BambuLabCertificateError,
    BambuLabClient,
    BambuLabConnectionError,
    BambuLabError,
    BambuLabSerialMismatchError,
    PrinterModel,
    PrintState,
)
from aiobambulab.tls import PrinterSSLContext

from .conftest import ACCESS_CODE, SERIAL, CertificateAuthority, load_fixture
from .fake_printer import CONNACK_BAD_CREDENTIALS, CONNACK_NOT_AUTHORIZED, FakePrinter

if TYPE_CHECKING:
    from collections.abc import Callable


async def wait_for(condition: Callable[[], bool]) -> None:
    """Wait until the condition holds."""
    async with asyncio.timeout(5):
        while not condition():
            await asyncio.sleep(0.01)


def status(**values: Any) -> dict[str, Any]:
    """Return a report with only the values that changed."""
    return {"print": {"command": "push_status", "msg": 1, **values}}


def reconnect_delays(caplog: pytest.LogCaptureFixture) -> list[Any]:
    """Return how long the client waited before each new attempt."""
    return [
        record.args[1]
        for record in caplog.records
        if record.name == "aiobambulab.client"
        and isinstance(record.args, tuple)
        and "Lost the connection" in record.getMessage()
    ]


@pytest.fixture(autouse=True)
def fast_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not wait long before connecting again."""
    monkeypatch.setattr("aiobambulab.client.RECONNECT_MIN_DELAY", 0.01)
    monkeypatch.setattr("aiobambulab.client.RECONNECT_MAX_DELAY", 0.04)


async def test_connect(printer: FakePrinter, client: BambuLabClient) -> None:
    """The client knows the printer and its state once it is connected."""
    assert client.serial == SERIAL
    assert not client.available
    assert client.state.print_state is None
    assert client.info.model is None

    await client.connect()

    assert client.available
    assert client.info.model is PrinterModel.P1S
    assert client.info.firmware_version == "01.08.02.00"
    assert client.state.print_state is PrintState.PRINTING
    assert client.state.progress == 42
    assert client.error is None
    # A P1S has no chamber sensor, so the model has to be known.
    assert client.state.chamber_temperature is None
    assert printer.requests == [
        {"info": {"sequence_id": "1", "command": "get_version"}},
        {
            "pushing": {
                "sequence_id": "2",
                "command": "pushall",
                "version": 1,
                "push_target": 1,
            }
        },
    ]


async def test_connect_with_a_serial_in_lower_case(
    printer: FakePrinter, ssl_context: ssl.SSLContext
) -> None:
    """The client uses capitals for the serial number, like the printer does."""
    async with BambuLabClient(
        "127.0.0.1",
        SERIAL.lower(),
        ACCESS_CODE,
        port=printer.port,
        ssl_context=ssl_context,
    ) as client:
        assert client.serial == SERIAL
        assert client.info.serial == SERIAL
        assert client.available


async def test_client_identifier(printer: FakePrinter, client: BambuLabClient) -> None:
    """The client identifies itself in a way every MQTT server accepts."""
    await client.connect()
    await printer.drop_clients()
    await wait_for(lambda: printer.connections == 2 and client.available)

    first, second = printer.client_ids
    assert first == second
    assert first.startswith("aiobambulab")
    assert first.isalnum()
    assert len(first) == 23


async def test_connect_twice(printer: FakePrinter, client: BambuLabClient) -> None:
    """Connecting a connected client does nothing."""
    await client.connect()
    await client.connect()

    assert printer.connections == 1


async def test_context_manager(printer: FakePrinter, client: BambuLabClient) -> None:
    """The client connects and disconnects as a context manager."""
    async with client as entered:
        assert entered is client
        assert client.available

    assert not client.available
    await wait_for(lambda: not printer._clients)


async def test_connect_with_the_default_tls_context(
    printer: FakePrinter, ca: CertificateAuthority, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a TLS context, the client creates one for the serial number."""
    monkeypatch.setattr("aiobambulab.tls.CA_FILE", ca.path)

    async with BambuLabClient(
        "127.0.0.1", SERIAL, ACCESS_CODE, port=printer.port
    ) as client:
        assert client.available


async def test_update(printer: FakePrinter, client: BambuLabClient) -> None:
    """The client merges what changed, and tells its listeners."""
    await client.connect()
    listener = Mock()
    remove_listener = client.add_listener(listener)

    printer.push(status(mc_percent=43, layer_num=97))
    await wait_for(lambda: client.state.progress == 43)

    assert client.state.current_layer == 97
    # What did not change is still known.
    assert client.state.total_layers == 240
    assert client.state.print_state is PrintState.PRINTING
    listener.assert_called_once_with()

    remove_listener()
    # Removing a listener twice is fine.
    remove_listener()
    printer.push(status(mc_percent=44))
    await wait_for(lambda: client.state.progress == 44)

    listener.assert_called_once_with()


async def test_update_of_a_nested_value(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """The client merges a changed value inside an object."""
    printer.version = load_fixture("h2d_version.json")
    printer.status = load_fixture("h2d_status.json")
    await client.connect()
    assert client.state.chamber_temperature == 35

    printer.push(status(device={"ctc": {"info": {"temp": 2293796}}}))
    await wait_for(lambda: client.state.chamber_temperature == 36)

    # The rest of the object is still known.
    assert client._report["device"]["ctc"]["state"] == 0
    assert client._report["device"]["bed"]["info"]["temp"] == 4587590


async def test_update_without_a_change(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """The client does not tell its listeners when nothing they see changed."""
    await client.connect()
    listener = Mock()
    client.add_listener(listener)

    printer.push(status(mc_percent=42, fan_gear=3))
    printer.push(status(mc_percent=43))
    await wait_for(lambda: client.state.progress == 43)

    listener.assert_called_once_with()


async def test_update_of_the_version(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """The client tells its listeners when the firmware changed."""
    await client.connect()
    listener = Mock()
    client.add_listener(listener)
    version = load_fixture("p1s_version.json")
    version["info"]["module"][0]["sw_ver"] = "01.09.00.00"

    printer.push(version)
    await wait_for(lambda: client.info.firmware_version == "01.09.00.00")

    listener.assert_called_once_with()

    printer.push(version)
    printer.push(status(mc_percent=43))
    await wait_for(lambda: client.state.progress == 43)

    assert listener.call_count == 2


@pytest.mark.parametrize(
    "message",
    [
        b"not json",
        b"\xff\xfe",
        b"[1, 2, 3]",
        b'{"print": "busy"}',
        b'{"print": {"command": "pause", "result": "success", "mc_percent": 99}}',
        b'{"info": {"command": "something_else", "module": []}}',
        b'{"system": {"command": "ledctrl", "result": "success"}}',
    ],
)
async def test_ignored_messages(
    printer: FakePrinter, client: BambuLabClient, message: bytes
) -> None:
    """The client ignores what is not a status or a version."""
    await client.connect()
    listener = Mock()
    client.add_listener(listener)
    state = client.state
    info = client.info

    printer.push(message)
    printer.push(status(mc_percent=43))
    await wait_for(lambda: client.state.progress == 43)

    listener.assert_called_once_with()
    assert client.info == info
    assert client.state.print_state is state.print_state


async def test_values_that_are_not_numbers(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """A number that is not one is not known, and does not stop the client."""
    await client.connect()
    assert client.state.bed_temperature == 60
    assert client.state.current_layer == 96

    printer.push(
        b'{"print": {"command": "push_status", "msg": 1, "bed_temper": NaN,'
        b' "layer_num": 1e999, "mc_percent": 43}}'
    )
    await wait_for(lambda: client.state.progress == 43)

    assert client.available
    assert client.state.bed_temperature is None
    assert client.state.current_layer is None


async def test_failing_listener(
    printer: FakePrinter, client: BambuLabClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A listener that fails does not stop the client or other listeners."""
    await client.connect()
    listener = Mock()
    client.add_listener(Mock(side_effect=RuntimeError("Boom")))
    client.add_listener(listener)

    printer.push(status(mc_percent=43))
    await wait_for(lambda: client.state.progress == 43)
    printer.push(status(mc_percent=44))
    await wait_for(lambda: client.state.progress == 44)

    assert listener.call_count == 2
    assert f"Error in a listener of printer {SERIAL}" in caplog.text


async def test_waits_for_a_complete_status(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """The client is not available on changes alone: it needs it all once."""
    complete = printer.status
    printer.status = None
    connect = asyncio.create_task(client.connect())
    await wait_for(lambda: len(printer.requests) == 2)

    printer.push(status(mc_percent=43))
    await asyncio.sleep(0.05)
    assert not connect.done()
    assert not client.available

    assert complete is not None
    printer.push(complete)
    await connect

    assert client.available
    assert client.state.progress == 42


async def test_waits_for_the_version(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """The client is not available before it knows which printer it is."""
    version = printer.version
    printer.version = None
    connect = asyncio.create_task(client.connect())
    await wait_for(lambda: len(printer.requests) == 2)
    await asyncio.sleep(0.05)
    assert not connect.done()

    assert version is not None
    printer.push(version)
    await connect

    assert client.info.model is PrinterModel.P1S
    assert client.state.chamber_temperature is None


@pytest.mark.parametrize("code", [CONNACK_BAD_CREDENTIALS, CONNACK_NOT_AUTHORIZED])
async def test_wrong_access_code(
    printer: FakePrinter, ssl_context: ssl.SSLContext, code: int
) -> None:
    """The client tells when the printer rejects the access code."""
    printer.refuse_code = code
    client = BambuLabClient(
        "127.0.0.1", SERIAL, "87654321", port=printer.port, ssl_context=ssl_context
    )

    with pytest.raises(BambuLabAuthenticationError):
        await client.connect()

    assert not client.available
    assert isinstance(client.error, BambuLabAuthenticationError)
    assert printer.requests == []


async def test_refused_for_another_reason(
    printer: FakePrinter, ssl_context: ssl.SSLContext
) -> None:
    """A printer that refuses the connection for another reason is unreachable."""
    printer.refuse_code = 3
    client = BambuLabClient(
        "127.0.0.1", SERIAL, "87654321", port=printer.port, ssl_context=ssl_context
    )

    with pytest.raises(BambuLabConnectionError) as exc_info:
        await client.connect()

    assert not isinstance(exc_info.value, BambuLabCertificateError)


async def test_wrong_serial(printer: FakePrinter, ca: CertificateAuthority) -> None:
    """The client does not send the access code to another printer."""
    context = PrinterSSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.serial = "01P00A999999999"
    context.load_verify_locations(cafile=ca.path)
    client = BambuLabClient(
        "127.0.0.1",
        "01P00A999999999",
        ACCESS_CODE,
        port=printer.port,
        ssl_context=context,
    )

    with pytest.raises(BambuLabSerialMismatchError):
        await client.connect()

    assert printer.requests == []


async def test_untrusted_certificate(
    other_ca: CertificateAuthority, ssl_context: ssl.SSLContext
) -> None:
    """The client does not talk to a device with a certificate of someone else."""
    async with FakePrinter(
        SERIAL, ACCESS_CODE, other_ca.issue(SERIAL), version=None, status=None
    ) as printer:
        client = BambuLabClient(
            "127.0.0.1", SERIAL, ACCESS_CODE, port=printer.port, ssl_context=ssl_context
        )

        with pytest.raises(BambuLabCertificateError) as exc_info:
            await client.connect()

    assert not isinstance(exc_info.value, BambuLabSerialMismatchError)
    assert printer.requests == []


async def test_bambu_lab_does_not_issue_the_test_certificates(
    printer: FakePrinter,
) -> None:
    """The default TLS context only trusts Bambu Lab."""
    client = BambuLabClient("127.0.0.1", SERIAL, ACCESS_CODE, port=printer.port)

    with pytest.raises(BambuLabCertificateError):
        await client.connect()


async def test_unreachable(printer: FakePrinter, client: BambuLabClient) -> None:
    """The client tells when nothing listens at the address."""
    await printer.stop()

    with pytest.raises(BambuLabConnectionError):
        await client.connect()

    assert not client.available


async def test_no_status(printer: FakePrinter, ssl_context: ssl.SSLContext) -> None:
    """The client gives up when the printer does not report its state."""
    printer.status = None
    client = BambuLabClient(
        "127.0.0.1",
        SERIAL,
        ACCESS_CODE,
        port=printer.port,
        ssl_context=ssl_context,
        timeout=0.3,
    )

    with pytest.raises(BambuLabConnectionError, match="did not report its status"):
        await client.connect()

    assert not client.available
    # The client left, it does not keep trying in the background.
    await wait_for(lambda: not printer._clients)
    assert printer.connections == 1


@pytest.mark.parametrize(
    ("answers_status", "message"),
    [(True, "did not report its version"), (False, "did not answer")],
)
async def test_no_version(
    printer: FakePrinter,
    ssl_context: ssl.SSLContext,
    answers_status: bool,  # noqa: FBT001
    message: str,
) -> None:
    """The client gives up when the printer does not tell what it is."""
    printer.version = None
    if not answers_status:
        printer.status = None
    client = BambuLabClient(
        "127.0.0.1",
        SERIAL,
        ACCESS_CODE,
        port=printer.port,
        ssl_context=ssl_context,
        timeout=0.3,
    )

    with pytest.raises(BambuLabConnectionError, match=message):
        await client.connect()

    assert not client.available


async def test_connect_again_after_a_failure(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """A client that could not connect can try again."""
    await printer.stop()
    with pytest.raises(BambuLabConnectionError):
        await client.connect()

    await printer.start()
    await client.connect()

    assert client.available


async def test_cancelled_connect(printer: FakePrinter, client: BambuLabClient) -> None:
    """A cancelled connect does not leave a connection behind."""
    printer.status = None
    connect = asyncio.create_task(client.connect())
    await wait_for(lambda: len(printer.requests) == 2)

    connect.cancel()
    with pytest.raises(asyncio.CancelledError):
        await connect

    await wait_for(lambda: not printer._clients)
    assert client._task is None


async def test_reconnect(printer: FakePrinter, client: BambuLabClient) -> None:
    """The client connects again when the connection is lost."""
    await client.connect()
    availability: list[bool] = []
    client.add_listener(lambda: availability.append(client.available))
    status_after_restart = load_fixture("p1s_status.json")
    status_after_restart["print"]["gcode_state"] = "IDLE"
    del status_after_restart["print"]["mc_percent"]
    printer.status = status_after_restart

    await printer.drop_clients()
    await wait_for(lambda: availability == [False, True])

    assert printer.connections == 2
    assert client.state.print_state is PrintState.IDLE
    # What the printer reported before the restart is forgotten.
    assert client.state.progress is None


async def test_reconnect_keeps_trying(
    printer: FakePrinter, client: BambuLabClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The client waits longer and longer while the printer is gone."""
    caplog.set_level("DEBUG", logger="aiobambulab.client")
    await client.connect()
    listener = Mock()
    client.add_listener(listener)

    await printer.stop()
    await wait_for(lambda: caplog.text.count("Lost the connection") >= 4)

    assert not client.available
    listener.assert_called_once_with()
    assert reconnect_delays(caplog)[:4] == [0.01, 0.02, 0.04, 0.04]

    await printer.start()
    await wait_for(lambda: client.available)

    assert listener.call_count == 2


async def test_reconnect_starts_over_after_a_long_connection(
    printer: FakePrinter, client: BambuLabClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The client connects again quickly after a connection that lasted."""
    caplog.set_level("DEBUG", logger="aiobambulab.client")
    await client.connect()
    await printer.stop()
    await wait_for(lambda: caplog.text.count("Lost the connection") >= 3)
    await printer.start()
    await wait_for(lambda: client.available)
    caplog.clear()

    # Longer than the longest delay between two attempts.
    await asyncio.sleep(0.06)
    await printer.drop_clients()
    await wait_for(lambda: "Lost the connection" in caplog.text)

    assert reconnect_delays(caplog)[0] == 0.01


async def test_disconnect(printer: FakePrinter, client: BambuLabClient) -> None:
    """Disconnecting tells the listeners, and can be done twice."""
    await client.connect()
    listener = Mock()
    client.add_listener(listener)

    await client.disconnect()
    await client.disconnect()

    assert not client.available
    listener.assert_called_once_with()
    await wait_for(lambda: not printer._clients)


async def test_unexpected_error_while_connecting(
    client: BambuLabClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bug does not leave the caller of connect waiting."""
    monkeypatch.setattr(client, "_listen", Mock(side_effect=RuntimeError("Boom")))

    with pytest.raises(BambuLabError, match="Unexpected error"):
        await client.connect()

    assert not client.available
    assert f"Unexpected error in the connection to printer {SERIAL}" in caplog.text


async def test_unexpected_error_while_connected(
    printer: FakePrinter, client: BambuLabClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A bug does not stop the client for good: it reports it, and tries again."""
    await client.connect()
    listener = Mock()
    client.add_listener(listener)

    with patch(
        "aiobambulab.client.PrinterState.from_report",
        side_effect=RuntimeError("Boom"),
    ):
        printer.push(status(mc_percent=43))
        await wait_for(lambda: not client.available)

    assert f"Unexpected error in the connection to printer {SERIAL}" in caplog.text
    assert type(client.error) is BambuLabError

    await wait_for(lambda: client.available)

    assert client.error is None
    assert listener.call_count == 2


async def test_error_while_reconnecting(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """The client tells why the printer is not available, and keeps trying."""
    await client.connect()

    printer.access_code = "87654321"
    await printer.drop_clients()
    await wait_for(lambda: isinstance(client.error, BambuLabAuthenticationError))

    assert not client.available
    attempts = printer.connections
    await wait_for(lambda: printer.connections > attempts)

    printer.access_code = ACCESS_CODE
    await wait_for(lambda: client.available)

    assert client.error is None


async def test_concurrent_connect(printer: FakePrinter, client: BambuLabClient) -> None:
    """Connecting twice at the same time connects once, and both wait for it."""
    await asyncio.gather(client.connect(), client.connect())

    assert client.available
    assert printer.connections == 1


@pytest.mark.parametrize("host", ["", "printer..local"])
async def test_invalid_host(ssl_context: ssl.SSLContext, host: str) -> None:
    """A host that cannot be connected to is like a printer that is not there."""
    client = BambuLabClient(host, SERIAL, ACCESS_CODE, ssl_context=ssl_context)

    with pytest.raises(BambuLabConnectionError):
        await client.connect()

    assert not client.available


async def test_disconnect_while_connecting(
    printer: FakePrinter, client: BambuLabClient
) -> None:
    """Disconnecting ends a connect that is still waiting for the printer."""
    printer.status = None
    connect = asyncio.create_task(client.connect())
    await wait_for(lambda: len(printer.requests) == 2)

    await client.disconnect()

    with pytest.raises(BambuLabError, match="Disconnected while connecting"):
        await connect


async def test_disconnect_when_closing_the_connection_fails(
    client: BambuLabClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disconnecting ends the client, also when the printer does not let go."""
    listening = asyncio.Event()
    attempts = 0

    async def listen() -> None:
        nonlocal attempts
        attempts += 1
        listening.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # What the MQTT client does when the printer does not answer.
            raise aiomqtt.MqttError from None

    monkeypatch.setattr(client, "_listen", listen)
    connect = asyncio.create_task(client.connect())
    await listening.wait()

    async with asyncio.timeout(1):
        await client.disconnect()

    with pytest.raises(BambuLabError):
        await connect
    assert attempts == 1

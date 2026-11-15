# aiobambulab

Asynchronous Python client for Bambu Lab 3D printers on the local network.

The client connects to the MQTT server that every Bambu Lab printer runs, and follows what the printer reports: the state of the print job, its progress, temperatures, and more. It does not use the Bambu Lab cloud.

- Fully asynchronous, built on [aiomqtt](https://github.com/empicano/aiomqtt). No threads.
- Push based: the printer tells the client what changed, and the client tells you.
- Typed models and typed errors.
- Verifies that it talks to your printer: it only accepts a certificate that Bambu Lab issued to the serial number you pass in.
- Connects again by itself when the connection is lost.
- Sends the basic commands: pause, resume, or stop a print, set the speed profile, and switch the light.
- Gives you the camera: images for the printers that send images, and the address of the video stream for the printers that have one.

## Installation

```shell
pip install aiobambulab
```

## What you need

- The IP address of the printer.
- The serial number of the printer. It is not case sensitive.
- The LAN access code of the printer.

You find all three on the screen of the printer. The printer does not have to be in LAN only mode.

## Usage

```python
import asyncio

from aiobambulab import BambuLabClient


async def main() -> None:
    async with BambuLabClient("192.168.1.50", "01P00A000000001", "12345678") as client:
        print(client.info.model_name, client.info.firmware_version)
        print(client.state)

        def on_change() -> None:
            if not client.available:
                print("The printer is gone")
                return
            print(client.state.print_state, client.state.progress)

        remove_listener = client.add_listener(on_change)
        await asyncio.sleep(3600)
        remove_listener()


asyncio.run(main())
```

`connect()`, which the context manager calls, returns once the client knows which printer it is and what its state is. From then on:

- `client.info` is what the printer is: its model, firmware version, and hardware version.
- `client.state` is what the printer is doing. A value is `None` when the printer does not report it. Temperatures are in whole degrees Celsius, like the printer shows them.
- `client.available` is `False` while the connection is lost. The client keeps trying to connect again, and `client.state` keeps the last known state.
- `client.error` is why the printer is not available, if that is known. The client keeps trying whatever the error is. An error like a rejected access code does not go away by itself, so act on it.
- Listeners are called when the state, the info, or the availability changes.

### Commands

```python
from aiobambulab import SpeedProfile

await client.set_chamber_light(on=True)
await client.pause_print()
await client.resume_print()
await client.stop_print()
await client.set_speed_profile(SpeedProfile.SILENT)
```

A command raises `BambuLabConnectionError` when the printer is not connected. The printer does not confirm a command in a way to rely on: what it did shows in the state it reports afterwards.

Newer firmware only accepts commands when the printer is in developer mode. `client.state.accepts_commands` tells whether it does. The light is the exception: the printer always accepts the command for it.

### Camera

Printers have one of two kinds of camera access, depending on the model.

The A1 and P1 series, and the A2L, send images:

```python
if client.supports_camera_images:
    image = await client.camera_image()  # A JPEG image
```

The first image takes a moment, because the connection to the camera only opens when you ask for an image. It stays open while you keep asking, so the next images come right away. It closes when you stop asking for 30 seconds, and on `disconnect()`.

The other printers serve a video stream, when that is turned on on the printer:

```python
if (url := client.camera_stream_url) is not None:
    ...  # An rtsps:// address for a video player. It holds the access code.
```

`client.state.camera_stream_enabled` is `None` for a printer without a video stream, and `False` when the stream is turned off on the printer.

### Errors

`connect()` raises one of these, all subclasses of `BambuLabError`:

| Error | Meaning |
| --- | --- |
| `BambuLabAuthenticationError` | The printer rejected the access code. |
| `BambuLabSerialMismatchError` | The printer at this address has another serial number. |
| `BambuLabCertificateError` | The device at this address has no certificate issued by Bambu Lab. |
| `BambuLabConnectionError` | The printer could not be reached, or it did not report its state in time. |

`BambuLabSerialMismatchError` is a `BambuLabCertificateError`, which is a `BambuLabConnectionError`. Catch the specific ones first.

### TLS

A printer serves a certificate that Bambu Lab issued to its serial number. By default, the client only trusts the certificate authorities of Bambu Lab, and checks the serial number in the certificate before it sends the access code.

To decide this yourself, pass your own `ssl.SSLContext` as `ssl_context`.

Creating the default context reads files from disk. The client does that in an executor. To create it yourself, for example to reuse it, call `create_ssl_context(serial)` in an executor.

## Development

This project uses [uv](https://docs.astral.sh/uv/).

```shell
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
uv run mypy
```

The tests run the client against a fake printer: a small MQTT server over TLS, in `tests/fake_printer.py`. Nothing in the tests is mocked between the client and the network.

## Credits

The protocol of the printers is not documented by Bambu Lab. This library builds on what others found out and wrote down:

- [OpenBambuAPI](https://github.com/Doridian/OpenBambuAPI), the community documentation of the protocol.
- [ha-bambulab](https://github.com/greghesp/ha-bambulab), the custom integration for Home Assistant. The certificate authorities in `src/aiobambulab/certs/bambulab.pem` are the ones of Bambu Lab that this project collected.

This library is not affiliated with or endorsed by Bambu Lab.

## License

MIT. See [LICENSE](LICENSE).

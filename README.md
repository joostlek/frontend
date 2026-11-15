# aiobambulab

Asynchronous Python client for Bambu Lab 3D printers on the local network.

The client connects to the MQTT server that every Bambu Lab printer runs, and follows what the printer reports: the state of the print job, its progress, temperatures, and more. It does not use the Bambu Lab cloud.

- Fully asynchronous, built on [aiomqtt](https://github.com/empicano/aiomqtt). No threads.
- Push based: the printer tells the client what changed, and the client tells you.
- Typed models and typed errors.
- Verifies that it talks to your printer: it only accepts a certificate that Bambu Lab issued to the serial number you pass in.
- Connects again by itself when the connection is lost.
- Knows what the printer is doing in detail: the stage of the print job, fans, nozzle, errors, and the filament in each tray of an AMS.
- Sends commands: pause, resume, or stop a print, set the speed profile, temperatures, and fans, switch the light, and more.
- Gives you the camera: images for the printers that send images, and the address of the video stream for the printers that have one.
- Finds the printers on your network.

## Installation

```shell
pip install aiobambulab
```

## What you need

- The IP address of the printer.
- The serial number of the printer. It is not case sensitive.
- The LAN access code of the printer.

You find all three on the screen of the printer. The printer does not have to be in LAN only mode.

## Finding printers

A printer announces itself on the network every few seconds. `discover()` listens for that, so you do not have to look up the IP address and the serial number:

```python
from aiobambulab import discover

for printer in await discover():
    print(printer.serial, printer.host, printer.name)
```

It returns shortly after the last printer showed up, or after 15 seconds when there are none. The access code is not announced: that one you still read from the screen of the printer.

Announcements do not cross routers, so this only finds printers on the same network.

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

### State

`client.state` is a `PrinterState`. Next to the print job and the temperatures, it holds:

- `stage`: what the printer is doing right now, like leveling its bed, changing filament, or being paused because the filament ran out. See `PrintStage`.
- `part_fan_speed`, `aux_fan_speed`, `chamber_fan_speed`, and `heatbreak_fan_speed`: the speed of each fan, as a percentage.
- `print_error`: the code of what went wrong with the print job, like `0700_8006`.
- `errors`: the problems the printer reports, each with the code that Bambu Lab calls an HMS code, and a severity.
- `ams`: the AMS units, each with its humidity, its temperature, and its trays. A tray has the `Filament` that is in it, with its type, name, color, and what remains of it. `active` tells which tray the printer prints from.
- `external_spool` and `external_spool_active`: the same for the spool that is not in an AMS.
- `nozzle_diameter` and `nozzle_type`.
- `timelapse_enabled` and `recording_enabled`: what the camera does during a print job.
- `sd_card_present`.
- `available_firmware_version`: the version the printer can update to, if there is one.

The texts that go with the codes of errors are not part of this library. Bambu Lab publishes them.

### Commands

```python
from aiobambulab import Fan, SpeedProfile

await client.set_chamber_light(on=True)
await client.pause_print()
await client.resume_print()
await client.stop_print()
await client.set_speed_profile(SpeedProfile.SILENT)
await client.set_nozzle_temperature(215)
await client.set_bed_temperature(60)
await client.set_fan_speed(Fan.PART_COOLING, 50)
await client.set_timelapse(enabled=True)
await client.set_recording(enabled=False)
await client.skip_objects([206])
await client.calibrate(bed_leveling=True)
await client.home()
await client.send_gcode("M400")
await client.refresh()
```

Temperatures, fans, and homing are sent as G-code. Whether a printer accepts a G-code depends on its model and its firmware.

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

## What is not in this library

- Anything that goes through the Bambu Lab cloud.
- Starting a print job, and everything else that needs the files on the printer: uploading, the cover image of a print job, and downloading a timelapse.
- Loading and unloading filament, and drying it in an AMS.
- The second nozzle of a printer with two: temperatures are those of the nozzle in use.
- What only a few models have, like a laser, a cutter, a door sensor, or an air filter.
- Updating the firmware.

## Credits

The protocol of the printers is not documented by Bambu Lab. This library builds on what others found out and wrote down:

- [OpenBambuAPI](https://github.com/Doridian/OpenBambuAPI), the community documentation of the protocol.
- [ha-bambulab](https://github.com/greghesp/ha-bambulab), the custom integration for Home Assistant. The certificate authorities in `src/aiobambulab/certs/bambulab.pem` are the ones of Bambu Lab that this project collected.

This library is not affiliated with or endorsed by Bambu Lab.

## License

MIT. See [LICENSE](LICENSE).

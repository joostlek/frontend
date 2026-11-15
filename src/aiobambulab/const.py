"""Constants for aiobambulab."""

from __future__ import annotations

from typing import Final

DEFAULT_PORT: Final = 8883
DEFAULT_TIMEOUT: Final = 15.0

# Every printer uses the same username. The password is the LAN access code.
MQTT_USERNAME: Final = "bblp"
MQTT_KEEPALIVE: Final = 60

# Printers announce themselves on this UDP port.
DISCOVERY_PORT: Final = 2021

# Printers without a video stream send images of their camera on this port.
CAMERA_PORT: Final = 6000
# How long the connection to the camera stays open after the last request.
CAMERA_IDLE_TIMEOUT: Final = 30.0

# Printers with a video stream serve it here.
STREAM_PORT: Final = 322
STREAM_PATH: Final = "/streaming/live/1"

RECONNECT_MIN_DELAY: Final = 1.0
RECONNECT_MAX_DELAY: Final = 60.0

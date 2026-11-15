"""Constants for aiobambulab."""

from __future__ import annotations

from typing import Final

DEFAULT_PORT: Final = 8883
DEFAULT_TIMEOUT: Final = 15.0

# Every printer uses the same username. The password is the LAN access code.
MQTT_USERNAME: Final = "bblp"
MQTT_KEEPALIVE: Final = 60

RECONNECT_MIN_DELAY: Final = 1.0
RECONNECT_MAX_DELAY: Final = 60.0

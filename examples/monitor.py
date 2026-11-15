"""Follow a printer, and print what changes.

Usage: python monitor.py <host> <serial> <access code>
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

from aiobambulab import BambuLabClient, BambuLabError


async def main(host: str, serial: str, access_code: str) -> None:
    """Connect to the printer and print its state until interrupted."""
    client = BambuLabClient(host, serial, access_code)

    def on_change() -> None:
        if not client.available:
            print("The printer is not available")
            return
        print(client.state)

    client.add_listener(on_change)
    try:
        await client.connect()
    except BambuLabError as err:
        print(f"Could not connect: {type(err).__name__}: {err}")
        return
    print(client.info)
    try:
        await asyncio.Event().wait()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    if len(sys.argv) != 4:  # noqa: PLR2004
        sys.exit(__doc__)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(*sys.argv[1:]))

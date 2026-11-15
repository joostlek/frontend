"""TLS setup to connect to a Bambu Lab printer.

A printer does not use a certificate from a public certificate authority. It
serves a certificate issued by Bambu Lab, and that certificate is issued to the
serial number of the printer, not to its host name or IP address.
"""

from __future__ import annotations

from pathlib import Path
import ssl
from typing import TYPE_CHECKING, Final, override

if TYPE_CHECKING:
    import socket

CA_FILE: Final = Path(__file__).parent / "certs" / "bambulab.pem"

# The code OpenSSL uses when a certificate is issued to another name.
VERIFY_CODE_HOSTNAME_MISMATCH: Final = 62


class PrinterSSLContext(ssl.SSLContext):
    """A TLS context that only accepts the certificate of one printer.

    MQTT clients ask for a certificate that matches the address they connect
    to. That can never match here, so this context asks for the serial number
    of the printer, whatever address the caller passes in.
    """

    serial: str

    @override
    def wrap_socket(
        self,
        sock: socket.socket,
        server_side: bool = False,
        do_handshake_on_connect: bool = True,
        suppress_ragged_eofs: bool = True,
        server_hostname: str | bytes | None = None,
        session: ssl.SSLSession | None = None,
    ) -> ssl.SSLSocket:
        """Wrap a socket, and verify the certificate against the serial number."""
        return super().wrap_socket(
            sock,
            server_side=server_side,
            do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs,
            server_hostname=self.serial,
            session=session,
        )


def create_ssl_context(serial: str) -> ssl.SSLContext:
    """Create the TLS context for the printer with this serial number.

    The context trusts the certificate authorities of Bambu Lab only, and
    checks that the certificate is issued to this serial number.

    This function reads the certificates from disk, so it blocks. Run it in an
    executor when you call it from an event loop.
    """
    context = PrinterSSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.serial = serial
    # The serial number is the common name of the certificate.
    context.hostname_checks_common_name = True
    context.load_verify_locations(cafile=CA_FILE)
    # Some printer firmware is reported to never answer a TLS 1.3 handshake.
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    return context

"""Fixtures for the tests of aiobambulab."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import ssl
from typing import TYPE_CHECKING, Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import pytest

from aiobambulab import BambuLabClient
from aiobambulab.tls import PrinterSSLContext

from .fake_printer import FakePrinter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

SERIAL = "01P00A000000001"
ACCESS_CODE = "12345678"

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a message of a printer."""
    message: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return message


@dataclass(frozen=True)
class CertificateAuthority:
    """A certificate authority that issues certificates to fake printers."""

    path: Path
    name: x509.Name
    key: ec.EllipticCurvePrivateKey

    def issue(self, common_name: str) -> ssl.SSLContext:
        """Return the TLS context of a printer with a certificate for this name."""
        key = ec.generate_private_key(ec.SECP256R1())
        certificate = _certificate(_name(common_name), key, self.name, self.key)
        directory = self.path.parent
        cert_file = directory / f"{common_name}.pem"
        key_file = directory / f"{common_name}.key"
        cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        key_file.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        return context


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _certificate(
    subject: x509.Name,
    key: ec.EllipticCurvePrivateKey,
    issuer: x509.Name,
    issuer_key: ec.EllipticCurvePrivateKey,
) -> x509.Certificate:
    """Create a certificate without alternative names, like that of a printer."""
    now = dt.datetime.now(dt.UTC)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.BasicConstraints(ca=subject == issuer, path_length=None),
            critical=True,
        )
        .sign(issuer_key, hashes.SHA256())
    )


def _certificate_authority(directory: Path, common_name: str) -> CertificateAuthority:
    directory.mkdir()
    name = _name(common_name)
    key = ec.generate_private_key(ec.SECP256R1())
    path = directory / "ca.pem"
    path.write_bytes(
        _certificate(name, key, name, key).public_bytes(serialization.Encoding.PEM)
    )
    return CertificateAuthority(path=path, name=name, key=key)


@pytest.fixture(scope="session")
def ca(tmp_path_factory: pytest.TempPathFactory) -> CertificateAuthority:
    """Return the certificate authority the tests trust."""
    return _certificate_authority(tmp_path_factory.mktemp("tls") / "ca", "Test CA")


@pytest.fixture(scope="session")
def other_ca(tmp_path_factory: pytest.TempPathFactory) -> CertificateAuthority:
    """Return a certificate authority the tests do not trust."""
    return _certificate_authority(tmp_path_factory.mktemp("tls") / "ca", "Other CA")


@pytest.fixture(scope="session")
def printer_ssl_context(ca: CertificateAuthority) -> ssl.SSLContext:
    """Return the TLS context of the printer."""
    return ca.issue(SERIAL)


@pytest.fixture
def ssl_context(ca: CertificateAuthority) -> ssl.SSLContext:
    """Return the TLS context of the client, which trusts the test authority."""
    context = PrinterSSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.serial = SERIAL
    context.load_verify_locations(cafile=ca.path)
    return context


@pytest.fixture
async def printer(printer_ssl_context: ssl.SSLContext) -> AsyncIterator[FakePrinter]:
    """Return a running P1S."""
    async with FakePrinter(
        SERIAL,
        ACCESS_CODE,
        printer_ssl_context,
        version=load_fixture("p1s_version.json"),
        status=load_fixture("p1s_status.json"),
    ) as printer:
        yield printer


@pytest.fixture
async def client(
    printer: FakePrinter, ssl_context: ssl.SSLContext
) -> AsyncIterator[BambuLabClient]:
    """Return a client for the printer. It is not connected yet."""
    client = BambuLabClient(
        "127.0.0.1",
        SERIAL,
        ACCESS_CODE,
        port=printer.port,
        ssl_context=ssl_context,
        timeout=2,
    )
    yield client
    await client.disconnect()

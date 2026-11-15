"""Tests for the TLS setup of aiobambulab."""

from __future__ import annotations

import ssl

from aiobambulab import create_ssl_context
from aiobambulab.tls import CA_FILE

from .conftest import SERIAL


def test_create_ssl_context() -> None:
    """The context verifies the certificate, and that it is for the serial."""
    context = create_ssl_context(SERIAL)

    assert context.verify_mode is ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.maximum_version is ssl.TLSVersion.TLSv1_2


def test_context_trusts_bambu_lab_only() -> None:
    """The context trusts the certificate authorities of Bambu Lab, no others."""
    context = create_ssl_context(SERIAL)

    certificates = context.get_ca_certs()
    assert len(certificates) == CA_FILE.read_text().count("BEGIN CERT")
    assert all(
        "BBL Technologies" in str(certificate["subject"])
        for certificate in certificates
    )

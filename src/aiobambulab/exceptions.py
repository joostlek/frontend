"""Exceptions for aiobambulab."""

from __future__ import annotations


class BambuLabError(Exception):
    """Base class for all errors raised by aiobambulab."""


class BambuLabConnectionError(BambuLabError):
    """The printer could not be reached, or it did not answer in time."""


class BambuLabCertificateError(BambuLabConnectionError):
    """The device did not present a certificate issued by Bambu Lab."""


class BambuLabSerialMismatchError(BambuLabCertificateError):
    """The certificate of the printer belongs to a different serial number."""


class BambuLabAuthenticationError(BambuLabError):
    """The printer rejected the access code."""

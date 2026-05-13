"""Exceptions for DNS Manager."""

from __future__ import annotations


class DNSManagerError(Exception):
    """Base error for this integration."""


class ProviderAuthError(DNSManagerError):
    """Provider rejected credentials."""


class ProviderAPIError(DNSManagerError):
    """Provider API returned an error response."""

    def __init__(self, message: str, *, errors: list[dict] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class UnsupportedProviderError(DNSManagerError):
    """Provider type is not supported."""


class IPDetectionError(DNSManagerError):
    """Could not detect public IP."""


class RecordNotFoundError(DNSManagerError):
    """Record could not be found on provider."""


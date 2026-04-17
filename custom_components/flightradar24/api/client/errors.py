from __future__ import annotations
import requests


class FlightRadar24Error(Exception):
    """Base class for all FlightRadar24 client errors."""


class AirportNotFoundError(FlightRadar24Error):
    """Raised when FR24 cannot resolve an airport code."""


class LoginError(FlightRadar24Error):
    """Raised when FR24 rejects the provided credentials."""


class CloudflareError(FlightRadar24Error):
    """Raised when FR24 returns HTTP 520 (Cloudflare upstream error)."""

    def __init__(self, message: str, response: requests.Response) -> None:
        super().__init__(message)
        self.message = message
        self.response = response

    def __str__(self) -> str:
        return self.message

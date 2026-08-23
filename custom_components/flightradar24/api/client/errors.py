from __future__ import annotations
import requests


class FlightRadar24Error(Exception):
    """Base class for all FlightRadar24 client errors."""


class AirportNotFoundError(FlightRadar24Error):
    """Raised when FR24 cannot resolve an airport code."""


class LoginError(FlightRadar24Error):
    """Raised when FR24 rejects the provided credentials.

    Only for genuine credential problems — transport failures that merely
    *look* like an auth failure (a Cloudflare 403, a 429) raise the
    corresponding ``TransportError`` subclass instead, so callers can tell
    "your password is wrong" apart from "FR24 would not talk to us".
    """


class TransportError(FlightRadar24Error):
    """Raised when a request never produced a usable answer.

    Network failures, timeouts and unexpected HTTP statuses. Always
    transient from the integration's point of view: retrying later is the
    right response, prompting the user for new credentials is not.
    """


class RateLimitError(TransportError):
    """Raised when FR24 answers HTTP 429."""


class BlockedError(TransportError):
    """Raised when Cloudflare serves a bot challenge instead of the API.

    FR24 fronts most of its endpoints with Cloudflare Bot Management, which
    answers non-browser clients with HTTP 403 and a ``cf-mitigated:
    challenge`` header. No amount of header tuning gets past it, so this is
    reported as its own error rather than a generic HTTP failure.
    """


class CloudflareError(TransportError):
    """Raised when FR24 returns HTTP 520 (Cloudflare upstream error)."""

    def __init__(self, message: str, response: requests.Response) -> None:
        super().__init__(message)
        self.message = message
        self.response = response

    def __str__(self) -> str:
        return self.message

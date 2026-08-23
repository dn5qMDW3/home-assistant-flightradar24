from __future__ import annotations
from typing import Any
import requests
from .errors import BlockedError, CloudflareError, RateLimitError, TransportError

# Cloudflare sets this on any response it generated itself instead of passing
# the request upstream. Its presence is the most reliable "you were blocked,
# not rejected" signal FR24 gives us.
_CF_MITIGATED_HEADER = "cf-mitigated"
_CHALLENGE_TITLE = b"just a moment"


class APIRequest:
    """Thin wrapper around ``requests`` for FR24 endpoints.

    Delegates URL/param encoding and gzip decoding to ``requests``; we add
    FR24-specific failure classification on top so callers never have to
    interpret a raw status code. Every failure leaves this constructor as a
    ``FlightRadar24Error`` subclass — a bare ``requests`` exception never
    escapes.
    """

    def __init__(
            self,
            url: str,
            *,
            params: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            data: dict[str, Any] | None = None,
            cookies: dict[str, str] | None = None,
            timeout: int = 30,
            exclude_status_codes: tuple[int, ...] = (),
    ) -> None:
        method = "POST" if data is not None else "GET"
        try:
            self._response = requests.request(
                method=method,
                url=url,
                params=params,
                headers=headers,
                cookies=cookies,
                data=data,
                timeout=timeout,
            )
        except requests.RequestException as err:
            raise TransportError(f"Could not reach {url}: {err}") from err

        status = self._response.status_code
        if status == 520:
            raise CloudflareError(
                "FlightRadar24 returned HTTP 520 (Cloudflare upstream error). "
                "You may be rate-limited.",
                self._response,
            )
        if status == 429:
            raise RateLimitError(
                f"FlightRadar24 rate-limited this request (HTTP 429): {self._error_detail()}"
            )
        if self._is_bot_challenge():
            raise BlockedError(
                f"FlightRadar24 served a Cloudflare bot challenge for {url} "
                f"(HTTP {status}). This endpoint is not reachable from Home Assistant."
            )
        if status not in exclude_status_codes:
            try:
                self._response.raise_for_status()
            except requests.HTTPError as err:
                raise TransportError(str(err)) from err

    def _is_bot_challenge(self) -> bool:
        """True when Cloudflare answered instead of FR24.

        Checked before the status-code handling so a challenge is never
        mistaken for a credential rejection: FR24's own auth failures come
        back as JSON, a challenge as an HTML interstitial.
        """
        if _CF_MITIGATED_HEADER in self._response.headers:
            return True
        if self._response.status_code not in (401, 403):
            return False
        if "application/json" in self._response.headers.get("Content-Type", ""):
            return False
        return _CHALLENGE_TITLE in self._response.content[:1024].lower()

    def _error_detail(self) -> str:
        """Best-effort human-readable reason from an error response body."""
        try:
            content = self._response.json()
        except ValueError:
            return self._response.reason or ""
        if isinstance(content, dict):
            # FR24 uses "msg"; keep "message" as a fallback for other endpoints.
            return str(content.get("msg") or content.get("message") or content)
        return str(content)

    def get_content(self) -> Any:
        content_type = self._response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return self._response.json()
        return self._response.content

    def get_cookies(self) -> dict[str, str]:
        return self._response.cookies.get_dict()

    def get_status_code(self) -> int:
        return self._response.status_code

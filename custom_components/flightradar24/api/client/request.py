from __future__ import annotations
from typing import Any
import requests
from .errors import CloudflareError


class APIRequest:
    """Thin wrapper around ``requests`` for FR24 endpoints.

    Delegates URL/param encoding and gzip decoding to ``requests``; we only
    add the FR24-specific Cloudflare (520) handling on top.
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
        self._response = requests.request(
            method=method,
            url=url,
            params=params,
            headers=headers,
            cookies=cookies,
            data=data,
            timeout=timeout,
        )
        if self._response.status_code == 520:
            raise CloudflareError(
                "FlightRadar24 returned HTTP 520 (Cloudflare upstream error). "
                "You may be rate-limited.",
                self._response,
            )
        if self._response.status_code not in exclude_status_codes:
            self._response.raise_for_status()

    def get_content(self) -> Any:
        content_type = self._response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return self._response.json()
        return self._response.content

    def get_cookies(self) -> dict[str, str]:
        return self._response.cookies.get_dict()

    def get_status_code(self) -> int:
        return self._response.status_code

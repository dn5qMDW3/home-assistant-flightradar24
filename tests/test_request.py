"""Tests for APIRequest failure classification and the login error path.

FR24 fronts most of its endpoints with Cloudflare Bot Management, which
answers with HTTP 403 rather than passing the request upstream. These tests
pin down that a block, a rate-limit and a genuine credential rejection each
produce a distinct exception type, because the integration reacts to them
very differently (retry vs. prompt the user for new credentials).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from api.client import (
    BlockedError,
    FlightRadar24API,
    LoginError,
    RateLimitError,
    TransportError,
)
from api.client.request import APIRequest

CHALLENGE_BODY = (
    b'<!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>'
    b'<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">'
)


def make_response(
    status: int,
    *,
    body: bytes = b"{}",
    content_type: str = "application/json",
    extra_headers: dict[str, str] | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = content_type
    response.headers.update(extra_headers or {})
    response.url = "https://www.flightradar24.com/test"
    return response


def request_returning(response: requests.Response):
    return patch("api.client.request.requests.request", return_value=response)


class TestFailureClassification:
    def test_cf_mitigated_header_is_a_block(self):
        response = make_response(
            403,
            body=CHALLENGE_BODY,
            content_type="text/html; charset=UTF-8",
            extra_headers={"cf-mitigated": "challenge", "server": "cloudflare"},
        )
        with request_returning(response), pytest.raises(BlockedError):
            APIRequest("https://www.flightradar24.com/test")

    def test_challenge_html_without_header_is_a_block(self):
        # Cloudflare does not always set cf-mitigated; the interstitial body
        # is the fallback signal.
        response = make_response(
            403, body=CHALLENGE_BODY, content_type="text/html; charset=UTF-8"
        )
        with request_returning(response), pytest.raises(BlockedError):
            APIRequest("https://www.flightradar24.com/test")

    def test_json_403_is_not_a_block(self):
        # FR24's own rejection comes back as JSON and must stay distinguishable
        # from a Cloudflare block, so it is reported as a transport error here
        # and turned into a LoginError by the caller.
        response = make_response(403, body=b'{"success":false,"msg":"nope"}')
        with request_returning(response), pytest.raises(TransportError) as err:
            APIRequest("https://www.flightradar24.com/test")
        assert not isinstance(err.value, BlockedError)

    def test_429_is_a_rate_limit(self):
        response = make_response(
            429, body=b'{"msg":"device has exceeded login attempts, try again later"}'
        )
        with request_returning(response), pytest.raises(RateLimitError) as err:
            APIRequest("https://www.flightradar24.com/test")
        assert "exceeded login attempts" in str(err.value)

    def test_network_failure_becomes_transport_error(self):
        with patch(
            "api.client.request.requests.request",
            side_effect=requests.ConnectionError("name resolution failed"),
        ):
            with pytest.raises(TransportError) as err:
                APIRequest("https://www.flightradar24.com/test")
        # A bare requests exception must never escape the client.
        assert "name resolution failed" in str(err.value)

    def test_excluded_status_is_returned_to_caller(self):
        response = make_response(400, body=b'{"errors":{}}')
        with request_returning(response):
            request = APIRequest(
                "https://www.flightradar24.com/test", exclude_status_codes=(400,)
            )
        assert request.get_status_code() == 400

    def test_success_passes_through(self):
        response = make_response(200, body=b'{"ok":true}')
        with request_returning(response):
            request = APIRequest("https://www.flightradar24.com/test")
        assert request.get_content() == {"ok": True}


class TestLogin:
    def test_reads_fr24s_msg_key(self):
        # Regression: the client used to look for "message" while FR24 sends
        # "msg", so the real reason was silently dropped.
        response = make_response(
            401, body=b'{"success":false,"msg":"Your email or password is incorrect"}'
        )
        with request_returning(response), pytest.raises(LoginError) as err:
            FlightRadar24API().login("user@example.com", "wrong")
        assert str(err.value) == "Your email or password is incorrect"

    def test_falls_back_to_message_key(self):
        response = make_response(401, body=b'{"success":false,"message":"legacy"}')
        with request_returning(response), pytest.raises(LoginError) as err:
            FlightRadar24API().login("user@example.com", "wrong")
        assert str(err.value) == "legacy"

    def test_block_is_not_reported_as_bad_credentials(self):
        # The whole point of the split: a Cloudflare block must not send the
        # user to a reauth prompt that cannot possibly succeed.
        response = make_response(
            403,
            body=CHALLENGE_BODY,
            content_type="text/html; charset=UTF-8",
            extra_headers={"cf-mitigated": "challenge"},
        )
        with request_returning(response), pytest.raises(BlockedError):
            FlightRadar24API().login("user@example.com", "correct")

    def test_non_json_body_is_a_login_error(self):
        response = make_response(200, body=b"not json", content_type="text/plain")
        with request_returning(response), pytest.raises(LoginError):
            FlightRadar24API().login("user@example.com", "pw")

    def test_success_without_user_data_is_a_login_error(self):
        response = make_response(200, body=b'{"success":true}')
        with request_returning(response), pytest.raises(LoginError):
            FlightRadar24API().login("user@example.com", "pw")

    def test_successful_login_stores_session(self):
        response = make_response(200, body=b'{"success":true,"userData":{"tier":"gold"}}')
        api = FlightRadar24API()
        with request_returning(response):
            api.login("user@example.com", "pw")
        assert api.is_logged_in()
        assert api.get_login_data() == {"tier": "gold"}

    def test_missing_premium_cookie_does_not_break_requests(self):
        # FR24 has renamed this cookie before; losing it should cost the
        # premium fields, not the whole request.
        response = make_response(200, body=b'{"success":true,"userData":{}}')
        api = FlightRadar24API()
        with request_returning(response):
            api.login("user@example.com", "pw")
        assert api._premium_token() is None

        feed = make_response(200, body=b'{"full_count":1,"version":4}')
        with request_returning(feed) as mock:
            api.get_flights(bounds="1,0,0,1")
        assert "enc" not in mock.call_args.kwargs["params"]

#!/usr/bin/env python3
"""End-to-end verification of the vendored FR24 client against the live service.

Usage (credentials are read from the environment — never printed or logged):

    FR24_USER=you@example.com FR24_PASSWORD='...' \
        .venv/bin/python scripts/verify_client.py

If FR24_USER/FR24_PASSWORD are not set, auth-dependent checks are skipped.
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "flightradar24"))

from api.airport import AirportProcessor  # noqa: E402
from api.client import (  # noqa: E402
    AirportNotFoundError,
    Entity,
    Flight,
    FlightRadar24API,
    LoginError,
)

PASS = "\033[92m PASS \033[0m"
FAIL = "\033[91m FAIL \033[0m"
SKIP = "\033[93m SKIP \033[0m"


class Summary:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0


def run(summary: Summary, name: str, fn: Callable[[], str]) -> None:
    try:
        note = fn()
    except Exception as err:
        summary.failed += 1
        print(f"[{FAIL}] {name}")
        print(f"        {type(err).__name__}: {err}")
        return
    summary.passed += 1
    print(f"[{PASS}] {name}")
    if note:
        print(f"        {note}")


def skip(summary: Summary, name: str, why: str) -> None:
    summary.skipped += 1
    print(f"[{SKIP}] {name}  ({why})")


def main() -> int:
    user = os.environ.get("FR24_USER")
    password = os.environ.get("FR24_PASSWORD")

    api = FlightRadar24API(timeout=20)
    s = Summary()

    # LHR ~ 50 km — enough to always see traffic
    lhr_bounds = FlightRadar24API.get_bounds_by_point(51.4700, -0.4543, 50000)

    def _bounds() -> str:
        return f"bounds={lhr_bounds}"

    run(s, "get_bounds_by_point (pure math)", _bounds)

    def _most() -> str:
        data = api.get_most_tracked()
        return f"returned {len(data.get('data', []))} entries"

    run(s, "get_most_tracked (no auth)", _most)
    time.sleep(1)

    flights: list[Flight] = []

    def _flights() -> str:
        flights.extend(api.get_flights(bounds=lhr_bounds))
        return f"returned {len(flights)} flights around LHR"

    run(s, "get_flights (no auth, bounds encoding)", _flights)
    time.sleep(1)

    if flights:
        sample = flights[0]

        def _details() -> str:
            details = api.get_flight_details(sample)
            keys = sorted(details.keys()) if isinstance(details, dict) else []
            return f"id={sample.id} top-level keys={keys[:6]}{'...' if len(keys) > 6 else ''}"

        run(s, "get_flight_details (no auth)", _details)
    else:
        skip(s, "get_flight_details", "no flights returned above")
    time.sleep(1)

    def _airport() -> str:
        data = api.get_airport_details("LHR")
        plugin = data.get("airport", {}).get("pluginData", {})
        return f"LHR pluginData sections: {sorted(plugin.keys())[:6]}"

    run(s, "get_airport_details (default flight_limit=50)", _airport)
    time.sleep(1)

    def _bad_airport() -> str:
        try:
            api.get_airport_details("ZZZ")
        except AirportNotFoundError as err:
            return f"raised AirportNotFoundError: {err}"
        return "UNEXPECTED: no error raised"

    run(s, "get_airport_details('ZZZ') raises AirportNotFoundError", _bad_airport)
    time.sleep(1)

    # Exercise the full AirportProcessor pipeline — stats, yesterday, recent,
    # weather, aircraft count, and ground schedule are all produced here.
    def _airport_parsing() -> str:
        processor = AirportProcessor(api)
        state = processor.add_subentry("LHR")
        processor.update_airport_info()

        assert state.stats is not None, "stats not populated"
        assert isinstance(state.arrivals, list), "arrivals not a list"
        assert isinstance(state.departures, list), "departures not a list"

        parts = [
            f"today arrivals_on_time={state.stats.arrivals_on_time!r}",
            f"yesterday={state.stats.arrivals_on_time_yesterday!r}",
            f"recent={state.stats.arrivals_on_time_recent!r}",
            f"weather.temp={state.weather.temperature if state.weather else None!r}",
            f"aircraft_count.ground={state.aircraft_count.ground if state.aircraft_count else None!r}",
            f"ground_schedule={len(state.ground) if state.ground is not None else None}",
            f"arrivals={len(state.arrivals)}",
            f"departures={len(state.departures)}",
        ]
        return "; ".join(parts)

    run(s, "AirportProcessor full pipeline (LHR)", _airport_parsing)
    time.sleep(1)

    def _search() -> str:
        results = api.search("BA117")
        counts = {k: len(v) for k, v in results.items()}
        return f"categories: {counts}"

    run(s, "search (params encoding)", _search)
    time.sleep(1)

    if user and password:
        def _login() -> str:
            api.login(user, password)
            assert api.is_logged_in(), "is_logged_in() returned False after login()"
            cookies = api._login_data["cookies"]  # noqa: SLF001 — sanity only
            assert "_frPl" in cookies, "FR24 did not set the _frPl cookie"
            return "login succeeded, _frPl cookie present"

        run(s, "login (auth)", _login)
        time.sleep(1)

        def _auth_flights() -> str:
            fl = api.get_flights(bounds=lhr_bounds)
            return f"got {len(fl)} flights with enc cookie"

        run(s, "get_flights after login (enc cookie sent)", _auth_flights)
    else:
        skip(s, "login", "FR24_USER / FR24_PASSWORD not set")
        skip(s, "get_flights after login", "no credentials")

    def _bad_login() -> str:
        fresh = FlightRadar24API(timeout=20)
        try:
            fresh.login("does-not-exist@example.invalid", "wrong-password")
        except LoginError as err:
            return f"raised LoginError: {err}"
        return "UNEXPECTED: login with bogus creds succeeded"

    run(s, "login with bad creds raises LoginError", _bad_login)

    def _distance() -> str:
        d = Entity(52.5, 13.4).get_distance_from(Entity(40.6413, -73.7781))
        assert 6000 < d < 6800, f"distance {d} km is out of sane range for Berlin->JFK"
        return f"Berlin->JFK: {round(d, 1)} km"

    run(s, "Entity.get_distance_from", _distance)

    print()
    total = s.passed + s.failed + s.skipped
    print(f"Summary: {s.passed}/{total} passed, {s.failed} failed, {s.skipped} skipped")
    return 1 if s.failed else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Dump the *shape* of authenticated FR24 responses — key names and value
types only, never the values themselves. Run once with credentials so we can
confirm the paths we parse match what FR24 actually sends back.

Usage:
    FR24_USER=... FR24_PASSWORD='...' \
        .venv/bin/python scripts/peek_shape.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components" / "flightradar24" / "api"))

from client import FlightRadar24API  # noqa: E402

_REDACT = {"userData", "cookies", "email", "password", "token", "enc"}
_MAX_DEPTH = 6


def walk(obj: Any, prefix: str = "", depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        print(f"{prefix or '<root>'}: <depth limit>")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _REDACT:
                print(f"{prefix + '.' + k if prefix else k}: <redacted>")
                continue
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                walk(v, path, depth + 1)
            elif v is None:
                print(f"{path}: None")
            else:
                print(f"{path}: {type(v).__name__}")
    elif isinstance(obj, list):
        print(f"{prefix}: list[{len(obj)}]")
        if obj and isinstance(obj[0], (dict, list)):
            walk(obj[0], f"{prefix}[0]", depth + 1)
        elif obj:
            print(f"{prefix}[0]: {type(obj[0]).__name__}")


def section(title: str) -> None:
    bar = "=" * len(title)
    print(f"\n{bar}\n{title}\n{bar}")


def main() -> int:
    user = os.environ.get("FR24_USER")
    password = os.environ.get("FR24_PASSWORD")
    if not (user and password):
        print("ERROR: set FR24_USER and FR24_PASSWORD in the environment.", file=sys.stderr)
        return 2

    api = FlightRadar24API(timeout=20)
    api.login(user, password)
    print(f"Login OK. is_logged_in={api.is_logged_in()}")

    bounds = FlightRadar24API.get_bounds_by_point(51.4700, -0.4543, 50000)
    flights = api.get_flights(bounds=bounds)
    if not flights:
        print("No flights around LHR right now — cannot inspect flight details.", file=sys.stderr)
    else:
        section("get_flight_details(first flight)")
        details = api.get_flight_details(flights[0])
        walk(details)

    section("get_airport_details('LHR')")
    airport = api.get_airport_details("LHR")
    # pluginData is where the rich stuff lives; show the schedule and weather in particular
    plugin = airport.get("airport", {}).get("pluginData", {})
    walk(plugin, prefix="airport.pluginData")

    print("\nDone. Paste everything above this line back into the chat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

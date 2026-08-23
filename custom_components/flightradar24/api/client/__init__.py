"""Vendored subset of FlightRadarAPI (https://github.com/JeanExtreme002/FlightRadarAPI).

Original work Copyright (c) 2020 Jean Loui Bernard Silva de Jesus.
Licensed under the MIT License (see LICENSE in this directory).
"""
from .api import FlightRadar24API
from .entities import Entity, Flight
from .errors import (
    AirportNotFoundError,
    BlockedError,
    CloudflareError,
    FlightRadar24Error,
    LoginError,
    RateLimitError,
    TransportError,
)

__all__ = [
    "AirportNotFoundError",
    "BlockedError",
    "CloudflareError",
    "Entity",
    "Flight",
    "FlightRadar24API",
    "FlightRadar24Error",
    "LoginError",
    "RateLimitError",
    "TransportError",
]

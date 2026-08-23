from __future__ import annotations
import dataclasses
import math
from typing import Any
from .core import Core
from .entities import Flight
from .errors import AirportNotFoundError, LoginError
from .request import APIRequest


@dataclasses.dataclass
class FlightTrackerConfig:
    """Params sent to the feed.js endpoint. Defaults match FR24's web client."""
    faa: str = "1"
    satellite: str = "1"
    mlat: str = "1"
    flarm: str = "1"
    adsb: str = "1"
    gnd: str = "1"
    air: str = "1"
    vehicles: str = "1"
    estimated: str = "1"
    maxage: str = "14400"
    gliders: str = "1"
    stats: str = "1"
    limit: str = "5000"


class FlightRadar24API:
    """Minimal client for the subset of FR24 endpoints this integration uses."""

    def __init__(self, timeout: int = 10) -> None:
        self._tracker_config = FlightTrackerConfig()
        self._login_data: dict[str, Any] | None = None
        self.timeout: int = timeout

    def login(self, user: str, password: str) -> None:
        response = APIRequest(
            Core.user_login_url,
            headers=Core.json_headers,
            data={"email": user, "password": password, "remember": "true", "type": "web"},
            timeout=self.timeout,
            # Read FR24's own JSON rejection rather than letting raise_for_status
            # turn it into an opaque transport failure. A Cloudflare challenge on
            # these same codes is caught earlier, so this only widens the window
            # for genuine credential errors.
            exclude_status_codes=(401, 403),
        )
        content = response.get_content()
        if not isinstance(content, dict):
            raise LoginError("FlightRadar24 returned an unexpected login response.")
        if not str(response.get_status_code()).startswith("2") or not content.get("success"):
            # FR24 reports the reason in "msg"; "message" is kept as a fallback.
            message = content.get("msg") or content.get("message")
            raise LoginError(message or "Your email or password is incorrect")
        if "userData" not in content:
            raise LoginError("FlightRadar24 accepted the login but returned no account data.")

        self._login_data = {
            "userData": content["userData"],
            "cookies": response.get_cookies(),
        }

    def logout(self) -> bool:
        if self._login_data is None:
            return True
        cookies = self._login_data["cookies"]
        self._login_data = None
        response = APIRequest(
            Core.user_login_url, headers=Core.json_headers, cookies=cookies, timeout=self.timeout
        )
        return str(response.get_status_code()).startswith("2")

    def is_logged_in(self) -> bool:
        return self._login_data is not None

    def _premium_token(self) -> str | None:
        """Session token unlocking premium fields, or None when absent.

        FR24 has changed this cookie's name before; a missing cookie only
        costs the extra fields, so it must not break an otherwise fine
        request.
        """
        if self._login_data is None:
            return None
        return self._login_data["cookies"].get("_frPl")

    def get_login_data(self) -> dict[str, Any]:
        if not self.is_logged_in():
            raise LoginError("You must log in to your account.")
        return dict(self._login_data["userData"])

    def get_flights(
            self,
            airline: str | None = None,
            bounds: str | None = None,
            registration: str | None = None,
            aircraft_type: str | None = None,
    ) -> list[Flight]:
        params: dict[str, Any] = dataclasses.asdict(self._tracker_config)
        if (token := self._premium_token()) is not None:
            params["enc"] = token
        if airline:
            params["airline"] = airline
        if bounds:
            params["bounds"] = bounds
        if registration:
            params["reg"] = registration
        if aircraft_type:
            params["type"] = aircraft_type

        response = APIRequest(
            Core.real_time_flight_tracker_data_url,
            params=params,
            headers=Core.json_headers,
            timeout=self.timeout,
        ).get_content()

        flights: list[Flight] = []
        for flight_id, flight_info in response.items():
            if not flight_id[0].isnumeric():
                continue
            flights.append(Flight(flight_id, flight_info))
        return flights

    def get_flight_details(self, flight: Flight) -> dict[str, Any]:
        return APIRequest(
            Core.flight_data_url,
            params={"flight": flight.id},
            headers=Core.json_headers,
            timeout=self.timeout,
        ).get_content()

    def get_airport_details(self, code: str, flight_limit: int = 50, page: int = 1) -> dict[str, Any]:
        if not 3 <= len(code) <= 4:
            raise ValueError(f"The code '{code}' is invalid. It must be the IATA or ICAO of the airport.")

        params: dict[str, Any] = {"format": "json", "code": code, "limit": flight_limit, "page": page}
        if (token := self._premium_token()) is not None:
            params["token"] = token

        response = APIRequest(
            Core.api_airport_data_url,
            params=params,
            headers=Core.json_headers,
            exclude_status_codes=(400,),
            timeout=self.timeout,
        )
        content = response.get_content()
        if response.get_status_code() == 400 and content.get("errors"):
            errors = content["errors"]["errors"]["parameters"]
            if errors.get("limit"):
                raise ValueError(errors["limit"]["notBetween"])
            raise AirportNotFoundError(f"Could not find an airport by the code '{code}'.", errors)

        result = content["result"]["response"]
        data = result.get("airport", {}).get("pluginData", {})
        if "details" not in data and not data.get("runways") and len(data) <= 3:
            raise AirportNotFoundError(f"Could not find an airport by the code '{code}'.")
        return result

    def get_most_tracked(self) -> dict[str, Any]:
        return APIRequest(
            Core.most_tracked_url, headers=Core.json_headers, timeout=self.timeout
        ).get_content()

    def search(self, query: str, limit: int = 50) -> dict[str, list[dict[str, Any]]]:
        response = APIRequest(
            Core.search_url,
            params={"query": query, "limit": limit},
            headers=Core.json_headers,
            timeout=self.timeout,
        ).get_content()
        results = response.get("results", [])
        stats = response.get("stats", {})

        i = 0
        counted_total = 0
        data: dict[str, list[dict[str, Any]]] = {}
        for name, count in stats.get("count", {}).items():
            data[name] = []
            while i < counted_total + count and i < len(results):
                data[name].append(results[i])
                i += 1
            counted_total += count
        return data

    @staticmethod
    def get_bounds_by_point(latitude: float, longitude: float, radius: float) -> str:
        """Turn a centre point + radius (metres) into FR24's ``y1,y2,x1,x2`` string."""
        half_side_km = abs(radius) / 1000
        earth_radius_km = 6371
        lat = math.radians(latitude)
        lon = math.radians(longitude)
        hypotenuse = math.sqrt(2 * half_side_km ** 2)
        angular = hypotenuse / earth_radius_km

        def _corner(bearing_deg: float) -> tuple[float, float]:
            bearing = math.radians(bearing_deg)
            corner_lat = math.asin(
                math.sin(lat) * math.cos(angular)
                + math.cos(lat) * math.sin(angular) * math.cos(bearing)
            )
            corner_lon = lon + math.atan2(
                math.sin(bearing) * math.sin(angular) * math.cos(lat),
                math.cos(angular) - math.sin(lat) * math.sin(corner_lat),
            )
            return math.degrees(corner_lat), math.degrees(corner_lon)

        lat_min, lon_min = _corner(225)
        lat_max, lon_max = _corner(45)
        return f"{lat_max},{lat_min},{lon_min},{lon_max}"

from __future__ import annotations
from enum import Enum
from typing import Any
from .client import FlightRadar24API
from .helper import get_value, to_float, to_int


class ScheduleType(Enum):
    ARRIVAL = 1
    DEPARTURE = 2
    GROUND = 3


class AirportStats:
    arrivals_on_time: int
    arrivals_delayed: int
    arrivals_delay_average: int
    arrivals_delay_index: float
    arrivals_canceled: int
    arrivals_on_time_yesterday: int
    arrivals_delayed_yesterday: int
    arrivals_canceled_yesterday: int
    arrivals_on_time_recent: int
    arrivals_delayed_recent: int
    arrivals_canceled_recent: int
    departures_on_time: int
    departures_delayed: int
    departures_delay_average: int
    departures_delay_index: float
    departures_canceled: int
    departures_on_time_yesterday: int
    departures_delayed_yesterday: int
    departures_canceled_yesterday: int
    departures_on_time_recent: int
    departures_delayed_recent: int
    departures_canceled_recent: int


class AirportWeather:
    temperature: float | None = None
    dewpoint: float | None = None
    wind_speed: float | None = None
    wind_direction: int | None = None
    pressure: float | None = None
    humidity: int | None = None
    visibility: float | None = None
    condition: str | None = None
    metar: str | None = None
    flight_category: str | None = None


class AirportAircraftCount:
    ground: int | None = None
    on_ground_visible: int | None = None
    on_ground_total: int | None = None


class AirportState:
    """All data for a single tracked airport."""

    __slots__ = ("code", "stats", "weather", "aircraft_count", "arrivals", "departures", "ground")

    def __init__(self, code: str) -> None:
        self.code: str = code.upper()
        self.stats: AirportStats | None = None
        self.weather: AirportWeather | None = None
        self.aircraft_count: AirportAircraftCount | None = None
        self.arrivals: list[dict[str, Any]] | None = None
        self.departures: list[dict[str, Any]] | None = None
        self.ground: list[dict[str, Any]] | None = None


class AirportProcessor:
    """Tracks zero or more airport subentries. Each subentry is one AirportState."""

    __slots__ = ("_client", "_subentries")

    def __init__(self, client: FlightRadar24API) -> None:
        self._client = client
        self._subentries: dict[str, AirportState] = {}

    @property
    def subentry_airports(self) -> dict[str, AirportState]:
        return self._subentries

    def add_subentry(self, code: str) -> AirportState:
        code = code.upper()
        state = self._subentries.get(code)
        if state is None:
            state = AirportState(code)
            self._subentries[code] = state
        return state

    def remove_subentry(self, code: str) -> None:
        self._subentries.pop(code.upper(), None)

    def update_airport_info(self) -> None:
        """Fetch and populate data for every subentry airport (coordinator tick)."""
        for state in self._subentries.values():
            self._fill_state(state)

    def _fill_state(self, state: AirportState) -> None:
        data = get_value(self._client.get_airport_details(state.code), ["airport", "pluginData"])
        state.stats = self._parse_stats(data)
        state.arrivals = self._parse_schedule(
            ScheduleType.ARRIVAL, get_value(data, ["schedule", "arrivals", "data"])
        )
        state.departures = self._parse_schedule(
            ScheduleType.DEPARTURE, get_value(data, ["schedule", "departures", "data"])
        )
        state.ground = self._parse_ground(get_value(data, ["schedule", "ground", "data"]))
        state.weather = self._parse_weather(get_value(data, ["weather"]))
        state.aircraft_count = self._parse_aircraft_count(get_value(data, ["aircraftCount"]))

    @staticmethod
    def _parse_stats(plugin: dict | None) -> AirportStats:
        stats = AirportStats()
        for direction, key in (("arrivals", "arrivals"), ("departures", "departures")):
            block = get_value(plugin, ["details", "stats", key]) or {}
            setattr(stats, f"{direction}_on_time", to_int(get_value(block, ["today", "quantity", "onTime"])))
            setattr(stats, f"{direction}_delayed", to_int(get_value(block, ["today", "quantity", "delayed"])))
            setattr(stats, f"{direction}_canceled", to_int(get_value(block, ["today", "quantity", "canceled"])))
            setattr(stats, f"{direction}_delay_average", to_int(get_value(block, ["delayAvg"])))
            setattr(stats, f"{direction}_delay_index", to_float(get_value(block, ["delayIndex"])))
            for period in ("yesterday", "recent"):
                for bucket, attr in (("onTime", "on_time"), ("delayed", "delayed"), ("canceled", "canceled")):
                    setattr(
                        stats,
                        f"{direction}_{attr}_{period}",
                        to_int(get_value(block, [period, "quantity", bucket])),
                    )
        return stats

    @staticmethod
    def _parse_weather(data: dict | None) -> AirportWeather | None:
        if not data:
            return None
        weather = AirportWeather()
        weather.temperature = to_float(get_value(data, ["temp", "celsius"]))
        weather.dewpoint = to_float(get_value(data, ["dewpoint", "celsius"]))
        weather.wind_speed = to_float(get_value(data, ["wind", "speed", "kts"]))
        weather.wind_direction = to_int(get_value(data, ["wind", "direction", "degree"]))
        weather.pressure = to_float(get_value(data, ["pressure", "hpa"]))
        weather.humidity = to_int(get_value(data, ["humidity"]))
        weather.visibility = to_float(get_value(data, ["sky", "visibility", "km"]))
        weather.condition = get_value(data, ["sky", "condition", "text"])
        weather.metar = get_value(data, ["metar"])
        weather.flight_category = get_value(data, ["flight", "category"])
        return weather

    @staticmethod
    def _parse_aircraft_count(data: dict | None) -> AirportAircraftCount | None:
        if not data:
            return None
        count = AirportAircraftCount()
        count.ground = to_int(get_value(data, ["ground"]))
        count.on_ground_visible = to_int(get_value(data, ["onGround", "visible"]))
        count.on_ground_total = to_int(get_value(data, ["onGround", "total"]))
        return count

    @staticmethod
    def _base_flight_dict(flight: dict | None) -> dict[str, Any]:
        """Fields shared by both schedule and ground-schedule flight rows."""
        return {
            "flight_id": get_value(flight, ["identification", "id"]),
            "flight_number": get_value(flight, ["identification", "number", "default"]),
            "callsign": get_value(flight, ["identification", "callsign"]),
            "aircraft_code": get_value(flight, ["aircraft", "model", "code"]),
            "aircraft_registration": get_value(flight, ["aircraft", "registration"]),
            "airline": get_value(flight, ["airline", "name"]),
            "airline_iata": get_value(flight, ["airline", "code", "iata"]),
        }

    @classmethod
    def _parse_ground(cls, data: list | None) -> list[dict[str, Any]] | None:
        if data is None:
            return None
        flights: list[dict[str, Any]] = []
        for item in data[:50]:
            flight = get_value(item, ["flight"])
            entry = cls._base_flight_dict(flight)
            entry.update({
                "aircraft_hex": get_value(flight, ["aircraft", "hex"]),
                "owner": get_value(flight, ["owner", "name"]),
                "on_ground_since": to_int(get_value(flight, ["aircraft", "onGroundUpdate"])),
                "on_ground_hours": to_float(get_value(flight, ["aircraft", "hoursDiff"])),
                "on_ground_seconds": to_int(get_value(flight, ["aircraft", "timeDiff"])),
            })
            flights.append(entry)
        return flights

    @classmethod
    def _parse_schedule(cls, schedule: ScheduleType, data: list | None) -> list[dict[str, Any]]:
        if not data:
            return []
        airport = "origin" if schedule == ScheduleType.ARRIVAL else "destination"
        flights: list[dict[str, Any]] = []
        for item in data[:50]:
            flight = get_value(item, ["flight"])
            entry = cls._base_flight_dict(flight)
            entry.update({
                "status_text": get_value(flight, ["status", "text"]),
                "status": get_value(flight, ["status", "generic", "status", "text"]),
                "airport_name": get_value(flight, ["airport", airport, "name"]),
                "airport_code_iata": get_value(flight, ["airport", airport, "code", "iata"]),
                "airport_city": get_value(flight, ["airport", airport, "position", "region", "city"]),
                "time_scheduled_departure": get_value(flight, ["time", "scheduled", "departure"]),
                "time_scheduled_arrival": get_value(flight, ["time", "scheduled", "arrival"]),
            })
            flights.append(entry)
        return flights

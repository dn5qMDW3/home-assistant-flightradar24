from __future__ import annotations
from math import acos, cos, radians, sin
from typing import Any


class Entity:
    """Point on the globe."""

    _default_text = "N/A"

    def __init__(self, latitude: float, longitude: float) -> None:
        self.latitude = latitude
        self.longitude = longitude

    def get_distance_from(self, entity: "Entity") -> float:
        """Great-circle distance in kilometres."""
        lat1, lon1 = radians(self.latitude), radians(self.longitude)
        lat2, lon2 = radians(entity.latitude), radians(entity.longitude)
        return acos(sin(lat1) * sin(lat2) + cos(lat1) * cos(lat2) * cos(lon2 - lon1)) * 6371


class Flight(Entity):
    """Flight record parsed from FR24's real-time feed array."""

    def __init__(self, flight_id: str, info: list[Any]) -> None:
        super().__init__(
            latitude=self._get(info[1]),
            longitude=self._get(info[2]),
        )
        number = info[13] if len(info) > 13 else None
        self.id = flight_id
        self.icao_24bit = self._get(info[0])
        self.heading = self._get(info[3])
        self.altitude = self._get(info[4])
        self.ground_speed = self._get(info[5])
        self.squawk = self._get(info[6])
        self.aircraft_code = self._get(info[8])
        self.registration = self._get(info[9])
        self.time = self._get(info[10])
        self.origin_airport_iata = self._get(info[11])
        self.destination_airport_iata = self._get(info[12])
        self.number = self._get(number)
        self.airline_iata = self._get(number[:2] if isinstance(number, str) else None)
        self.on_ground = self._get(info[14])
        self.vertical_speed = self._get(info[15])
        self.callsign = self._get(info[16])
        self.airline_icao = self._get(info[18]) if len(info) > 18 else self._default_text

    def _get(self, value: Any, default: Any = None) -> Any:
        default = default if default is not None else self._default_text
        return value if value is not None and value != self._default_text else default

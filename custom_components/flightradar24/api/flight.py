from typing import Any
from enum import Enum
from .client import Entity, Flight, FlightRadar24API
from .helper import to_int, get_value
from .event import (
    EVENT_AREA_LANDED,
    EVENT_AREA_TOOK_OFF,
    EVENT_ENTRY,
    EVENT_EXIT,
    EVENT_MOST_TRACKED_NEW,
    EVENT_TRACKED_LANDED,
    EVENT_TRACKED_TOOK_OFF,
    EventManager,
)
import pycountry


class FlightType(Enum):
    TRACKED = 1
    IN_AREA = 2


def _to_country_alpha2(code: str | None) -> str | None:
    if code is None or len(code) == 2:
        return code
    country = pycountry.countries.get(alpha_3=code)
    return country.alpha_2 if country is not None else code


# Field-name → JSON path for ``get_flight_details`` response.
# Country-code fields are post-processed to ISO 3166 alpha-2 after extraction.
_FLIGHT_FIELDS: tuple[tuple[str, tuple[str | int, ...]], ...] = (
    ('flight_number', ('identification', 'number', 'default')),
    ('callsign', ('identification', 'callsign')),
    ('aircraft_registration', ('aircraft', 'registration')),
    ('aircraft_photo_small', ('aircraft', 'images', 'thumbnails', 0, 'src')),
    ('aircraft_photo_medium', ('aircraft', 'images', 'medium', 0, 'src')),
    ('aircraft_photo_large', ('aircraft', 'images', 'large', 0, 'src')),
    ('aircraft_model', ('aircraft', 'model', 'text')),
    ('aircraft_code', ('aircraft', 'model', 'code')),
    ('airline', ('airline', 'name')),
    ('airline_short', ('airline', 'short')),
    ('airline_iata', ('airline', 'code', 'iata')),
    ('airline_icao', ('airline', 'code', 'icao')),
    ('airport_origin_name', ('airport', 'origin', 'name')),
    ('airport_origin_code_iata', ('airport', 'origin', 'code', 'iata')),
    ('airport_origin_code_icao', ('airport', 'origin', 'code', 'icao')),
    ('airport_origin_country_name', ('airport', 'origin', 'position', 'country', 'name')),
    ('airport_origin_country_code', ('airport', 'origin', 'position', 'country', 'code')),
    ('airport_origin_city', ('airport', 'origin', 'position', 'region', 'city')),
    ('airport_origin_timezone_offset', ('airport', 'origin', 'timezone', 'offset')),
    ('airport_origin_timezone_abbr', ('airport', 'origin', 'timezone', 'abbr')),
    ('airport_origin_terminal', ('airport', 'origin', 'info', 'terminal')),
    ('airport_origin_latitude', ('airport', 'origin', 'position', 'latitude')),
    ('airport_origin_longitude', ('airport', 'origin', 'position', 'longitude')),
    ('airport_destination_name', ('airport', 'destination', 'name')),
    ('airport_destination_code_iata', ('airport', 'destination', 'code', 'iata')),
    ('airport_destination_code_icao', ('airport', 'destination', 'code', 'icao')),
    ('airport_destination_country_name', ('airport', 'destination', 'position', 'country', 'name')),
    ('airport_destination_country_code', ('airport', 'destination', 'position', 'country', 'code')),
    ('airport_destination_city', ('airport', 'destination', 'position', 'region', 'city')),
    ('airport_destination_timezone_offset', ('airport', 'destination', 'timezone', 'offset')),
    ('airport_destination_timezone_abbr', ('airport', 'destination', 'timezone', 'abbr')),
    ('airport_destination_terminal', ('airport', 'destination', 'info', 'terminal')),
    ('airport_destination_latitude', ('airport', 'destination', 'position', 'latitude')),
    ('airport_destination_longitude', ('airport', 'destination', 'position', 'longitude')),
    ('time_scheduled_departure', ('time', 'scheduled', 'departure')),
    ('time_scheduled_arrival', ('time', 'scheduled', 'arrival')),
    ('time_real_departure', ('time', 'real', 'departure')),
    ('time_real_arrival', ('time', 'real', 'arrival')),
    ('time_estimated_departure', ('time', 'estimated', 'departure')),
    ('time_estimated_arrival', ('time', 'estimated', 'arrival')),
    # Premium-only EMS / Mode-S data (populated when logged in, None otherwise).
    ('mach', ('ems', 'mach')),
    ('indicated_airspeed', ('ems', 'ias')),
    ('true_airspeed', ('ems', 'tas')),
    ('outside_air_temperature', ('ems', 'oat')),
    ('wind_direction', ('ems', 'wind_dir')),
    ('wind_speed', ('ems', 'wind_speed')),
    ('gps_altitude', ('ems', 'agps')),
    ('selected_altitude', ('ems', 'mcp')),
)


class FlightProcessor:
    __slots__ = ('_in_area', '_tracked', '_most_tracked', '_entered', '_exited', '_min_altitude', '_max_altitude',
                 '_point', '_client', '_bounds', '_event_manager')

    def __init__(
            self,
            client: FlightRadar24API,
            event_manager: EventManager,
            min_altitude: int,
            max_altitude: int,
            point: Entity,
            bounds: str,
    ) -> None:
        self._min_altitude = min_altitude
        self._max_altitude = max_altitude
        self._point = point
        self._client = client
        self._bounds = bounds
        self._event_manager = event_manager
        self._in_area: dict[str, dict[str, Any]] | None = None
        self._tracked: dict[str, dict[str, Any]] = {}
        self._most_tracked: dict[str, dict[str, Any]] | None = None
        self._entered: list[dict[str, Any]] = []
        self._exited: list[dict[str, Any]] = []

    @property
    def tracked(self) -> dict[str, dict[str, Any]]:
        return self._tracked

    @property
    def tracked_list(self) -> list[dict[str, Any]]:
        return list(self._tracked.values()) if self._tracked else []

    @property
    def in_area_list(self) -> list[dict[str, Any]]:
        return list(self._in_area.values()) if self._in_area else []

    @property
    def most_tracked_list(self) -> list[dict[str, Any]] | None:
        return list(self._most_tracked.values()) if self._most_tracked else None

    @property
    def entered_list(self) -> list[dict[str, Any]]:
        return self._entered

    @property
    def exited_list(self) -> list[dict[str, Any]]:
        return self._exited

    def clear_tracked(self) -> None:
        """Clear ephemeral tracked flights. Preserves subentry-added aircraft."""
        self._tracked = {
            fid: entry for fid, entry in self._tracked.items()
            if entry.get("from_subentry")
        }

    def set_tracked(self, tracked: dict[str, dict[str, Any]]) -> None:
        self._tracked = tracked

    def enable_most_tracked(self) -> None:
        self._most_tracked = {}

    @staticmethod
    def _registration_placeholder(registration: str) -> dict[str, Any]:
        """Synthetic registration-only entry, matching the dict shape
        ``_find_flight`` already produces for ``type=aircraft`` results
        (see the elif branch around line 289). Lets ``update_flights_tracked``
        keep querying ``feed.js?reg=<reg>`` every cycle.
        """
        return {
            "id": registration,
            "callsign": None,
            "flight_number": None,
            "aircraft_registration": registration,
            "tracked_type": "not_airborne",
        }

    def add_track(self, number: str, from_subentry: bool = False) -> dict | None:
        found: dict[str, dict[str, Any]] = {}
        number = number.upper()
        self._find_flight(found, number)
        if not found:
            if not from_subentry:
                return None
            found[number] = self._registration_placeholder(number)
        if from_subentry:
            for entry in found.values():
                entry["from_subentry"] = True
        self._tracked = self._tracked | found if self._tracked else found

        return found

    def remove_track(self, number: str) -> dict | None:
        number = number.upper()
        for flight_id, flight in self._tracked.items():
            if (number == flight.get('aircraft_registration') or
                    number == flight.get('flight_number') or
                    number == flight.get('callsign')):
                return self._tracked.pop(flight_id)
        return None

    def update_flights_in_area(self) -> None:
        self._entered = {}
        self._exited = {}
        flights = self._client.get_flights(bounds=self._bounds)
        current: dict[str, dict[str, Any]] = {}
        for obj in flights:
            if not self._min_altitude <= obj.altitude <= self._max_altitude:
                continue
            self._update_flights_data(obj, current, self._in_area, FlightType.IN_AREA)

        if self._in_area is not None:
            entries = current.keys() - self._in_area.keys()
            self._entered = [current[x] for x in entries]
            exits = self._in_area.keys() - current.keys()
            self._exited = [self._in_area[x] for x in exits]
            self._event_manager.add_events(EVENT_ENTRY, self._entered)
            self._event_manager.add_events(EVENT_EXIT, self._exited)
        self._in_area = current

    def update_flights_tracked(self) -> None:
        if not self._tracked:
            return
        current = self._fetch_tracked_live()
        self._reconcile_tracked_remainder(current)
        self._tracked = current

    def _fetch_tracked_live(self) -> dict[str, dict[str, Any]]:
        """Ask FR24 for live data on every registration we know about."""
        current: dict[str, dict[str, Any]] = {}
        registrations = [
            entry['aircraft_registration']
            for entry in self._tracked.values()
            if entry.get('aircraft_registration')
        ]
        if not registrations:
            return current
        for obj in self._client.get_flights(registration=','.join(registrations)):
            self._update_flights_data(obj, current, self._tracked, FlightType.TRACKED)
            if obj.id in current:
                current[obj.id]['tracked_type'] = 'live'
        return current

    def _reconcile_tracked_remainder(self, current: dict[str, dict[str, Any]]) -> None:
        """For tracked entries not matched live, preserve placeholders or re-search."""
        live_identifiers: set[str] = {
            ident for entry in current.values()
            for ident in (entry.get('flight_number'), entry.get('callsign'))
            if ident
        }
        live_registrations: set[str] = {
            entry['aircraft_registration'] for entry in current.values()
            if entry.get('aircraft_registration')
        }

        for flight_id in self._tracked.keys() - current.keys():
            entry = self._tracked[flight_id]
            flight_number = entry.get('flight_number')
            callsign = entry.get('callsign')

            # Already represented by a live flight with matching number/callsign?
            if flight_number and flight_number in live_identifiers:
                continue
            if not flight_number and callsign and callsign in live_identifiers:
                continue

            number = flight_number or callsign
            if not number:
                # Registration-only placeholder: preserve unless a live flight
                # with the same registration is already in current.
                reg = entry.get('aircraft_registration')
                if reg and reg not in live_registrations:
                    current[flight_id] = {**entry, 'tracked_type': 'not_airborne'}
                continue

            # Re-search by number/callsign; if still not found, keep as not_found.
            before = len(current)
            self._find_flight(current, number)
            if len(current) > before:
                live_identifiers.add(number)
            else:
                current[flight_id] = {**entry, 'tracked_type': 'not_found'}

    def _find_flight(self, current: dict[str, dict[str, Any]], number: str) -> None:
        def process_search_flight(objects: dict, search: str) -> dict | None:
            live = objects.get('live')
            if live:
                for element in live:
                    detail = element.get('detail')
                    if detail and search in (detail.get('reg'), detail.get('callsign'), detail.get('flight')):
                        return element
            schedule = objects.get('schedule')
            if schedule:
                for element in schedule:
                    detail = element.get('detail')
                    if detail and search in (detail.get('callsign'), detail.get('flight')):
                        return element
            aircraft = objects.get('aircraft')
            if aircraft:
                for element in aircraft:
                    if element.get('id') == search:
                        return element
            return None

        flights = self._client.search(number)
        found = process_search_flight(flights, number)
        if not found:
            return
        if found.get('type') == 'live':
            data = [None] * 20
            data[1] = get_value(found, ['detail', 'lat'])
            data[2] = get_value(found, ['detail', 'lon'])
            data[13] = []
            # Note: reg/callsign from ``found['detail']`` are re-fetched via
            # get_flight_details downstream; no need to set them on the Flight obj.
            self._update_flights_data(Flight(found.get('id'), data), current, self._tracked)
        elif found.get('type') == 'aircraft':
            # Aircraft is known to FR24 but not currently flying and has no
            # scheduled flight we can resolve. Add a registration-only
            # placeholder; update_flights_tracked() will upgrade it to 'live'
            # once the aircraft takes off.
            current[found.get('id')] = {
                'id': found.get('id'),
                'callsign': None,
                'flight_number': None,
                'aircraft_registration': found.get('id'),
                'tracked_type': 'not_airborne',
            }
            return
        else:
            current[found.get('id')] = {
                'id': found.get('id'),
                'callsign': found['detail'].get('callsign'),
                'flight_number': found['detail'].get('flight'),
                'aircraft_registration': None,
            }
        current[found.get('id')]['tracked_type'] = found.get('type')

    def update_most_tracked(self) -> None:
        if self._most_tracked is None:
            return
        flights = self._client.get_most_tracked()
        current: dict[str, dict[str, Any]] = {}
        for obj in flights.get('data'):
            current[obj['flight_id']] = {
                'id': obj.get('flight_id'),
                'flight_number': obj.get('flight'),
                'callsign': obj.get('callsign'),
                'squawk': obj.get('squawk'),
                'clicks': obj.get('clicks'),
                'airport_origin_code_iata': obj.get('from_iata'),
                'airport_origin_city': obj.get('from_city'),
                'airport_destination_code_iata': obj.get('to_iata'),
                'airport_destination_city': obj.get('to_city'),
                'aircraft_code': obj.get('model'),
                'aircraft_model': obj.get('type'),
                'on_ground': obj.get('on_ground'),
            }
        entries = [current[x] for x in (current.keys() - self._most_tracked.keys())]
        self._most_tracked = current
        self._event_manager.add_events(EVENT_MOST_TRACKED_NEW, entries)

    def _update_flights_data(
            self,
            obj: Flight,
            current: dict[str, dict[str, Any]],
            tracked: dict[str, dict[str, Any]] | None,
            sensor_type: FlightType | None = None,
    ) -> None:
        previous = tracked.get(obj.id) if tracked else None
        last_on_ground = previous.get('on_ground') if previous else None

        if previous and self._is_valid(previous) and to_int(last_on_ground) == obj.on_ground:
            flight = previous
        else:
            flight = self._get_flight_data(self._client.get_flight_details(obj))

        if flight is None:
            return

        distance = obj.get_distance_from(self._point)
        flight.update({
            'latitude': obj.latitude,
            'longitude': obj.longitude,
            'altitude': obj.altitude,
            'heading': obj.heading,
            'ground_speed': obj.ground_speed,
            'squawk': obj.squawk,
            'vertical_speed': obj.vertical_speed,
            'on_ground': obj.on_ground,
            'distance': distance,
            'closest_distance': min(distance, flight.get('closest_distance', distance)),
        })
        current[flight['id']] = flight
        self._takeoff_and_landing(flight, last_on_ground, obj.on_ground, sensor_type)

    # (sensor_type, is_on_ground) → event name
    _TAKEOFF_LANDING_EVENTS: dict[tuple[FlightType, int], str] = {
        (FlightType.IN_AREA, 0): EVENT_AREA_TOOK_OFF,
        (FlightType.IN_AREA, 1): EVENT_AREA_LANDED,
        (FlightType.TRACKED, 0): EVENT_TRACKED_TOOK_OFF,
        (FlightType.TRACKED, 1): EVENT_TRACKED_LANDED,
    }

    def _takeoff_and_landing(
            self,
            flight: dict[str, Any],
            previous: Any,
            current: Any,
            sensor_type: FlightType | None,
    ) -> None:
        if sensor_type is None:
            return
        previous = to_int(previous)
        current = to_int(current)
        if previous is None or current is None or previous == current:
            return
        event = self._TAKEOFF_LANDING_EVENTS.get((sensor_type, current))
        if event:
            self._event_manager.add_events(event, [flight])

    def _get_flight_data(self, flight: dict) -> dict[str, Any] | None:
        flight_id = get_value(flight, ['identification', 'id'])
        if flight_id is None:
            return None

        data: dict[str, Any] = {'id': flight_id}
        for key, path in _FLIGHT_FIELDS:
            data[key] = get_value(flight, list(path))
        for key in ('airport_origin_country_code', 'airport_destination_country_code'):
            data[key] = _to_country_alpha2(data[key])
        return data

    def _is_valid(self, flight: dict) -> bool:
        return all(flight.get(f) is not None for f in ['flight_number', 'time_scheduled_departure',
                                                       'time_estimated_arrival'])

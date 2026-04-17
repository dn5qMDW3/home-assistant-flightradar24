from enum import Enum
from .client import FlightRadar24API
from .helper import to_int, to_float, get_value
from typing import Any


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


class AirportProcessor:
    __slots__ = (
        '_client', '_code', '_stats', '_arrivals', '_departures', '_ground',
        '_weather', '_aircraft_count',
    )

    def __init__(self, client: FlightRadar24API) -> None:
        self._client = client
        self._code: str | None = None
        self._stats: AirportStats | None = None
        self._weather: AirportWeather | None = None
        self._aircraft_count: AirportAircraftCount | None = None
        self._arrivals: list[dict[str, Any]] | None = None
        self._departures: list[dict[str, Any]] | None = None
        self._ground: list[dict[str, Any]] | None = None

    @property
    def code(self) -> str | None:
        return self._code

    @property
    def stats(self) -> AirportStats | None:
        return self._stats

    @property
    def weather(self) -> AirportWeather | None:
        return self._weather

    @property
    def aircraft_count(self) -> AirportAircraftCount | None:
        return self._aircraft_count

    @property
    def arrivals(self) -> list[dict[str, Any]]:
        return self._arrivals

    @property
    def departures(self) -> list[dict[str, Any]]:
        return self._departures

    @property
    def ground(self) -> list[dict[str, Any]] | None:
        return self._ground

    def set_track(self, code: str) -> None:
        code = code.upper()
        self.update_airport_info(code)
        self._code = code

    def restore_code(self, code: str) -> None:
        code = code.upper()
        self._code = code

    def remove_track(self) -> None:
        self._code = None
        self._stats = None
        self._weather = None
        self._aircraft_count = None
        self._arrivals = None
        self._departures = None
        self._ground = None

    def update_airport_info(self, code: str = None) -> None:
        if not self._code and not code:
            return

        data = get_value(self._client.get_airport_details(self._code or code), ['airport', 'pluginData'])
        self._stats = AirportStats()
        stats = get_value(data, ['details', 'stats', 'arrivals'])
        self._stats.arrivals_on_time = to_int(get_value(stats, ['today', 'quantity', 'onTime']))
        self._stats.arrivals_delayed = to_int(get_value(stats, ['today', 'quantity', 'delayed']))
        self._stats.arrivals_canceled = to_int(get_value(stats, ['today', 'quantity', 'canceled']))
        self._stats.arrivals_delay_average = to_int(get_value(stats, ['delayAvg']))
        self._stats.arrivals_delay_index = to_float(get_value(stats, ['delayIndex']))
        self._stats.arrivals_on_time_yesterday = to_int(get_value(stats, ['yesterday', 'quantity', 'onTime']))
        self._stats.arrivals_delayed_yesterday = to_int(get_value(stats, ['yesterday', 'quantity', 'delayed']))
        self._stats.arrivals_canceled_yesterday = to_int(get_value(stats, ['yesterday', 'quantity', 'canceled']))
        self._stats.arrivals_on_time_recent = to_int(get_value(stats, ['recent', 'quantity', 'onTime']))
        self._stats.arrivals_delayed_recent = to_int(get_value(stats, ['recent', 'quantity', 'delayed']))
        self._stats.arrivals_canceled_recent = to_int(get_value(stats, ['recent', 'quantity', 'canceled']))
        stats = get_value(data, ['details', 'stats', 'departures'])
        self._stats.departures_on_time = to_int(get_value(stats, ['today', 'quantity', 'onTime']))
        self._stats.departures_delayed = to_int(get_value(stats, ['today', 'quantity', 'delayed']))
        self._stats.departures_canceled = to_int(get_value(stats, ['today', 'quantity', 'canceled']))
        self._stats.departures_delay_average = to_int(get_value(stats, ['delayAvg']))
        self._stats.departures_delay_index = to_float(get_value(stats, ['delayIndex']))
        self._stats.departures_on_time_yesterday = to_int(get_value(stats, ['yesterday', 'quantity', 'onTime']))
        self._stats.departures_delayed_yesterday = to_int(get_value(stats, ['yesterday', 'quantity', 'delayed']))
        self._stats.departures_canceled_yesterday = to_int(get_value(stats, ['yesterday', 'quantity', 'canceled']))
        self._stats.departures_on_time_recent = to_int(get_value(stats, ['recent', 'quantity', 'onTime']))
        self._stats.departures_delayed_recent = to_int(get_value(stats, ['recent', 'quantity', 'delayed']))
        self._stats.departures_canceled_recent = to_int(get_value(stats, ['recent', 'quantity', 'canceled']))

        self._update_schedule(ScheduleType.ARRIVAL, get_value(data, ['schedule', 'arrivals', 'data']))
        self._update_schedule(ScheduleType.DEPARTURE, get_value(data, ['schedule', 'departures', 'data']))
        self._update_ground(get_value(data, ['schedule', 'ground', 'data']))
        self._update_weather(get_value(data, ['weather']))
        self._update_aircraft_count(get_value(data, ['aircraftCount']))

    def _update_ground(self, data: list | None) -> None:
        if not data:
            self._ground = [] if data == [] else None
            return
        flights: list[dict[str, Any]] = []
        for i, item in enumerate(data):
            if i == 50:
                break
            item = get_value(item, ['flight'])
            flights.append({
                'flight_id': get_value(item, ['identification', 'id']),
                'flight_number': get_value(item, ['identification', 'number', 'default']),
                'callsign': get_value(item, ['identification', 'callsign']),
                'aircraft_code': get_value(item, ['aircraft', 'model', 'code']),
                'aircraft_model': get_value(item, ['aircraft', 'model', 'text']),
                'aircraft_registration': get_value(item, ['aircraft', 'registration']),
                'aircraft_hex': get_value(item, ['aircraft', 'hex']),
                'aircraft_country_code': get_value(item, ['aircraft', 'country', 'code']),
                'airline': get_value(item, ['airline', 'name']),
                'airline_short': get_value(item, ['airline', 'short']),
                'airline_iata': get_value(item, ['airline', 'code', 'iata']),
                'airline_icao': get_value(item, ['airline', 'code', 'icao']),
                'owner': get_value(item, ['owner', 'name']),
                'on_ground_since': to_int(get_value(item, ['aircraft', 'onGroundUpdate'])),
                'on_ground_hours': to_float(get_value(item, ['aircraft', 'hoursDiff'])),
                'on_ground_seconds': to_int(get_value(item, ['aircraft', 'timeDiff'])),
            })
        self._ground = flights

    def _update_weather(self, data: dict | None) -> None:
        if not data:
            self._weather = None
            return
        weather = AirportWeather()
        weather.temperature = to_float(get_value(data, ['temp', 'celsius']))
        weather.dewpoint = to_float(get_value(data, ['dewpoint', 'celsius']))
        weather.wind_speed = to_float(get_value(data, ['wind', 'speed', 'kts']))
        weather.wind_direction = to_int(get_value(data, ['wind', 'direction', 'degree']))
        weather.pressure = to_float(get_value(data, ['pressure', 'hpa']))
        weather.humidity = to_int(get_value(data, ['humidity']))
        weather.visibility = to_float(get_value(data, ['sky', 'visibility', 'km']))
        weather.condition = get_value(data, ['sky', 'condition', 'text'])
        weather.metar = get_value(data, ['metar'])
        weather.flight_category = get_value(data, ['flight', 'category'])
        self._weather = weather

    def _update_aircraft_count(self, data: dict | None) -> None:
        if not data:
            self._aircraft_count = None
            return
        count = AirportAircraftCount()
        count.ground = to_int(get_value(data, ['ground']))
        count.on_ground_visible = to_int(get_value(data, ['onGround', 'visible']))
        count.on_ground_total = to_int(get_value(data, ['onGround', 'total']))
        self._aircraft_count = count

    def _update_schedule(self, schedule: ScheduleType, data: list) -> None:
        flights = []
        airport = 'origin' if schedule == ScheduleType.ARRIVAL else 'destination'
        i = 0
        for item in data:
            i += 1
            item = get_value(item, ['flight'])
            flights.append({
                'status_text': get_value(item, ['status', 'text']),
                'status': get_value(item, ['status', 'generic', 'status', 'text']),
                'flight_id': get_value(item, ['identification', 'id']),
                'flight_number': get_value(item, ['identification', 'number', 'default']),
                'callsign': get_value(item, ['identification', 'callsign']),
                'aircraft_code': get_value(item, ['aircraft', 'model', 'code']),
                'aircraft_model': get_value(item, ['aircraft', 'model', 'text']),
                'aircraft_registration': get_value(item, ['aircraft', 'registration']),
                'airline': get_value(item, ['airline', 'name']),
                'airline_short': get_value(item, ['airline', 'short']),
                'airline_iata': get_value(item, ['airline', 'code', 'iata']),
                'airline_icao': get_value(item, ['airline', 'code', 'icao']),
                'airport_name': get_value(item, ['airport', airport, 'name']),
                'airport_code_iata': get_value(item, ['airport', airport, 'code', 'iata']),
                'airport_code_icao': get_value(item, ['airport', airport, 'code', 'icao']),
                'airport_country_name': get_value(item, ['airport', airport, 'position', 'country', 'name']),
                'airport_country_code': get_value(item, ['airport', airport, 'position', 'country', 'code']),
                'airport_city': get_value(item, ['airport', airport, 'position', 'region', 'city']),
                'time_scheduled_departure': get_value(item, ['time', 'scheduled', 'departure']),
                'time_scheduled_arrival': get_value(item, ['time', 'scheduled', 'arrival']),
                'time_real_departure': get_value(item, ['time', 'real', 'departure']),
                'time_real_arrival': get_value(item, ['time', 'real', 'arrival']),
                'time_estimated_departure': get_value(item, ['time', 'estimated', 'departure']),
                'time_estimated_arrival': get_value(item, ['time', 'estimated', 'arrival']),
            })
            if i == 50:
                break
        if schedule == ScheduleType.ARRIVAL:
            self._arrivals = flights
        else:
            self._departures = flights

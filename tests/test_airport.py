"""Tests for AirportProcessor parsers.

The parse methods are static and pure — they take the already-fetched
pluginData dict (or sub-dicts) and return parsed objects. No HTTP, no
coordinator needed.
"""
from __future__ import annotations

from api.airport import (
    AirportAircraftCount,
    AirportProcessor,
    AirportState,
    AirportStats,
    AirportWeather,
    ScheduleType,
)


class TestParseStats:
    def test_full_block(self, load_fixture):
        plugin = load_fixture("airport_details_lhr.json")["airport"]["pluginData"]
        stats = AirportProcessor._parse_stats(plugin)
        assert stats.arrivals_on_time == 248
        assert stats.arrivals_delayed == 64
        assert stats.arrivals_canceled == 3
        assert stats.arrivals_delay_average == 18
        assert stats.arrivals_delay_index == 0.35
        assert stats.arrivals_on_time_yesterday == 577
        assert stats.arrivals_on_time_recent == 55
        assert stats.departures_on_time == 219
        assert stats.departures_delay_index == 0.42

    def test_empty_plugin_returns_stats_with_none_fields(self):
        stats = AirportProcessor._parse_stats(None)
        assert isinstance(stats, AirportStats)
        assert stats.arrivals_on_time is None
        assert stats.departures_delay_index is None

    def test_partial_plugin_only_today(self):
        plugin = {"details": {"stats": {
            "arrivals":   {"today": {"quantity": {"onTime": 100}}},
            "departures": {},
        }}}
        stats = AirportProcessor._parse_stats(plugin)
        assert stats.arrivals_on_time == 100
        assert stats.arrivals_delayed is None
        assert stats.arrivals_on_time_yesterday is None
        assert stats.departures_on_time is None


class TestParseWeather:
    def test_none_input_returns_none(self):
        assert AirportProcessor._parse_weather(None) is None

    def test_full_weather(self, load_fixture):
        plugin = load_fixture("airport_details_lhr.json")["airport"]["pluginData"]
        weather = AirportProcessor._parse_weather(plugin["weather"])
        assert isinstance(weather, AirportWeather)
        assert weather.temperature == 16.0
        assert weather.dewpoint == 10.0
        assert weather.wind_speed == 15.0
        assert weather.wind_direction == 270
        assert weather.pressure == 1013.0
        assert weather.humidity == 68
        assert weather.visibility == 10.0
        assert weather.condition == "Broken clouds"
        assert weather.metar.startswith("EGLL ")
        assert weather.flight_category == "VFR"

    def test_missing_subblocks_yields_none_fields(self):
        weather = AirportProcessor._parse_weather({"metar": "TEST"})
        assert weather.metar == "TEST"
        assert weather.temperature is None
        assert weather.wind_speed is None


class TestParseAircraftCount:
    def test_none_returns_none(self):
        assert AirportProcessor._parse_aircraft_count(None) is None

    def test_full(self, load_fixture):
        plugin = load_fixture("airport_details_lhr.json")["airport"]["pluginData"]
        count = AirportProcessor._parse_aircraft_count(plugin["aircraftCount"])
        assert isinstance(count, AirportAircraftCount)
        assert count.ground == 159
        assert count.on_ground_visible == 124
        assert count.on_ground_total == 159

    def test_missing_on_ground_block(self):
        count = AirportProcessor._parse_aircraft_count({"ground": 10})
        assert count.ground == 10
        assert count.on_ground_visible is None
        assert count.on_ground_total is None


class TestParseGround:
    def test_none_input_returns_none(self):
        assert AirportProcessor._parse_ground(None) is None

    def test_empty_list_returns_empty_list(self):
        assert AirportProcessor._parse_ground([]) == []

    def test_full_entry(self, load_fixture):
        plugin = load_fixture("airport_details_lhr.json")["airport"]["pluginData"]
        ground = AirportProcessor._parse_ground(plugin["schedule"]["ground"]["data"])
        assert len(ground) == 1
        entry = ground[0]
        assert entry["flight_number"] == "BA201"
        assert entry["callsign"] == "SHT3B"
        assert entry["aircraft_registration"] == "G-EUUY"
        assert entry["aircraft_hex"] == "406B7A"
        assert entry["aircraft_country_code"] == "GB"
        assert entry["on_ground_since"] == 1700010000
        assert entry["on_ground_hours"] == 2.5
        assert entry["on_ground_seconds"] == 9000

    def test_truncates_at_50(self):
        data = [{"flight": {"identification": {"id": str(i)}}} for i in range(60)]
        ground = AirportProcessor._parse_ground(data)
        assert len(ground) == 50


class TestParseSchedule:
    def test_none_returns_empty(self):
        assert AirportProcessor._parse_schedule(ScheduleType.ARRIVAL, None) == []

    def test_empty_list_returns_empty(self):
        assert AirportProcessor._parse_schedule(ScheduleType.DEPARTURE, []) == []

    def test_arrival_uses_origin(self, load_fixture):
        plugin = load_fixture("airport_details_lhr.json")["airport"]["pluginData"]
        arrivals = AirportProcessor._parse_schedule(
            ScheduleType.ARRIVAL, plugin["schedule"]["arrivals"]["data"]
        )
        assert len(arrivals) == 1
        assert arrivals[0]["flight_number"] == "BA117"
        # origin airport = JFK for an arrival into LHR
        assert arrivals[0]["airport_code_iata"] == "JFK"
        assert arrivals[0]["airport_country_code"] == "US"

    def test_truncates_at_50(self):
        data = [{"flight": {"identification": {"id": str(i)}}} for i in range(100)]
        flights = AirportProcessor._parse_schedule(ScheduleType.ARRIVAL, data)
        assert len(flights) == 50


class TestAirportState:
    def test_upper_cases_code(self):
        state = AirportState("lhr")
        assert state.code == "LHR"

    def test_starts_empty(self):
        state = AirportState("LHR")
        assert state.stats is None
        assert state.weather is None
        assert state.aircraft_count is None
        assert state.arrivals is None
        assert state.departures is None
        assert state.ground is None


class TestProcessorSubentryAPI:
    def test_add_subentry_is_idempotent(self):
        proc = AirportProcessor(client=None)
        s1 = proc.add_subentry("lhr")
        s2 = proc.add_subentry("LHR")
        assert s1 is s2
        assert set(proc.subentry_airports) == {"LHR"}

    def test_remove_subentry(self):
        proc = AirportProcessor(client=None)
        proc.add_subentry("LHR")
        proc.remove_subentry("lhr")
        assert proc.subentry_airports == {}

    def test_remove_unknown_is_noop(self):
        proc = AirportProcessor(client=None)
        proc.remove_subentry("ZZZ")  # should not raise

"""Tests for FlightProcessor parsing helpers and the vendored Flight /
Entity / bounds math.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.client import Entity, Flight, FlightRadar24API
from api.event import EventManager
from api.flight import FlightProcessor, _to_country_alpha2


class TestToCountryAlpha2:
    def test_none_passes_through(self):
        assert _to_country_alpha2(None) is None

    def test_alpha2_passes_through(self):
        assert _to_country_alpha2("US") == "US"

    def test_alpha3_converts(self):
        assert _to_country_alpha2("USA") == "US"
        assert _to_country_alpha2("GBR") == "GB"

    def test_unknown_alpha3_returns_as_is(self):
        # invalid alpha-3 is passed through rather than raising
        assert _to_country_alpha2("ZZZ") == "ZZZ"


class TestGetFlightData:
    @pytest.fixture
    def processor(self) -> FlightProcessor:
        return FlightProcessor(
            client=MagicMock(),
            event_manager=EventManager(),
            min_altitude=-1,
            max_altitude=100000,
            point=Entity(0.0, 0.0),
            bounds="",
        )

    def test_full_extraction(self, processor, load_fixture):
        flight = load_fixture("flight_details_full.json")
        data = processor._get_flight_data(flight)
        assert data["id"] == "3f43cd65"
        assert data["flight_number"] == "BA117"
        assert data["callsign"] == "SHT1A"
        assert data["aircraft_registration"] == "G-YMMP"
        assert data["aircraft_code"] == "B772"
        assert data["airline_iata"] == "BA"
        assert data["airport_origin_code_iata"] == "LHR"
        assert data["airport_destination_code_iata"] == "JFK"
        # alpha-3 → alpha-2 post-processing
        assert data["airport_origin_country_code"] == "GB"
        assert data["airport_destination_country_code"] == "US"
        # EMS block populates
        assert data["mach"] == 0.82
        assert data["indicated_airspeed"] == 320
        assert data["outside_air_temperature"] == -52

    def test_missing_id_returns_none(self, processor):
        assert processor._get_flight_data({}) is None

    def test_minimal_id_only(self, processor):
        data = processor._get_flight_data({"identification": {"id": "xyz"}})
        assert data["id"] == "xyz"
        # Every other field is None
        assert data["flight_number"] is None
        assert data["mach"] is None
        assert data["airport_origin_country_code"] is None


class TestFindFlight:
    @pytest.fixture
    def processor(self) -> FlightProcessor:
        return FlightProcessor(
            client=MagicMock(),
            event_manager=EventManager(),
            min_altitude=-1,
            max_altitude=100000,
            point=Entity(0.0, 0.0),
            bounds="",
        )

    def test_live_category_match_by_registration(self, processor):
        processor._client.search.return_value = {
            "live": [{"id": "lf1", "type": "live", "detail": {
                "reg": "4X-ISR", "callsign": "ELY1", "flight": "LY001",
                "lat": 32.0, "lon": 34.9,
            }}],
            "schedule": [],
            "aircraft": [],
        }
        # _find_flight calls _update_flights_data which in turn calls
        # get_flight_details. Stub get_flight_details to return id-only.
        processor._client.get_flight_details.return_value = {
            "identification": {"id": "lf1"}
        }
        current: dict = {}
        processor._find_flight(current, "4X-ISR")
        assert "lf1" in current
        assert current["lf1"]["tracked_type"] == "live"

    def test_aircraft_category_creates_not_airborne_placeholder(self, processor):
        processor._client.search.return_value = {
            "live": [],
            "schedule": [],
            "aircraft": [{"id": "4X-ISR", "type": "aircraft"}],
        }
        current: dict = {}
        processor._find_flight(current, "4X-ISR")
        assert "4X-ISR" in current
        entry = current["4X-ISR"]
        assert entry["tracked_type"] == "not_airborne"
        assert entry["aircraft_registration"] == "4X-ISR"
        assert entry["flight_number"] is None
        assert entry["callsign"] is None

    def test_schedule_category_match_by_flight_number(self, processor):
        processor._client.search.return_value = {
            "live": [],
            "schedule": [{"id": "sch1", "type": "schedule", "detail": {
                "callsign": "SHT9X", "flight": "BA999"
            }}],
            "aircraft": [],
        }
        current: dict = {}
        processor._find_flight(current, "BA999")
        assert "sch1" in current
        assert current["sch1"]["flight_number"] == "BA999"

    def test_no_match_leaves_current_empty(self, processor):
        processor._client.search.return_value = {
            "live": [], "schedule": [], "aircraft": [],
        }
        current: dict = {}
        processor._find_flight(current, "NOPE")
        assert current == {}


class TestSubentryPlaceholder:
    @pytest.fixture
    def processor(self) -> FlightProcessor:
        return FlightProcessor(
            client=MagicMock(),
            event_manager=EventManager(),
            min_altitude=-1,
            max_altitude=100000,
            point=Entity(0.0, 0.0),
            bounds="",
        )

    def test_empty_search_seeds_subentry_placeholder(self, processor):
        processor._client.search.return_value = {
            "live": [], "schedule": [], "aircraft": [],
        }
        found = processor.add_track("58-0052", from_subentry=True)
        assert found is not None
        assert "58-0052" in processor.tracked
        entry = processor.tracked["58-0052"]
        assert entry["aircraft_registration"] == "58-0052"
        assert entry["tracked_type"] == "not_airborne"
        assert entry["from_subentry"] is True
        assert entry["flight_number"] is None
        assert entry["callsign"] is None

    def test_empty_search_without_subentry_returns_none(self, processor):
        processor._client.search.return_value = {
            "live": [], "schedule": [], "aircraft": [],
        }
        found = processor.add_track("58-0052", from_subentry=False)
        assert found is None
        assert processor.tracked == {}


class TestAddTrack:
    @pytest.fixture
    def processor(self) -> FlightProcessor:
        return FlightProcessor(
            client=MagicMock(),
            event_manager=EventManager(),
            min_altitude=-1,
            max_altitude=100000,
            point=Entity(0.0, 0.0),
            bounds="",
        )

    def test_from_subentry_flag_propagates(self, processor):
        processor._client.search.return_value = {
            "live": [], "schedule": [],
            "aircraft": [{"id": "G-ABCD", "type": "aircraft"}],
        }
        found = processor.add_track("g-abcd", from_subentry=True)
        assert found is not None
        assert found["G-ABCD"]["from_subentry"] is True
        # Clear preserves subentry-tagged
        processor.clear_tracked()
        assert "G-ABCD" in processor.tracked

    def test_clear_tracked_drops_ephemeral(self, processor):
        processor._client.search.return_value = {
            "live": [], "schedule": [],
            "aircraft": [{"id": "G-ABCD", "type": "aircraft"}],
        }
        processor.add_track("G-ABCD", from_subentry=False)
        assert "G-ABCD" in processor.tracked
        processor.clear_tracked()
        assert processor.tracked == {}


class TestFlightConstructor:
    def test_full_info_array(self):
        info = ["4A12F3", 52.5, 13.4, 90, 35000, 450, "1234", None, "B738",
                "G-ABCD", 1234567890, "LHR", "JFK", "BA117", 0, 0, "SHT1A", None, "BAW"]
        f = Flight("39abc01", info)
        assert f.id == "39abc01"
        assert f.altitude == 35000
        assert f.registration == "G-ABCD"
        assert f.airline_iata == "BA"  # first 2 chars of info[13] = "BA117"
        assert f.airline_icao == "BAW"
        assert f.callsign == "SHT1A"

    def test_synthetic_empty_number(self):
        # What _find_flight produces when reconstructing from search 'live' hits:
        info = [None] * 20
        info[1] = 52.5
        info[2] = 13.4
        info[13] = []
        f = Flight("9x", info)
        assert f.id == "9x"
        # info[13][:2] → [] which is not a str → airline_iata is the sentinel
        assert f.airline_iata == f._default_text


class TestEntity:
    def test_distance_berlin_to_jfk(self):
        berlin = Entity(52.5, 13.4)
        jfk = Entity(40.6413, -73.7781)
        # Known-good value from our live smoke test: ~6377 km
        assert 6300 < berlin.get_distance_from(jfk) < 6450

    def test_distance_to_self_is_zero(self):
        p = Entity(52.5, 13.4)
        assert p.get_distance_from(p) == 0.0


class TestBounds:
    def test_known_lhr_bounds(self):
        # Matches the verify script's output (± numerical drift)
        b = FlightRadar24API.get_bounds_by_point(51.4700, -0.4543, 50000)
        parts = b.split(",")
        assert len(parts) == 4
        y1, y2, x1, x2 = map(float, parts)
        # Box should cover LHR
        assert y2 < 51.47 < y1
        assert x1 < -0.4543 < x2


class TestTakeoffAndLanding:
    @pytest.fixture
    def processor(self) -> FlightProcessor:
        return FlightProcessor(
            client=MagicMock(),
            event_manager=EventManager(),
            min_altitude=-1,
            max_altitude=100000,
            point=Entity(0.0, 0.0),
            bounds="",
        )

    def _events_of_type(self, processor, event_name):
        return [e for e in processor._event_manager._events if e.event == event_name]

    def test_no_sensor_type_fires_nothing(self, processor):
        flight = {"id": "x"}
        processor._takeoff_and_landing(flight, 1, 0, None)
        assert processor._event_manager._events == []

    def test_unchanged_position_fires_nothing(self, processor):
        flight = {"id": "x"}
        from api.flight import FlightType
        processor._takeoff_and_landing(flight, 0, 0, FlightType.IN_AREA)
        assert processor._event_manager._events == []

    def test_takeoff_in_area(self, processor):
        from api.flight import FlightType
        from api.event import EVENT_AREA_TOOK_OFF
        processor._takeoff_and_landing({"id": "x"}, 1, 0, FlightType.IN_AREA)
        assert len(self._events_of_type(processor, EVENT_AREA_TOOK_OFF)) == 1

    def test_landing_in_area(self, processor):
        from api.flight import FlightType
        from api.event import EVENT_AREA_LANDED
        processor._takeoff_and_landing({"id": "x"}, 0, 1, FlightType.IN_AREA)
        assert len(self._events_of_type(processor, EVENT_AREA_LANDED)) == 1

    def test_takeoff_tracked(self, processor):
        from api.flight import FlightType
        from api.event import EVENT_TRACKED_TOOK_OFF
        processor._takeoff_and_landing({"id": "x"}, 1, 0, FlightType.TRACKED)
        assert len(self._events_of_type(processor, EVENT_TRACKED_TOOK_OFF)) == 1

    def test_landing_tracked(self, processor):
        from api.flight import FlightType
        from api.event import EVENT_TRACKED_LANDED
        processor._takeoff_and_landing({"id": "x"}, 0, 1, FlightType.TRACKED)
        assert len(self._events_of_type(processor, EVENT_TRACKED_LANDED)) == 1


class TestUpdateFlightsTracked:
    @pytest.fixture
    def processor(self) -> FlightProcessor:
        return FlightProcessor(
            client=MagicMock(),
            event_manager=EventManager(),
            min_altitude=-1,
            max_altitude=100000,
            point=Entity(0.0, 0.0),
            bounds="",
        )

    def test_empty_tracked_is_noop(self, processor):
        processor.update_flights_tracked()
        processor._client.get_flights.assert_not_called()

    def test_not_airborne_placeholder_preserved_when_aircraft_not_flying(self, processor):
        # Set up a placeholder that came from the 'aircraft' category
        processor._tracked = {
            "4X-ISR": {
                "id": "4X-ISR", "flight_number": None, "callsign": None,
                "aircraft_registration": "4X-ISR", "tracked_type": "not_airborne",
            }
        }
        processor._client.get_flights.return_value = []  # still not flying

        processor.update_flights_tracked()

        assert "4X-ISR" in processor._tracked
        assert processor._tracked["4X-ISR"]["tracked_type"] == "not_airborne"

    def test_placeholder_replaced_by_live_when_aircraft_takes_off(self, processor):
        processor._tracked = {
            "4X-ISR": {
                "id": "4X-ISR", "flight_number": None, "callsign": None,
                "aircraft_registration": "4X-ISR", "tracked_type": "not_airborne",
            }
        }
        # Now the aircraft is airborne — FR24 returns a Flight with the matching reg.
        live_info = [None] * 20
        live_info[0] = "ABC"
        live_info[1] = 52.0
        live_info[2] = 13.0
        live_info[4] = 35000
        live_info[5] = 450
        live_info[9] = "4X-ISR"
        live_info[13] = "LY001"
        live_info[14] = 0
        live_info[16] = "ELY1"
        live_flight = Flight("live-flight-id", live_info)
        processor._client.get_flights.return_value = [live_flight]
        processor._client.get_flight_details.return_value = {
            "identification": {"id": "live-flight-id"},
            "aircraft": {"registration": "4X-ISR"},
        }

        processor.update_flights_tracked()

        # Placeholder replaced, live entry present
        assert "4X-ISR" not in processor._tracked
        assert "live-flight-id" in processor._tracked
        assert processor._tracked["live-flight-id"]["tracked_type"] == "live"

    def test_ephemeral_flight_with_no_reg_kept_as_not_found(self, processor):
        # Tracked by flight number, no registration, no live match
        processor._tracked = {
            "BA117-id": {
                "id": "BA117-id", "flight_number": "BA117",
                "callsign": None, "aircraft_registration": None,
            }
        }
        processor._client.get_flights.return_value = []
        processor._client.search.return_value = {"live": [], "schedule": [], "aircraft": []}

        processor.update_flights_tracked()

        assert "BA117-id" in processor._tracked
        assert processor._tracked["BA117-id"]["tracked_type"] == "not_found"

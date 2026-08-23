"""Tests for the in-area entry/exit bookkeeping.

FR24's feed intermittently answers with a stub payload containing no
aircraft at all (observed roughly one read in four). Believing it fires a
burst of exit events followed by matching entry events on the next tick,
which is exactly the thing automations subscribe to — so an emptied area
has to be confirmed before it is acted on.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.client import Entity
from api.event import EventManager
from api.flight import FlightProcessor


class FakeFlight:
    """Minimal stand-in for the vendored Flight entity."""

    def __init__(self, flight_id: str, altitude: int = 10000) -> None:
        self.id = flight_id
        self.altitude = altitude
        self.latitude = 52.5
        self.longitude = 13.4
        self.heading = 90
        self.ground_speed = 400
        self.squawk = "1000"
        self.vertical_speed = 0
        self.on_ground = 0
        self.registration = f"REG{flight_id}"
        self.callsign = f"CS{flight_id}"
        self.number = f"NO{flight_id}"

    def get_distance_from(self, point) -> float:
        return 12.0


@pytest.fixture
def processor():
    client = MagicMock()
    proc = FlightProcessor(
        client=client,
        event_manager=EventManager(),
        min_altitude=-1,
        max_altitude=100000,
        point=Entity(52.5, 13.4),
        bounds="1,0,0,1",
    )
    # FlightProcessor uses __slots__, so stub the detail fetch on the client
    # rather than patching a method onto the instance.
    client.get_flight_details.side_effect = lambda obj: {
        "identification": {"id": obj.id}
    }
    return proc


def feed(processor, *flight_ids: str) -> None:
    processor._client.get_flights.return_value = [FakeFlight(f) for f in flight_ids]
    processor.update_flights_in_area()


class TestEmptyFeedGuard:
    def test_populates_on_first_read(self, processor):
        feed(processor, "a", "b")
        assert len(processor.in_area_list) == 2

    def test_single_empty_read_is_ignored(self, processor):
        feed(processor, "a", "b")
        feed(processor)
        # The area is held, and crucially no exit events were emitted.
        assert len(processor.in_area_list) == 2
        assert not processor.exited_list

    def test_repeated_empty_read_is_believed(self, processor):
        feed(processor, "a", "b")
        feed(processor)
        feed(processor)
        assert not processor.in_area_list
        assert len(processor.exited_list) == 2

    def test_recovery_after_one_empty_read_emits_nothing(self, processor):
        # The real-world pattern: good, stub, good. Nothing should have moved.
        feed(processor, "a", "b")
        feed(processor)
        feed(processor, "a", "b")
        assert len(processor.in_area_list) == 2
        assert not processor.entered_list
        assert not processor.exited_list

    def test_streak_resets_between_empty_reads(self, processor):
        feed(processor, "a")
        feed(processor)          # suspect
        feed(processor, "a")     # recovered, streak resets
        feed(processor)          # suspect again, must not be believed
        assert len(processor.in_area_list) == 1

    def test_genuine_departure_still_reported(self, processor):
        # A real exit that leaves other aircraft behind is not an empty read
        # and must be reported immediately.
        feed(processor, "a", "b")
        feed(processor, "a")
        assert len(processor.exited_list) == 1
        assert len(processor.in_area_list) == 1

    def test_entries_reported_immediately(self, processor):
        feed(processor, "a")
        feed(processor, "a", "b")
        assert len(processor.entered_list) == 1

    def test_empty_first_read_is_not_suppressed(self, processor):
        # Nothing is being protected yet, so an empty start is taken as-is.
        feed(processor)
        assert not processor.in_area_list
        assert not processor.exited_list

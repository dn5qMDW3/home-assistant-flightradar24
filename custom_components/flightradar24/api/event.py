from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

# Event names fired onto the HA bus. Canonical source — const.py no longer
# holds these; keeps the api/ subpackage free of upward imports.
_DOMAIN = "flightradar24"
EVENT_ENTRY = f"{_DOMAIN}_entry"
EVENT_EXIT = f"{_DOMAIN}_exit"
EVENT_AREA_LANDED = f"{_DOMAIN}_area_landed"
EVENT_AREA_TOOK_OFF = f"{_DOMAIN}_area_took_off"
EVENT_TRACKED_LANDED = f"{_DOMAIN}_tracked_landed"
EVENT_TRACKED_TOOK_OFF = f"{_DOMAIN}_tracked_took_off"
EVENT_MOST_TRACKED_NEW = f"{_DOMAIN}_most_tracked_new"


@dataclass
class Event:
    event: str
    data: dict[str, Any]


class EventManager:
    __slots__ = ('_events',)

    def __init__(self) -> None:
        self._events: list[Event] = []

    def add_events(self, event: str, flights: list[dict[str, Any]]) -> None:
        self._events.extend([Event(event, flight) for flight in flights])

    def fire_events(self, device: str, callback: Callable[[Event], None]) -> None:
        for event in self._events:
            event.data['tracked_by_device'] = device
            callback(event)
        self._events = []

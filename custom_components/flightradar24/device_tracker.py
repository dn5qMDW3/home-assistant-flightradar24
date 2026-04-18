from __future__ import annotations
from typing import Any
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DEFAULT_NAME, DOMAIN, SUBENTRY_AIRCRAFT
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data

    if coordinator.enable_tracker:
        tracker = FlightRadar24Tracker(coordinator)
        async_add_entities([tracker])

        @callback
        def _pick_flight() -> None:
            _update_items(coordinator, tracker)

        entry.async_on_unload(coordinator.async_add_listener(_pick_flight))
        _pick_flight()

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_AIRCRAFT:
            continue
        async_add_entities(
            [FlightRadar24AircraftTracker(coordinator, subentry.data["registration"])],
            config_subentry_id=subentry.subentry_id,
        )


@callback
def _update_items(coordinator: FlightRadar24Coordinator, tracker: FlightRadar24Tracker) -> None:
    """Pick the next available 'live' flight for the legacy single-tracker slot."""
    if not coordinator.enable_tracker:
        return
    if not tracker.info:
        for flight in coordinator.flight.tracked.values():
            if flight.get("tracked_type") == "live":
                tracker.info = flight
                return
        return
    flight = coordinator.flight.tracked.get(tracker.info["id"])
    tracker.info = flight if flight and flight.get("tracked_type") == "live" else {}


class _FlightTrackerBase(FlightRadar24Entity, TrackerEntity):
    """Shared plumbing for trackers that expose one flight's latitude/longitude."""

    _attr_name = None
    _attr_icon = "mdi:airplane"

    def _flight(self) -> dict[str, Any] | None:
        """Return the flight dict this tracker currently follows, or None."""
        raise NotImplementedError

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        flight = self._flight()
        return flight.get("latitude") if flight else None

    @property
    def longitude(self) -> float | None:
        flight = self._flight()
        return flight.get("longitude") if flight else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._flight() or {}


class FlightRadar24Tracker(_FlightTrackerBase):
    """Legacy single-slot tracker: follows the first 'live' tracked flight."""

    def __init__(self, coordinator: FlightRadar24Coordinator) -> None:
        super().__init__(coordinator, DOMAIN)
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}"
        self.info: dict[str, Any] = {}

    def _flight(self) -> dict[str, Any] | None:
        return self.info or None


class FlightRadar24AircraftTracker(_FlightTrackerBase):
    """Per-aircraft-subentry tracker: follows one specific registration."""

    def __init__(self, coordinator: FlightRadar24Coordinator, registration: str) -> None:
        super().__init__(coordinator, f"aircraft_{registration}_tracker")
        self._registration = registration.upper()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.unique_id}_aircraft_{self._registration}")},
            name=f"{DEFAULT_NAME} {self._registration}",
            manufacturer=DEFAULT_NAME,
            via_device=(DOMAIN, coordinator.unique_id),
        )

    def _flight(self) -> dict[str, Any] | None:
        for entry in self.coordinator.flight.tracked.values():
            if (
                (entry.get("aircraft_registration") or "").upper() == self._registration
                and entry.get("tracked_type") == "live"
            ):
                return entry
        return None

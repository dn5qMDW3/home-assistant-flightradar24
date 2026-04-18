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
        tracked = FlightRadar24Tracker(coordinator)
        async_add_entities([tracked])

        @callback
        def coordinator_updated() -> None:
            _update_items(coordinator, tracked)

        entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))
        coordinator_updated()

    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_AIRCRAFT:
            continue
        async_add_entities(
            [FlightRadar24AircraftTracker(coordinator, subentry.data["registration"])],
            config_subentry_id=subentry.subentry_id,
        )


@callback
def _update_items(coordinator: FlightRadar24Coordinator, tracked: FlightRadar24Tracker) -> None:
    if not coordinator.enable_tracker:
        return

    if not tracked.info:
        for flight in coordinator.flight.tracked.values():
            if flight.get("tracked_type") == "live":
                tracked.info = flight
                break
        return

    flight = coordinator.flight.tracked.get(tracked.info["id"])
    if flight and flight.get("tracked_type") == "live":
        tracked.info = flight
    else:
        tracked.info = {}


class FlightRadar24Tracker(FlightRadar24Entity, TrackerEntity):
    _attr_name = None
    _attr_icon = "mdi:airplane"

    def __init__(self, coordinator: FlightRadar24Coordinator) -> None:
        super().__init__(coordinator, DOMAIN)
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}"
        self.info: dict[str, Any] = {}

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.info

    @property
    def latitude(self) -> float | None:
        return self.info.get("latitude")

    @property
    def longitude(self) -> float | None:
        return self.info.get("longitude")


class FlightRadar24AircraftTracker(FlightRadar24Entity, TrackerEntity):
    """Device tracker following a specific aircraft subentry's registration."""

    _attr_name = None
    _attr_icon = "mdi:airplane"

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

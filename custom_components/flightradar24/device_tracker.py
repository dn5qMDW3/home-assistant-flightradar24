from __future__ import annotations
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import SUBENTRY_AIRCRAFT
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity, subentry_device_info


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_AIRCRAFT:
            continue
        async_add_entities(
            [FlightRadar24AircraftTracker(coordinator, subentry.data["registration"])],
            config_subentry_id=subentry.subentry_id,
        )


class FlightRadar24AircraftTracker(FlightRadar24Entity, TrackerEntity):
    """Device tracker following a specific aircraft subentry's registration."""

    _attr_name = None
    _attr_icon = "mdi:airplane"

    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: FlightRadar24Coordinator, registration: str) -> None:
        super().__init__(coordinator, f"aircraft_{registration}_tracker")
        self._registration = registration.upper()
        self._attr_device_info = subentry_device_info(coordinator, "aircraft", self._registration)

    @callback
    def _handle_coordinator_update(self) -> None:
        flight = self.coordinator.airborne_flight_by_registration(self._registration)
        self._attr_latitude = flight.get("latitude") if flight else None
        self._attr_longitude = flight.get("longitude") if flight else None
        self._attr_extra_state_attributes = flight or {}
        self.async_write_ha_state()

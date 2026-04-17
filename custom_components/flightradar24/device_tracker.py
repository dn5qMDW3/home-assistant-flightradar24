from __future__ import annotations
from typing import Any
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    if not coordinator.enable_tracker:
        return

    tracked = FlightRadar24Tracker(coordinator)
    async_add_entities([tracked])

    @callback
    def coordinator_updated() -> None:
        _update_items(coordinator, tracked)

    entry.async_on_unload(coordinator.async_add_listener(coordinator_updated))
    coordinator_updated()


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

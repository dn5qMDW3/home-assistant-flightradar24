from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


@dataclass(frozen=True, kw_only=True)
class FR24BinarySensorDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[FlightRadar24Coordinator], bool]


BINARY_SENSORS: tuple[FR24BinarySensorDescription, ...] = (
    FR24BinarySensorDescription(
        key="aircraft_in_area",
        translation_key="aircraft_in_area",
        icon="mdi:airplane-marker",
        is_on_fn=lambda coord: bool(coord.flight.in_area_list),
    ),
    FR24BinarySensorDescription(
        key="tracked_flight_airborne",
        translation_key="tracked_flight_airborne",
        icon="mdi:airplane",
        is_on_fn=lambda coord: any(
            f.get("tracked_type") == "live" for f in coord.flight.tracked.values()
        ),
    ),
    FR24BinarySensorDescription(
        key="airport_tracked",
        translation_key="airport_tracked",
        icon="mdi:airport",
        is_on_fn=lambda coord: bool(coord.airport.subentry_airports),
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    async_add_entities(
        FlightRadar24BinarySensor(coordinator, desc) for desc in BINARY_SENSORS
    )


class FlightRadar24BinarySensor(FlightRadar24Entity, BinarySensorEntity):
    entity_description: FR24BinarySensorDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FR24BinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator)

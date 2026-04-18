from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


@dataclass(frozen=True, kw_only=True)
class FlightRadar24TextEntityDescription(TextEntityDescription):
    method: Callable[[FlightRadar24Coordinator, str], Any]


FLIGHT_TYPES: tuple[FlightRadar24TextEntityDescription, ...] = (
    FlightRadar24TextEntityDescription(
        key="add_track",
        translation_key="add_track",
        icon="mdi:airplane-plus",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.add_flight_track(value),
    ),
    FlightRadar24TextEntityDescription(
        key="remove_track",
        translation_key="remove_track",
        icon="mdi:airplane-minus",
        entity_category=EntityCategory.CONFIG,
        method=lambda coordinator, value: coordinator.remove_flight_track(value),
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    async_add_entities(
        FlightRadar24TextFlight(coordinator, desc) for desc in FLIGHT_TYPES
    )


class FlightRadar24TextFlight(FlightRadar24Entity, TextEntity):
    entity_description: FlightRadar24TextEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24TextEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_native_value = ""

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        await self.entity_description.method(self.coordinator, value)
        self.async_write_ha_state()
        self._attr_native_value = ""

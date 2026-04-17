from __future__ import annotations
from typing import Any
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity

SCAN_DESCRIPTION = SwitchEntityDescription(
    key="scanning",
    translation_key="scanning",
    icon="mdi:connection",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    async_add_entities([FlightRadar24ScanEntity(coordinator)])


class FlightRadar24ScanEntity(FlightRadar24Entity, SwitchEntity):
    entity_description = SCAN_DESCRIPTION

    def __init__(self, coordinator: FlightRadar24Coordinator) -> None:
        super().__init__(coordinator, SCAN_DESCRIPTION.key)
        self.entity_description = SCAN_DESCRIPTION

    @property
    def is_on(self) -> bool:
        return self.coordinator.scanning

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.scanning = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.scanning = False
        self.async_write_ha_state()

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


@dataclass(frozen=True, kw_only=True)
class FlightRadar24ButtonEntityDescription(ButtonEntityDescription):
    method: Callable[[FlightRadar24Coordinator], Any]


async def _clear_tracked(coordinator: FlightRadar24Coordinator) -> None:
    coordinator.flight.clear_tracked()


BUTTON_TYPES: tuple[FlightRadar24ButtonEntityDescription, ...] = (
    FlightRadar24ButtonEntityDescription(
        key="tracked_clear",
        translation_key="tracked_clear",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        method=_clear_tracked,
    ),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    async_add_entities(
        FlightRadar24ButtonEntity(coordinator, description) for description in BUTTON_TYPES
    )


class FlightRadar24ButtonEntity(FlightRadar24Entity, ButtonEntity):
    entity_description: FlightRadar24ButtonEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24ButtonEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.method(self.coordinator)

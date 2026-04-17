from __future__ import annotations
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import FlightRadar24Coordinator


class FlightRadar24Entity(CoordinatorEntity[FlightRadar24Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FlightRadar24Coordinator, unique_key: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{unique_key}"

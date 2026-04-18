from __future__ import annotations
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DEFAULT_NAME, DOMAIN
from .coordinator import FlightRadar24Coordinator


class FlightRadar24Entity(CoordinatorEntity[FlightRadar24Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: FlightRadar24Coordinator, unique_key: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}_{DOMAIN}_{unique_key}"


def subentry_device_info(
        coordinator: FlightRadar24Coordinator, kind: str, identifier: str,
) -> DeviceInfo:
    """DeviceInfo for a per-subentry device (airport by IATA/ICAO, aircraft by registration)."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{coordinator.unique_id}_{kind}_{identifier}")},
        name=f"{DEFAULT_NAME} {identifier}",
        manufacturer=DEFAULT_NAME,
        via_device=(DOMAIN, coordinator.unique_id),
    )

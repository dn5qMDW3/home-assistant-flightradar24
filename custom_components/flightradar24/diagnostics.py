from __future__ import annotations
from typing import Any
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from . import FlightRadar24ConfigEntry

_REDACT = {CONF_LATITUDE, CONF_LONGITUDE, CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
        hass: HomeAssistant, entry: FlightRadar24ConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    airport = coordinator.airport
    flight = coordinator.flight

    return {
        "entry": async_redact_data(entry.as_dict(), _REDACT),
        "coordinator": {
            "scanning": coordinator.scanning,
            "enable_tracker": coordinator.enable_tracker,
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
        },
        "flight": {
            "in_area_count": len(flight.in_area_list),
            "tracked_count": len(flight.tracked_list),
            "entered_count": len(flight.entered_list),
            "exited_count": len(flight.exited_list),
            "most_tracked_enabled": flight.most_tracked_list is not None,
            "most_tracked_count": (
                len(flight.most_tracked_list) if flight.most_tracked_list else 0
            ),
        },
        "airport": {
            "tracked_code": airport.code,
            "has_stats": airport.stats is not None,
            "arrivals_count": len(airport.arrivals) if airport.arrivals is not None else None,
            "departures_count": len(airport.departures) if airport.departures is not None else None,
        },
    }

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
        hass: HomeAssistant, entry: FlightRadar24ConfigEntry,
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    flight = coordinator.flight

    airports: dict[str, dict[str, Any]] = {}
    for code, state in coordinator.airport.subentry_airports.items():
        airports[code] = {
            "has_stats": state.stats is not None,
            "has_weather": state.weather is not None,
            "has_aircraft_count": state.aircraft_count is not None,
            "arrivals_count": len(state.arrivals) if state.arrivals is not None else None,
            "departures_count": len(state.departures) if state.departures is not None else None,
            "ground_count": len(state.ground) if state.ground is not None else None,
        }

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
            "tracked_types": [f.get("tracked_type") for f in flight.tracked.values()],
        },
        "airports": airports,
    }

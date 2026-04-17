from __future__ import annotations
from typing import TYPE_CHECKING
import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import FlightRadar24Coordinator

SERVICE_TRACK_FLIGHT = "track_flight"
SERVICE_UNTRACK_FLIGHT = "untrack_flight"
SERVICE_CLEAR_TRACKED = "clear_tracked"
SERVICE_SEARCH_FLIGHT = "search_flight"

ATTR_NUMBER = "number"
ATTR_QUERY = "query"
ATTR_ENTRY_ID = "entry_id"

_NUMBER_SCHEMA = vol.Schema({
    vol.Required(ATTR_NUMBER): cv.string,
    vol.Optional(ATTR_ENTRY_ID): cv.string,
})

_QUERY_SCHEMA = vol.Schema({
    vol.Required(ATTR_QUERY): cv.string,
    vol.Optional(ATTR_ENTRY_ID): cv.string,
})

_EMPTY_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ENTRY_ID): cv.string,
})


def _resolve_coordinator(hass: HomeAssistant, call: ServiceCall) -> "FlightRadar24Coordinator":
    entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [e for e in entries if getattr(e, "runtime_data", None) is not None]
    if not loaded:
        raise ServiceValidationError("No Flightradar24 config entry is loaded.")

    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        for entry in loaded:
            if entry.entry_id == entry_id:
                return entry.runtime_data
        raise ServiceValidationError(f"Flightradar24 config entry '{entry_id}' not found or not loaded.")

    if len(loaded) > 1:
        raise ServiceValidationError(
            "Multiple Flightradar24 entries are loaded; pass 'entry_id' to pick one."
        )
    return loaded[0].runtime_data


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register FR24 services once. Safe to call on every setup."""
    if hass.services.has_service(DOMAIN, SERVICE_TRACK_FLIGHT):
        return

    async def _track_flight(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call)
        number = call.data[ATTR_NUMBER]
        if not await coordinator.add_flight_track(number):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="flight_not_found",
                translation_placeholders={"number": number},
            )

    async def _untrack_flight(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call)
        await coordinator.remove_flight_track(call.data[ATTR_NUMBER])

    async def _clear_tracked(call: ServiceCall) -> None:
        coordinator = _resolve_coordinator(hass, call)
        await coordinator.clear_flight_tracks()

    async def _search_flight(call: ServiceCall) -> ServiceResponse:
        coordinator = _resolve_coordinator(hass, call)
        results = await coordinator.search_flights(call.data[ATTR_QUERY])
        return {"results": results}

    hass.services.async_register(DOMAIN, SERVICE_TRACK_FLIGHT, _track_flight, schema=_NUMBER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UNTRACK_FLIGHT, _untrack_flight, schema=_NUMBER_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_TRACKED, _clear_tracked, schema=_EMPTY_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_SEARCH_FLIGHT, _search_flight,
        schema=_QUERY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )

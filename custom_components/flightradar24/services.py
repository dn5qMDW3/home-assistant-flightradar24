from __future__ import annotations
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN, SUBENTRY_AIRCRAFT, SUBENTRY_AIRPORT

if TYPE_CHECKING:
    from .coordinator import FlightRadar24Coordinator

SERVICE_TRACK_FLIGHT = "track_flight"
SERVICE_UNTRACK_FLIGHT = "untrack_flight"
SERVICE_CLEAR_TRACKED = "clear_tracked"
SERVICE_SEARCH_FLIGHT = "search_flight"
SERVICE_TRACK_AIRPORT = "track_airport"
SERVICE_UNTRACK_AIRPORT = "untrack_airport"
SERVICE_TRACK_AIRCRAFT = "track_aircraft"
SERVICE_UNTRACK_AIRCRAFT = "untrack_aircraft"

ATTR_NUMBER = "number"
ATTR_QUERY = "query"
ATTR_ENTRY_ID = "entry_id"
ATTR_CODE = "code"
ATTR_REGISTRATION = "registration"

_ENTRY_ONLY = vol.Schema({vol.Optional(ATTR_ENTRY_ID): cv.string})
_NUMBER_SCHEMA = _ENTRY_ONLY.extend({vol.Required(ATTR_NUMBER): cv.string})
_QUERY_SCHEMA = _ENTRY_ONLY.extend({vol.Required(ATTR_QUERY): cv.string})
_CODE_SCHEMA = _ENTRY_ONLY.extend({vol.Required(ATTR_CODE): cv.string})
_REGISTRATION_SCHEMA = _ENTRY_ONLY.extend({vol.Required(ATTR_REGISTRATION): cv.string})


def _resolve_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [e for e in entries if getattr(e, "runtime_data", None) is not None]
    if not loaded:
        raise ServiceValidationError("No Flightradar24 config entry is loaded.")

    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        for entry in loaded:
            if entry.entry_id == entry_id:
                return entry
        raise ServiceValidationError(
            f"Flightradar24 config entry '{entry_id}' not found or not loaded."
        )
    if len(loaded) > 1:
        raise ServiceValidationError(
            "Multiple Flightradar24 entries are loaded; pass 'entry_id' to pick one."
        )
    return loaded[0]


def _resolve_coordinator(hass: HomeAssistant, call: ServiceCall) -> "FlightRadar24Coordinator":
    return _resolve_entry(hass, call).runtime_data


def _find_subentry_by_field(
        entry: ConfigEntry, subentry_type: str, field: str, value: str,
) -> tuple[str, ConfigSubentry] | None:
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type == subentry_type and subentry.data.get(field) == value:
            return subentry_id, subentry
    return None


def _validate_airport(code: str) -> None:
    if not (3 <= len(code) <= 4 and code.isalpha()):
        raise ServiceValidationError(
            "Airport code must be 3 (IATA) or 4 (ICAO) letters."
        )


def _validate_registration(reg: str) -> None:
    if len(reg) < 3:
        raise ServiceValidationError(
            "Aircraft registration must be at least 3 characters."
        )


async def _add_subentry(
        hass: HomeAssistant,
        call: ServiceCall,
        *,
        subentry_type: str,
        field: str,
        label: str,
        validator: Callable[[str], None],
) -> None:
    entry = _resolve_entry(hass, call)
    value = (call.data[field] or "").strip().upper()
    validator(value)
    if _find_subentry_by_field(entry, subentry_type, field, value):
        raise ServiceValidationError(f"{label} {value} is already tracked.")
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={field: value},
            subentry_type=subentry_type,
            title=value,
            unique_id=None,
        ),
    )
    await hass.config_entries.async_reload(entry.entry_id)


async def _remove_subentry(
        hass: HomeAssistant,
        call: ServiceCall,
        *,
        subentry_type: str,
        field: str,
        label: str,
) -> None:
    entry = _resolve_entry(hass, call)
    value = (call.data[field] or "").strip().upper()
    found = _find_subentry_by_field(entry, subentry_type, field, value)
    if not found:
        raise ServiceValidationError(f"{label} {value} is not tracked.")
    hass.config_entries.async_remove_subentry(entry, found[0])
    await hass.config_entries.async_reload(entry.entry_id)


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

    async def _track_airport(call: ServiceCall) -> None:
        await _add_subentry(
            hass, call, subentry_type=SUBENTRY_AIRPORT, field=ATTR_CODE,
            label="Airport", validator=_validate_airport,
        )

    async def _untrack_airport(call: ServiceCall) -> None:
        await _remove_subentry(
            hass, call, subentry_type=SUBENTRY_AIRPORT, field=ATTR_CODE, label="Airport",
        )

    async def _track_aircraft(call: ServiceCall) -> None:
        await _add_subentry(
            hass, call, subentry_type=SUBENTRY_AIRCRAFT, field=ATTR_REGISTRATION,
            label="Aircraft", validator=_validate_registration,
        )

    async def _untrack_aircraft(call: ServiceCall) -> None:
        await _remove_subentry(
            hass, call, subentry_type=SUBENTRY_AIRCRAFT, field=ATTR_REGISTRATION, label="Aircraft",
        )

    _REGISTRY: tuple[tuple[str, Any, vol.Schema, SupportsResponse], ...] = (
        (SERVICE_TRACK_FLIGHT, _track_flight, _NUMBER_SCHEMA, SupportsResponse.NONE),
        (SERVICE_UNTRACK_FLIGHT, _untrack_flight, _NUMBER_SCHEMA, SupportsResponse.NONE),
        (SERVICE_CLEAR_TRACKED, _clear_tracked, _ENTRY_ONLY, SupportsResponse.NONE),
        (SERVICE_SEARCH_FLIGHT, _search_flight, _QUERY_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_TRACK_AIRPORT, _track_airport, _CODE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_UNTRACK_AIRPORT, _untrack_airport, _CODE_SCHEMA, SupportsResponse.NONE),
        (SERVICE_TRACK_AIRCRAFT, _track_aircraft, _REGISTRATION_SCHEMA, SupportsResponse.NONE),
        (SERVICE_UNTRACK_AIRCRAFT, _untrack_aircraft, _REGISTRATION_SCHEMA, SupportsResponse.NONE),
    )
    for name, handler, schema, response in _REGISTRY:
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=response,
        )

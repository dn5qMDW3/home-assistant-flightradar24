from __future__ import annotations
from logging import getLogger
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PASSWORD,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from .api.client import Entity, FlightRadar24API, LoginError
from .const import (
    CONF_MAX_ALTITUDE,
    CONF_MIN_ALTITUDE,
    CONF_MOST_TRACKED,
    CONF_MOST_TRACKED_DEFAULT,
    MAX_ALTITUDE,
    MIN_ALTITUDE,
    SUBENTRY_AIRCRAFT,
    SUBENTRY_AIRPORT,
)
from .coordinator import FlightRadar24Coordinator
from .services import async_register_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WEATHER,
]

FlightRadar24ConfigEntry = ConfigEntry[FlightRadar24Coordinator]

_LOGGER = getLogger(__name__)


async def _async_login(
        hass: HomeAssistant,
        client: FlightRadar24API,
        username: str | None,
        password: str | None,
) -> None:
    if not (username and password):
        return
    try:
        await hass.async_add_executor_job(client.login, username, password)
    except LoginError as err:
        raise ConfigEntryAuthFailed(f"FlightRadar24 login failed: {err}") from err


async def async_setup_entry(hass: HomeAssistant, entry: FlightRadar24ConfigEntry) -> bool:
    client = FlightRadar24API()
    await _async_login(hass, client, entry.data.get(CONF_USERNAME), entry.data.get(CONF_PASSWORD))

    latitude = entry.data[CONF_LATITUDE]
    longitude = entry.data[CONF_LONGITUDE]
    bounds = client.get_bounds_by_point(latitude, longitude, entry.data[CONF_RADIUS])

    coordinator = FlightRadar24Coordinator(
        hass,
        bounds,
        client,
        entry.data[CONF_SCAN_INTERVAL],
        _LOGGER,
        entry.entry_id,
        entry.data.get(CONF_MIN_ALTITUDE, MIN_ALTITUDE),
        entry.data.get(CONF_MAX_ALTITUDE, MAX_ALTITUDE),
        Entity(latitude, longitude),
    )

    if entry.data.get(CONF_MOST_TRACKED, CONF_MOST_TRACKED_DEFAULT):
        coordinator.flight.enable_most_tracked()

    # Register airport subentries before the first refresh so their data is
    # fetched in the same executor burst as the primary airport.
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_AIRPORT:
            coordinator.airport.add_subentry(subentry.data["code"])

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Aircraft subentries: resolve each registration via flight.add_track
    # (async because it performs an executor HTTP call via the coordinator).
    # ``from_subentry=True`` tags the tracking entry so ``clear_tracked`` keeps it.
    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_AIRCRAFT:
            await coordinator.add_flight_track(
                subentry.data["registration"], from_subentry=True,
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlightRadar24ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: FlightRadar24ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

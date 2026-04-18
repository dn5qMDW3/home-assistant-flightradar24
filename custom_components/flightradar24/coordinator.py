from __future__ import annotations
import asyncio
from datetime import timedelta
from logging import Logger
from typing import Any
from .api.client import Entity, FlightRadar24API
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api.airport import AirportProcessor
from .api.event import Event, EventManager
from .api.flight import FlightProcessor
from .const import DEFAULT_NAME, DOMAIN, EVENT_FLIGHT_NOT_FOUND, URL

_SCAN_OFF_MESSAGE = "FlightRadar24: API data fetching is OFF"


class FlightRadar24Coordinator(DataUpdateCoordinator[None]):

    def __init__(
            self,
            hass: HomeAssistant,
            bounds: str,
            client: FlightRadar24API,
            update_interval: int,
            logger: Logger,
            unique_id: str,
            min_altitude: int,
            max_altitude: int,
            point: Entity,
    ) -> None:
        self.unique_id = unique_id
        self.client = client
        self.event_manager = EventManager()
        self.flight = FlightProcessor(client, self.event_manager, min_altitude, max_altitude, point, bounds)
        self.airport = AirportProcessor(client)
        self.scanning: bool = True
        self.device_info = DeviceInfo(
            configuration_url=URL,
            identifiers={(DOMAIN, self.unique_id)},
            manufacturer=DEFAULT_NAME,
            name=DEFAULT_NAME,
        )

        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    def _is_scanning(self) -> bool:
        if not self.scanning:
            self.logger.error(_SCAN_OFF_MESSAGE)
            return False
        return True

    def flight_by_registration(self, registration: str) -> dict[str, Any] | None:
        """Return the tracked flight entry matching an aircraft registration."""
        target = registration.upper()
        for entry in self.flight.tracked.values():
            if (entry.get("aircraft_registration") or "").upper() == target:
                return entry
        return None

    def airborne_flight_by_registration(self, registration: str) -> dict[str, Any] | None:
        """Same as ``flight_by_registration`` but only returns the entry if live."""
        entry = self.flight_by_registration(registration)
        return entry if entry and entry.get("tracked_type") == "live" else None

    async def add_flight_track(self, number: str, *, from_subentry: bool = False) -> bool:
        """Return True if the flight was added, False otherwise.

        Fires ``flightradar24_flight_not_found`` on the HA event bus when
        the flight cannot be resolved, so automations (and the matching
        service handler's ServiceValidationError) can surface it.

        If ``from_subentry`` is True, the tracked entry is tagged so that
        :meth:`clear_flight_tracks` preserves it across the service call.
        """
        if not self._is_scanning():
            return False
        try:
            found = await self.hass.async_add_executor_job(
                self.flight.add_track, number, from_subentry,
            )
        except Exception as err:
            self.logger.error("FlightRadar24: %s", err)
            if from_subentry:
                self.flight.ensure_subentry_placeholder(number)
            self.hass.bus.async_fire(
                EVENT_FLIGHT_NOT_FOUND, {"number": number, "reason": str(err)},
            )
            return False
        if not found:
            self.logger.error("FlightRadar24: Add Track - No flight found by - %s", number)
            self.hass.bus.async_fire(
                EVENT_FLIGHT_NOT_FOUND, {"number": number, "reason": "not_found"},
            )
            return False
        return True

    async def aircraft_exists(self, registration: str) -> bool:
        """Async wrapper around ``flight.aircraft_exists`` for use from
        config flows and service handlers. Lets exceptions from the
        underlying ``client.search`` propagate to the caller.
        """
        return await self.hass.async_add_executor_job(
            self.flight.aircraft_exists, registration,
        )

    async def remove_flight_track(self, number: str) -> None:
        if not self._is_scanning():
            return
        remove = await self.hass.async_add_executor_job(self.flight.remove_track, number)
        if not remove:
            self.logger.error("FlightRadar24: Remove Track - No flight found by - %s", number)

    async def clear_flight_tracks(self) -> None:
        await self.hass.async_add_executor_job(self.flight.clear_tracked)

    async def search_flights(self, query: str) -> dict:
        return await self.hass.async_add_executor_job(self.client.search, query)

    async def _async_update_data(self) -> None:
        if not self.scanning:
            return
        try:
            await asyncio.gather(
                self.hass.async_add_executor_job(self.flight.update_flights_in_area),
                self.hass.async_add_executor_job(self.flight.update_flights_tracked),
                self.hass.async_add_executor_job(self.flight.update_most_tracked),
                self.hass.async_add_executor_job(self.airport.update_airport_info),
            )
        except Exception as err:
            raise UpdateFailed(f"FlightRadar24: {err}") from err

        def fire(event: Event) -> None:
            self.hass.bus.fire(event.event, event.data)

        self.event_manager.fire_events(self.config_entry.title, fire)

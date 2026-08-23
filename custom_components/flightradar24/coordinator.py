from __future__ import annotations
import asyncio
from datetime import timedelta
from logging import Logger
from typing import Any
from .api.client import Entity, FlightRadar24API
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api.airport import AirportProcessor
from .api.event import Event, EventManager
from .api.flight import FlightProcessor
from .const import (
    DEFAULT_NAME,
    DOMAIN,
    EVENT_FLIGHT_NOT_FOUND,
    SUBENTRY_AIRCRAFT,
    SUBENTRY_AIRPORT,
    URL,
)

_SCAN_OFF_MESSAGE = "FlightRadar24: API data fetching is OFF"


class FlightRadar24Coordinator(DataUpdateCoordinator[None]):

    def __init__(
            self,
            hass: HomeAssistant,
            config_entry: ConfigEntry,
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
        self._task_errors: dict[str, str] = {}
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
            config_entry=config_entry,
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

    def _sync_subentries(self) -> None:
        """Reconcile flight._tracked and airport subscriptions against the
        current set of config subentries. Runs at the start of every refresh.

        Idempotent: missing aircraft placeholders / airport subscriptions are
        seeded; entries for removed subentries are dropped (only entries
        flagged ``from_subentry=True`` so ephemeral ``track_flight`` tracks
        are preserved). Wrapped in a broad except so a malformed subentry
        does not kill the entire refresh.
        """
        try:
            aircraft_regs: set[str] = set()
            airport_codes: set[str] = set()
            for subentry in self.config_entry.subentries.values():
                if subentry.subentry_type == SUBENTRY_AIRCRAFT:
                    reg = (subentry.data.get("registration") or "").upper()
                    if reg:
                        aircraft_regs.add(reg)
                        self.flight.ensure_subentry_placeholder(reg)
                elif subentry.subentry_type == SUBENTRY_AIRPORT:
                    code = (subentry.data.get("code") or "").upper()
                    if code:
                        airport_codes.add(code)
                        if code not in self.airport.subentry_airports:
                            self.airport.add_subentry(code)

            stale_ids = [
                fid for fid, entry in self.flight.tracked.items()
                if entry.get("from_subentry")
                and (entry.get("aircraft_registration") or "").upper() not in aircraft_regs
            ]
            for fid in stale_ids:
                self.flight.tracked.pop(fid, None)

            for code in list(self.airport.subentry_airports.keys()):
                if code not in airport_codes:
                    self.airport.remove_subentry(code)
        except Exception as err:  # noqa: BLE001 — never fail a refresh over a bad subentry
            self.logger.warning("FlightRadar24: subentry sync failed: %s", err)

    def _report(self, task: str, err: BaseException | None) -> None:
        """Log a task's outcome, but only when it changes.

        A refresh runs every few seconds, so an endpoint that is persistently
        unreachable would otherwise fill the log with the same line forever.
        Recoveries are logged too, so the log still shows when a task healed.
        """
        message = f"{type(err).__name__}: {err}" if err is not None else None
        if self._task_errors.get(task) == message:
            return
        if message is None:
            self.logger.info("FlightRadar24: %s recovered", task)
            self._task_errors.pop(task, None)
            return
        self.logger.warning("FlightRadar24: %s failed - %s", task, message)
        self._task_errors[task] = message

    async def _async_update_data(self) -> None:
        if not self.scanning:
            return
        self._sync_subentries()

        tasks = {
            "flights in area": self.flight.update_flights_in_area,
            "tracked flights": self.flight.update_flights_tracked,
            "most tracked": self.flight.update_most_tracked,
            "airport info": self.airport.update_airport_info,
        }
        # Each upstream endpoint sits behind a different host, and FR24 blocks
        # them independently. Gather with return_exceptions so one dead endpoint
        # degrades its own sensors instead of taking down the whole refresh.
        results = await asyncio.gather(
            *(self.hass.async_add_executor_job(fn) for fn in tasks.values()),
            return_exceptions=True,
        )

        # return_exceptions=True also captures CancelledError, which is a
        # BaseException rather than an Exception — swallowing it would keep a
        # shutting-down refresh alive, so let it through untouched.
        for result in results:
            if isinstance(result, asyncio.CancelledError):
                raise result

        failures: list[BaseException] = []
        for task, result in zip(tasks, results):
            err = result if isinstance(result, BaseException) else None
            if err is not None:
                failures.append(err)
            self._report(task, err)

        if len(failures) == len(tasks):
            # Nothing at all came back — genuinely a failed refresh.
            raise UpdateFailed(f"FlightRadar24: {failures[0]}") from failures[0]

        def fire(event: Event) -> None:
            self.hass.bus.fire(event.event, event.data)

        self.event_manager.fire_events(self.config_entry.title, fire)

from __future__ import annotations
import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .api.airport import AirportState
from .const import DEFAULT_NAME, DOMAIN, SUBENTRY_AIRCRAFT, SUBENTRY_AIRPORT
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


@dataclass(frozen=True, kw_only=True)
class FlightRadar24SensorEntityDescription(SensorEntityDescription):
    """Description for sensors that read from the coordinator directly (static sensors)."""
    value: Callable[[FlightRadar24Coordinator], Any]
    attributes: Callable[[FlightRadar24Coordinator], Any] | None = None


@dataclass(frozen=True, kw_only=True)
class FlightRadar24AirportSensorDescription(SensorEntityDescription):
    """Description for per-airport-subentry sensors that read from an AirportState."""
    value: Callable[[AirportState], Any]
    attributes: Callable[[AirportState], Any] | None = None


def _area_sensor(
        key: str, list_attr: str, icon: str,
) -> FlightRadar24SensorEntityDescription:
    return FlightRadar24SensorEntityDescription(
        key=key,
        translation_key=key,
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda coord, a=list_attr: len(getattr(coord.flight, a)),
        attributes=lambda coord, a=list_attr: {"flights": getattr(coord.flight, a)},
    )


def _stat_sensor(
        direction: str, suffix: str, icon: str,
        precision: int | None = None,
) -> FlightRadar24AirportSensorDescription:
    attr = f"{direction}_{suffix}"
    return FlightRadar24AirportSensorDescription(
        key=f"airport_{attr}",
        translation_key=f"airport_{attr}",
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        value=lambda state, a=attr: getattr(state.stats, a) if state.stats else None,
    )


def _schedule_sensor(
        direction: str, icon: str,
) -> FlightRadar24AirportSensorDescription:
    return FlightRadar24AirportSensorDescription(
        key=f"airport_{direction}",
        translation_key=f"airport_{direction}",
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda state, d=direction: (
            len(items) if (items := getattr(state, d)) is not None else None
        ),
        attributes=lambda state, d=direction: (
            {"flights": items} if (items := getattr(state, d)) is not None else None
        ),
    )


_STAT_FIELDS: tuple[tuple[str, str, int | None], ...] = (
    ("on_time", "mdi:airplane-check", None),
    ("delayed", "mdi:airplane-alert", None),
    ("delay_average", "mdi:airplane-clock", None),
    ("delay_index", "mdi:airplane-clock", 2),
    ("canceled", "mdi:airplane-remove", None),
)

_SCHEDULE_ICONS: dict[str, str] = {
    "arrivals": "mdi:airplane-landing",
    "departures": "mdi:airplane-takeoff",
    "ground": "mdi:airplane-marker",
}


def _weather_sensor(
        key: str,
        attr: str,
        *,
        icon: str | None = None,
        unit: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
) -> FlightRadar24AirportSensorDescription:
    return FlightRadar24AirportSensorDescription(
        key=f"airport_weather_{key}",
        translation_key=f"airport_weather_{key}",
        icon=icon,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        value=lambda state, a=attr: getattr(state.weather, a) if state.weather else None,
    )


def _aircraft_count_sensor(
        key: str, attr: str, icon: str,
) -> FlightRadar24AirportSensorDescription:
    return FlightRadar24AirportSensorDescription(
        key=f"airport_aircraft_{key}",
        translation_key=f"airport_aircraft_{key}",
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda state, a=attr: (
            getattr(state.aircraft_count, a) if state.aircraft_count else None
        ),
    )


STATIC_SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
    _area_sensor("in_area", "in_area_list", "mdi:airplane-marker"),
    _area_sensor("entered", "entered_list", "mdi:airplane-check"),
    _area_sensor("exited", "exited_list", "mdi:airplane-remove"),
    FlightRadar24SensorEntityDescription(
        key="most_tracked",
        translation_key="most_tracked",
        icon="mdi:airplane-search",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda coord: len(coord.flight.most_tracked_list) if coord.flight.most_tracked_list else None,
        attributes=lambda coord: (
            {"flights": coord.flight.most_tracked_list} if coord.flight.most_tracked_list else None
        ),
    ),
)


AIRPORT_SENSOR_TYPES: tuple[FlightRadar24AirportSensorDescription, ...] = (
    *(
        _stat_sensor(direction, suffix, icon, precision)
        for direction in ("arrivals", "departures")
        for suffix, icon, precision in _STAT_FIELDS
    ),
    *(
        _schedule_sensor(direction, icon)
        for direction, icon in _SCHEDULE_ICONS.items()
    ),
    _weather_sensor(
        "temperature", "temperature",
        device_class=SensorDeviceClass.TEMPERATURE, unit="°C",
    ),
    _weather_sensor(
        "dewpoint", "dewpoint",
        device_class=SensorDeviceClass.TEMPERATURE, unit="°C",
    ),
    _weather_sensor(
        "wind_speed", "wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED, unit="kn",
    ),
    _weather_sensor(
        "wind_direction", "wind_direction",
        icon="mdi:compass", unit="°",
    ),
    _weather_sensor(
        "pressure", "pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE, unit="hPa",
    ),
    _weather_sensor(
        "humidity", "humidity",
        device_class=SensorDeviceClass.HUMIDITY, unit="%",
    ),
    _weather_sensor(
        "visibility", "visibility",
        device_class=SensorDeviceClass.DISTANCE, unit="km",
    ),
    _weather_sensor(
        "condition", "condition",
        icon="mdi:weather-partly-cloudy", state_class=None,
    ),
    _weather_sensor(
        "flight_category", "flight_category",
        icon="mdi:airplane-clock", state_class=None,
    ),
    _weather_sensor(
        "metar", "metar",
        icon="mdi:weather-cloudy", state_class=None,
    ),
    _aircraft_count_sensor("ground", "ground", "mdi:airplane-marker"),
    _aircraft_count_sensor("on_ground_visible", "on_ground_visible", "mdi:airplane-marker"),
    _aircraft_count_sensor("on_ground_total", "on_ground_total", "mdi:airplane-marker"),
    *(
        FlightRadar24AirportSensorDescription(
            key=f"airport_{direction}_{suffix}_{period}",
            translation_key=f"airport_{direction}_{suffix}_{period}",
            icon=icon,
            state_class=SensorStateClass.MEASUREMENT,
            value=(
                lambda state, d=direction, s=suffix, p=period:
                    getattr(state.stats, f"{d}_{s}_{p}") if state.stats else None
            ),
        )
        for direction in ("arrivals", "departures")
        for period in ("yesterday", "recent")
        for suffix, icon in (
            ("on_time", "mdi:airplane-check"),
            ("delayed", "mdi:airplane-alert"),
            ("canceled", "mdi:airplane-remove"),
        )
    ),
)


RESTORE_SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
    FlightRadar24SensorEntityDescription(
        key="tracked",
        translation_key="tracked",
        icon="mdi:airplane",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda coord: len(coord.flight.tracked_list),
        attributes=lambda coord: {"flights": coord.flight.tracked_list},
    ),
)


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data

    static_sensors: list[FlightRadar24Sensor] = []
    static_sensors.extend(FlightRadar24Sensor(coordinator, desc) for desc in STATIC_SENSOR_TYPES)
    static_sensors.extend(FlightRadar24RestoreSensor(coordinator, desc) for desc in RESTORE_SENSOR_TYPES)
    async_add_entities(static_sensors)

    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_AIRPORT:
            code = subentry.data["code"]
            async_add_entities(
                (
                    FlightRadar24AirportSubentrySensor(coordinator, code, desc)
                    for desc in AIRPORT_SENSOR_TYPES
                ),
                config_subentry_id=subentry.subentry_id,
            )
        elif subentry.subentry_type == SUBENTRY_AIRCRAFT:
            reg = subentry.data["registration"]
            async_add_entities(
                [FlightRadar24AircraftSubentrySensor(coordinator, reg)],
                config_subentry_id=subentry.subentry_id,
            )


class FlightRadar24Sensor(FlightRadar24Entity, SensorEntity):
    entity_description: FlightRadar24SensorEntityDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            description: FlightRadar24SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_native_value = self.entity_description.value(self.coordinator)
        if self.entity_description.attributes is not None:
            attrs = self.entity_description.attributes(self.coordinator)
            if attrs is not None:
                new_attributes = copy.deepcopy(attrs)
                new_attributes["last_updated"] = dt_util.utcnow().isoformat()
                self._attr_extra_state_attributes = new_attributes
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.entity_description.value(self.coordinator) is not None


class FlightRadar24RestoreSensor(FlightRadar24Sensor, RestoreSensor):

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if not last_state:
            return

        tracked: dict[str, Any] = {}
        for flight in last_state.attributes.get("flights", {}):
            key = flight.get("id") or flight.get("flight_number") or flight.get("callsign")
            if key:
                tracked[key] = flight
        self.coordinator.flight.set_tracked(tracked)


class FlightRadar24AirportSubentrySensor(FlightRadar24Entity, SensorEntity):
    """Airport sensor bound to a specific subentry's AirportState.

    Description value/attributes lambdas receive the AirportState directly;
    the entity handles the None-state and write-state plumbing.
    """

    entity_description: FlightRadar24AirportSensorDescription

    def __init__(
            self,
            coordinator: FlightRadar24Coordinator,
            airport_code: str,
            description: FlightRadar24AirportSensorDescription,
    ) -> None:
        super().__init__(coordinator, f"{airport_code}_{description.key}")
        self.entity_description = description
        self._airport_code = airport_code.upper()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.unique_id}_airport_{self._airport_code}")},
            name=f"{DEFAULT_NAME} {self._airport_code}",
            manufacturer=DEFAULT_NAME,
            via_device=(DOMAIN, coordinator.unique_id),
        )

    def _state(self) -> AirportState | None:
        return self.coordinator.airport.subentry_airports.get(self._airport_code)

    @callback
    def _handle_coordinator_update(self) -> None:
        state = self._state()
        if state is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = None
            self.async_write_ha_state()
            return
        self._attr_native_value = self.entity_description.value(state)
        if self.entity_description.attributes is not None:
            attrs = self.entity_description.attributes(state)
            if attrs is not None:
                new_attributes = copy.deepcopy(attrs)
                new_attributes["last_updated"] = dt_util.utcnow().isoformat()
                self._attr_extra_state_attributes = new_attributes
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        state = self._state()
        return state is not None and self.entity_description.value(state) is not None


class FlightRadar24AircraftSubentrySensor(FlightRadar24Entity, SensorEntity):
    """Per-aircraft-subentry sensor showing tracked_type + full flight dict.

    State is the tracking mode (``live`` / ``not_airborne`` / ``not_found``
    / ``unknown``); attributes carry every field FlightProcessor knows
    about this aircraft.
    """

    _attr_translation_key = "aircraft_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["live", "not_airborne", "not_found", "unknown"]

    def __init__(
            self, coordinator: FlightRadar24Coordinator, registration: str,
    ) -> None:
        super().__init__(coordinator, f"aircraft_{registration}")
        self._registration = registration.upper()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.unique_id}_aircraft_{self._registration}")},
            name=f"{DEFAULT_NAME} {self._registration}",
            manufacturer=DEFAULT_NAME,
            via_device=(DOMAIN, coordinator.unique_id),
        )

    def _flight(self) -> dict[str, Any] | None:
        for entry in self.coordinator.flight.tracked.values():
            if (entry.get("aircraft_registration") or "").upper() == self._registration:
                return entry
        return None

    @property
    def native_value(self) -> str:
        flight = self._flight()
        return flight.get("tracked_type") or "unknown" if flight else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._flight() or {}

    @property
    def icon(self) -> str:
        flight = self._flight()
        if flight and flight.get("tracked_type") == "live":
            return "mdi:airplane"
        return "mdi:airplane-off"

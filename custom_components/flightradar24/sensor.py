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
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity


@dataclass(frozen=True, kw_only=True)
class FlightRadar24SensorEntityDescription(SensorEntityDescription):
    value: Callable[[FlightRadar24Coordinator], Any]
    attributes: Callable[[FlightRadar24Coordinator], Any] | None = None


def _area_sensor(
        key: str, list_attr: str, icon: str,
) -> FlightRadar24SensorEntityDescription:
    def _value(coord: FlightRadar24Coordinator) -> int:
        return len(getattr(coord.flight, list_attr))

    def _attributes(coord: FlightRadar24Coordinator) -> dict[str, Any]:
        return {"flights": getattr(coord.flight, list_attr)}

    return FlightRadar24SensorEntityDescription(
        key=key,
        translation_key=key,
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        value=_value,
        attributes=_attributes,
    )


def _stat_sensor(
        direction: str, suffix: str, icon: str,
        precision: int | None = None,
) -> FlightRadar24SensorEntityDescription:
    attr = f"{direction}_{suffix}"

    def _value(coord: FlightRadar24Coordinator) -> Any:
        return getattr(coord.airport.stats, attr) if coord.airport.stats else None

    return FlightRadar24SensorEntityDescription(
        key=f"airport_{attr}",
        translation_key=f"airport_{attr}",
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=precision,
        value=_value,
    )


def _schedule_sensor(
        direction: str, icon: str,
) -> FlightRadar24SensorEntityDescription:
    def _value(coord: FlightRadar24Coordinator) -> int | None:
        items = getattr(coord.airport, direction)
        return len(items) if items is not None else None

    def _attributes(coord: FlightRadar24Coordinator) -> dict[str, Any] | None:
        items = getattr(coord.airport, direction)
        return {"flights": items} if items is not None else None

    return FlightRadar24SensorEntityDescription(
        key=f"airport_{direction}",
        translation_key=f"airport_{direction}",
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        value=_value,
        attributes=_attributes,
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
) -> FlightRadar24SensorEntityDescription:
    def _value(coord: FlightRadar24Coordinator) -> Any:
        return getattr(coord.airport.weather, attr) if coord.airport.weather else None

    return FlightRadar24SensorEntityDescription(
        key=f"airport_weather_{key}",
        translation_key=f"airport_weather_{key}",
        icon=icon,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=state_class,
        value=_value,
    )


def _aircraft_count_sensor(
        key: str, attr: str, icon: str,
) -> FlightRadar24SensorEntityDescription:
    def _value(coord: FlightRadar24Coordinator) -> Any:
        return getattr(coord.airport.aircraft_count, attr) if coord.airport.aircraft_count else None

    return FlightRadar24SensorEntityDescription(
        key=f"airport_aircraft_{key}",
        translation_key=f"airport_aircraft_{key}",
        icon=icon,
        state_class=SensorStateClass.MEASUREMENT,
        value=_value,
    )


SENSOR_TYPES: tuple[FlightRadar24SensorEntityDescription, ...] = (
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
        FlightRadar24SensorEntityDescription(
            key=f"airport_{direction}_{suffix}_{period}",
            translation_key=f"airport_{direction}_{suffix}_{period}",
            icon=icon,
            state_class=SensorStateClass.MEASUREMENT,
            value=(
                lambda coord, d=direction, s=suffix, p=period:
                    getattr(coord.airport.stats, f"{d}_{s}_{p}") if coord.airport.stats else None
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

    sensors: list[FlightRadar24Sensor] = []
    sensors.extend(FlightRadar24Sensor(coordinator, desc) for desc in SENSOR_TYPES)
    sensors.extend(FlightRadar24RestoreSensor(coordinator, desc) for desc in RESTORE_SENSOR_TYPES)
    async_add_entities(sensors)


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

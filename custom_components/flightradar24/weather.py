from __future__ import annotations
from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    WeatherEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DEFAULT_NAME, DOMAIN, SUBENTRY_AIRPORT
from .coordinator import FlightRadar24Coordinator
from .entity import FlightRadar24Entity

_CONDITION_MAP: dict[str, str] = {
    "clear": ATTR_CONDITION_SUNNY,
    "sunny": ATTR_CONDITION_SUNNY,
    "mostly sunny": ATTR_CONDITION_SUNNY,
    "fair": ATTR_CONDITION_SUNNY,
    "partly cloudy": ATTR_CONDITION_PARTLYCLOUDY,
    "mostly cloudy": ATTR_CONDITION_PARTLYCLOUDY,
    "scattered clouds": ATTR_CONDITION_PARTLYCLOUDY,
    "broken clouds": ATTR_CONDITION_CLOUDY,
    "cloudy": ATTR_CONDITION_CLOUDY,
    "overcast": ATTR_CONDITION_CLOUDY,
    "fog": ATTR_CONDITION_FOG,
    "mist": ATTR_CONDITION_FOG,
    "haze": ATTR_CONDITION_FOG,
    "rain": ATTR_CONDITION_RAINY,
    "light rain": ATTR_CONDITION_RAINY,
    "heavy rain": ATTR_CONDITION_RAINY,
    "showers": ATTR_CONDITION_RAINY,
    "drizzle": ATTR_CONDITION_RAINY,
    "snow": ATTR_CONDITION_SNOWY,
    "light snow": ATTR_CONDITION_SNOWY,
    "heavy snow": ATTR_CONDITION_SNOWY,
    "windy": ATTR_CONDITION_WINDY,
    "night": ATTR_CONDITION_CLEAR_NIGHT,
}


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: FlightRadar24Coordinator = entry.runtime_data
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_AIRPORT:
            continue
        async_add_entities(
            [FlightRadar24AirportWeather(coordinator, subentry.data["code"])],
            config_subentry_id=subentry.subentry_id,
        )


class FlightRadar24AirportWeather(FlightRadar24Entity, WeatherEntity):
    """Weather entity bound to a specific airport subentry's AirportState."""

    _attr_translation_key = "airport_weather"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KNOTS
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS

    def __init__(
            self, coordinator: FlightRadar24Coordinator, airport_code: str,
    ) -> None:
        super().__init__(coordinator, f"{airport_code}_weather")
        self._airport_code = airport_code.upper()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.unique_id}_airport_{self._airport_code}")},
            name=f"{DEFAULT_NAME} {self._airport_code}",
            manufacturer=DEFAULT_NAME,
            via_device=(DOMAIN, coordinator.unique_id),
        )

    def _weather(self):
        state = self.coordinator.airport.subentry_airports.get(self._airport_code)
        return state.weather if state else None

    @property
    def available(self) -> bool:
        return self._weather() is not None

    @property
    def native_temperature(self) -> float | None:
        w = self._weather()
        return w.temperature if w else None

    @property
    def humidity(self) -> int | None:
        w = self._weather()
        return w.humidity if w else None

    @property
    def native_pressure(self) -> float | None:
        w = self._weather()
        return w.pressure if w else None

    @property
    def native_wind_speed(self) -> float | None:
        w = self._weather()
        return w.wind_speed if w else None

    @property
    def wind_bearing(self) -> int | None:
        w = self._weather()
        return w.wind_direction if w else None

    @property
    def native_visibility(self) -> float | None:
        w = self._weather()
        return w.visibility if w else None

    @property
    def native_dew_point(self) -> float | None:
        w = self._weather()
        return w.dewpoint if w else None

    @property
    def condition(self) -> str | None:
        w = self._weather()
        if not w or not w.condition:
            return None
        return _CONDITION_MAP.get(w.condition.lower())

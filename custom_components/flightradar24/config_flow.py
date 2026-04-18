from __future__ import annotations
from logging import getLogger
from typing import Any, TYPE_CHECKING
import voluptuous as vol
from .api.client import FlightRadar24API, LoginError
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigSubentryFlow,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_PASSWORD,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from .const import (
    CONF_MAX_ALTITUDE,
    CONF_MIN_ALTITUDE,
    CONF_MOST_TRACKED,
    CONF_MOST_TRACKED_DEFAULT,
    DEFAULT_NAME,
    DOMAIN,
    MAX_ALTITUDE,
    MIN_ALTITUDE,
    SUBENTRY_AIRCRAFT,
    SUBENTRY_AIRPORT,
)

if TYPE_CHECKING:
    from .coordinator import FlightRadar24Coordinator

_LOGGER = getLogger(__name__)


async def _validate_login(hass, username: str, password: str) -> str | None:
    """Attempt a FR24 login. Returns None on success or a strings.json error key."""
    try:
        client = FlightRadar24API()
        await hass.async_add_executor_job(client.login, username, password)
    except LoginError as err:
        _LOGGER.warning("FlightRadar24 login failed: %s", err)
        return "login_failed"
    return None


_RADIUS_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=100, max=500000, step=100, unit_of_measurement="m", mode=NumberSelectorMode.BOX)
)
_SCAN_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=1, max=3600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
)
_ALTITUDE_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_ALTITUDE,
        max=MAX_ALTITUDE,
        step=1,
        unit_of_measurement="ft",
        mode=NumberSelectorMode.BOX,
    )
)
_BOOL_SELECTOR = BooleanSelector()
_USERNAME_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class FlightRadarConfigFlow(ConfigFlow, domain=DOMAIN):

    @classmethod
    @callback
    def async_get_supported_subentry_types(
            cls, config_entry: ConfigEntry,
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {
            SUBENTRY_AIRPORT: AirportSubentryFlow,
            SUBENTRY_AIRCRAFT: AircraftSubentryFlow,
        }

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            username = (user_input.get(CONF_USERNAME) or "").strip()
            password = user_input.get(CONF_PASSWORD) or ""

            if bool(username) != bool(password):
                errors["base"] = "credentials_required"
            elif username and password:
                if err_key := await _validate_login(self.hass, username, password):
                    errors["base"] = err_key

            if not errors:
                # Strip empty credential fields so they don't pollute the entry data.
                data = {k: v for k, v in user_input.items() if v not in (None, "")}
                unique_id = (
                    f"{data[CONF_LATITUDE]}-"
                    f"{data[CONF_LONGITUDE]}-"
                    f"{data[CONF_RADIUS]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=data)

        schema = vol.Schema({
            vol.Required(CONF_RADIUS, default=1000): _RADIUS_SELECTOR,
            vol.Required(CONF_LATITUDE): cv.latitude,
            vol.Required(CONF_LONGITUDE): cv.longitude,
            vol.Required(CONF_SCAN_INTERVAL, default=10): _SCAN_INTERVAL_SELECTOR,
            vol.Optional(CONF_USERNAME): _USERNAME_SELECTOR,
            vol.Optional(CONF_PASSWORD): _PASSWORD_SELECTOR,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_LATITUDE: self.hass.config.latitude,
                    CONF_LONGITUDE: self.hass.config.longitude,
                    **({CONF_USERNAME: user_input.get(CONF_USERNAME, "")} if user_input else {}),
                },
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Triggered by HA when ConfigEntryAuthFailed is raised."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "")
            if not (username and password):
                errors["base"] = "credentials_required"
            elif err_key := await _validate_login(self.hass, username, password):
                errors["base"] = err_key

            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_USERNAME: username, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        schema = vol.Schema({
            vol.Required(CONF_USERNAME, default=entry.data.get(CONF_USERNAME, "")): _USERNAME_SELECTOR,
            vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        })
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FlightRadarOptionsFlow()


class FlightRadarOptionsFlow(OptionsFlow):

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        data = user_input or self.config_entry.data

        if user_input is not None:
            username = data.get(CONF_USERNAME)
            password = data.get(CONF_PASSWORD)

            if bool(username) != bool(password):
                errors["base"] = "credentials_required"
            elif username and password:
                if err_key := await _validate_login(self.hass, username, password):
                    errors["base"] = err_key

            if not errors:
                self.hass.config_entries.async_update_entry(self.config_entry, data=user_input)
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        data_schema = vol.Schema({
            vol.Required(CONF_RADIUS, default=data.get(CONF_RADIUS)): _RADIUS_SELECTOR,
            vol.Required(CONF_LATITUDE, default=data.get(CONF_LATITUDE)): cv.latitude,
            vol.Required(CONF_LONGITUDE, default=data.get(CONF_LONGITUDE)): cv.longitude,
            vol.Required(CONF_SCAN_INTERVAL, default=data.get(CONF_SCAN_INTERVAL)): _SCAN_INTERVAL_SELECTOR,
            vol.Optional(
                CONF_MIN_ALTITUDE,
                description={"suggested_value": data.get(CONF_MIN_ALTITUDE, MIN_ALTITUDE)},
            ): _ALTITUDE_SELECTOR,
            vol.Optional(
                CONF_MAX_ALTITUDE,
                description={"suggested_value": data.get(CONF_MAX_ALTITUDE, MAX_ALTITUDE)},
            ): _ALTITUDE_SELECTOR,
            vol.Optional(
                CONF_MOST_TRACKED,
                description={"suggested_value": data.get(CONF_MOST_TRACKED, CONF_MOST_TRACKED_DEFAULT)},
            ): _BOOL_SELECTOR,
            vol.Optional(
                CONF_USERNAME,
                description={"suggested_value": data.get(CONF_USERNAME, "")},
            ): _USERNAME_SELECTOR,
            vol.Optional(
                CONF_PASSWORD,
                description={"suggested_value": data.get(CONF_PASSWORD, "")},
            ): _PASSWORD_SELECTOR,
        })

        return self.async_show_form(step_id="init", data_schema=data_schema, errors=errors)


class AirportSubentryFlow(ConfigSubentryFlow):
    """Flow for adding / reconfiguring an airport subentry."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = (user_input.get("code") or "").strip().upper()
            if not (3 <= len(code) <= 4) or not code.isalpha():
                errors["base"] = "invalid_airport_code"
            else:
                entry = self._get_entry()
                already = any(
                    sub.subentry_type == SUBENTRY_AIRPORT and sub.data.get("code") == code
                    for sub in entry.subentries.values()
                )
                if already:
                    errors["base"] = "airport_already_tracked"
                else:
                    return self.async_create_entry(title=code, data={"code": code})

        schema = vol.Schema({vol.Required("code"): cv.string})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class AircraftSubentryFlow(ConfigSubentryFlow):
    """Flow for adding / reconfiguring an aircraft (tail number) subentry."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            reg = (user_input.get("registration") or "").strip().upper()
            if not reg or len(reg) < 3:
                errors["base"] = "invalid_registration"
            else:
                entry = self._get_entry()
                already = any(
                    sub.subentry_type == SUBENTRY_AIRCRAFT
                    and sub.data.get("registration") == reg
                    for sub in entry.subentries.values()
                )
                if already:
                    errors["base"] = "aircraft_already_tracked"
                else:
                    coordinator: "FlightRadar24Coordinator" = entry.runtime_data
                    try:
                        exists = await coordinator.aircraft_exists(reg)
                    except Exception:  # noqa: BLE001 — surface any FR24/network failure as "can't verify"
                        errors["base"] = "aircraft_check_failed"
                    else:
                        if not exists:
                            errors["base"] = "aircraft_not_found"
                        else:
                            return self.async_create_entry(
                                title=reg, data={"registration": reg},
                            )

        schema = vol.Schema({vol.Required("registration"): cv.string})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

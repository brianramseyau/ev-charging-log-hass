"""Shared fixtures."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charging_log.const import (
    CONF_ODOMETER_ENTITY,
    CONF_SECRET_HASH,
    CONF_TELEMETRY_ENTITY,
    DOMAIN,
)
from custom_components.ev_charging_log.view import hash_secret
from homeassistant.core import HomeAssistant

SECRET = "x" * 43
ODOMETER = "sensor.car_odometer"
TELEMETRY = "sensor.car_telemetry_last_updated"
OTHER = "sensor.front_door_lock_battery"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations: None) -> None:
    """Load custom_components/ in every test, with the recorder (a dependency) set up first."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured companion."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="EV Charging Log companion",
        data={
            CONF_ODOMETER_ENTITY: ODOMETER,
            CONF_TELEMETRY_ENTITY: TELEMETRY,
            CONF_SECRET_HASH: hash_secret(SECRET),
        },
    )


def set_car_sensors(hass: HomeAssistant) -> None:
    """Register the two sensors the config flow's selectors filter for."""
    hass.states.async_set(
        ODOMETER,
        "118102",
        {"device_class": "distance", "unit_of_measurement": "km"},
    )
    hass.states.async_set(TELEMETRY, "2026-09-20T22:59:31+00:00", {"device_class": "timestamp"})

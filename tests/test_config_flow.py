"""Config and options flow tests."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.ev_charging_log.const import (
    CONF_ODOMETER_ENTITY,
    CONF_SECRET,
    CONF_SECRET_HASH,
    CONF_TELEMETRY_ENTITY,
    DOMAIN,
)
from custom_components.ev_charging_log.view import hash_secret
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ODOMETER, SECRET, TELEMETRY, set_car_sensors


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_creates_entry_storing_only_the_hash(recorder_mock, hass: HomeAssistant) -> None:
    """The secret is hashed; the plaintext is never stored."""
    set_car_sensors(hass)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_ODOMETER_ENTITY: ODOMETER,
            CONF_TELEMETRY_ENTITY: TELEMETRY,
            CONF_SECRET: f" {SECRET} ",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ODOMETER_ENTITY: ODOMETER,
        CONF_TELEMETRY_ENTITY: TELEMETRY,
        CONF_SECRET_HASH: hash_secret(SECRET),
    }
    assert SECRET not in str(result["data"])


async def test_entity_selectors_filter_by_device_class(recorder_mock, hass: HomeAssistant) -> None:
    """The pickers only offer distance and timestamp sensors."""
    result = await _start(hass)
    schema = result["data_schema"].schema
    configs = {str(key): value.config for key, value in schema.items() if hasattr(value, "config")}
    assert configs[CONF_ODOMETER_ENTITY]["domain"] == ["sensor"]
    assert configs[CONF_ODOMETER_ENTITY]["device_class"] == ["distance"]
    assert configs[CONF_TELEMETRY_ENTITY]["device_class"] == ["timestamp"]


async def test_rejects_short_secret(recorder_mock, hass: HomeAssistant) -> None:
    """A truncated paste is caught."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ODOMETER_ENTITY: ODOMETER, CONF_TELEMETRY_ENTITY: TELEMETRY, CONF_SECRET: "short"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SECRET: "secret_too_short"}


async def test_rejects_same_entity_twice(recorder_mock, hass: HomeAssistant) -> None:
    """Odometer and telemetry must differ."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_ODOMETER_ENTITY: ODOMETER, CONF_TELEMETRY_ENTITY: ODOMETER, CONF_SECRET: SECRET},
    )
    assert result["errors"] == {"base": "same_entity"}


async def test_single_instance(recorder_mock, hass: HomeAssistant, config_entry) -> None:
    """A second setup aborts."""
    config_entry.add_to_hass(hass)
    result = await _start(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_warns_when_recorder_excludes_an_entity(recorder_mock, hass: HomeAssistant) -> None:
    """Excluded entities get a confirm step, then setup continues."""
    with patch.object(recorder_mock, "entity_filter", lambda entity_id: entity_id != TELEMETRY):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_ODOMETER_ENTITY: ODOMETER, CONF_TELEMETRY_ENTITY: TELEMETRY, CONF_SECRET: SECRET},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "not_recorded"
        assert result["description_placeholders"] == {"entities": TELEMETRY}

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_rotates_secret(recorder_mock, hass: HomeAssistant, config_entry) -> None:
    """A new secret replaces the hash."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    new_secret = "y" * 43

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ODOMETER_ENTITY: ODOMETER, CONF_TELEMETRY_ENTITY: TELEMETRY, CONF_SECRET: new_secret},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.data[CONF_SECRET_HASH] == hash_secret(new_secret)


async def test_options_blank_secret_keeps_current(
    recorder_mock, hass: HomeAssistant, config_entry
) -> None:
    """Changing only the entities keeps the existing secret."""
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ODOMETER_ENTITY: "sensor.other_odometer", CONF_TELEMETRY_ENTITY: TELEMETRY},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.data[CONF_ODOMETER_ENTITY] == "sensor.other_odometer"
    assert config_entry.data[CONF_SECRET_HASH] == hash_secret(SECRET)

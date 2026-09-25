"""Endpoint tests: auth, window rules, and history built from real recorded states."""

from __future__ import annotations

from datetime import datetime, timedelta
from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .conftest import ODOMETER, OTHER, SECRET, TELEMETRY

URL = "/api/ev_charging_log/odometer"
AUTH = {"Authorization": f"Bearer {SECRET}"}


async def _setup(hass: HomeAssistant, config_entry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def _iso(value: datetime) -> str:
    return value.isoformat()


async def test_missing_or_wrong_secret_is_401(
    recorder_mock, hass: HomeAssistant, hass_client_no_auth, config_entry
) -> None:
    """No secret, a wrong secret, or the wrong scheme all get an empty 401."""
    await _setup(hass, config_entry)
    client = await hass_client_no_auth()
    for headers in (
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": f"Basic {SECRET}"},
        {"Authorization": "Bearer "},
    ):
        resp = await client.get(URL, headers=headers)
        assert resp.status == HTTPStatus.UNAUTHORIZED
        assert await resp.text() == ""
        assert resp.headers["Cache-Control"] == "no-store"


async def test_bad_secret_does_not_feed_ip_ban(
    recorder_mock, hass: HomeAssistant, hass_client_no_auth, config_entry
) -> None:
    """Repeated bad secrets never trip HA's login-attempt counter."""
    await _setup(hass, config_entry)
    client = await hass_client_no_auth()
    for _ in range(10):
        resp = await client.get(URL, headers={"Authorization": "Bearer wrong"})
        assert resp.status == HTTPStatus.UNAUTHORIZED
    resp = await client.get(URL, headers=AUTH)
    assert resp.status == HTTPStatus.OK


async def test_404_without_a_loaded_entry(
    recorder_mock, hass: HomeAssistant, hass_client_no_auth, config_entry
) -> None:
    """After unload the view stays registered but answers 404."""
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    client = await hass_client_no_auth()
    resp = await client.get(URL, headers=AUTH)
    assert resp.status == HTTPStatus.NOT_FOUND


async def test_current_state_by_default(
    recorder_mock, hass: HomeAssistant, hass_client_no_auth, config_entry
) -> None:
    """With no window, the live state of each entity is returned."""
    hass.states.async_set(ODOMETER, "118204", {"unit_of_measurement": "km"})
    hass.states.async_set(TELEMETRY, "2026-09-23T08:40:52+00:00")
    await _setup(hass, config_entry)

    client = await hass_client_no_auth()
    resp = await client.get(URL, headers=AUTH)
    assert resp.status == HTTPStatus.OK
    assert resp.headers["Cache-Control"] == "no-store"
    body = await resp.json()
    assert body["version"] == 1
    assert body["odometer"]["unit"] == "km"
    assert [c["state"] for c in body["odometer"]["changes"]] == ["118204"]
    assert [c["state"] for c in body["telemetry"]["changes"]] == ["2026-09-23T08:40:52+00:00"]


async def test_passes_unavailable_through_verbatim(
    recorder_mock, hass: HomeAssistant, hass_client_no_auth, config_entry
) -> None:
    """The app decides what's usable, not the companion."""
    hass.states.async_set(ODOMETER, "unavailable")
    hass.states.async_set(TELEMETRY, "unknown")
    await _setup(hass, config_entry)
    body = await (await (await hass_client_no_auth()).get(URL, headers=AUTH)).json()
    assert body["odometer"] == {"unit": None, "changes": [body["odometer"]["changes"][0]]}
    assert body["odometer"]["changes"][0]["state"] == "unavailable"
    assert body["telemetry"]["changes"][0]["state"] == "unknown"


async def test_history_window(
    recorder_mock,
    hass: HomeAssistant,
    hass_client_no_auth,
    config_entry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Recorded changes come back, the first one being the state at `start`."""
    t0 = dt_util.parse_datetime("2026-09-23T06:00:00+00:00")
    freezer.move_to(t0)
    hass.states.async_set(ODOMETER, "118102", {"unit_of_measurement": "km"})
    hass.states.async_set(TELEMETRY, "2026-09-23T05:59:00+00:00")
    hass.states.async_set(OTHER, "80")
    await _setup(hass, config_entry)
    await async_wait_recording_done(hass)

    # Arrives home, then sits on the charger reporting an unchanged odometer.
    freezer.move_to(t0 + timedelta(hours=2, minutes=41))
    hass.states.async_set(ODOMETER, "118204", {"unit_of_measurement": "km"})
    hass.states.async_set(TELEMETRY, "2026-09-23T08:40:52+00:00")
    for minutes in (35, 70):
        freezer.move_to(t0 + timedelta(hours=2, minutes=41 + minutes))
        hass.states.async_set(TELEMETRY, _iso(t0 + timedelta(hours=2, minutes=40 + minutes)))
    await async_wait_recording_done(hass)

    freezer.move_to(t0 + timedelta(hours=6))
    start = t0 + timedelta(hours=1)
    end = t0 + timedelta(hours=5)
    client = await hass_client_no_auth()
    resp = await client.get(
        URL,
        headers=AUTH,
        # entity_id is ignored: the entities come only from the config entry.
        params={"start": _iso(start), "end": _iso(end), "entity_id": OTHER},
    )
    assert resp.status == HTTPStatus.OK
    body = await resp.json()

    odometer = body["odometer"]["changes"]
    assert [c["state"] for c in odometer] == ["118102", "118204"]
    assert dt_util.parse_datetime(odometer[0]["at"]) == start
    telemetry = body["telemetry"]["changes"]
    assert len(telemetry) == 4
    assert dt_util.parse_datetime(telemetry[0]["at"]) == start
    assert telemetry[0]["state"] == "2026-09-23T05:59:00+00:00"
    assert OTHER not in str(body)
    assert body["oldestRecorded"] is not None


async def test_window_excludes_changes_after_end(
    recorder_mock,
    hass: HomeAssistant,
    hass_client_no_auth,
    config_entry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Nothing later than `end` is returned."""
    t0 = dt_util.parse_datetime("2026-09-23T06:00:00+00:00")
    freezer.move_to(t0)
    hass.states.async_set(ODOMETER, "100", {"unit_of_measurement": "km"})
    hass.states.async_set(TELEMETRY, _iso(t0))
    await _setup(hass, config_entry)
    await async_wait_recording_done(hass)
    freezer.move_to(t0 + timedelta(hours=3))
    hass.states.async_set(ODOMETER, "200", {"unit_of_measurement": "km"})
    await async_wait_recording_done(hass)

    client = await hass_client_no_auth()
    body = await (
        await client.get(
            URL,
            headers=AUTH,
            params={"start": _iso(t0 + timedelta(hours=1)), "end": _iso(t0 + timedelta(hours=2))},
        )
    ).json()
    assert [c["state"] for c in body["odometer"]["changes"]] == ["100"]


async def test_window_validation(
    recorder_mock, hass: HomeAssistant, hass_client_no_auth, config_entry
) -> None:
    """Bad instants, reversed windows and windows over 31 days are 400s."""
    await _setup(hass, config_entry)
    client = await hass_client_no_auth()
    now = dt_util.utcnow()
    for params in (
        {"start": "yesterday"},
        {"end": "2026-09-23T08:00:00"},  # no timezone
        {"start": _iso(now), "end": _iso(now - timedelta(hours=1))},
        {"start": _iso(now - timedelta(days=31, seconds=1)), "end": _iso(now)},
    ):
        resp = await client.get(URL, headers=AUTH, params=params)
        assert resp.status == HTTPStatus.BAD_REQUEST, params

    resp = await client.get(
        URL, headers=AUTH, params={"start": _iso(now - timedelta(days=31)), "end": _iso(now)}
    )
    assert resp.status == HTTPStatus.OK

"""The companion's only endpoint: GET /api/ev_charging_log/odometer.

Deliberately simple. It checks the secret, reads the recorder for the two
entities chosen in the config entry, and returns raw state changes. Pairing and
matching happen in the app. Entity IDs come only from the config entry, never
the request, so the secret can't be used to read anything else.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
from http import HTTPStatus
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.recorder import get_instance, history
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.http import KEY_HASS
from homeassistant.util import dt as dt_util

from .const import (
    API_URL,
    API_VERSION,
    CONF_ODOMETER_ENTITY,
    CONF_SECRET_HASH,
    CONF_TELEMETRY_ENTITY,
    DATA_ENTRY,
    MAX_WINDOW,
)

NO_STORE = {"Cache-Control": "no-store"}


def hash_secret(secret: str) -> str:
    """Return the SHA-256 hex digest stored in place of the secret."""
    return hashlib.sha256(secret.encode()).hexdigest()


def _authorized(request: web.Request, expected_hash: str) -> bool:
    header = request.headers.get("Authorization", "")
    scheme, _, secret = header.partition(" ")
    if scheme.lower() != "bearer" or not secret:
        return False
    return hmac.compare_digest(hash_secret(secret.strip()), expected_hash)


def _parse_instant(value: str) -> datetime | None:
    parsed = dt_util.parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        return None
    return dt_util.as_utc(parsed)


def _change(state: State, start: datetime) -> dict[str, str]:
    # The recorder reports the state in effect at `start` with its original
    # last_changed; clamp it so the first entry reads as "the state at start".
    return {"state": state.state, "at": max(state.last_changed, start).isoformat()}


def _history(hass: HomeAssistant, start: datetime, end: datetime, entity_id: str) -> list[State]:
    """Run in the recorder's executor: state changes, start-time state included."""
    return history.state_changes_during_period(
        hass,
        start,
        end,
        entity_id,
        no_attributes=True,
        include_start_time_state=True,
    ).get(entity_id, [])


def _oldest_recorded(hass: HomeAssistant) -> str | None:
    instance = get_instance(hass)
    oldest_ts = getattr(getattr(instance, "states_manager", None), "oldest_ts", None)
    if oldest_ts:
        return dt_util.utc_from_timestamp(oldest_ts).isoformat()
    keep_days = getattr(instance, "keep_days", None)
    if keep_days:
        return (dt_util.utcnow() - timedelta(days=keep_days)).isoformat()
    return None


class OdometerView(HomeAssistantView):
    """Odometer and telemetry-timestamp history, behind a scoped secret."""

    url = API_URL
    name = "api:ev_charging_log:odometer"
    # HA's own token isn't used: the secret below is the only credential, and a
    # leaked one can only read these two entities. Failures are deliberately NOT
    # fed into HA's IP ban (process_wrong_login): behind Home Assistant Cloud or a
    # reverse proxy, every request can appear to come from one address, and a
    # stale secret in the app would ban it, locking the user out of all of HA.
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        """Return history for [start, end] (both optional)."""
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = hass.data.get(DATA_ENTRY)
        if entry is None:
            return web.Response(status=HTTPStatus.NOT_FOUND, headers=NO_STORE)
        if not _authorized(request, entry.data[CONF_SECRET_HASH]):
            # Returned, never raised: HA's ban middleware counts a failed login
            # only when a handler *raises* HTTPUnauthorized (see requires_auth).
            return web.Response(status=HTTPStatus.UNAUTHORIZED, headers=NO_STORE)

        now = dt_util.utcnow()
        end: datetime | None = now
        if (raw_end := request.query.get("end")) is not None:
            end = _parse_instant(raw_end)
        if end is None:
            return self._bad_request("end must be an ISO 8601 time with a timezone")
        start: datetime | None = end
        if (raw_start := request.query.get("start")) is not None:
            start = _parse_instant(raw_start)
        if start is None:
            return self._bad_request("start must be an ISO 8601 time with a timezone")
        if start > end:
            return self._bad_request("start must be before end")
        if end - start > MAX_WINDOW:
            return self._bad_request("the window is limited to 31 days")

        odometer_id: str = entry.data[CONF_ODOMETER_ENTITY]
        telemetry_id: str = entry.data[CONF_TELEMETRY_ENTITY]
        odometer_state = hass.states.get(odometer_id)
        unit = odometer_state.attributes.get("unit_of_measurement") if odometer_state else None

        if start == end and end >= now:
            # "What does it read right now?" The live state machine is newer than
            # the recorder, which commits in batches.
            changes = {
                entity_id: [_change(state, start)] if (state := hass.states.get(entity_id)) else []
                for entity_id in (odometer_id, telemetry_id)
            }
        else:
            recorder = get_instance(hass)
            changes = {}
            for entity_id in (odometer_id, telemetry_id):
                states = await recorder.async_add_executor_job(
                    _history, hass, start, end, entity_id
                )
                changes[entity_id] = [
                    _change(state, start) for state in states if state.last_changed <= end
                ]

        body: dict[str, Any] = {
            "version": API_VERSION,
            "odometer": {"unit": unit, "changes": changes[odometer_id]},
            "telemetry": {"changes": changes[telemetry_id]},
            "oldestRecorded": _oldest_recorded(hass),
        }
        return self.json(body, headers=NO_STORE)

    def _bad_request(self, message: str) -> web.Response:
        return self.json_message(message, HTTPStatus.BAD_REQUEST, headers=NO_STORE)

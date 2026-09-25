"""EV Charging Log companion.

Serves one read-only, secret-protected endpoint with the recorded history of
exactly two entities (a car's odometer and its telemetry timestamp), for the
EV Charging Log app to fill in charging-session odometers. See README.md.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_ENTRY, DATA_VIEW_REGISTERED
from .view import OdometerView


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the companion from its config entry."""
    # HA can't unregister an HTTP view, so it's registered once per process and
    # answers 404 whenever no entry is loaded (see OdometerView.get).
    if not hass.data.get(DATA_VIEW_REGISTERED):
        hass.http.register_view(OdometerView())
        hass.data[DATA_VIEW_REGISTERED] = True
    hass.data[DATA_ENTRY] = entry
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry; the view goes inactive."""
    if hass.data.get(DATA_ENTRY) is entry:
        hass.data.pop(DATA_ENTRY)
    return True

"""Constants for the EV Charging Log companion."""

from datetime import timedelta

DOMAIN = "ev_charging_log"

CONF_ODOMETER_ENTITY = "odometer_entity"
CONF_TELEMETRY_ENTITY = "telemetry_entity"
CONF_SECRET = "secret"
CONF_SECRET_HASH = "secret_sha256"

# The app generates 32 random bytes, base64url-encoded (43 characters).
MIN_SECRET_LENGTH = 32

# Bump only for a breaking change to the response. The app refuses any version
# it doesn't know and tells the user to update, rather than misreading it.
API_VERSION = 1
API_URL = "/api/ev_charging_log/odometer"
MAX_WINDOW = timedelta(days=31)

DATA_ENTRY = f"{DOMAIN}_entry"
DATA_VIEW_REGISTERED = f"{DOMAIN}_view_registered"

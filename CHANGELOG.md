# Changelog

## 0.1.0

First release.

- `GET /api/ev_charging_log/odometer` (response `version` 1): recorded history of
  one odometer entity and one telemetry-timestamp entity, protected by a secret
  generated in EV Charging Log.
- Config flow with entity pickers filtered to distance and timestamp sensors,
  and a warning when the recorder excludes either entity.
- Options flow to change the entities or rotate the secret.

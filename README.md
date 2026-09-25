# EV Charging Log companion for Home Assistant

A small Home Assistant integration that lets
[EV Charging Log](https://github.com/brianramseyau/ev-charging-log) read your
car's odometer, so charging sessions imported from the charger fill in their
own odometer readings.

It exposes **one read-only endpoint**. It returns the recorded history of
exactly two entities you choose — an odometer and the car's "telemetry last
updated" timestamp — and nothing else. It calls no services and can't be pointed
at any other entity.

## Why a companion instead of a Home Assistant token?

Home Assistant access tokens have no scopes. Even a non-admin user's token can
read every entity and call every service — with a car integration installed,
that includes unlocking the car. That's too much to hand an app that needs two
sensors.

This companion is protected by its own secret instead. EV Charging Log
generates it, you paste it here once, and Home Assistant stores only its
SHA-256 hash. If the secret leaks, the most anyone can do is read your
odometer history.

## Requirements

- A car integration providing:
  - an **odometer** sensor (`device_class: distance`, reporting in **km**), and
  - a **telemetry timestamp** sensor (`device_class: timestamp`) holding when
    the car itself last reported.

  [hass-byd-vehicle](https://github.com/jkaberg/hass-byd-vehicle) provides
  both (_Odometer_ and _Telemetry last updated_). Any integration with
  equivalent sensors works.
- Both entities recorded by Home Assistant's recorder (the default). The app can
  only fill in charges still within the recorder's retention (10 days by
  default).

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=brianramseyau&repository=ev-charging-log-hass&category=integration)

1. Click the badge above, or in HACS open the menu → **Custom repositories**,
   add `https://github.com/brianramseyau/ev-charging-log-hass` with type
   **Integration**.
2. Install **EV Charging Log companion** and restart Home Assistant.
3. In EV Charging Log, open **Settings → Car odometer (Home Assistant)**, enter
   your Home Assistant URL and tap **Generate secret**. Copy the secret.
4. In Home Assistant, go to **Settings → Devices & services → Add integration →
   EV Charging Log companion**. Pick the odometer and telemetry sensors and paste
   the secret.
5. Back in the app, tap **Test**.

To **rotate the secret**, tap **Rotate secret** in the app, then paste the new
one under **Devices & services → EV Charging Log companion → Configure**. The old
secret stops working as soon as you save. Leave the field blank there to change
only the entities.

## Security notes

- The endpoint is reachable wherever Home Assistant is, including through Home
  Assistant Cloud. The secret (256 random bits) is what protects it.
- Failed requests are **not** fed into Home Assistant's IP ban. Behind Home
  Assistant Cloud or a reverse proxy, every request can appear to come from one
  address, and a stale secret in the app would otherwise get that address banned
  and lock you out of Home Assistant entirely. Guessing a 256-bit secret isn't a
  realistic attack, so rate-limiting adds nothing.
- Only the SHA-256 hash of the secret is stored, in the config entry.

## HTTP contract

This is the only coupling between this repository and the app. A breaking change
bumps `version`, and the app shows "update the companion" rather than misreading
the response.

```http
GET /api/ev_charging_log/odometer?start=2026-09-21T00:00:00Z&end=2026-09-24T09:00:00Z
Authorization: Bearer <secret>
```

```json
{
  "version": 1,
  "odometer": {
    "unit": "km",
    "changes": [
      { "state": "118102", "at": "2026-09-21T00:00:00+00:00" },
      { "state": "118204", "at": "2026-09-23T08:41:10+00:00" }
    ]
  },
  "telemetry": {
    "changes": [
      { "state": "2026-09-20T22:59:31+00:00", "at": "2026-09-21T00:00:00+00:00" },
      { "state": "2026-09-23T08:40:52+00:00", "at": "2026-09-23T08:41:10+00:00" }
    ]
  },
  "oldestRecorded": "2026-09-14T03:00:00+00:00"
}
```

- `start` and `end` are optional ISO 8601 instants **with a timezone**. `end`
  defaults to now and `start` to `end`, which returns just the current state.
  `start` must not be after `end`, and the window is limited to 31 days. Anything
  else is a `400`.
- The first entry in each `changes` list is the state in effect at `start`, with
  `at` clamped to `start`. Changes after `end` are never included.
- `state` is passed through verbatim, including `unavailable` and `unknown`. The
  app decides what's usable.
- `unit` is the odometer entity's current `unit_of_measurement`.
- `oldestRecorded` is where the recorder's history begins.
- Every response sets `Cache-Control: no-store`. A wrong or missing secret gets
  an empty `401`. With no configured entry, the response is `404`.
- Any other query parameter (such as `entity_id`) is ignored.

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Tests use
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
and run against a real recorder.

## Licence

MIT

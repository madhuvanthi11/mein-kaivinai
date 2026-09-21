# Data sources and honesty rules

## What comes from where

| Layer | Source | Nature |
|---|---|---|
| Current + hourly weather | Open-Meteo Forecast API | Live |
| Location search | Open-Meteo Geocoding API | Live |
| Map tiles | OpenStreetMap | Live |
| Risk score | Deterministic rule set (`risk.py`) | Transparent model |
| Peak window | Computed from the live hourly series | Derived |
| Ward heat-island offset | Land-cover model (`local_context.py`) | Model |
| Ward land-cover profiles | Indicative reference values | Prototype data |
| Historical baselines | ERA5 — not configured | Absent |

Open-Meteo's free non-commercial tier needs no API key and no account.

## Variables requested

Both `current` and `hourly`, with `timezone=auto`, 7 forecast days and 24 past
hours:

```
temperature_2m          relative_humidity_2m    dew_point_2m
apparent_temperature    wind_speed_10m          wind_direction_10m
wind_gusts_10m          surface_pressure        precipitation
cloud_cover             shortwave_radiation
```

Model selection is left to Open-Meteo's default best-model behaviour.

## Rules the code enforces

**No fabricated weather, ever.** `open_meteo.py` either returns values that came
out of the response or raises `WeatherUnavailable`. There is no default, no
fallback constant, no stale-cache-forever mode. On failure the UI shows *"Live
weather data is temporarily unavailable. Please retry."* and displays nothing.
`test_open_meteo_outage_returns_503_and_no_weather` asserts the failure response
contains no temperature field at all.

**No fake confidence.** Reported as `"Rule-based assessment"`. No percentage.

**No invented rankings.** Wards are ranked by computed score using dense ranking,
so equal scores share a rank and are flagged `tied` rather than being separated by
fabricated precision.

**No claimed deliveries.** `MockSMSProvider` always returns
`status: not_configured`, `delivered: false`, and the text *"No SMS was sent."*
It exists so the UI has a provider to display, not so a demo can look like it
sent messages. `FCMProvider` behaves the same way when credentials are absent —
and also when they are present but the integration is not implemented, which is
the honest answer in this prototype.

**No official-warning claims.** Nothing is attributed to IMD. The map is labelled
*"Weather-derived ward risk points. Not official government warnings."* Officer
guidance is labelled *"AI-generated decision-support recommendations. Not
official orders."* `test_no_imd_or_official_warning_claims` scans response bodies
for both strings.

**No raw weather in Firestore.** Saved places store a label and coordinates.
Weather is fetched live on every request and would be stale the moment it was
written.

## Caching

~10 minutes per rounded coordinate. Concurrent callers for the same ward wait on
a single in-flight request rather than each firing their own, which matters when
the control room fetches 16 wards at once. A full city refresh is 10–16 upstream
calls, well inside Open-Meteo's free-tier limits.

## Place names (reverse geocoding)

Open-Meteo geocodes a name to coordinates but does not go the other way, so the
"use my location" flow resolves coordinates to a place name through
**OpenStreetMap Nominatim**.

- Endpoint: `GET /api/reverse-geocode?lat=&lon=`, proxied through FastAPI like
  everything else, cached for an hour per point.
- The most specific named place OSM holds is used — neighbourhood, suburb,
  village, town, then city — with the wider city and state appended for context.
- Nominatim's usage policy asks for an identifying `User-Agent` and no more than
  one request per second. Both are honoured in `services/open_meteo.py`; the
  rate limit is serialised rather than hoped for.
- Licence: place names © OpenStreetMap contributors, ODbL. The attribution is
  returned with every lookup and rendered in the app footer.
- **If OSM has no name for the point, the endpoint returns 404 and the app shows
  the coordinates.** No locality is ever guessed from a nearby one.

For production traffic, run your own Nominatim instance and point
`NOMINATIM_URL` at it. The public server is not intended to carry an app's load.

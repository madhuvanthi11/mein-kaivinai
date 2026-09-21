# Thermal metrics, Human Thermal Stress and Heat-Health Impact Risk

```
Open-Meteo weather ─► estimated radiant environment ─► UTCI / est. WBGT / Heat Index
   ─► Human Thermal Stress (0-100) ─► persistence + night-time heat
   ─► Heat-Health Impact Risk (0-100) ─► 5-day forecast ─► government action / citizen advisory
```

Code: `backend/app/services/`

| File | Role |
|---|---|
| `thermal_config.py` | **Every** threshold, anchor and weight. Nothing is hard-coded elsewhere. `GET /api/thermal/methodology` exposes it. |
| `thermal_metrics.py` | Radiant environment, UTCI, WBGT, Heat Index, Human Thermal Stress. |
| `thermal_forecast.py` | Hourly series, persistence, night heat, the 5 forecast days. |
| `impact.py` | Heat-Health Impact Risk. |
| `assessment.py` | One cached calculation shared by every endpoint. |
| `vulnerability.py`, `health_outcomes.py`, `historical.py` | Provider interfaces that report **unavailable** until real data exists. |

## What is estimated
Open-Meteo has no mean radiant temperature or globe temperature. They are estimated for a standing person
on an open, unshaded site from direct-normal, diffuse and global radiation (see the module docstring in
`thermal_metrics.py`). Long-wave exchange is assumed at air temperature. Wet-bulb is psychrometric (Stull),
not natural wet-bulb. Consequently UTCI and WBGT are *modelled/estimated*, never *measured*, and are
probably higher than a shaded person would experience.

## Human Thermal Stress
Weighted **mean** (UTCI 0.60, WBGT 0.25, Heat Index 0.15, renormalised over metrics available that hour) of
each metric mapped to 0-100 through published category boundaries (Bröde 2012 for UTCI, NWS for Heat Index,
US Army/ACSM flags for WBGT). A mean cannot exceed its largest input, so correlated metrics are not double
counted. Persistence and night heat are *not* part of it.

## Impact risk
`0.60 * thermal stress + 0.25 * persistence + 0.15 * night heat` (weights renormalised if a part is missing).
Vulnerability/exposure indices, when a provider supplies them, scale the result; today they are reported as
`"vulnerability_data": "unavailable"`. This is not a mortality or hospitalisation probability.

## Values that are provisional
Tagged `PROVISIONAL` in `thermal_config.py` (HTS weights, impact weights, persistence caps, night window,
ground albedo, recommendation trigger points). They are operational choices, not published standards.

## Plugging in ERA5 later
Implement `HistoricalWeatherProvider.baseline()` (and the abstract methods) in `historical.py::ERA5Provider`,
returning `{"status": "available", "source": "ERA5", ...}`. `get_historical_baseline()`, `/api/historical/baseline`
and the `historical` block of every summary pick it up. `thermal_metrics.py`, the forecast engine, the impact
engine, recommendations and both dashboards need no change.

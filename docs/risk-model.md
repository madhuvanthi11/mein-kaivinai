# The heat-risk engine

A published rule set. Not a trained model, and the application never claims
otherwise. Every point in the score traces to a weather value Open-Meteo
returned, or to the ward adjustment described in `hyperlocal.md`.

Source: `backend/app/services/risk.py`.

## Score composition

| Term | Max points | Why it is in the score |
|---|---|---|
| Apparent temperature | 55 | What the body actually experiences; the dominant term |
| Air temperature | 10 | Dry-bulb contribution independent of humidity and wind |
| Solar radiation | 10 | Direct sun load on someone outdoors |
| Humidity | 10 | Suppressed sweat evaporation; only applied when air temp ≥ 28 °C |
| Persistence | 10 | Heat that has already run for hours is more harmful than a fresh spike |
| Daytime | 5 | 10:00–17:00, when people are out working |
| Wind relief | −8 | Moving air carries heat away; only applied when it feels ≥ 32 °C |

Each term is a clamped linear ramp. Apparent temperature, for example, ramps from
0 at 27 °C to full weight at 50 °C. The total is clamped to 0–100.

## Levels

```
  0–24   Low
 25–44   Moderate
 45–64   High
 65–79   Very High
 80–100  Extreme
```

The default alert threshold is 65 — the start of Very High. It is configurable
per request in the control room.

## Drivers

Any term contributing 5 points or more is reported as a driver, top three first,
so the UI can say *"driven by high feels-like temperature and high humidity"*
rather than showing a bare number. Wind relief is reported separately when it
removes 3 or more points.

The ward heat-island contribution is surfaced as its own driver in degrees rather
than points, so the interface can say *"this ward runs 2.4 °C hotter than the
surrounding area"* instead of burying it inside the apparent-temperature term.

## Confidence

Reported as the string `"Rule-based assessment"`.

There is no statistically derived confidence interval here, so inventing a
percentage would be dishonest. A test asserts the field never contains `%`.

## Peak window

Computed from the actual hourly series, never hardcoded.

1. Find the highest-scoring hour in the next 24.
2. Extend backwards and forwards while neighbouring hours stay within 15% of
   that peak.
3. Report `peak_start`, `peak_end` (exclusive) and `peak_score`.

The window follows the data. A test moves the synthetic heat bulge to the evening
and asserts the reported window moves to 18:00–22:00.

## What this engine does not do

- It is not calibrated against local heat-morbidity records. Thresholds are
  reasoned from established heat-stress guidance, not derived from Tamil Nadu
  hospital admissions.
- It does not model individual vulnerability — age, health, occupation, access to
  cooling. Guidance mentions vulnerable groups but the score does not weight them.
- It does not use humidity below 28 °C, where its effect on heat stress is
  negligible and including it would add noise.

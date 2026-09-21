# The ward layer

## The problem

Open-Meteo resolves weather at roughly 1–11 km depending on the model. Wards
inside one city are often 2–5 km apart, so two of them frequently fall in the
same grid cell and return **identical** weather.

Feeding ward coordinates into a weather API therefore does not produce a
hyperlocal product. It produces the same city forecast repeated 16 times.

The difference between wards is real and well documented — it is the urban heat
island — but it is not in the forecast, so it has to be modelled.

## The approach

```
adjusted_apparent_temperature = open_meteo_apparent_temperature + uhi_offset
```

Source: `backend/app/services/local_context.py`.

### Land-cover terms, in °C at full intensity

| Term | Weight | Mechanism |
|---|---|---|
| Built-up surface | +2.40 | Concrete and asphalt store daytime heat, re-radiate it |
| Industrial | +0.90 | Waste heat from plant, foundries, heavy traffic corridors |
| Density | +0.70 | Close buildings trap heat and block sky-view cooling |
| Vegetation | −1.90 | Shade plus evapotranspiration |
| Water | −1.10 | High thermal mass, sea and lake breeze |

### Modifiers

- **Ventilation** — wind flushes trapped heat out of a ward. The offset scales
  from full at 0 km/h down to 45% at 60 km/h.
- **Diurnal** — the island is *weakest* at midday (×0.75) and *strongest* a few
  hours after sunset (×1.25), when built surfaces release stored heat while open
  land has already cooled. This is the opposite of most people's intuition and is
  the main reason night-time heat is so dangerous in dense wards.
- **Wetness** — cloud cover reduces the offset by up to 25%; measurable rain
  multiplies it by 0.7.

The result is clamped to −2.5 … +4.0 °C, the range reported for Indian tier-1 and
tier-2 cities.

### Measured spread, Chennai at 15:00, light wind

```
T. Nagar          +2.17 °C
Meenakshi Temple  +2.11 °C     (Madurai, shown for comparison)
BHEL Township     +0.78 °C     (Tiruchirappalli)
Uthangudi         +0.52 °C     (Madurai)
Adyar             +0.35 °C
```

## Constraints the model respects

**Only apparent temperature is shifted.** Air temperature, humidity, wind,
pressure, radiation and precipitation stay exactly as Open-Meteo reported them.
The model has no basis for altering those, so it does not pretend to.
`test_adjustment_only_touches_apparent_temperature` asserts this.

**Coefficients are published, not hidden.** They sit in the module with their
reasoning so a jury or a reviewer can audit them.

**It is labelled as a model everywhere it surfaces.** The citizen dashboard shows
*"Open-Meteo forecasts at roughly 1–11 km. This adjustment estimates the
difference between wards from their land cover. It is a model, not a
measurement."*

## The land-cover profiles

Each ward carries five values on a 0–1 scale, in `backend/app/data/wards.py`:

```
built_up    0 = open land/farmland        1 = continuous concrete and asphalt
green       0 = no vegetation             1 = dense canopy / park / forest
water       0 = no water body near        1 = directly on sea front or large lake
industrial  0 = purely residential        1 = heavy industry / foundry / port yard
density     0 = sparse peri-urban         1 = very high residential crowding
```

These are **indicative prototype values** compiled from OpenStreetMap land use,
city master plans and visual survey of satellite imagery. They are not
measurements. They are the only part of the system that is not live data, and
they should be reviewed by someone with local knowledge before any deployment.

## Replacing them with real data

Implement `LandCoverProvider`:

```python
class LandCoverProvider(ABC):
    def available(self) -> bool: ...
    def profile(self, ward: Ward) -> dict: ...
    @property
    def attribution(self) -> str: ...
```

Register it with `set_provider(...)`. If it reports itself unavailable the
registry falls back to the static profiles rather than breaking — there is a test
for that. Candidate sources: Bhuvan LULC, Sentinel-2 NDVI for vegetation,
Landsat 8/9 thermal bands for land-surface temperature.

`SatelliteLandCoverProvider` is stubbed and deliberately reports itself
unavailable, so nothing can silently substitute values it does not have.

## Ward coverage

54 wards: Chennai 16, Madurai 16, Coimbatore 12, Tiruchirappalli 10.

A searched point within 6 km of a ward centroid resolves to that ward
(`WARD_MATCH_RADIUS_KM`). Anything further falls back to the plain area forecast,
labelled *"Area reading"* in the UI with an explanation, and the local-context
panel reports that the adjustment does not apply.

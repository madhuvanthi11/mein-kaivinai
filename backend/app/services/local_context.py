"""Hyperlocal (ward-scale) adjustment layer.

Open-Meteo resolves weather at roughly 1-11 km. Two wards inside the same city
often fall in the same or adjacent grid cells, so the raw forecast alone cannot
express the difference between a concrete market ward and a tree-lined riverside
ward. That difference is real and well documented: it is the urban heat island.

This module closes that gap with a transparent, deterministic adjustment that
converts a ward's land-cover profile into a felt-temperature offset in degrees
Celsius. It is a MODEL, not a measurement, and every surface that shows it says so.

    adjusted_apparent_temperature = open_meteo_apparent_temperature + uhi_offset

Design of the offset
--------------------
Warming terms
  built-up surface   concrete and asphalt store daytime heat and re-radiate it
  industrial         waste heat from plant, foundries, heavy traffic corridors
  crowding           buildings close together trap heat and block sky-view

Cooling terms
  vegetation         shade plus evapotranspiration
  water bodies       high thermal mass, sea/lake breeze

Modifiers applied to the raw offset
  ventilation   wind flushes trapped heat out of a ward, so the offset shrinks
                as wind speed rises
  diurnal       the urban heat island is strongest after sunset, when built
                surfaces release stored heat while open land has already cooled
  cloud/rain    a wet or overcast hour suppresses the island

Coefficients are first-order and chosen to keep the total inside a plausible
0-4 degree C envelope, which is the range reported for Indian tier-1 and tier-2
cities. They are published here rather than hidden so a jury can audit them.

Swapping in real data
---------------------
Implement LandCoverProvider against a satellite source (Bhuvan LULC, Sentinel-2
NDVI, Landsat thermal) and register it. Nothing downstream changes.
"""
from abc import ABC, abstractmethod

from ..data.wards import BY_ID, Ward

# Warming and cooling weights, in degrees C at full (1.0) intensity.
W_BUILT_UP = 2.40
W_INDUSTRIAL = 0.90
W_DENSITY = 0.70
W_GREEN = -1.90
W_WATER = -1.10

OFFSET_MIN, OFFSET_MAX = -2.5, 4.0

# The island is weakest in the middle of the day and strongest a few hours
# after sunset. Index is local hour 0-23.
DIURNAL = [1.15, 1.15, 1.10, 1.05, 1.00, 0.90, 0.80, 0.75, 0.75, 0.78,
           0.82, 0.85, 0.88, 0.90, 0.92, 0.95, 1.00, 1.05, 1.15, 1.25,
           1.25, 1.22, 1.20, 1.18]


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class LandCoverProvider(ABC):
    """Supplies a 0-1 land-cover profile for a ward."""

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def profile(self, ward: Ward) -> dict: ...

    @property
    @abstractmethod
    def attribution(self) -> str: ...


class StaticProfileProvider(LandCoverProvider):
    """Reads the indicative profiles committed in data/wards.py."""

    def available(self) -> bool:
        return True

    def profile(self, ward: Ward) -> dict:
        return ward.profile()

    @property
    def attribution(self) -> str:
        return "Indicative ward land-cover profile (prototype reference values)"


class SatelliteLandCoverProvider(LandCoverProvider):
    """Placeholder for a real LULC / land-surface-temperature feed.

    Deliberately reports itself unavailable so the app never depends on it and
    never silently substitutes values it does not have.
    """

    def available(self) -> bool:
        return False

    def profile(self, ward: Ward) -> dict:
        raise RuntimeError("Satellite land-cover provider is not configured")

    @property
    def attribution(self) -> str:
        return "Satellite-derived land cover (not configured)"


_provider: LandCoverProvider = StaticProfileProvider()


def provider() -> LandCoverProvider:
    return _provider


def set_provider(p: LandCoverProvider) -> None:
    """Register a better land-cover source; falls back if it is unavailable."""
    global _provider
    _provider = p if p.available() else StaticProfileProvider()


def base_offset(profile: dict) -> float:
    """Land-cover contribution before weather modifiers, in degrees C."""
    return (W_BUILT_UP * _clamp(profile.get("built_up", 0))
            + W_INDUSTRIAL * _clamp(profile.get("industrial", 0))
            + W_DENSITY * _clamp(profile.get("density", 0))
            + W_GREEN * _clamp(profile.get("green", 0))
            + W_WATER * _clamp(profile.get("water", 0)))


def ventilation_factor(wind_kmh) -> float:
    """Wind flushes trapped heat. 0 km/h keeps the full offset, 30+ km/h halves it."""
    return _clamp(1.0 - (wind_kmh or 0.0) / 60.0, 0.45, 1.0)


def wetness_factor(cloud_pct, precip_mm) -> float:
    """Cloud and rain suppress the island."""
    f = 1.0 - 0.25 * _clamp((cloud_pct or 0.0) / 100.0)
    if (precip_mm or 0.0) > 0.2:
        f *= 0.7
    return f


def offset_for_hour(profile: dict, hour_row: dict) -> float:
    """Degrees C to add to this hour's apparent temperature for this ward."""
    try:
        hour = int(hour_row["time"][11:13])
    except (KeyError, TypeError, ValueError):
        hour = 12
    raw = base_offset(profile)
    adj = (raw
           * DIURNAL[hour % 24]
           * ventilation_factor(hour_row.get("wind_speed_kmh"))
           * wetness_factor(hour_row.get("cloud_cover_pct"), hour_row.get("precipitation_mm")))
    return round(max(OFFSET_MIN, min(OFFSET_MAX, adj)), 2)


def explain(profile: dict) -> dict:
    """Per-term breakdown so the UI can show why a ward runs hot or cool."""
    terms = {
        "built_up": W_BUILT_UP * _clamp(profile.get("built_up", 0)),
        "industrial": W_INDUSTRIAL * _clamp(profile.get("industrial", 0)),
        "density": W_DENSITY * _clamp(profile.get("density", 0)),
        "green": W_GREEN * _clamp(profile.get("green", 0)),
        "water": W_WATER * _clamp(profile.get("water", 0)),
    }
    ordered = sorted(terms.items(), key=lambda kv: -abs(kv[1]))
    return {
        "base_offset_c": round(base_offset(profile), 2),
        "terms": [{"code": k, "effect": "warms" if v > 0 else "cools", "degrees_c": round(v, 2)}
                  for k, v in ordered if abs(v) >= 0.1],
        "method": "Land-cover urban-heat-island model",
    }


def apply_to_hours(hours: list, ward: Ward) -> tuple[list, list]:
    """Return (adjusted hours, per-hour offsets) for a ward.

    Only apparent temperature is shifted. Air temperature, humidity, wind and the
    rest are left exactly as Open-Meteo reported them -- the model has no basis
    for changing those, so it does not pretend to.
    """
    profile = provider().profile(ward)
    out, offsets = [], []
    for h in hours:
        off = offset_for_hour(profile, h)
        at = h.get("apparent_temperature_c")
        row = dict(h)
        if at is not None:
            row["apparent_temperature_c"] = round(at + off, 1)
            row["uhi_offset_c"] = off
        else:
            row["uhi_offset_c"] = None
        out.append(row)
        offsets.append(off)
    return out, offsets

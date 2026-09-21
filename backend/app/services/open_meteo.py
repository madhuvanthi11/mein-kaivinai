"""Open-Meteo client: fetch, validate, normalize.

Hard rule for this file: it either returns values that came out of the Open-Meteo
response, or it raises. It never invents, defaults, rounds-in a missing number, or
falls back to a cached-forever value to keep the UI looking alive.
"""
import asyncio
import time

import httpx

from .. import config

VARIABLES = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "surface_pressure",
    "precipitation", "cloud_cover", "shortwave_radiation",
]

# Extra HOURLY-only variables used by the thermal-metrics layer. All are documented
# Open-Meteo hourly variables. `current` keeps the smaller list above so a change
# here can never break the live-conditions request. Wet-bulb is not requested: it
# is derived from temperature and humidity (Stull 2011) in thermal_metrics.py.
HOURLY_EXTRA = ["direct_radiation", "diffuse_radiation", "direct_normal_irradiance"]
HOURLY_VARIABLES = VARIABLES + HOURLY_EXTRA

# Open-Meteo field -> our normalized field (unit made explicit in the name).
MAP = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "dew_point_2m": "dew_point_c",
    "apparent_temperature": "apparent_temperature_c",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_direction_deg",
    "wind_gusts_10m": "wind_gust_kmh",
    "surface_pressure": "surface_pressure_hpa",
    "precipitation": "precipitation_mm",
    "cloud_cover": "cloud_cover_pct",
    "shortwave_radiation": "solar_radiation_wm2",
}

EXTRA_MAP = {
    "direct_radiation": "direct_radiation_wm2",
    "diffuse_radiation": "diffuse_radiation_wm2",
    "direct_normal_irradiance": "direct_normal_irradiance_wm2",
}

# Kept for backwards compatibility with existing tests.
CUR = VARIABLES


class WeatherUnavailable(Exception):
    """Open-Meteo could not be reached, or returned something unusable."""


class LocationNotFound(Exception):
    """Geocoding returned no match."""


def normalize(raw: dict, name: str | None = None) -> dict:
    try:
        cur = raw["current"]
        h = raw["hourly"]
        hourly = []
        for i, t in enumerate(h["time"]):
            row = {"time": t}
            for src, dst in MAP.items():
                row[dst] = h[src][i]
            # Optional radiation components: absent -> None (never defaulted), and the
            # thermal layer then reports UTCI/WBGT as unavailable with a reason.
            for src, dst in EXTRA_MAP.items():
                col = h.get(src)
                row[dst] = col[i] if col is not None and i < len(col) else None
            hourly.append(row)
        if not hourly:
            raise WeatherUnavailable("Open-Meteo returned an empty hourly series")
        return {
            "location": {
                "name": name or f"{raw['latitude']:.2f}, {raw['longitude']:.2f}",
                "latitude": raw["latitude"],
                "longitude": raw["longitude"],
                "timezone": raw.get("timezone"),
            },
            "source": "Open-Meteo",
            # Observation time as reported by the API, local to the location.
            "updated_at": cur["time"],
            "current": {dst: cur[src] for src, dst in MAP.items()},
            "hourly": hourly,
        }
    except (KeyError, IndexError, TypeError) as e:
        raise WeatherUnavailable(f"Unexpected Open-Meteo response: {e}")


# Most specific first: the name a person standing there would use.
_PLACE_KEYS = ("neighbourhood", "suburb", "quarter", "residential", "village",
               "hamlet", "town", "city_district", "municipality", "city")
_AREA_KEYS = ("city", "town", "municipality", "county", "state_district", "district")


def _place_from_osm(raw: dict) -> dict | None:
    """Pick the most specific named place OSM returned, with its wider area.

    Every value here comes out of the Nominatim response. Nothing is guessed:
    if OSM has no name for the point, this returns None.
    """
    addr = (raw or {}).get("address") or {}
    name = next((addr[k] for k in _PLACE_KEYS if addr.get(k)), None)
    if not name:
        name = raw.get("name") or None
    if not name:
        return None
    area = next((addr[k] for k in _AREA_KEYS if addr.get(k) and addr[k] != name), None)
    state = addr.get("state")
    return {
        "name": name,
        "area": area,
        "state": state,
        "label": ", ".join([p for p in (name, area, state) if p]),
        "latitude": float(raw.get("lat", 0)) or None,
        "longitude": float(raw.get("lon", 0)) or None,
        "source": "OpenStreetMap Nominatim",
        "attribution": "Place names © OpenStreetMap contributors (ODbL)",
    }


class OpenMeteoService:
    def __init__(self):
        self._cache: dict = {}
        self._reverse_cache: dict = {}
        self._locks: dict = {}
        self._last_reverse: float = 0.0

    async def _get(self, url: str, params: dict) -> dict:
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as c:
                r = await c.get(url, params=params)
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise WeatherUnavailable(str(e))

    def _lock(self, key):
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def forecast(self, lat: float, lon: float, name: str | None = None) -> dict:
        """Cached ~10 min per coordinate. Concurrent callers for the same ward
        wait on one request instead of each firing their own."""
        key = (round(lat, 3), round(lon, 3))
        async with self._lock(key):
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < config.CACHE_TTL_SECONDS:
                data = hit[1]
            else:
                raw = await self._get(config.OPEN_METEO_URL, {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": "auto",
                    "current": ",".join(VARIABLES),
                    "hourly": ",".join(HOURLY_VARIABLES),
                    "forecast_days": config.FORECAST_DAYS,
                    "past_hours": config.PAST_HOURS,
                    "wind_speed_unit": "kmh",
                })
                data = normalize(raw)
                self._cache[key] = (time.time(), data)
        out = dict(data)
        out["hourly"] = list(data["hourly"])
        out["current"] = dict(data["current"])
        out["location"] = {**data["location"], **({"name": name} if name else {})}
        return out

    async def geocode(self, query: str, count: int = 8) -> list:
        raw = await self._get(config.GEOCODE_URL, {
            "name": query, "count": count, "language": "en", "format": "json",
        })
        results = raw.get("results") or []
        if not results:
            raise LocationNotFound(query)
        return [{
            "name": r.get("name"),
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "country": r.get("country"),
            "admin1": r.get("admin1"),
            "timezone": r.get("timezone"),
        } for r in results]

    async def reverse_geocode(self, lat: float, lon: float) -> dict:
        """Coordinates -> a human place name, from OpenStreetMap's Nominatim.

        Returns the most specific named place OSM has for the point. If OSM has
        no name for it, this raises rather than inventing one -- the caller then
        shows the coordinates, which is the truth.
        """
        key = (round(lat, 4), round(lon, 4))
        async with self._lock(("rev",) + key):
            hit = self._reverse_cache.get(key)
            if hit and time.time() - hit[0] < config.CACHE_TTL_SECONDS * 6:
                return hit[1]

            # Nominatim's usage policy asks for no more than one request a
            # second from a single client. Serialised here rather than hoped for.
            gap = time.time() - self._last_reverse
            if gap < config.REVERSE_GEOCODE_MIN_INTERVAL:
                await asyncio.sleep(config.REVERSE_GEOCODE_MIN_INTERVAL - gap)
            self._last_reverse = time.time()

            try:
                async with httpx.AsyncClient(
                        timeout=config.HTTP_TIMEOUT,
                        headers={"User-Agent": config.NOMINATIM_USER_AGENT,
                                 "Accept-Language": "en"}) as c:
                    r = await c.get(config.NOMINATIM_URL, params={
                        "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14,
                        "addressdetails": 1,
                    })
                    r.raise_for_status()
                    raw = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise WeatherUnavailable(f"Reverse geocoding unavailable: {e}")

            place = _place_from_osm(raw)
            if place is None:
                raise LocationNotFound(f"{lat},{lon}")
            self._reverse_cache[key] = (time.time(), place)
            return place

    def cache_stats(self) -> dict:
        now = time.time()
        fresh = sum(1 for ts, _ in self._cache.values() if now - ts < config.CACHE_TTL_SECONDS)
        return {"entries": len(self._cache), "fresh": fresh, "ttl_seconds": config.CACHE_TTL_SECONDS}


service = OpenMeteoService()

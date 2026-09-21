"""Open-Meteo request shape, parsing and failure behaviour."""
import pytest

from app import config
from app.services.open_meteo import (HOURLY_VARIABLES, MAP, VARIABLES, LocationNotFound,
                                     WeatherUnavailable, normalize, service)


def test_all_required_variables_requested():
    required = {"temperature_2m", "relative_humidity_2m", "dew_point_2m", "apparent_temperature",
                "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "surface_pressure",
                "precipitation", "cloud_cover", "shortwave_radiation"}
    assert required == set(VARIABLES)


def test_parsing_produces_normalized_object(payload):
    w = normalize(payload())
    assert w["source"] == "Open-Meteo"
    assert len(w["hourly"]) == 48
    assert set(MAP.values()) <= set(w["current"])
    assert set(MAP.values()) <= set(w["hourly"][0])
    assert w["updated_at"] == "2026-09-21T11:00"
    assert w["location"]["timezone"] == "Asia/Kolkata"


def test_values_come_from_the_response_not_invented(payload):
    p = payload(base_t=33.0)
    w = normalize(p)
    assert w["current"]["temperature_c"] == p["current"]["temperature_2m"]
    assert w["hourly"][5]["wind_gust_kmh"] == p["hourly"]["wind_gusts_10m"][5]


def test_malformed_response_raises_rather_than_defaulting():
    with pytest.raises(WeatherUnavailable):
        normalize({"foo": 1})
    with pytest.raises(WeatherUnavailable):
        normalize({"latitude": 1, "longitude": 1, "current": {}, "hourly": {}})


@pytest.mark.asyncio
async def test_request_params_are_correct(monkeypatch, payload):
    seen = {}

    async def spy(url, params):
        seen.update(params)
        return payload()

    monkeypatch.setattr(service, "_get", spy)
    service._cache.clear()
    await service.forecast(9.92, 78.12)
    assert seen["timezone"] == "auto"
    assert seen["forecast_days"] >= 7
    assert seen["past_hours"] >= 1
    assert seen["wind_speed_unit"] == "kmh"
    assert set(seen["current"].split(",")) == set(VARIABLES)
    assert set(seen["hourly"].split(",")) == set(HOURLY_VARIABLES)


@pytest.mark.asyncio
async def test_cache_reuses_one_call_per_location(monkeypatch, payload):
    calls = []

    async def counting(url, params):
        calls.append(params["latitude"])
        return payload(lat=params["latitude"])

    monkeypatch.setattr(service, "_get", counting)
    service._cache.clear()
    await service.forecast(9.92, 78.12)
    await service.forecast(9.92, 78.12)
    await service.forecast(13.08, 80.27)
    assert len(calls) == 2, "second identical request should be served from cache"
    assert service.cache_stats()["ttl_seconds"] == config.CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_geocode_no_match_raises(monkeypatch):
    async def empty(url, params):
        return {}

    monkeypatch.setattr(service, "_get", empty)
    with pytest.raises(LocationNotFound):
        await service.geocode("zzzzzz")

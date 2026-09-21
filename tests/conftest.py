"""Shared fixtures.

Everything here is a synthetic Open-Meteo-SHAPED payload used to exercise parsing
and scoring offline. It is never served to the UI and never reaches production
code paths -- the only way a value reaches the dashboard is through a real HTTP
call to Open-Meteo.
"""
import os
import sys
import tempfile

import pytest

# Set before the app is imported: config reads these at import time.
# DEV_AUTH lets the suite exercise the role workflow without a live Firebase
# project. It is insecure by design and /api/status says so.
os.environ["DEV_AUTH"] = "1"
os.environ.setdefault("STORE_PATH", os.path.join(tempfile.mkdtemp(), "store.json"))
os.environ.setdefault(
    "ROLE_REGISTRY_PATH", os.path.join(tempfile.mkdtemp(), "role_registry.json"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.open_meteo import HOURLY_VARIABLES, VARIABLES  # noqa: E402


def raw_payload(base_t=30.0, lat=13.08, lon=80.27, wind=5.0, humidity=70.0, day="2026-09-21",
                days=2):
    """An hourly series (default two days) with a realistic midday bulge."""
    from datetime import date, timedelta
    d0 = date.fromisoformat(day)
    times = [f"{(d0 + timedelta(days=d)).isoformat()}T{h:02d}:00" for d in range(days) for h in range(24)]
    n = len(times)

    def series(k):
        if k == "temperature_2m":
            return [base_t + (8 if 10 <= i % 24 <= 16 else 0) for i in range(n)]
        if k == "apparent_temperature":
            return [base_t + 4 + (10 if 10 <= i % 24 <= 16 else 0) for i in range(n)]
        if k == "shortwave_radiation":
            return [800 if 10 <= i % 24 <= 16 else 0 for i in range(n)]
        if k == "direct_radiation":
            return [600 if 10 <= i % 24 <= 16 else 0 for i in range(n)]
        if k == "diffuse_radiation":
            return [150 if 10 <= i % 24 <= 16 else 0 for i in range(n)]
        if k == "direct_normal_irradiance":
            return [800 if 10 <= i % 24 <= 16 else 0 for i in range(n)]
        if k == "relative_humidity_2m":
            return [humidity] * n
        if k == "wind_direction_10m":
            return [90] * n
        if k == "wind_speed_10m":
            return [wind] * n
        if k == "cloud_cover":
            return [20] * n
        if k == "precipitation":
            return [0.0] * n
        return [5] * n

    hourly = {"time": times, **{k: series(k) for k in HOURLY_VARIABLES}}
    current = {"time": f"{day}T11:00", **{k: hourly[k][11] for k in VARIABLES}}
    return {"latitude": lat, "longitude": lon, "timezone": "Asia/Kolkata",
            "current": current, "hourly": hourly}


@pytest.fixture
def payload():
    return raw_payload


@pytest.fixture
def client(monkeypatch):
    """TestClient with Open-Meteo replaced by the synthetic payload.

    Temperature varies with latitude so location switching is observable.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.open_meteo import service

    async def fake_get(url, params):
        if "geocoding" in url:
            if params["name"].lower().startswith("zzz"):
                return {}
            return {"results": [{"name": params["name"], "latitude": 9.92, "longitude": 78.12,
                                 "country": "India", "admin1": "Tamil Nadu",
                                 "timezone": "Asia/Kolkata"}]}
        lat = params["latitude"]
        return raw_payload(base_t=24.0 if lat > 11 else 37.0, lat=lat, lon=params["longitude"])

    monkeypatch.setattr(service, "_get", fake_get)
    service._cache.clear()
    return TestClient(app)


@pytest.fixture
def client7(monkeypatch):
    """Like `client`, but with a 7-day series so the 5-day forecast can be exercised."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.open_meteo import service
    from app.services import assessment

    async def fake_get(url, params):
        lat = params["latitude"]
        return raw_payload(base_t=24.0 if lat > 11 else 33.0, lat=lat, lon=params["longitude"], days=7)

    monkeypatch.setattr(service, "_get", fake_get)
    service._cache.clear()
    assessment._cache.clear()
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_store():
    """Workflow state must not leak between tests."""
    from app.services.store import repo
    repo.clear()
    yield
    repo.clear()


def as_role(uid, role, jurisdiction="all"):
    """Header for the dev authenticator. Real deployments use Firebase tokens."""
    return {"X-Dev-User": f"{uid}|{role}|{jurisdiction}"}


@pytest.fixture
def roles():
    return as_role

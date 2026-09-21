"""End-to-end API behaviour: contracts, location switching, failures, honesty."""
import pytest

from app.services import risk
from app.services.open_meteo import WeatherUnavailable, service


# ----------------------------------------------------------------- basics
def test_health_and_status(client):
    assert client.get("/health").json()["ok"] is True
    s = client.get("/api/status").json()
    assert s["weather_source"] == "Open-Meteo"
    assert s["weather_requires_key"] is False
    assert "not a trained ML model" in s["risk_engine"]
    assert s["ward_count"] > 40


def test_app_starts_without_era5_or_firebase(client):
    s = client.get("/api/status").json()
    assert s["historical"]["available"] is False
    assert s["firebase_configured"] is False
    # The weather path must still work with both switched off.
    assert client.get("/api/weather/summary?lat=13.08&lon=80.27").status_code == 200


# ----------------------------------------------------------------- weather
def test_current_returns_every_normalized_field(client):
    c = client.get("/api/weather/current?lat=13.08&lon=80.27").json()
    for k in ("temperature_c", "relative_humidity_pct", "dew_point_c", "apparent_temperature_c",
              "wind_speed_kmh", "wind_direction_deg", "wind_gust_kmh", "surface_pressure_hpa",
              "precipitation_mm", "cloud_cover_pct", "solar_radiation_wm2"):
        assert k in c["current"], k
    assert c["source"] == "Open-Meteo"
    assert c["updated_at"]


def test_hourly_covers_the_forecast_horizon(client):
    h = client.get("/api/weather/hourly?lat=13.08&lon=80.27").json()["hourly"]
    assert len(h) >= 24
    assert all("time" in r for r in h)


def test_summary_carries_source_and_disclaimer(client):
    s = client.get("/api/weather/summary?lat=13.08&lon=80.27").json()
    assert s["source"] == "Open-Meteo"
    assert s["disclaimer"] == "Risk assessment generated from current/forecast weather data."
    assert s["risk"]["confidence"] == "Rule-based assessment"
    assert s["recommendations"]


# ----------------------------------------------------------------- hyperlocal
def test_summary_inside_a_city_resolves_to_a_ward(client):
    s = client.get("/api/weather/summary?lat=9.9195&lon=78.1193&name=Madurai").json()
    assert s["resolution"] == "ward"
    assert s["ward"]["city"] == "Madurai"
    assert s["local_context"]["current_offset_c"] is not None


def test_summary_outside_pilot_cities_still_works(client):
    s = client.get("/api/weather/summary?lat=28.6139&lon=77.2090&name=Delhi").json()
    assert s["resolution"] == "area"
    assert s["ward"] is None
    assert s["risk"]["score"] is not None
    assert s["local_context"]["current_offset_c"] is None


def test_ward_registry_has_no_weather_in_it(client):
    body = client.get("/api/wards").json()
    assert body["cities"]
    blob = repr(body)
    for forbidden in ("temperature_c", "apparent_temperature", "risk", "score"):
        assert forbidden not in blob, "the static registry must not carry weather values"


def test_ward_endpoint_returns_hyperlocal_view(client):
    w = client.get("/api/wards/che-t-nagar").json()
    assert w["ward"]["name"] == "T. Nagar"
    assert w["current"]["apparent_temperature_baseline_c"] is not None
    assert w["current"]["apparent_temperature_c"] != w["current"]["apparent_temperature_baseline_c"]
    assert w["local_context"]["attribution"]
    assert w["hourly"]


def test_two_wards_in_one_city_differ(client):
    dense = client.get("/api/wards/che-t-nagar").json()
    green = client.get("/api/wards/che-adyar").json()
    assert dense["current"]["apparent_temperature_c"] > green["current"]["apparent_temperature_c"]
    assert dense["risk"]["score"] >= green["risk"]["score"]


def test_unknown_ward_is_404(client):
    assert client.get("/api/wards/not-a-ward").status_code == 404


def test_nearest_ward_endpoint(client):
    inside = client.get("/api/wards/nearest?lat=9.9195&lon=78.1193").json()
    assert inside["ward"]["city"] == "Madurai"
    outside = client.get("/api/wards/nearest?lat=28.61&lon=77.21").json()
    assert outside["ward"] is None


# ----------------------------------------------------------------- monitoring
def test_city_monitoring_is_ward_level_and_ranked(client):
    m = client.get("/api/monitor/city?city=Madurai").json()
    assert m["resolution"] == "ward"
    assert len(m["points"]) >= 10
    scores = [p["risk"]["score"] for p in m["points"]]
    assert scores == sorted(scores, reverse=True)
    assert all("id" in p["ward"] for p in m["points"])
    assert "not official government warnings" in m["label"].lower()


def test_monitoring_reports_the_intra_city_spread(client):
    m = client.get("/api/monitor/city?city=Chennai").json()
    s = m["spread"]
    assert s["hottest_ward"] != s["coolest_ward"]
    assert s["feels_like_spread_c"] > 0, "the whole point is that wards differ"


def test_unknown_city_is_404(client):
    assert client.get("/api/monitor/city?city=Atlantis").status_code == 404


def test_government_recommendations_are_labelled(client):
    m = client.get("/api/monitor/city?city=Chennai").json()
    assert m["recommendations_label"] == "AI-generated decision-support recommendations"
    assert m["recommendations"]


# ----------------------------------------------------------------- switching
def test_location_switch_changes_weather_risk_and_chart(client):
    chennai = client.get("/api/weather/summary?lat=13.0827&lon=80.2707").json()
    madurai = client.get("/api/weather/summary?lat=9.9252&lon=78.1198").json()
    assert chennai["current"]["temperature_c"] != madurai["current"]["temperature_c"]
    assert chennai["risk"]["score"] != madurai["risk"]["score"]
    assert [h["temperature_c"] for h in chennai["hourly"]] != \
           [h["temperature_c"] for h in madurai["hourly"]]
    assert chennai["ward"]["city"] != madurai["ward"]["city"]


def test_geocode_drives_the_switch(client):
    r = client.get("/api/geocode?query=Madurai").json()["results"][0]
    s = client.get(f"/api/weather/summary?lat={r['latitude']}&lon={r['longitude']}").json()
    assert s["ward"]["city"] == "Madurai"


# ----------------------------------------------------------------- failures
def test_geocode_not_found(client):
    r = client.get("/api/geocode?query=zzzzzzz")
    assert r.status_code == 404
    assert r.json()["detail"] == "Location not found."


def test_open_meteo_outage_returns_503_and_no_weather(monkeypatch, client):
    async def boom(url, params):
        raise WeatherUnavailable("network down")

    monkeypatch.setattr(service, "_get", boom)
    service._cache.clear()
    for path in ("/api/weather/summary?lat=1&lon=1", "/api/weather/current?lat=1&lon=1",
                 "/api/risk/current?lat=1&lon=1", "/api/wards/che-t-nagar",
                 "/api/monitor/city?city=Madurai"):
        r = client.get(path)
        assert r.status_code == 503, path
        body = r.json()
        assert "temporarily unavailable" in body["detail"].lower()
        assert "temperature" not in repr(body).lower(), "no fabricated weather on failure"


def test_timeout_is_converted_to_a_clean_unavailable(monkeypatch):
    """A real httpx timeout must surface as the user-facing 503, not a 500 traceback.

    Uses an unpatched client so the genuine httpx -> WeatherUnavailable -> 503
    conversion chain in open_meteo.py is what gets exercised.
    """
    import httpx
    from fastapi.testclient import TestClient
    from app.main import app

    async def slow(self, url, params=None, **kw):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "get", slow)
    service._cache.clear()
    r = TestClient(app).get("/api/weather/summary?lat=1&lon=1")
    assert r.status_code == 503
    assert "temporarily unavailable" in r.json()["detail"].lower()


# ----------------------------------------------------------------- alerts
def test_broadcast_never_claims_an_sms_was_sent(client):
    d = client.post("/api/alerts/broadcast", json={
        "ward": "T. Nagar", "city": "Chennai", "level": "High",
        "message": "test"}).json()["delivery"]
    sms = next(x for x in d if x["provider"] == "sms")
    assert sms["status"] == "not_configured"
    assert sms["delivered"] is False
    assert "no sms was sent" in sms["detail"].lower()


def test_fcm_reports_not_configured_rather_than_sent(client):
    d = client.post("/api/alerts/broadcast", json={"level": "High", "message": "t"}).json()["delivery"]
    fcm = next(x for x in d if x["provider"] == "fcm")
    assert fcm["status"] != "sent" and fcm["delivered"] is False


def test_ward_alert_is_built_from_live_assessment(client):
    r = client.post("/api/alerts/ward/che-t-nagar").json()
    a = r["alert"]
    assert a["ward"] == "T. Nagar" and a["city"] == "Chennai"
    assert isinstance(a["score"], int)
    assert a["threshold"] == risk.ALERT_AT
    assert "T. Nagar" in a["message"]
    assert r["crossed_threshold"] in (True, False)


def test_alert_for_unknown_ward_is_404(client):
    assert client.post("/api/alerts/ward/nope").status_code == 404


# ----------------------------------------------------------------- honesty
def test_no_imd_or_official_warning_claims(client):
    for path in ("/api/weather/summary?lat=13.08&lon=80.27", "/api/monitor/city?city=Chennai",
                 "/api/wards/che-t-nagar", "/api/status"):
        blob = repr(client.get(path).json()).lower()
        assert "imd" not in blob
        assert "official warning" not in blob


@pytest.mark.parametrize("bad", [
    "/api/weather/current?lat=999&lon=0",
    "/api/weather/current?lat=0&lon=999",
    "/api/geocode?query=a",
])
def test_input_validation(client, bad):
    assert client.get(bad).status_code == 422


# ----------------------------------------------------------------- reverse geocoding
def _fake_nominatim(monkeypatch, payload):
    """Replace the Nominatim HTTP call, keeping the parsing under test."""
    from app.services import open_meteo as om

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            return _Resp(payload)

    monkeypatch.setattr(om.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(om.config, "REVERSE_GEOCODE_MIN_INTERVAL", 0.0)
    om.service._reverse_cache.clear()


def test_reverse_geocode_returns_the_most_specific_named_place(client, monkeypatch):
    _fake_nominatim(monkeypatch, {
        "lat": "9.9195", "lon": "78.1193",
        "address": {"suburb": "Goripalayam", "city": "Madurai",
                    "state_district": "Madurai", "state": "Tamil Nadu"},
    })
    r = client.get("/api/reverse-geocode?lat=9.9195&lon=78.1193")
    assert r.status_code == 200
    place = r.json()["place"]
    assert place["name"] == "Goripalayam"
    assert place["area"] == "Madurai"
    assert place["label"] == "Goripalayam, Madurai, Tamil Nadu"
    assert "OpenStreetMap" in place["attribution"]


def test_reverse_geocode_also_reports_the_nearest_ward(client, monkeypatch):
    _fake_nominatim(monkeypatch, {
        "lat": "9.9195", "lon": "78.1193",
        "address": {"suburb": "Goripalayam", "city": "Madurai"},
    })
    body = client.get("/api/reverse-geocode?lat=9.9195&lon=78.1193").json()
    assert body["ward"]["city"] == "Madurai"
    assert body["distance_km"] is not None


def test_reverse_geocode_invents_nothing_when_osm_has_no_name(client, monkeypatch):
    """An unnamed point returns 404. It never falls back to a guessed locality."""
    _fake_nominatim(monkeypatch, {"lat": "0", "lon": "0", "address": {}})
    r = client.get("/api/reverse-geocode?lat=0&lon=0")
    assert r.status_code == 404
    assert "no named place" in r.json()["detail"].lower()
    assert "place" not in r.json()

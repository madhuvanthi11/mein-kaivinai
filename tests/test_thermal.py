"""Thermal metrics, Human Thermal Stress, persistence, night heat, forecast, impact risk."""
import math

import pytest

from app.services import (assessment, historical, impact, recommendations as rec,
                          thermal_config as cfg, thermal_forecast as tf, thermal_metrics as tm,
                          vulnerability as vuln)

SUN = dict(temperature_c=35, relative_humidity=55, dew_point_c=24.5, wind_speed_mps=2.0,
           shortwave_radiation_wm2=850, direct_radiation_wm2=600, diffuse_radiation_wm2=150,
           direct_normal_irradiance_wm2=800)
NIGHT = dict(temperature_c=29, relative_humidity=75, dew_point_c=24, wind_speed_mps=2.0,
             shortwave_radiation_wm2=0, direct_radiation_wm2=0, diffuse_radiation_wm2=0,
             direct_normal_irradiance_wm2=0)


def m(**kw):
    return tm.compute({**SUN, **kw})


# ------------------------------------------------------------- UTCI / WBGT / HI
def test_metrics_are_returned_with_provenance():
    r = m()
    for k in ("utci", "wbgt", "heat_index"):
        assert r[k]["value"] is not None and r[k]["unit"] == "°C"
        assert r[k]["measurement"] is False and r[k]["quality"] == "modelled"
    assert r["wbgt"]["method"] == "estimated"
    assert r["radiant_environment"]["method"] == "estimated_from_weather_and_radiation"
    assert r["radiant_environment"]["measurement"] is False
    assert set(r["categories"]) == {"utci", "wbgt", "heat_index", "human_thermal_stress"}


def test_humidity_raises_relevant_metrics():
    dry, wet = m(relative_humidity=30), m(relative_humidity=85)
    assert wet["utci"]["value"] > dry["utci"]["value"]
    assert wet["wbgt"]["value"] > dry["wbgt"]["value"]
    assert wet["heat_index"]["value"] > dry["heat_index"]["value"]


def test_wind_lowers_utci_but_not_heat_index():
    calm, breezy = m(wind_speed_mps=1.0), m(wind_speed_mps=6.0)
    assert breezy["utci"]["value"] < calm["utci"]["value"]
    assert breezy["heat_index"]["value"] == calm["heat_index"]["value"]   # HI has no wind term


def test_radiation_raises_radiant_load_and_stress():
    shade = m(shortwave_radiation_wm2=0, direct_radiation_wm2=0, diffuse_radiation_wm2=0,
              direct_normal_irradiance_wm2=0)
    sun = m()
    assert sun["radiant_environment"]["radiant_excess_c"] > shade["radiant_environment"]["radiant_excess_c"] + 10
    assert sun["utci"]["value"] > shade["utci"]["value"]
    assert sun["wbgt"]["value"] > shade["wbgt"]["value"]
    assert sun["heat_index"]["value"] == shade["heat_index"]["value"]     # radiation-free by design
    assert shade["radiant_environment"]["radiant_excess_c"] == pytest.approx(0, abs=0.2)


def test_heat_index_is_not_apparent_temperature():
    r = tm.compute({**SUN, "apparent_temperature_c": 99})
    assert r["heat_index"]["value"] != 99


def test_heat_index_not_applicable_when_cool():
    r = tm.compute({**NIGHT, "temperature_c": 22, "dew_point_c": 18})
    assert r["heat_index"]["value"] is None and r["heat_index"]["quality"] == "not_applicable"
    assert r["heat_index"]["reason"]
    assert r["utci"]["value"] is not None            # other metrics unaffected


def test_missing_radiation_gives_null_with_reason_not_a_guess():
    r = m(direct_normal_irradiance_wm2=None, direct_radiation_wm2=None)
    for k in ("utci", "wbgt"):
        assert r[k]["value"] is None and r[k]["quality"] == "unavailable"
        assert "adiation" in r[k]["reason"]
    assert r["heat_index"]["value"] is not None
    assert r["human_thermal_stress"]["quality"] == "partial"
    assert r["human_thermal_stress"]["score"] is not None


def test_missing_humidity_does_not_crash():
    r = m(relative_humidity=None)
    assert r["utci"]["value"] is None and r["utci"]["reason"]
    assert r["human_thermal_stress"]["score"] is None
    assert r["human_thermal_stress"]["quality"] == "unavailable"


def test_saturated_humidity_is_handled():
    r = m(relative_humidity=100)
    assert r["wbgt"]["value"] is not None
    assert "rh_capped_at_99_for_wet_bulb" in r["wbgt"]["notes"]


def test_out_of_range_input_returns_quality_flag_not_exception():
    r = m(temperature_c=60)
    assert r["utci"]["value"] is None and r["utci"]["quality"] == "out_of_range"
    assert tm.compute({})["human_thermal_stress"]["score"] is None      # empty obs


def test_wind_units_and_utci_minimum():
    a = tm.compute({**SUN, "wind_speed_kmh": 7.2, "wind_speed_mps": None})    # = 2 m/s
    assert a["utci"]["value"] == m()["utci"]["value"]
    calm = m(wind_speed_mps=0.1)
    assert "wind_raised_to_UTCI_minimum_0.5_mps" in calm["utci"]["notes"]
    assert calm["utci"]["value"] is not None


def test_series_matches_single_evaluation():
    series = tm.compute_series([SUN, NIGHT])
    assert series[0]["utci"]["value"] == m()["utci"]["value"]
    assert series[1]["utci"]["value"] == tm.compute(NIGHT)["utci"]["value"]


# ---------------------------------------------------------- Human Thermal Stress
def test_hts_is_bounded_and_reports_components():
    h = m()["human_thermal_stress"]
    assert 0 <= h["score"] <= 100
    assert set(h["components"]) == {"utci", "wbgt", "heat_index"}
    assert h["level"] == cfg.level_for_score(h["score"])
    assert h["drivers"] and h["drivers"][0]["code"] in ("utci", "wbgt", "heat_index")
    assert sum(c["weight"] for c in h["components"].values()) == pytest.approx(1.0, abs=0.01)


def test_hts_is_a_mean_not_a_sum():
    h = m()["human_thermal_stress"]
    scores = [c["score"] for c in h["components"].values()]
    assert min(scores) <= h["score"] <= max(scores)          # cannot exceed its largest input
    assert h["score"] == pytest.approx(sum(c["points"] for c in h["components"].values()), abs=0.2)


def test_hts_rises_with_heat_and_falls_at_night():
    assert m()["human_thermal_stress"]["score"] > tm.compute(NIGHT)["human_thermal_stress"]["score"]
    assert m(temperature_c=40)["human_thermal_stress"]["score"] > m()["human_thermal_stress"]["score"]


def test_thresholds_live_in_one_config_and_agree_with_scores():
    assert cfg.level_for_score(0) == "Low" and cfg.level_for_score(30) == "Moderate"
    assert cfg.level_for_score(50) == "High" and cfg.level_for_score(70) == "Very High"
    assert cfg.level_for_score(90) == "Extreme"
    # A metric value at its published category boundary lands on the matching score band.
    assert cfg.level_for_score(cfg.score_from_value("utci", 38.0)) == "Very High"
    assert cfg.level_for_score(cfg.score_from_value("utci", 31.9)) == "Moderate"
    assert cfg.level_for_score(cfg.score_from_value("wbgt", 32.2)) == "Extreme"


# ------------------------------------------------- persistence / night / forecast
def series(day_pattern, days=5, start="2026-09-21", night_t=27.0):
    """Hourly rows; day_pattern(d, h) -> (temp, sun 0/1)."""
    from datetime import date, timedelta
    rows = []
    d0 = date.fromisoformat(start)
    for d in range(days):
        for h in range(24):
            t, sun = day_pattern(d, h)
            rows.append({"time": f"{(d0 + timedelta(days=d)).isoformat()}T{h:02d}:00",
                         "temperature_c": t, "relative_humidity_pct": 60.0, "dew_point_c": t - 8,
                         "wind_speed_kmh": 7.0, "solar_radiation_wm2": 850 * sun,
                         "direct_radiation_wm2": 600 * sun, "diffuse_radiation_wm2": 150 * sun,
                         "direct_normal_irradiance_wm2": 800 * sun, "apparent_temperature_c": t + 3})
    return rows


def hot_day(peak):
    return lambda d, h: ((peak if 10 <= h <= 17 else 27.0), 1 if 8 <= h <= 17 else 0)


def test_prolonged_stress_increases_persistence():
    brief = tf.build(series(lambda d, h: (39 if 13 <= h <= 14 else 27.0, 1 if 8 <= h <= 17 else 0)), 12)
    long_ = tf.build(series(hot_day(39)), 12)
    pb, pl = brief["days"][0]["persistence"], long_["days"][0]["persistence"]
    assert pl["longest_high_stress_run_h"] > pb["longest_high_stress_run_h"]
    assert pl["score"] > pb["score"]
    assert any(s["code"] in ("vh_run", "high_run") for s in pl["statements"])


def test_consecutive_days_are_counted_only_when_they_happen():
    hot = tf.build(series(hot_day(39)), 12)
    assert [d["persistence"]["consecutive_high_stress_days"] for d in hot["days"]] == [1, 2, 3, 4, 5]
    cool = tf.build(series(lambda d, h: (24.0, 0.3 if 8 <= h <= 17 else 0)), 12)
    assert all(d["persistence"]["consecutive_high_stress_days"] == 0 for d in cool["days"])
    assert cool["days"][0]["persistence"]["statements"] == []      # no claim without support
    assert cool["days"][0]["persistence"]["recovery"]["status"] == "not_applicable"


def test_five_day_forecast_shape():
    f = tf.build(series(hot_day(38)), 12)
    assert len(f["days"]) == 5
    d = f["days"][0]
    for k in ("date", "level", "max_utci", "max_wbgt", "max_heat_index", "max_human_thermal_stress",
              "peak_time", "persistence", "night_heat"):
        assert k in d
    p = d["persistence"]
    assert {"high_stress_hours", "very_high_stress_hours", "recovery"} <= set(p)
    assert 10 <= int(d["peak_time"][11:13]) <= 17           # peak is where the heat actually is
    assert d["max_utci"] > 30


def test_night_heat_uses_actual_overnight_values():
    warm = tf.build(series(lambda d, h: ((38 if 10 <= h <= 17 else 33.0), 1 if 8 <= h <= 17 else 0)), 12)
    cool = tf.build(series(lambda d, h: ((38 if 10 <= h <= 17 else 24.0), 1 if 8 <= h <= 17 else 0)), 12)
    nw, nc = warm["days"][0]["night_heat"], cool["days"][0]["night_heat"]
    assert nw["min_temperature_c"] == pytest.approx(33.0) and nc["min_temperature_c"] == pytest.approx(24.0)
    assert nw["score"] > nc["score"] and nw["stressed_hours"] > nc["stressed_hours"]
    assert nw["complete"] is True
    assert any(s["code"] == "night_elevated" for s in nw["statements"])
    assert nc["stressed_hours"] == 0 and nc["statements"] == []


def test_missing_radiation_series_does_not_crash_forecast():
    rows = series(hot_day(38))
    for r in rows:
        r["direct_normal_irradiance_wm2"] = None
    f = tf.build(rows, 12)
    assert f["current"]["utci"]["quality"] == "unavailable"
    assert f["days"][0]["max_human_thermal_stress"] is not None       # heat index still scores
    assert f["days"][0]["max_utci"] is None


def test_local_adjustment_is_applied_and_labelled():
    rows = series(hot_day(35))
    plain = tf.build(rows, 12)["days"][0]["max_utci"]
    for r in rows:
        r["uhi_offset_c"] = 3.0
    adj = tf.build(rows, 12)
    assert adj["days"][0]["max_utci"] > plain
    assert adj["hourly"][12]["local_adjustment_c"] == 3.0


# ------------------------------------------------------------------ impact risk
def test_impact_without_vulnerability_says_so_and_invents_nothing():
    r = impact.compute(78, 85, 72)
    assert r["vulnerability_data"] == "unavailable"
    assert r["vulnerability"] is None and r["exposure"] is None
    assert "not personalised" in r["vulnerability_note"]
    assert r["impact_risk"] == round(0.6 * 78 + 0.25 * 85 + 0.15 * 72)
    assert "mortality" not in str(r["basis"]).lower() or "not a mortality" in r["basis"].lower()
    assert r["level"] == cfg.level_for_score(r["impact_risk"])


def test_impact_grows_with_persistence_and_night_heat():
    base = impact.compute(70, 10, 10)["impact_risk"]
    assert impact.compute(70, 90, 10)["impact_risk"] > base
    assert impact.compute(70, 10, 90)["impact_risk"] > base


def test_impact_handles_missing_components():
    assert impact.compute(None, None, None)["status"] == "unavailable"
    assert impact.compute(60, None, None)["status"] == "partial"


def test_real_vulnerability_data_would_plug_in_without_other_changes():
    class Fake(vuln.VulnerabilityProvider):
        def get_vulnerability(self, location_id):
            return {"status": "available", "source": "test", "vulnerability_index": 0.9, "exposure_index": 0.8}
    original = vuln.provider()
    vuln.set_provider(Fake())
    try:
        r = impact.compute(60, 60, 60)
        assert r["impact_risk"] > 60 and r["vulnerability"] == 0.9
        assert r["modifiers_applied"] == ["vulnerability", "exposure"]
    finally:
        vuln.set_provider(original)
    assert impact.compute(60, 60, 60)["vulnerability_data"] == "unavailable"


def test_a_broken_provider_cannot_break_the_dashboard():
    class Bad(vuln.VulnerabilityProvider):
        def get_vulnerability(self, location_id):
            raise RuntimeError("boom")
    original = vuln.provider()
    vuln.set_provider(Bad())
    try:
        assert vuln.get_vulnerability("x")["status"] == "unavailable"
    finally:
        vuln.set_provider(original)


# --------------------------------------------------------- recommendation triggers
def _actions(pattern):
    f = tf.build(series(pattern), 12)
    win = f["window_24h"]
    imp = impact.for_window(win)
    for d in f["days"]:
        d["impact"] = impact.for_day(d)
    return rec.government_actions("Test locality", imp, win, f["days"])


def test_recommendations_fire_from_conditions_and_carry_evidence():
    acts = _actions(lambda d, h: ((40 if 10 <= h <= 17 else 32.0), 1 if 8 <= h <= 17 else 0))
    codes = {a["code"] for a in acts}
    assert {"shift_outdoor_work", "cooling_centres_water", "advance_preparedness"} <= codes
    for a in acts:
        assert a["action"] and a["trigger"] and a["evidence"] and a["urgency"] and a["locality"] == "Test locality"
        assert a["personalised"] is False                   # no demographic data -> general guidance
    assert acts == sorted(acts, key=lambda a: rec.URGENCY_ORDER[a["urgency"]])


def test_no_recommendations_for_benign_weather():
    assert _actions(lambda d, h: (25.0, 0.3 if 8 <= h <= 17 else 0)) == []


def test_night_recommendation_needs_hot_nights():
    warm = {a["code"] for a in _actions(lambda d, h: ((38 if 10 <= h <= 17 else 34.0), 1 if 8 <= h <= 17 else 0))}
    cool = {a["code"] for a in _actions(lambda d, h: ((38 if 10 <= h <= 17 else 24.0), 1 if 8 <= h <= 17 else 0))}
    assert "night_recovery_messaging" in warm and "night_recovery_messaging" not in cool


# ------------------------------------------------------------------- historical
def test_historical_is_explicitly_unavailable():
    r = historical.get_historical_baseline({"latitude": 13.08, "longitude": 80.27}, "climatology")
    assert r["status"] == "unavailable" and r["source"] == "ERA5"
    assert r["reason"] == "Historical dataset not connected"
    assert not any(k in r for k in ("baseline", "anomaly", "mean"))


# -------------------------------------------------------------------------- API
CHENNAI = "lat=13.08&lon=80.27&name=Chennai"
MADURAI = "lat=9.92&lon=78.12"


def test_thermal_endpoints_chennai(client7):
    c = client7.get(f"/api/thermal/current?{CHENNAI}").json()
    assert c["utci"]["quality"] == "modelled" and c["wbgt"]["method"] == "estimated"
    assert c["human_thermal_stress"]["score"] is not None
    h = client7.get(f"/api/thermal/hourly?{CHENNAI}").json()
    assert h["type"] == "forecast" and len(h["hourly"]) >= 24 and "utci" in h["hourly"][0]
    f = client7.get(f"/api/thermal/forecast?{CHENNAI}").json()
    assert len(f["days"]) == 5 and [d["day"] for d in f["days"]] == [1, 2, 3, 4, 5]
    assert client7.get("/api/thermal/methodology").json()["metrics"]["utci"]["anchors"]


def test_impact_and_risk_forecast(client7):
    i = client7.get(f"/api/impact/current?{CHENNAI}").json()
    assert i["impact"]["vulnerability_data"] == "unavailable"
    assert i["health_outcomes"]["mortality"]["status"] == "unavailable"
    assert "not yet calibrated" in i["health_outcomes"]["message"]
    f = client7.get(f"/api/impact/forecast?{CHENNAI}").json()
    assert len(f["days"]) == 5 and all("impact" in d for d in f["days"])
    r = client7.get(f"/api/risk/forecast?{CHENNAI}").json()
    assert r["risk_measure"] == "Heat-Health Impact Risk" and len(r["days"]) == 5


def test_historical_endpoint_and_summary_do_not_crash(client7):
    h = client7.get(f"/api/historical/baseline?{CHENNAI}")
    assert h.status_code == 200 and h.json()["status"] == "unavailable"
    s = client7.get(f"/api/weather/summary?{CHENNAI}").json()
    assert s["historical"]["status"] == "unavailable"


def test_summary_carries_the_full_story(client7):
    s = client7.get(f"/api/weather/summary?{CHENNAI}").json()
    assert s["risk"]["basis"] == "impact_risk" and s["risk"]["score"] == s["impact"]["impact_risk"]
    assert s["thermal"]["current"]["utci"]["value"] is not None
    assert len(s["forecast"]) == 5
    assert {d["item"] for d in s["data_method"]} >= {"live_weather", "historical_baseline", "hyperlocal_adjustment"}
    assert "utci" in s["hourly"][0]
    assert s["legacy_risk"]["confidence"] == "Rule-based assessment"


def test_pilot_locality_is_labelled_as_model_estimated(client7):
    s = client7.get("/api/wards/mdu-meenakshi").json()
    assert s["local_context"]["label"] == "Model-estimated local heat adjustment"
    assert s["thermal"]["local_adjustment"].startswith("model-estimated")
    assert s["action_items"] is not None and s["risk"]["basis"] == "impact_risk"


def test_government_recommendations_endpoint(client7):
    r = client7.get("/api/government/recommendations?city=Madurai").json()
    assert r["vulnerability_data"] == "unavailable" and r["localities"]
    for a in r["action_plan"]:
        assert {"action", "trigger", "evidence", "urgency", "locality"} <= set(a)
    m = client7.get("/api/monitor/city?city=Madurai").json()
    assert m["points"][0]["thermal"]["utci"]["value"] is not None
    assert len(m["points"][0]["forecast_brief"]) == 5


def test_thermal_endpoints_survive_an_open_meteo_outage(monkeypatch, client7):
    from app.services import open_meteo
    async def boom(url, params):
        raise open_meteo.WeatherUnavailable("down")
    monkeypatch.setattr(open_meteo.service, "_get", boom)
    open_meteo.service._cache.clear()
    assert client7.get("/api/thermal/current?lat=1&lon=1").status_code == 503


def test_thermal_calculation_is_cached_per_observation(client7, monkeypatch):
    calls = []
    real = tf.build
    monkeypatch.setattr(tf, "build", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    client7.get(f"/api/thermal/current?{CHENNAI}")
    client7.get(f"/api/impact/current?{CHENNAI}")
    client7.get(f"/api/thermal/forecast?{CHENNAI}")
    assert len(calls) == 1

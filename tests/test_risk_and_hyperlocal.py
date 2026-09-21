"""Risk scoring, peak detection, wind conversion and the ward heat-island layer."""
from app.data.wards import BY_ID, WARDS
from app.services import local_context as lc, recommendations as rec, risk, wind
from app.services.open_meteo import normalize
from app.services.wards import haversine_km, nearest, ranked, spread


# ----------------------------------------------------------------- risk engine
def test_hotter_weather_scores_higher(payload):
    hot, cool = normalize(payload(38)), normalize(payload(24))
    a, b = risk.assess(hot), risk.assess(cool)
    assert a["score"] > b["score"]
    assert 0 <= a["score"] <= 100 and 0 <= b["score"] <= 100


def test_confidence_is_never_a_fake_percentage(payload):
    a = risk.assess(normalize(payload(36)))
    assert a["confidence"] == "Rule-based assessment"
    assert "%" not in a["confidence"]


def test_levels_map_to_thresholds():
    assert risk.level_for(10) == "Low"
    assert risk.level_for(30) == "Moderate"
    assert risk.level_for(50) == "High"
    assert risk.level_for(70) == "Very High"
    assert risk.level_for(95) == "Extreme"


def test_drivers_are_explainable(payload):
    a = risk.assess(normalize(payload(38)))
    assert a["drivers"], "an elevated score must explain itself"
    assert all("code" in d and "effect" in d for d in a["drivers"])


def test_wind_reduces_score(payload):
    calm = risk.assess(normalize(payload(36, wind=0)))
    breezy = risk.assess(normalize(payload(36, wind=28)))
    assert breezy["score"] < calm["score"]


def test_humidity_raises_score(payload):
    dry = risk.assess(normalize(payload(34, humidity=35)))
    humid = risk.assess(normalize(payload(34, humidity=88)))
    assert humid["score"] > dry["score"]


# ----------------------------------------------------------------- peak window
def test_peak_is_computed_not_hardcoded(payload):
    p = risk.assess(normalize(payload(34)))
    assert p["peak_start"] == "2026-09-21T11:00"
    assert p["peak_end"] == "2026-09-21T17:00"
    assert p["peak_score"] is not None


def test_peak_window_shifts_with_the_data(payload):
    raw = payload(30)
    # Move the heat bulge to the evening; the window must follow it.
    raw["hourly"]["apparent_temperature"] = [48 if 18 <= i % 24 <= 21 else 26 for i in range(48)]
    raw["hourly"]["temperature_2m"] = [42 if 18 <= i % 24 <= 21 else 24 for i in range(48)]
    p = risk.assess(normalize(raw))
    assert p["peak_start"].endswith("18:00")
    assert p["peak_end"].endswith("22:00")


# ----------------------------------------------------------------- wind
def test_wind_direction_conversion():
    assert [wind.compass(d) for d in (0, 44, 90, 135, 180, 225, 270, 315, 359)] == \
           ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
    assert wind.compass(None) is None


def test_wind_analysis_uses_real_values(payload):
    w = normalize(payload(30, wind=17))
    a = wind.analyze(w["current"], w["hourly"][:24])
    assert a["current_speed_kmh"] == 17
    assert a["dominant_direction"] == "E"
    assert len(a["trend"]) == 24


# ----------------------------------------------------------------- hyperlocal
def test_every_ward_has_a_valid_profile():
    for w in WARDS:
        p = w.profile()
        assert set(p) == {"built_up", "green", "water", "industrial", "density"}
        assert all(0.0 <= v <= 1.0 for v in p.values()), w.id
        assert w.name_ta and w.city_ta


def test_ward_ids_are_unique():
    assert len(BY_ID) == len(WARDS)


def test_dense_ward_runs_hotter_than_green_ward():
    row = {"time": "2026-09-21T15:00", "wind_speed_kmh": 8,
           "cloud_cover_pct": 20, "precipitation_mm": 0.0}
    dense = lc.offset_for_hour(BY_ID["che-t-nagar"].profile(), row)
    green = lc.offset_for_hour(BY_ID["che-adyar"].profile(), row)
    assert dense > green
    assert dense - green > 1.0, "the pilot must show a meaningful intra-city spread"


def test_heat_island_is_stronger_at_night():
    p = BY_ID["mdu-meenakshi"].profile()
    base = {"wind_speed_kmh": 5, "cloud_cover_pct": 10, "precipitation_mm": 0.0}
    noon = lc.offset_for_hour(p, {**base, "time": "2026-09-21T13:00"})
    night = lc.offset_for_hour(p, {**base, "time": "2026-09-21T20:00"})
    assert night > noon


def test_wind_and_rain_suppress_the_heat_island():
    p = BY_ID["che-t-nagar"].profile()
    calm = lc.offset_for_hour(p, {"time": "2026-09-21T15:00", "wind_speed_kmh": 2,
                                  "cloud_cover_pct": 10, "precipitation_mm": 0.0})
    windy = lc.offset_for_hour(p, {"time": "2026-09-21T15:00", "wind_speed_kmh": 40,
                                   "cloud_cover_pct": 10, "precipitation_mm": 0.0})
    wet = lc.offset_for_hour(p, {"time": "2026-09-21T15:00", "wind_speed_kmh": 2,
                                 "cloud_cover_pct": 95, "precipitation_mm": 4.0})
    assert windy < calm and wet < calm


def test_offset_stays_inside_a_plausible_envelope():
    row = {"time": "2026-09-21T20:00", "wind_speed_kmh": 0,
           "cloud_cover_pct": 0, "precipitation_mm": 0.0}
    for w in WARDS:
        off = lc.offset_for_hour(w.profile(), row)
        assert lc.OFFSET_MIN <= off <= lc.OFFSET_MAX, w.id


def test_adjustment_only_touches_apparent_temperature(payload):
    w = normalize(payload(35))
    before = w["hourly"][12]
    after, _ = lc.apply_to_hours(w["hourly"], BY_ID["che-t-nagar"])
    row = after[12]
    assert row["apparent_temperature_c"] != before["apparent_temperature_c"]
    for k in ("temperature_c", "relative_humidity_pct", "wind_speed_kmh",
              "surface_pressure_hpa", "solar_radiation_wm2", "precipitation_mm"):
        assert row[k] == before[k], f"{k} must stay exactly as Open-Meteo reported"


def test_ward_adjustment_changes_the_score(payload):
    w = normalize(payload(35))
    plain = risk.assess(w)
    hot_ward, _ = lc.apply_to_hours(w["hourly"], BY_ID["che-t-nagar"])
    adjusted = risk.assess({**w, "hourly": hot_ward})
    assert adjusted["score"] > plain["score"]
    assert any(d["code"] == "local_heat_island" for d in adjusted["drivers"])


def test_explanation_lists_warming_and_cooling_terms():
    e = lc.explain(BY_ID["che-adyar"].profile())
    assert e["terms"]
    assert {"warms", "cools"} & {t["effect"] for t in e["terms"]}
    assert e["method"] == "Land-cover urban-heat-island model"


def test_satellite_provider_reports_itself_unavailable():
    assert lc.SatelliteLandCoverProvider().available() is False
    lc.set_provider(lc.SatelliteLandCoverProvider())
    assert isinstance(lc.provider(), lc.StaticProfileProvider), "must fall back, not break"


# ----------------------------------------------------------------- ward lookup
def test_nearest_ward_matches_inside_a_city():
    w, d = nearest(9.9195, 78.1193)
    assert w is not None and w.city == "Madurai" and d < 1


def test_nearest_returns_none_when_far_away():
    w, d = nearest(28.6139, 77.2090)  # Delhi
    assert w is None and d > 100


def test_haversine_is_sane():
    d = haversine_km(13.0827, 80.2707, 9.9252, 78.1198)
    assert 380 < d < 440


# ----------------------------------------------------------------- ranking
def _pt(name, score):
    return {"ward": {"id": name, "name": name}, "risk": {"score": score, "level": risk.level_for(score)},
            "current": {"apparent_temperature_c": 30 + score / 10}}


def test_ties_share_a_rank_and_are_flagged():
    r = ranked([_pt("a", 80), _pt("b", 80), _pt("c", 60)])
    assert [x["rank"] for x in r] == [1, 1, 3]
    assert r[0]["tied"] and r[1]["tied"] and not r[2]["tied"]


def test_spread_reports_the_intra_city_range():
    s = spread([_pt("hot", 80), _pt("mid", 70), _pt("cool", 40)])
    assert s["hottest_ward"] == "hot" and s["coolest_ward"] == "cool"
    assert s["score_range"] == [40, 80]
    assert s["feels_like_spread_c"] == 4.0


# ----------------------------------------------------------------- guidance
def test_ward_guidance_is_specific_to_land_cover():
    hot = {"level": "High", "score": 70}
    dense = rec.for_ward(hot, BY_ID["che-t-nagar"])
    green = rec.for_ward(hot, BY_ID["trz-bhel"])
    assert "ward_low_shade" in dense
    assert "ward_low_shade" not in green


def test_low_risk_gets_no_emergency_guidance():
    assert rec.for_ward({"level": "Low", "score": 10}, BY_ID["che-t-nagar"]) == \
           ["normal_precaution", "hydrate"]

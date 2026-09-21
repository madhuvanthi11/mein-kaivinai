"""Ward-level orchestration: live weather per ward + hyperlocal risk."""
import asyncio
from math import radians, sin, cos, asin, sqrt

from . import risk, wind, local_context as lc, recommendations as rec, assessment as asm
from .open_meteo import service, WeatherUnavailable
from ..data.wards import WARDS, BY_ID, CITIES, LAND_COVER_NOTE, Ward
from .. import config


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def nearest(lat: float, lon: float):
    """Closest ward and its distance, or (None, None) if nothing is in range."""
    best, best_d = None, None
    for w in WARDS:
        d = haversine_km(lat, lon, w.lat, w.lon)
        if best_d is None or d < best_d:
            best, best_d = w, d
    if best_d is not None and best_d > config.WARD_MATCH_RADIUS_KM:
        return None, round(best_d, 1)
    return best, round(best_d, 1)


def cities() -> list:
    return [{"name": c, "name_ta": v["name_ta"], "ward_count": len(v["wards"]),
             "wards": [w.brief() for w in v["wards"]]}
            for c, v in CITIES.items()]


async def ward_weather(w: Ward) -> dict:
    """Live Open-Meteo forecast for the ward centroid, with the UHI layer applied."""
    raw = await service.forecast(w.lat, w.lon, w.name)
    hours, _ = lc.apply_to_hours(raw["hourly"], w)
    adjusted = {**raw, "hourly": hours}
    i = risk.now_index(adjusted)
    cur = dict(raw["current"])
    baseline_at = cur.get("apparent_temperature_c")
    off = hours[i].get("uhi_offset_c") if i < len(hours) else None
    if baseline_at is not None and off is not None:
        cur["apparent_temperature_baseline_c"] = baseline_at
        cur["apparent_temperature_c"] = round(baseline_at + off, 1)
        cur["uhi_offset_c"] = off
    adjusted["current"] = cur
    adjusted["ward"] = w.brief()
    return adjusted


async def ward_detail(ward_id: str, horizon_h: int = 48) -> dict:
    w = BY_ID[ward_id]
    a = await ward_weather(w)
    i = risk.now_index(a)
    an = asm.analyse(a, w.id)
    pl = asm.payload(a, w.id)
    assessment = an["risk"]           # Heat-Health Impact Risk, legacy `risk` shape
    lo, hi = max(0, i - 6), i + horizon_h
    hours = asm.merge_hourly(a["hourly"], an["package"])
    scored = risk.hourly_scores(a["hourly"])[lo:hi]
    win = an["package"]["window_24h"]
    return {
        "ward": a["ward"],
        "location": a["location"],
        "source": a["source"],
        "updated_at": a["updated_at"],
        "current": a["current"],
        "risk": assessment,
        "legacy_risk": risk.assess(a),
        "hourly": [{**h, "risk_score": s["score"]} for h, s in zip(hours[lo:hi], scored)],
        "wind": wind.analyze(a["current"], a["hourly"][i:i + 24]),
        "local_context": {**lc.explain(w.profile()),
                          "current_offset_c": a["current"].get("uhi_offset_c"),
                          "attribution": lc.provider().attribution,
                          "label": "Model-estimated local heat adjustment",
                          "note": LAND_COVER_NOTE},
        **pl,
        "recommendations": rec.citizen_for_impact(an["impact"], win["night_heat"], win["persistence"]) if assessment else [],
        "action_items": rec.government_actions(w.name, an["impact"], win, an["package"]["days"], w) if assessment else [],
        "disclaimer": "Risk assessment generated from current/forecast weather data.",
        "health_disclaimer": "Heat-Health Impact Risk is a weather-based index. It is not a mortality "
                             "or hospitalisation prediction.",
    }


async def monitor(ward_list: list) -> tuple[list, list]:
    """Fetch every ward concurrently, score it, rank by risk."""
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_FETCHES)

    async def one(w: Ward):
        async with sem:
            try:
                a = await ward_weather(w)
            except WeatherUnavailable:
                return {"ward": w.brief(), "ok": False}
        an = asm.analyse(a, w.id)
        assessment = an["risk"]
        if assessment is None:
            return {"ward": w.brief(), "ok": False}
        pkg, win = an["package"], an["package"]["window_24h"]
        cur = pkg["current"]
        return {
            "ward": a["ward"], "ok": True, "risk": assessment, "current": a["current"],
            "impact": an["impact"],
            "thermal": {"utci": cur["utci"], "wbgt": cur["wbgt"], "heat_index": cur["heat_index"],
                        "human_thermal_stress": cur["human_thermal_stress"],
                        "window_24h": win},
            "forecast_brief": [{"day": d["day"], "date": d["date"], "level": d["level"],
                                "max_human_thermal_stress": d["max_human_thermal_stress"],
                                "impact_risk": d["impact"]["impact_risk"],
                                "max_utci": d["max_utci"], "max_wbgt": d["max_wbgt"],
                                "max_heat_index": d["max_heat_index"], "peak_time": d["peak_time"],
                                "persistence": {"high_stress_hours": d["persistence"]["high_stress_hours"],
                                                "very_high_stress_hours": d["persistence"]["very_high_stress_hours"]},
                                "night_heat": {"min_temperature_c": d["night_heat"]["min_temperature_c"]}}
                               for d in pkg["days"]],
            "actions": rec.government_actions(w.name, an["impact"], win, pkg["days"], w),
            "wind_direction": wind.compass(a["current"].get("wind_direction_deg")),
            "uhi_offset_c": a["current"].get("uhi_offset_c"),
            "updated_at": a["updated_at"],
        }

    res = await asyncio.gather(*[one(w) for w in ward_list])
    ok = sorted([r for r in res if r["ok"]], key=lambda r: -r["risk"]["score"])
    return ok, [r["ward"]["name"] for r in res if not r["ok"]]


def ranked(points: list) -> list:
    """Dense ranking: equal scores share a rank, so we never fabricate precision."""
    out, last, rank = [], None, 0
    for idx, p in enumerate(points):
        s = p["risk"]["score"]
        if s != last:
            rank = idx + 1
            last = s
        out.append({**p, "rank": rank, "tied": False})
    counts = {}
    for p in out:
        counts[p["rank"]] = counts.get(p["rank"], 0) + 1
    for p in out:
        p["tied"] = counts[p["rank"]] > 1
    return out


def spread(points: list) -> dict:
    """Intra-city spread -- the headline hyperlocal statistic."""
    if not points:
        return {}
    scores = [p["risk"]["score"] for p in points]
    temps = [p["current"].get("apparent_temperature_c") for p in points
             if p["current"].get("apparent_temperature_c") is not None]
    return {
        "hottest_ward": points[0]["ward"]["name"],
        "coolest_ward": points[-1]["ward"]["name"],
        "score_range": [min(scores), max(scores)],
        "feels_like_range_c": [round(min(temps), 1), round(max(temps), 1)] if temps else None,
        "feels_like_spread_c": round(max(temps) - min(temps), 1) if temps else None,
    }

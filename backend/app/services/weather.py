"""Plain-location weather + risk, used when a point has no registered ward.

Ward-aware paths live in services/wards.py. This module keeps the app fully
functional for any coordinate on earth, which is what makes location search
useful outside the four pilot cities.
"""
from . import risk, wind, recommendations as rec, local_context as lc, assessment as asm
from .open_meteo import service
from .wards import nearest, ward_detail


async def summary(lat: float, lon: float, name: str | None = None, horizon_h: int = 48) -> dict:
    """If the point falls inside a registered ward, return the hyperlocal view.
    Otherwise return the mesoscale view, clearly marked as such."""
    ward, distance = nearest(lat, lon)
    if ward is not None:
        detail = await ward_detail(ward.id, horizon_h)
        return {**detail, "resolution": "ward", "match_distance_km": distance,
                "searched": {"name": name, "latitude": lat, "longitude": lon}}

    w = await service.forecast(lat, lon, name)
    i = risk.now_index(w)
    an = asm.analyse(w, None)
    pl = asm.payload(w, None)
    assessment = an["risk"]           # Heat-Health Impact Risk, legacy `risk` shape
    win = an["package"]["window_24h"]
    lo, hi = max(0, i - 6), i + horizon_h
    hours = asm.merge_hourly(w["hourly"], an["package"])
    scored = risk.hourly_scores(w["hourly"])[lo:hi]
    label = name or w["location"]["name"]
    return {
        "ward": None,
        "resolution": "area",
        "match_distance_km": distance,
        "location": w["location"],
        "source": w["source"],
        "updated_at": w["updated_at"],
        "current": w["current"],
        "risk": assessment,
        "legacy_risk": risk.assess(w),
        "hourly": [{**h, "risk_score": s["score"]} for h, s in zip(hours[lo:hi], scored)],
        "wind": wind.analyze(w["current"], w["hourly"][i:i + 24]),
        "local_context": {
            "method": "Not available outside pilot localities",
            "label": "No local heat adjustment applied",
            "note": "The model-estimated local heat adjustment covers the pilot localities only. "
                    "This reading is the area forecast from Open-Meteo, unadjusted.",
            "attribution": lc.provider().attribution,
            "terms": [], "base_offset_c": None, "current_offset_c": None,
        },
        **pl,
        "recommendations": rec.citizen_for_impact(an["impact"], win["night_heat"], win["persistence"]) if assessment else [],
        "action_items": rec.government_actions(label, an["impact"], win, an["package"]["days"]) if assessment else [],
        "disclaimer": "Risk assessment generated from current/forecast weather data.",
        "health_disclaimer": "Heat-Health Impact Risk is a weather-based index. It is not a mortality "
                             "or hospitalisation prediction.",
    }

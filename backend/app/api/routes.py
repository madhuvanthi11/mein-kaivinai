from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from .. import config
from ..data.wards import BY_ID, CITIES, LAND_COVER_NOTE
from ..schemas import AlertIn
from ..services import (assessment as asm, thermal_config, alerts, authz, delivery, historical, local_context as lc,
                        notifications, recommendations as rec, risk, store,
                        wards as ward_svc, weather, wind, workflow)
from ..services.open_meteo import LocationNotFound, WeatherUnavailable, service

router = APIRouter(prefix="/api")

UNAVAILABLE = "Live weather data is temporarily unavailable. Please retry."
LAT = Query(..., ge=-90, le=90, description="Latitude")
LON = Query(..., ge=-180, le=180, description="Longitude")


async def _forecast(lat, lon, name=None):
    try:
        return await service.forecast(lat, lon, name)
    except WeatherUnavailable:
        raise HTTPException(503, UNAVAILABLE)


def _ward_or_404(ward_id: str):
    w = BY_ID.get(ward_id)
    if w is None:
        raise HTTPException(404, "Ward not found.")
    return w


# --------------------------------------------------------------- weather
@router.get("/weather/current", tags=["weather"])
async def weather_current(lat: float = LAT, lon: float = LON, name: str | None = None):
    w = await _forecast(lat, lon, name)
    return {k: w[k] for k in ("location", "source", "updated_at", "current")}


@router.get("/weather/hourly", tags=["weather"])
async def weather_hourly(lat: float = LAT, lon: float = LON, name: str | None = None):
    w = await _forecast(lat, lon, name)
    return {**{k: w[k] for k in ("location", "source", "updated_at")}, "hourly": w["hourly"]}


@router.get("/weather/summary", tags=["weather"])
async def weather_summary(lat: float = LAT, lon: float = LON, name: str | None = None):
    """Everything the citizen dashboard needs in one call.

    Resolves to a ward view when the point is inside a pilot ward, otherwise to
    the plain area forecast.
    """
    try:
        return await weather.summary(lat, lon, name)
    except WeatherUnavailable:
        raise HTTPException(503, UNAVAILABLE)


# --------------------------------------------------------------- risk
@router.get("/risk/current", tags=["risk"])
async def risk_current(lat: float = LAT, lon: float = LON):
    w = await _forecast(lat, lon)
    return {"location": w["location"], "updated_at": w["updated_at"], "risk": risk.assess(w),
            "engine": "legacy apparent-temperature rule score; the primary risk is "
                      "Heat-Health Impact Risk at /api/impact/current"}


@router.get("/risk/hourly", tags=["risk"])
async def risk_hourly(lat: float = LAT, lon: float = LON):
    w = await _forecast(lat, lon)
    return {"location": w["location"], "hourly": risk.hourly_scores(w["hourly"])}


@router.get("/risk/peak", tags=["risk"])
async def risk_peak(lat: float = LAT, lon: float = LON):
    w = await _forecast(lat, lon)
    return risk.peak(risk.hourly_scores(w["hourly"]), risk.now_index(w))



# --------------------------------------------------------------- thermal / impact
async def _bundle(lat, lon, name=None):
    """Weather (ward-adjusted when the point is in a pilot locality) + its analysis."""
    ward, _d = ward_svc.nearest(lat, lon)
    try:
        if ward is not None:
            w = await ward_svc.ward_weather(ward)
        else:
            w = await service.forecast(lat, lon, name)
    except WeatherUnavailable:
        raise HTTPException(503, UNAVAILABLE)
    wid = ward.id if ward else None
    return w, wid, asm.analyse(w, wid), ward


def _head(w, ward):
    return {"location": w["location"], "updated_at": w["updated_at"], "source": "Open-Meteo",
            "locality": ward.brief() if ward else None,
            "resolution": "pilot_locality" if ward else "area"}


@router.get("/thermal/methodology", tags=["thermal"])
async def thermal_methodology():
    """Every threshold, weight and anchor used by the thermal layer."""
    return thermal_config.methodology()


@router.get("/thermal/current", tags=["thermal"])
async def thermal_current(lat: float = LAT, lon: float = LON, name: str | None = None):
    w, wid, an, ward = await _bundle(lat, lon, name)
    pkg = an["package"]
    cur = pkg["current"]
    return {**_head(w, ward), "time": pkg["current_time"], "utci": cur["utci"], "wbgt": cur["wbgt"],
            "heat_index": cur["heat_index"], "human_thermal_stress": cur["human_thermal_stress"],
            "radiant_environment": cur["radiant_environment"], "categories": cur["categories"],
            "quality": cur["quality"], "method": cur["method"],
            "window_24h": pkg["window_24h"],
            "local_adjustment": "model-estimated" if ward else "none"}


@router.get("/thermal/hourly", tags=["thermal"])
async def thermal_hourly(lat: float = LAT, lon: float = LON, name: str | None = None):
    w, wid, an, ward = await _bundle(lat, lon, name)
    return {**_head(w, ward), "type": "forecast", "hourly": an["package"]["hourly"]}


@router.get("/thermal/forecast", tags=["thermal"])
async def thermal_forecast(lat: float = LAT, lon: float = LON, name: str | None = None):
    w, wid, an, ward = await _bundle(lat, lon, name)
    return {**_head(w, ward), "type": "forecast", "days": an["package"]["days"],
            "note": "Day 1 is the current calendar day and includes hours already elapsed."}


@router.get("/risk/forecast", tags=["risk"])
async def risk_forecast(lat: float = LAT, lon: float = LON, name: str | None = None):
    w, wid, an, ward = await _bundle(lat, lon, name)
    return {**_head(w, ward), "type": "forecast", "risk_measure": "Heat-Health Impact Risk",
            "days": [{"day": d["day"], "date": d["date"], "level": d["impact"]["level"],
                      "impact_risk": d["impact"]["impact_risk"], "peak_time": d["peak_time"]}
                     for d in an["package"]["days"]]}


@router.get("/impact/current", tags=["impact"])
async def impact_current(lat: float = LAT, lon: float = LON, name: str | None = None):
    w, wid, an, ward = await _bundle(lat, lon, name)
    return {**_head(w, ward), "window": "next 24 hours", "impact": an["impact"],
            "vulnerability": an["vulnerability"],
            "health_outcomes": asm.health_outcomes.status()}


@router.get("/impact/forecast", tags=["impact"])
async def impact_forecast(lat: float = LAT, lon: float = LON, name: str | None = None):
    w, wid, an, ward = await _bundle(lat, lon, name)
    return {**_head(w, ward), "type": "forecast",
            "days": [{"day": d["day"], "date": d["date"], "impact": d["impact"]}
                     for d in an["package"]["days"]]}


@router.get("/historical/baseline", tags=["historical"])
async def historical_baseline(lat: float = LAT, lon: float = LON, period: str = "climatology"):
    """Never fabricates: reports 'unavailable' until a historical provider (ERA5) is connected."""
    return historical.get_historical_baseline({"latitude": lat, "longitude": lon}, period)


@router.get("/government/recommendations", tags=["government"])
async def government_recommendations(city: str = Query(config.DEFAULT_CITY)):
    """Action items driven by each locality's calculated thermal stress, persistence,
    night heat and forecast. General heat-action guidance: not personalised to any
    demographic group while vulnerability/exposure data is unavailable."""
    m = await monitor_city(city, thermal_config.IMPACT["alert_at"])
    return {"city": city, "label": rec.LABEL, "basis": "Heat-Health Impact Risk",
            "vulnerability_data": "unavailable", "action_plan": m["action_plan"],
            "localities": [{"locality": p["ward"]["name"], "impact": p["impact"],
                            "actions": p["actions"]} for p in m["points"]]}


# --------------------------------------------------------------- wind
@router.get("/wind/hourly", tags=["wind"])
async def wind_hourly(lat: float = LAT, lon: float = LON):
    w = await _forecast(lat, lon)
    return wind.analyze(w["current"], w["hourly"][risk.now_index(w):][:48])


# --------------------------------------------------------------- geocoding
@router.get("/geocode", tags=["location"])
async def geocode(query: str = Query(..., min_length=2)):
    try:
        return {"results": await service.geocode(query)}
    except LocationNotFound:
        raise HTTPException(404, "Location not found.")
    except WeatherUnavailable:
        raise HTTPException(503, "Location search is temporarily unavailable.")


@router.get("/reverse-geocode", tags=["location"])
async def reverse_geocode(lat: float = LAT, lon: float = LON):
    """Coordinates -> place name, for the "use my location" flow.

    Kept separate from the weather call on purpose: if OpenStreetMap is slow or
    has no name for the point, the weather still loads and the UI shows the
    coordinates rather than a made-up locality.
    """
    try:
        place = await service.reverse_geocode(lat, lon)
    except LocationNotFound:
        raise HTTPException(404, "No named place found at these coordinates.")
    except WeatherUnavailable as e:
        raise HTTPException(503, f"Place lookup is temporarily unavailable. {e}")
    ward, distance = ward_svc.nearest(lat, lon)
    return {"place": place, "ward": ward.brief() if ward else None,
            "distance_km": distance}


# --------------------------------------------------------------- wards
@router.get("/wards", tags=["wards"])
async def list_wards():
    """Static registry. No weather here -- this endpoint never calls Open-Meteo."""
    return {
        "cities": ward_svc.cities(),
        "default_city": config.DEFAULT_CITY,
        "default_ward_id": config.DEFAULT_WARD_ID,
        "land_cover_note": LAND_COVER_NOTE,
        "match_radius_km": config.WARD_MATCH_RADIUS_KM,
    }


@router.get("/wards/nearest", tags=["wards"])
async def nearest_ward(lat: float = LAT, lon: float = LON):
    w, d = ward_svc.nearest(lat, lon)
    if w is None:
        return {"ward": None, "distance_km": d,
                "detail": "No pilot ward within range. Area forecast will be used."}
    return {"ward": w.brief(), "distance_km": d}


@router.get("/wards/{ward_id}", tags=["wards"])
async def ward_view(ward_id: str):
    """Full hyperlocal dashboard payload for one ward."""
    _ward_or_404(ward_id)
    try:
        return await ward_svc.ward_detail(ward_id)
    except WeatherUnavailable:
        raise HTTPException(503, UNAVAILABLE)


@router.get("/wards/{ward_id}/context", tags=["wards"])
async def ward_context(ward_id: str):
    """Why this ward runs hot or cool. Static model explanation, no API call."""
    w = _ward_or_404(ward_id)
    return {"ward": w.brief(), **lc.explain(w.profile()),
            "attribution": lc.provider().attribution, "note": LAND_COVER_NOTE}


# --------------------------------------------------------------- monitoring
@router.get("/monitor/city", tags=["monitoring"])
async def monitor_city(city: str = Query(config.DEFAULT_CITY),
                       threshold: int = Query(risk.ALERT_AT, ge=0, le=100)):
    """Live ward-by-ward monitoring for one city, ranked by risk."""
    if city.lower() == "all":
        selected = [w for v in CITIES.values() for w in v["wards"]]
    else:
        match = next((v for k, v in CITIES.items() if k.lower() == city.lower()), None)
        if match is None:
            raise HTTPException(404, "City not found.")
        selected = match["wards"]

    points, failed = await ward_svc.monitor(selected)
    if not points:
        raise HTTPException(503, UNAVAILABLE)

    points = ward_svc.ranked(points)
    worst = points[0]["risk"]["level"]
    profiles = [BY_ID[p["ward"]["id"]] for p in points]
    breaching = alerts.evaluate(points, threshold)

    return {
        "city": city,
        "source": "Open-Meteo",
        "resolution": "ward",
        "label": "Weather-derived ward risk points. Not official government warnings.",
        "land_cover_note": LAND_COVER_NOTE,
        "points": points,
        "hotspots": points[:6],
        "spread": ward_svc.spread(points),
        "worst_level": worst,
        "alert_threshold": threshold,
        "wards_above_threshold": [
            {"ward_id": p["ward"]["id"], "ward": p["ward"]["name"], "score": p["risk"]["score"],
             "level": p["risk"]["level"]} for p in breaching],
        "recommendations": rec.for_government(worst, profiles),
        "recommendations_label": rec.LABEL,
        "action_plan": sorted([a for p in points for a in p["actions"]],
                              key=lambda a: rec.URGENCY_ORDER.get(a["urgency"], 9)),
        "risk_measure": "Heat-Health Impact Risk (weather + persistence; vulnerability data unavailable)",
        "unavailable": failed,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# Kept so older clients/bookmarks keep working.
@router.get("/monitor/tamilnadu", tags=["monitoring"], include_in_schema=False)
async def monitor_legacy(threshold: int = risk.ALERT_AT):
    return await monitor_city("all", threshold)


# --------------------------------------------------------------- alerts
@router.post("/alerts/broadcast", tags=["alerts"])
async def broadcast(a: AlertIn):
    alert = {
        "ward": a.ward, "ward_id": a.ward_id, "city": a.city, "level": a.level,
        "score": a.score, "threshold": a.threshold, "message": a.message,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "basis": "Rule-based assessment from live Open-Meteo forecast",
    }
    return {"alert": alert, "delivery": notifications.dispatch(alert),
            "note": "Delivery status reflects what each provider actually did."}


@router.post("/alerts/ward/{ward_id}", tags=["alerts"])
async def alert_for_ward(ward_id: str, threshold: int = Query(risk.ALERT_AT, ge=0, le=100)):
    """Build an alert from the ward's live assessment and hand it to the providers."""
    w = _ward_or_404(ward_id)
    try:
        a = await ward_svc.ward_weather(w)
    except WeatherUnavailable:
        raise HTTPException(503, UNAVAILABLE)
    assessment = asm.analyse(a, w.id)["risk"]
    if assessment is None:
        raise HTTPException(503, UNAVAILABLE)
    alert = alerts.build(w.name, w.city, assessment, threshold)
    alert["ward_id"] = w.id
    return {"alert": alert, "delivery": notifications.dispatch(alert),
            "crossed_threshold": assessment["score"] >= threshold,
            "note": "Delivery status reflects what each provider actually did."}


# --------------------------------------------------------------- meta
@router.get("/status", tags=["meta"])
async def status():
    """What is live, what is optional and switched off. Used by the UI footer."""
    return {
        "weather_source": "Open-Meteo",
        "weather_requires_key": False,
        "risk_engine": "Deterministic rule-based (not a trained ML model)",
        "primary_risk": "Heat-Health Impact Risk (thermal stress + persistence + night heat)",
        "thermal_metrics": {"library": "pythermalcomfort", "metrics": ["UTCI", "WBGT (estimated)", "Heat Index"],
                            "radiant_environment": "estimated from Open-Meteo radiation"},
        "vulnerability": "unavailable",
        "health_outcome_models": "not calibrated",
        "hyperlocal_model": lc.provider().attribution,
        "cache": service.cache_stats(),
        "historical": historical.status(),
        "notifications": notifications.status(),
        "auth": authz.status(),
        "roles": list(authz.ROLES),
        "workflow": workflow.status(),
        "delivery": delivery.status(),
        "persistence": store.status(),
        "firebase_configured": config.FCM_CONFIGURED,
        "ward_count": len(BY_ID),
        "cities": list(CITIES.keys()),
    }

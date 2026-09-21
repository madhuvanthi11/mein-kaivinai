"""One place that turns a weather series into thermal metrics, forecast and impact risk.

    weather (normalised, optionally ward-adjusted)
        -> thermal_forecast.build   (metrics, HTS, persistence, night heat, days)
        -> impact.compute           (Heat-Health Impact Risk)
        -> payload used by every endpoint

Results are cached briefly per (location, observation time) so the map, the
dashboards and the alert workflow share one calculation instead of repeating it.
"""
import time

from .. import config
from . import historical, impact, thermal_config as cfg, thermal_forecast as tf, health_outcomes
from . import risk as legacy_risk, vulnerability as vuln

_cache: dict = {}
_MAX = 256

DATA_METHOD = [
    {"item": "live_weather", "source": "Open-Meteo", "status": "connected", "type": "forecast model (not station observation)"},
    {"item": "forecast", "source": "Open-Meteo", "status": "connected", "type": "forecast"},
    {"item": "thermal_metrics", "source": "pythermalcomfort / documented methods (UTCI, Rothfusz heat index, Stull wet-bulb)", "status": "connected", "type": "modelled; radiant environment estimated"},
    {"item": "historical_baseline", "source": "ERA5", "status": "unavailable", "type": "not connected"},
    {"item": "hyperlocal_adjustment", "source": "Land-cover heat-island model", "status": "model-estimated", "type": "estimated"},
    {"item": "vulnerability_exposure", "source": None, "status": "unavailable", "type": "not connected"},
    {"item": "health_outcomes", "source": None, "status": "unavailable", "type": "not calibrated"},
]


def _key(w, ward_id):
    loc = w["location"]
    return (ward_id, round(loc["latitude"], 3), round(loc["longitude"], 3), w["updated_at"],
            bool(w["hourly"] and w["hourly"][0].get("uhi_offset_c") is not None))


def analyse(w, ward_id=None):
    """Return the full thermal + impact assessment for a normalised weather object."""
    k = _key(w, ward_id)
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < config.CACHE_TTL_SECONDS:
        return hit[1]
    i = legacy_risk.now_index(w)
    pkg = tf.build(w["hourly"], i)
    win = pkg["window_24h"]
    imp = impact.for_window(win, ward_id)
    for d in pkg["days"]:
        d["impact"] = impact.for_day(d, ward_id)
        d["level"] = d["impact"]["level"] or d["level"]
        d["thermal_stress_level"] = cfg.level_for_score(d["max_human_thermal_stress"])
    out = {
        "package": pkg, "impact": imp, "risk": impact.as_risk(imp, win),
        "vulnerability": vuln.get_vulnerability(ward_id),
    }
    if len(_cache) >= _MAX:
        _cache.pop(next(iter(_cache)))
    _cache[k] = (time.time(), out)
    return out


def merge_hourly(hours, pkg):
    """Attach thermal fields to weather hourly rows (by position; same series)."""
    return [{**h, "utci": t["utci"], "wbgt": t["wbgt"], "heat_index": t["heat_index"],
             "human_thermal_stress": t["human_thermal_stress"], "thermal_level": t["level"]}
            for h, t in zip(hours, pkg["hourly"])]


def payload(w, ward_id=None, location_label=None):
    """The thermal/impact blocks shared by the ward view, area view and API."""
    a = analyse(w, ward_id)
    pkg = a["package"]
    return {
        "thermal": {"current": pkg["current"], "time": pkg["current_time"], "window_24h": pkg["window_24h"],
                    "local_adjustment": ("model-estimated local heat adjustment applied to air temperature"
                                         if w["hourly"] and w["hourly"][0].get("uhi_offset_c") is not None
                                         else "none (area forecast, unadjusted)")},
        "impact": a["impact"],
        "forecast": pkg["days"],
        "vulnerability": a["vulnerability"],
        "health_outcomes": health_outcomes.status(),
        "historical": historical.get_historical_baseline(w["location"], "climatology"),
        "data_method": DATA_METHOD,
    }

"""Heat-Health Impact Risk (0-100).

  thermal stress + persistence + night-time heat  [+ vulnerability + exposure]

This is a transparent weather-driven risk index. It is NOT a probability of
illness, admission or death (see health_outcomes.py). While no vulnerability or
exposure data is connected, both are reported as "unavailable" and the score is
computed from weather and persistence alone; nothing is assumed about who lives
in the area.
"""
from datetime import datetime, timedelta

from . import thermal_config as cfg
from . import vulnerability as vuln

CONFIDENCE = "Rule-based assessment"
BASIS = "Heat-Health Impact Risk (weather + persistence; not a mortality probability)"


def _factor(gain, index):
    return 1 + gain * (2 * index - 1)


def compute(thermal_stress, persistence, night_heat, location_id=None, vulnerability=None):
    """Combine sub-scores (each 0-100 or None) into the impact-risk block."""
    w = cfg.IMPACT["weights"]
    parts = {"thermal_stress": thermal_stress, "persistence": persistence, "night_heat": night_heat}
    avail = {k: v for k, v in parts.items() if v is not None}
    v = vulnerability if vulnerability is not None else vuln.get_vulnerability(location_id)
    if thermal_stress is None or not avail:
        return {"impact_risk": None, "level": None, "status": "unavailable",
                "reason": "Thermal stress could not be calculated.", "thermal_stress": None,
                "persistence": persistence, "night_heat": night_heat, "exposure": None,
                "vulnerability": None, "vulnerability_data": v["status"], "drivers": [],
                "confidence": CONFIDENCE, "basis": BASIS}
    wsum = sum(w[k] for k in avail)
    contrib = {k: w[k] / wsum * val for k, val in avail.items()}
    base = sum(contrib.values())
    score, mods = base, []
    vi = ei = None
    if v.get("status") == "available":
        vi, ei = v.get("vulnerability_index"), v.get("exposure_index")
        if vi is not None:
            score *= _factor(cfg.IMPACT["vulnerability_gain"], vi)
            mods.append("vulnerability")
        if ei is not None:
            score *= _factor(cfg.IMPACT["exposure_gain"], ei)
            mods.append("exposure")
    score = int(round(max(0.0, min(100.0, score))))
    drivers = [{"code": k, "value": round(parts[k], 1), "points": round(c, 1),
                "level": cfg.level_for_score(parts[k])} for k, c in
               sorted(contrib.items(), key=lambda kv: -kv[1])]
    return {
        "impact_risk": score, "score": score, "level": cfg.level_for_score(score),
        "status": "ok" if len(avail) == 3 else "partial",
        "thermal_stress": round(thermal_stress, 1),
        "persistence": None if persistence is None else round(persistence, 1),
        "night_heat": None if night_heat is None else round(night_heat, 1),
        "exposure": ei, "vulnerability": vi,
        "vulnerability_data": v["status"], "exposure_data": v["status"] if ei is not None else "unavailable",
        "vulnerability_note": (None if v["status"] == "available" else
                               "Vulnerability and exposure data are unavailable; risk is weather- and "
                               "persistence-based and is not personalised to any population group."),
        "modifiers_applied": mods,
        "drivers": drivers, "confidence": CONFIDENCE, "basis": BASIS,
        "weights": {k: round(w[k] / wsum, 3) for k in avail},
        "health_outcome_model": "not yet calibrated — requires historical health outcome data",
    }


def for_window(window, location_id=None):
    return compute(window["max_human_thermal_stress"], window["persistence"]["score"],
                   window["night_heat"]["score"], location_id)


def for_day(day, location_id=None):
    if day.get("max_human_thermal_stress") is None:
        return compute(None, None, None, location_id)
    return compute(day["max_human_thermal_stress"], day["persistence"]["score"],
                   day["night_heat"]["score"], location_id)


def as_risk(impact_block, window):
    """Project the impact block onto the legacy `risk` shape (score/level/peak/drivers)
    so alert thresholds, the map and the approval workflow all run on impact risk."""
    if impact_block.get("impact_risk") is None:
        return None
    pk = window.get("peak_time")
    hw = window["persistence"].get("high_stress_window")
    start = hw["start"] if hw else pk
    end_src = hw["end"] if hw else pk
    end = (datetime.fromisoformat(end_src) + timedelta(hours=1)).isoformat(timespec="minutes") if end_src else None
    return {
        "score": impact_block["impact_risk"], "level": impact_block["level"],
        "drivers": [{"code": d["code"], "effect": "raise", "points": d["points"]}
                    for d in impact_block["drivers"]],
        "confidence": CONFIDENCE, "basis": "impact_risk",
        "peak_start": start, "peak_end": end, "peak_score": window.get("max_human_thermal_stress"),
        "peak_time": pk,
    }

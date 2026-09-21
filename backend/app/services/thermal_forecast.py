"""Hourly thermal series, persistence, night-time heat and the 5-day forecast.

Input is the normalised Open-Meteo hourly series (optionally carrying the
ward's model-estimated `uhi_offset_c`). Everything returned is computed from
those hours; a statement is only produced when the numbers support it.

Day 1 is the current calendar day and includes hours that have already
elapsed. A night belongs to the day on which it starts (20:00 -> 06:00 next day).
"""
import math

from . import thermal_config as cfg
from . import thermal_metrics as tm

P = cfg.PERSISTENCE
N = cfg.NIGHT


# ------------------------------------------------------------ observations
def _magnus_rh(t, td):
    return 100.0 * math.exp(17.625 * td / (243.04 + td)) / math.exp(17.625 * t / (243.04 + t))


def observation(row):
    """Thermal input for one hourly row.

    If the row carries a ward heat-island offset it is added to air temperature
    (a model-estimated local adjustment) and humidity is re-derived at constant
    dew point so the air stays physically consistent. Unadjusted rows pass through.
    """
    t = row.get("temperature_c")
    rh = row.get("relative_humidity_pct")
    off = row.get("uhi_offset_c") or 0.0
    dew = row.get("dew_point_c")
    if t is not None and off and dew is not None:
        t = t + off
        rh = min(100.0, _magnus_rh(t, min(dew, t)))
    elif t is not None and off:
        t = t + off
    return {
        "temperature_c": t, "relative_humidity_pct": rh, "dew_point_c": dew,
        "wind_speed_kmh": row.get("wind_speed_kmh"),
        "shortwave_radiation_wm2": row.get("solar_radiation_wm2"),
        "direct_radiation_wm2": row.get("direct_radiation_wm2"),
        "diffuse_radiation_wm2": row.get("diffuse_radiation_wm2"),
        "direct_normal_irradiance_wm2": row.get("direct_normal_irradiance_wm2"),
        "pressure_hpa": row.get("surface_pressure_hpa"),
    }


def hourly_metrics(hours, mtype="forecast"):
    return tm.compute_series([observation(h) for h in hours], mtype)


# -------------------------------------------------------------- run helpers
def _runs(scores, threshold):
    """Yield (start_idx, end_idx_inclusive) of consecutive scores >= threshold."""
    start = None
    for i, s in enumerate(scores):
        hit = s is not None and s >= threshold
        if hit and start is None:
            start = i
        if not hit and start is not None:
            yield start, i - 1
            start = None
    if start is not None:
        yield start, len(scores) - 1


def _longest(scores, threshold):
    best = None
    for a, b in _runs(scores, threshold):
        if best is None or (b - a) > (best[1] - best[0]):
            best = (a, b)
    return best


def _hm(t):
    return t[11:16]


def _persistence_score(run_high_h, run_vh_h, consecutive_days):
    w = P["weights"]
    return round(w["run_high"] * min(1, run_high_h / P["run_high_cap_h"])
                 + w["run_very_high"] * min(1, run_vh_h / P["run_vh_cap_h"])
                 + w["consecutive_days"] * min(1, consecutive_days / P["days_cap"]), 1)


def _persistence(times, scores, consecutive_days, series_scores=None, series_times=None, offset=0):
    """Persistence stats for a window. `series_*` (the whole forecast) is used
    only to look beyond the window for the recovery time."""
    hi, vh = P["high_score"], P["very_high_score"]
    lh, lv = _longest(scores, hi), _longest(scores, vh)
    run_h = (lh[1] - lh[0] + 1) if lh else 0
    run_v = (lv[1] - lv[0] + 1) if lv else 0
    rec = {"status": "not_applicable", "hours": None}
    if lh and series_scores is not None:
        end = offset + lh[1]
        rec = {"status": "not_within_forecast", "hours": None}
        for k in range(end + 1, len(series_scores)):
            s = series_scores[k]
            if s is not None and s < P["recovery_target_score"]:
                rec = {"status": "ok", "hours": k - end - 1,
                       "back_to_low_at": series_times[k]}
                break
    statements = []
    if lv:
        statements.append({"code": "vh_run", "hours": run_v, "from": _hm(times[lv[0]]),
                           "to": _hm(times[lv[1]]),
                           "text": f"Very high thermal stress may persist for {run_v} consecutive hour(s) "
                                   f"({_hm(times[lv[0]])}–{_hm(times[lv[1]])})."})
    if lh:
        statements.append({"code": "high_run", "hours": run_h, "from": _hm(times[lh[0]]),
                           "to": _hm(times[lh[1]]),
                           "text": f"High or worse thermal stress runs {run_h} consecutive hour(s) "
                                   f"({_hm(times[lh[0]])}–{_hm(times[lh[1]])})."})
    if consecutive_days >= 2:
        statements.append({"code": "multi_day", "days": consecutive_days,
                           "text": f"High thermal stress is forecast on {consecutive_days} consecutive days."})
    return {
        "longest_high_stress_run_h": run_h, "longest_very_high_run_h": run_v,
        "high_stress_hours": sum(1 for s in scores if s is not None and s >= hi),
        "very_high_stress_hours": sum(1 for s in scores if s is not None and s >= vh),
        "high_stress_window": None if not lh else {"start": times[lh[0]], "end": times[lh[1]]},
        "consecutive_high_stress_days": consecutive_days,
        "recovery": rec,
        "score": _persistence_score(run_h, run_v, consecutive_days),
        "statements": statements,
    }


def _is_night(time_str):
    h = int(time_str[11:13])
    return h >= N["start_hour"] or h < N["end_hour"]


def _night(rows, scores):
    """Night-time heat from the hours supplied (all must be night hours)."""
    vals = [(r, s) for r, s in zip(rows, scores) if s is not None]
    temps = [r["_t"] for r in rows if r.get("_t") is not None]
    if not vals:
        return {"status": "unavailable", "reason": "No night hours with a computable thermal-stress score.",
                "hours_available": 0, "score": None, "level": None,
                "min_temperature_c": None, "max_temperature_c": None,
                "mean_thermal_stress": None, "stressed_hours": 0, "complete": False,
                "statements": []}
    mean_s = sum(s for _, s in vals) / len(vals)
    stressed = sum(1 for _, s in vals if s >= N["stress_hour_score"])
    full = (N["end_hour"] + 24 - N["start_hour"])
    tmin = min(temps) if temps else None
    st = []
    if stressed:
        st.append({"code": "night_elevated", "stressed_hours": stressed, "min_temperature_c": tmin,
                   "text": f"Night-time thermal stress persists for {stressed} of {len(vals)} night hour(s)"
                           + (f"; the overnight minimum is {tmin:.1f} °C" if tmin is not None else "")
                           + ", reducing overnight recovery."})
    return {"status": "ok", "hours_available": len(vals), "complete": len(vals) >= full,
            "score": round(mean_s, 1), "level": cfg.level_for_score(mean_s),
            "min_temperature_c": None if tmin is None else round(tmin, 1),
            "max_temperature_c": None if not temps else round(max(temps), 1),
            "mean_thermal_stress": round(mean_s, 1), "stressed_hours": stressed,
            "stressed_definition": f"night hours with Human Thermal Stress ≥ {N['stress_hour_score']} "
                                   "(UTCI ≥ 26 °C, moderate heat stress)",
            "statements": st}


def _mx(vals):
    v = [x for x in vals if x is not None]
    return round(max(v), 1) if v else None


def build(hours, now_i, tz_note=None):
    """Full thermal package for a location from its hourly series."""
    mets = hourly_metrics(hours)
    times = [h["time"] for h in hours]
    hts = [m["human_thermal_stress"]["score"] for m in mets]
    for h, m in zip(hours, mets):
        h_t = observation(h)["temperature_c"]
        m["_t"] = h_t

    hourly = [{
        "time": t, "temperature_c": None if m["_t"] is None else round(m["_t"], 1),
        "utci": m["utci"]["value"], "wbgt": m["wbgt"]["value"], "heat_index": m["heat_index"]["value"],
        "human_thermal_stress": s, "level": m["human_thermal_stress"]["level"],
        "quality": m["quality"], "local_adjustment_c": h.get("uhi_offset_c"),
    } for t, m, s, h in zip(times, mets, hts, hours)]

    dates = []
    for t in times:
        if t[:10] not in dates:
            dates.append(t[:10])
    today = times[now_i][:10]
    day_list = [d for d in dates if d >= today][:cfg.FORECAST_DAYS_SHOWN]

    days, consecutive = [], 0
    for di, d in enumerate(day_list):
        idx = [i for i, t in enumerate(times) if t[:10] == d]
        a, b = idx[0], idx[-1]
        ds = hts[a:b + 1]
        dt = times[a:b + 1]
        peak_i = max((i for i in range(len(ds)) if ds[i] is not None), key=lambda i: ds[i], default=None)
        pk_s = None if peak_i is None else ds[peak_i]
        consecutive = consecutive + 1 if any(s is not None and s >= P["high_score"] for s in ds) else 0
        pers = _persistence(dt, ds, consecutive, hts, times, offset=a)
        # night that starts this evening
        night_idx = [i for i, t in enumerate(times)
                     if _is_night(t) and (
                         (t[:10] == d and int(t[11:13]) >= N["start_hour"])
                         or (t[:10] == (dates[dates.index(d) + 1] if dates.index(d) + 1 < len(dates) else "") and int(t[11:13]) < N["end_hour"]))]
        night = _night([mets[i] for i in night_idx], [hts[i] for i in night_idx])
        ms = [mets[i] for i in range(a, b + 1)]
        days.append({
            "day": di + 1, "date": d, "includes_elapsed_hours": di == 0,
            "level": cfg.level_for_score(pk_s), "status": "ok" if pk_s is not None else "unavailable",
            "max_utci": _mx([m["utci"]["value"] for m in ms]),
            "max_wbgt": _mx([m["wbgt"]["value"] for m in ms]),
            "max_heat_index": _mx([m["heat_index"]["value"] for m in ms]),
            "max_human_thermal_stress": pk_s if pk_s is None else round(pk_s, 1),
            "peak_time": None if peak_i is None else dt[peak_i],
            "peak_utci_category": None if peak_i is None else ms[peak_i]["utci"]["category"],
            "peak_wbgt_category": None if peak_i is None else ms[peak_i]["wbgt"]["category"],
            "peak_heat_index_category": None if peak_i is None else ms[peak_i]["heat_index"]["category"],
            "max_temperature_c": _mx([m["_t"] for m in ms]),
            "hours_with_data": sum(1 for s in ds if s is not None),
            "persistence": pers, "night_heat": night,
        })

    # current + next-24h window
    cur = tm.compute(observation(hours[now_i]), "current")
    w_end = min(len(hours), now_i + 24)
    ws, wt = hts[now_i:w_end], times[now_i:w_end]
    consec0 = 0
    for dd in days:
        if dd["persistence"]["high_stress_hours"] > 0:
            consec0 += 1
        else:
            break
    wpers = _persistence(wt, ws, consec0, hts, times, offset=now_i)
    nidx = [i for i in range(now_i, w_end) if _is_night(times[i])]
    wnight = _night([mets[i] for i in nidx], [hts[i] for i in nidx])
    pk = max((i for i in range(len(ws)) if ws[i] is not None), key=lambda i: ws[i], default=None)
    window = {
        "hours": len(ws), "from": wt[0] if wt else None, "to": wt[-1] if wt else None,
        "max_human_thermal_stress": None if pk is None else round(ws[pk], 1),
        "peak_time": None if pk is None else wt[pk],
        "max_utci": _mx([mets[i]["utci"]["value"] for i in range(now_i, w_end)]),
        "max_wbgt": _mx([mets[i]["wbgt"]["value"] for i in range(now_i, w_end)]),
        "max_heat_index": _mx([mets[i]["heat_index"]["value"] for i in range(now_i, w_end)]),
        "persistence": wpers, "night_heat": wnight,
    }
    for m in mets:
        m.pop("_t", None)
    return {"current": cur, "current_time": times[now_i], "window_24h": window, "days": days,
            "hourly": hourly, "hours_total": len(hours)}

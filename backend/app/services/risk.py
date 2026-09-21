"""Transparent deterministic heat-risk engine (0-100).

This is a published rule set, not a machine-learning model, and it never claims
to be one. Every point in the score can be traced to a weather value that
Open-Meteo actually returned, or to the ward land-cover adjustment in
local_context.py, which is labelled as a model wherever it appears.

Score composition (maximum points)
  apparent temperature  55   the dominant term: what the body actually feels
  air temperature       10   independent contribution of dry-bulb heat
  solar radiation       10   direct sun load on someone outdoors
  humidity              10   suppressed sweat evaporation, only when warm
  persistence           10   heat that has already run for hours is more harmful
  daytime                5   exposure hours when people are out working
  wind relief           -8   moving air carries heat away

Because the apparent-temperature series is shifted by the ward's urban-heat-island
offset before scoring, the same city can legitimately show different scores in
different wards for the same hour. That is the point of the product.
"""
from datetime import datetime, timedelta

LEVELS = [(25, "Low"), (45, "Moderate"), (65, "High"), (80, "Very High"), (101, "Extreme")]
CONFIDENCE = "Rule-based assessment"
# Alert thresholds, by score.
ALERT_AT = 65


def level_for(score):
    for lim, name in LEVELS:
        if score < lim:
            return name
    return "Extreme"


def _c(x):
    return max(0.0, min(1.0, x))


def contributions(hours, i):
    h = hours[i]
    at, t = h.get("apparent_temperature_c"), h.get("temperature_c")
    if at is None or t is None:
        return None
    rh = h.get("relative_humidity_pct") or 0
    sw = h.get("solar_radiation_wm2") or 0
    ws = h.get("wind_speed_kmh") or 0
    hour = int(h["time"][11:13])
    prev = hours[max(0, i - 6):i]
    hot = sum(1 for p in prev if (p.get("apparent_temperature_c") or 0) >= 38)
    return {
        "apparent_temperature": _c((at - 27) / 23) * 55,
        "temperature": _c((t - 30) / 15) * 10,
        "solar_radiation": _c(sw / 900) * 10,
        "humidity": _c((rh - 40) / 50) * 10 if t >= 28 else 0.0,
        "daytime": 5.0 if 10 <= hour <= 17 else 0.0,
        "persistence": hot / 6 * 10,
        "wind_relief": -_c(ws / 30) * 8 if at >= 32 else 0.0,
    }


def score_at(hours, i):
    c = contributions(hours, i)
    if c is None:
        return None
    s = int(round(max(0, min(100, sum(c.values())))))
    drivers = [{"code": k, "effect": "raise", "points": round(v, 1)}
               for k, v in sorted(c.items(), key=lambda kv: -kv[1]) if v >= 5][:3]
    if c["wind_relief"] <= -3:
        drivers.append({"code": "wind_relief", "effect": "reduce", "points": round(c["wind_relief"], 1)})

    # Surface the hyperlocal contribution separately, in degrees, so the UI can
    # say "this ward runs 2.4 C hotter than the surrounding area" rather than
    # burying it inside the apparent-temperature term.
    off = hours[i].get("uhi_offset_c")
    if off is not None and abs(off) >= 0.4:
        drivers.append({"code": "local_heat_island" if off > 0 else "local_cooling",
                        "effect": "raise" if off > 0 else "reduce",
                        "degrees_c": off})
    return {"score": s, "level": level_for(s), "drivers": drivers, "confidence": CONFIDENCE}


def hourly_scores(hours):
    out = []
    for i, h in enumerate(hours):
        r = score_at(hours, i)
        out.append({"time": h["time"],
                    "score": r["score"] if r else None,
                    "level": r["level"] if r else None,
                    "temperature_c": h.get("temperature_c"),
                    "apparent_temperature_c": h.get("apparent_temperature_c"),
                    "uhi_offset_c": h.get("uhi_offset_c")})
    return out


def now_index(weather):
    key = weather["updated_at"][:13]
    for i, h in enumerate(weather["hourly"]):
        if h["time"][:13] == key:
            return i
    return 0


def peak(scored, start, horizon=24):
    """Longest continuous band around the highest-scoring hour in the horizon.

    The band extends while neighbouring hours stay within 15% of the peak, so
    the window reported is the actual dangerous stretch rather than a fixed
    hardcoded afternoon block.
    """
    win = [(i, s["score"]) for i, s in enumerate(scored[start:start + horizon], start)
           if s["score"] is not None]
    if not win:
        return {"peak_start": None, "peak_end": None, "peak_score": None}
    pi, ps = max(win, key=lambda x: x[1])
    thr = 0.85 * ps
    a = b = pi
    while a - 1 >= start and (scored[a - 1]["score"] or -1) >= thr:
        a -= 1
    while b + 1 < len(scored) and b + 1 < start + horizon and (scored[b + 1]["score"] or -1) >= thr:
        b += 1
    end = (datetime.fromisoformat(scored[b]["time"]) + timedelta(hours=1)).isoformat(timespec="minutes")
    return {"peak_start": scored[a]["time"], "peak_end": end, "peak_score": ps}


def assess(weather):
    i = now_index(weather)
    cur = score_at(weather["hourly"], i)
    if cur is None:
        return None
    return {**cur, **peak(hourly_scores(weather["hourly"]), i)}

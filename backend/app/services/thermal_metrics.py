"""Scientific thermal-metrics layer: UTCI, estimated WBGT, Heat Index and the
Human Thermal Stress (HTS) score.

Pipeline:  weather observation -> radiant environment (estimated) -> UTCI /
WBGT / Heat Index (pythermalcomfort) -> HTS (0-100, transparent weighted mean).

What is and is not measured
---------------------------
Open-Meteo gives air temperature, humidity, wind and solar radiation. It does
NOT give mean radiant temperature (Tmrt) or globe temperature. Both are
ESTIMATED here for a standing person on an open, unshaded site:

    Sstr = a_k * ( f_p * DNI + 0.5 * D + 0.5 * albedo * G )
    Tmrt = ( Ta_K^4 + Sstr / (eps_p * sigma) ) ^ 0.25 - 273.15

with DNI = direct normal irradiance, D = diffuse and G = global horizontal
radiation from Open-Meteo. The person's projected area factor f_p depends on
solar elevation, which is recovered from the API's own numbers
(sin(elevation) = direct_horizontal / DNI), so no astronomy is assumed.
Long-wave exchange is assumed to be at ambient air temperature (Open-Meteo
supplies no long-wave), which is a known simplification. Globe temperature is
found by inverting the ISO 7726 globe equation (pythermalcomfort) for that Tmrt.

Every metric is therefore "modelled", never "measured", and says so.

No function here raises on bad input: a metric that cannot be computed comes
back with value None, a quality flag and a reason.
"""
import math
import warnings

import numpy as np

from . import thermal_config as cfg

try:  # pythermalcomfort >= 3.8 moved these helpers
    from pythermalcomfort.environment import mean_radiant_tmp as _mrt_from_globe  # type: ignore
except Exception:  # pragma: no cover
    from pythermalcomfort.utilities import mean_radiant_tmp as _mrt_from_globe  # type: ignore
try:
    from pythermalcomfort.psychrometrics import wet_bulb_tmp as _wet_bulb
except Exception:  # pragma: no cover
    from pythermalcomfort.utilities import wet_bulb_tmp as _wet_bulb  # type: ignore
from pythermalcomfort.models import utci as _utci, heat_index_rothfusz as _hi, wbgt as _wbgt

SIGMA = 5.670374419e-8
METHOD = "pythermalcomfort (UTCI polynomial, Rothfusz heat index, Stull wet-bulb, ISO 7726 globe); " \
         "radiant environment estimated from Open-Meteo radiation"


# ------------------------------------------------------------------ helpers
def _num(v):
    try:
        if v is None:
            return math.nan
        f = float(v)
        return f if math.isfinite(f) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _obs_arrays(observations):
    """Normalise a list of observation dicts into aligned float arrays (NaN = missing)."""
    def col(*keys, scale=1.0):
        out = []
        for o in observations:
            v = math.nan
            for k in keys:
                if o.get(k) is not None:
                    v = _num(o[k])
                    break
            out.append(v * scale if not math.isnan(v) else v)
        return np.array(out, dtype=float)

    wind = col("wind_speed_mps")
    if np.isnan(wind).all():
        wind = col("wind_speed_kmh", scale=1 / 3.6)
    return {
        "tdb": col("temperature_c"),
        "rh": col("relative_humidity", "relative_humidity_pct"),
        "dew": col("dew_point_c"),
        "wind": wind,
        "ghi": col("shortwave_radiation_wm2", "solar_radiation_wm2"),
        "dir_h": col("direct_radiation_wm2"),
        "dif": col("diffuse_radiation_wm2"),
        "dni": col("direct_normal_irradiance_wm2"),
    }


def _quiet(fn, *a, **k):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fn(*a, **k)


# ------------------------------------------------- radiant environment (estimated)
def estimate_mrt(tdb, ghi, dir_h, dif, dni):
    """Estimated mean radiant temperature (°C). NaN where radiation inputs are missing."""
    r = cfg.RADIANT
    ok = ~(np.isnan(tdb) | np.isnan(ghi) | np.isnan(dir_h) | np.isnan(dif) | np.isnan(dni))
    ghi_, dir_, dif_, dni_ = (np.where(ok, np.maximum(x, 0), 0.0) for x in (ghi, dir_h, dif, dni))
    with np.errstate(divide="ignore", invalid="ignore"):
        sin_el = np.where(dni_ > 1.0, np.clip(dir_ / np.where(dni_ > 1.0, dni_, 1.0), 0.0, 1.0), 0.0)
    elev_deg = np.degrees(np.arcsin(sin_el))
    # Jendritzky/Fanger projected-area factor for a standing person.
    fp = 0.308 * np.cos(np.radians(elev_deg * (0.998 - elev_deg ** 2 / 50000.0)))
    fp = np.where(dni_ > 1.0, fp, 0.0)
    v = r["sky_and_ground_view_factor"]
    sstr = r["shortwave_absorptivity"] * (fp * dni_ + v * dif_ + v * r["ground_albedo"] * ghi_)
    ta_k = np.where(ok, tdb, 0.0) + 273.15
    tmrt = (ta_k ** 4 + sstr / (r["longwave_emissivity"] * SIGMA)) ** 0.25 - 273.15
    return np.where(ok, tmrt, np.nan)


def estimate_globe(tmrt, tdb, wind10):
    """Invert the ISO 7726 globe equation (pythermalcomfort forward model) by bisection."""
    r = cfg.RADIANT
    v = np.maximum(np.where(np.isnan(wind10), 0.1, wind10) * r["person_height_wind_ratio"], 0.1)
    ok = ~(np.isnan(tmrt) | np.isnan(tdb))
    t = np.where(ok, tdb, 30.0)
    target = np.where(ok, tmrt, 30.0)
    lo, hi = t - 15.0, t + 90.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        f = np.asarray(_quiet(_mrt_from_globe, tg=mid, tdb=t, v=v, d=r["globe_diameter_m"],
                              emissivity=r["globe_emissivity"]), dtype=float)
        hi = np.where(f > target, mid, hi)
        lo = np.where(f > target, lo, mid)
    return np.where(ok, (lo + hi) / 2.0, np.nan)


# ------------------------------------------------------------------ core
def _metric(name, value, *, unit="°C", category=None, native=None, quality, reason=None,
            notes=None, mtype="forecast"):
    score = cfg.score_from_value(name, value) if value is not None else None
    return {
        "metric": name.upper() if name != "heat_index" else "Heat Index",
        "value": None if value is None else round(float(value), 1),
        "unit": unit,
        "category": category,
        "native_category": native,
        "score": None if score is None else round(score, 1),
        "source": "Open-Meteo",
        "type": mtype,
        "method": "estimated" if name in ("wbgt",) else "modelled",
        "measurement": False,
        "quality": quality,
        "reason": reason,
        "notes": notes or [],
    }


def _category(name, value):
    s = cfg.score_from_value(name, value)
    return cfg.level_for_score(s)


def compute_series(observations, mtype="forecast"):
    """Compute all thermal metrics for a list of observations (vectorised)."""
    n = len(observations)
    if n == 0:
        return []
    a = _obs_arrays(observations)
    tdb, rh, wind = a["tdb"], a["rh"], a["wind"]

    notes = [[] for _ in range(n)]
    rh_c = np.where((rh > 99) & (rh <= 100), 99.0, rh)   # Stull wet-bulb validity is 5-99 %
    for i in np.where((rh > 99) & (rh <= 100))[0]:
        notes[i].append("rh_capped_at_99_for_wet_bulb")
    wind_u = np.clip(wind, cfg.RADIANT["utci_min_wind_mps"], 17.0)
    for i in np.where((~np.isnan(wind)) & (wind < cfg.RADIANT["utci_min_wind_mps"]))[0]:
        notes[i].append("wind_raised_to_UTCI_minimum_0.5_mps")

    tmrt = estimate_mrt(tdb, a["ghi"], a["dir_h"], a["dif"], a["dni"])
    globe = estimate_globe(tmrt, tdb, wind)

    utci_v = np.full(n, np.nan)
    ok_u = ~(np.isnan(tdb) | np.isnan(rh) | np.isnan(wind) | np.isnan(tmrt))
    if ok_u.any():
        r = _quiet(_utci, tdb=tdb[ok_u], tr=tmrt[ok_u], v=wind_u[ok_u], rh=rh[ok_u])
        utci_v[ok_u] = np.asarray(r.utci, dtype=float)

    hi_v = np.full(n, np.nan)
    ok_h = ~(np.isnan(tdb) | np.isnan(rh))
    if ok_h.any():
        r = _quiet(_hi, tdb=tdb[ok_h], rh=rh[ok_h])
        hi_v[ok_h] = np.asarray(r.hi, dtype=float)

    twb = np.full(n, np.nan)
    ok_w = ~(np.isnan(tdb) | np.isnan(rh_c))
    if ok_w.any():
        twb[ok_w] = np.asarray(_quiet(_wet_bulb, tdb=tdb[ok_w], rh=rh_c[ok_w]), dtype=float)
    wbgt_v = np.full(n, np.nan)
    ok_b = ~(np.isnan(twb) | np.isnan(globe))
    if ok_b.any():
        r = _quiet(_wbgt, twb=twb[ok_b], tg=globe[ok_b], tdb=tdb[ok_b], with_solar_load=True)
        wbgt_v[ok_b] = np.asarray(r.wbgt, dtype=float)

    out = []
    for i in range(n):
        missing_rad = np.isnan(tmrt[i]) and not np.isnan(tdb[i])
        # ---- UTCI
        if not math.isnan(utci_v[i]):
            u = _metric("utci", utci_v[i], category=_category("utci", utci_v[i]),
                        native=None, quality="modelled", notes=notes[i] + ["mean_radiant_temperature_estimated"],
                        mtype=mtype)
        else:
            why = ("Radiation inputs missing; mean radiant temperature cannot be estimated."
                   if missing_rad else
                   "Temperature, humidity or wind missing." if np.isnan(tdb[i]) or np.isnan(rh[i]) or np.isnan(wind[i])
                   else "Inputs outside the UTCI validity range.")
            u = _metric("utci", None, quality="unavailable" if (missing_rad or np.isnan(tdb[i]) or np.isnan(rh[i]) or np.isnan(wind[i])) else "out_of_range",
                        reason=why, mtype=mtype)
        # ---- WBGT
        if not math.isnan(wbgt_v[i]):
            w = _metric("wbgt", wbgt_v[i], category=_category("wbgt", wbgt_v[i]), quality="modelled",
                        notes=notes[i] + ["globe_temperature_estimated", "psychrometric_wet_bulb_used"], mtype=mtype)
        else:
            why = ("Radiation inputs missing; globe temperature cannot be estimated." if missing_rad
                   else "Temperature or humidity missing or outside wet-bulb validity range.")
            w = _metric("wbgt", None, quality="unavailable", reason=why, mtype=mtype)
        # ---- Heat index
        if not math.isnan(hi_v[i]):
            h = _metric("heat_index", hi_v[i], category=_category("heat_index", hi_v[i]),
                        quality="modelled", mtype=mtype)
        else:
            if np.isnan(tdb[i]) or np.isnan(rh[i]):
                q, why = "unavailable", "Temperature or humidity missing."
            else:
                q, why = "not_applicable", ("Heat index (NWS/Rothfusz) is defined only for air "
                                            "temperature ≥ 27 °C and suitable humidity.")
            h = _metric("heat_index", None, quality=q, reason=why, mtype=mtype)

        hts = human_thermal_stress({"utci": u, "wbgt": w, "heat_index": h})
        vals = lambda x: None if math.isnan(x) else round(float(x), 1)
        out.append({
            "utci": u, "wbgt": w, "heat_index": h,
            "human_thermal_stress": hts,
            "radiant_environment": {
                "mean_radiant_temperature_c": vals(tmrt[i]),
                "globe_temperature_c": vals(globe[i]),
                "wet_bulb_c": vals(twb[i]),
                "radiant_excess_c": None if math.isnan(tmrt[i]) else round(float(tmrt[i] - tdb[i]), 1),
                "method": "estimated_from_weather_and_radiation",
                "measurement": False, "quality": "modelled" if not math.isnan(tmrt[i]) else "unavailable",
            },
            "categories": {"utci": u["category"], "wbgt": w["category"], "heat_index": h["category"],
                           "human_thermal_stress": hts["level"]},
            "quality": hts["quality"],
            "method": METHOD,
        })
    return out


def compute(obs, mtype="forecast"):
    """Thermal metrics for a single normalised observation."""
    return compute_series([obs], mtype)[0]


# ------------------------------------------------------------- HTS aggregation
DRIVER_TEXT = {"utci": "UTCI", "wbgt": "Estimated WBGT", "heat_index": "Heat Index"}


def human_thermal_stress(metrics):
    """0-100 transparent index: weighted MEAN of the available normalised metric scores.

    A mean (weights renormalised over available metrics), not a sum, because the
    three inputs are correlated views of the same heat load. Persistence and
    night heat are reported separately and enter the impact-risk layer only,
    so nothing is counted twice.
    """
    avail = {k: m for k, m in metrics.items() if m.get("score") is not None}
    if not avail:
        return {"score": None, "level": None, "quality": "unavailable",
                "reason": "No thermal metric could be calculated.", "components": {}, "drivers": [],
                "method": "weighted mean of normalised UTCI, WBGT and Heat Index scores"}
    wsum = sum(cfg.HTS_WEIGHTS[k] for k in avail)
    comps, score = {}, 0.0
    for k in cfg.HTS_WEIGHTS:
        m = metrics.get(k)
        if k in avail:
            wn = cfg.HTS_WEIGHTS[k] / wsum
            pts = wn * m["score"]
            score += pts
            comps[k] = {"value": m["value"], "unit": m["unit"], "category": m["category"],
                        "score": m["score"], "weight": round(wn, 3), "points": round(pts, 1)}
        else:
            comps[k] = {"value": None, "quality": m.get("quality"), "reason": m.get("reason"),
                        "weight": 0.0, "points": 0.0}
    score = round(score, 1)
    ranked = sorted(avail.items(), key=lambda kv: -kv[1]["score"])
    drivers = [{"code": k, "label": DRIVER_TEXT[k], "value": m["value"], "unit": m["unit"],
                "category": m["category"]} for k, m in ranked
               if cfg.level_index(m["category"]) is not None and cfg.level_index(m["category"]) >= 1]
    partial = len(avail) < len(cfg.HTS_WEIGHTS)
    return {"score": score, "level": cfg.level_for_score(score), "components": comps,
            "drivers": drivers, "quality": "partial" if partial else "modelled",
            "method": "weighted mean of normalised UTCI, WBGT and Heat Index scores "
                      "(weights renormalised over available metrics; no double counting)"}

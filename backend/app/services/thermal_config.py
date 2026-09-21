"""Single source of truth for every thermal-stress threshold and weight.

Nothing in this file is a measurement. Each block says where its numbers come
from. Values marked PROVISIONAL are operational choices, not published
standards; they are exposed at /api/thermal/methodology so they can be audited
and replaced (for example with ERA5-derived local percentiles) in ONE place.
Frontend and backend read categories from API responses and never hard-code
thresholds.
"""

LEVELS = ["Low", "Moderate", "High", "Very High", "Extreme"]

# ---- Score scale (0-100) ---------------------------------------------------
# Lower bound of each level on the 0-100 scale. Same bands the existing
# rule-based risk engine already used (25/45/65/80), so scores stay comparable.
SCORE_BANDS = [(0, "Low"), (25, "Moderate"), (45, "High"), (65, "Very High"), (80, "Extreme")]

# ---- Per-metric category boundaries and score anchors -----------------------
# Each anchor list is (metric value, score). Category boundaries sit exactly on
# the anchors for 25/45/65/80, so a metric's own published category and its
# 0-100 score always agree. Between anchors, scores are linearly interpolated.
METRICS = {
    "utci": {
        "unit": "°C",
        "source": "Bröde et al. 2012, UTCI assessment scale (Int J Biometeorol 56:481)",
        # UTCI >=26 moderate, >=32 strong, >=38 very strong, >=46 extreme heat stress
        "anchors": [(9, 0), (26, 25), (32, 45), (38, 65), (46, 80), (52, 100)],
        "native_categories": ["no thermal stress", "moderate heat stress", "strong heat stress",
                              "very strong heat stress", "extreme heat stress"],
        "valid_range": {"tdb": (-50.0, 50.0), "wind_10m_mps": (0.5, 17.0)},
    },
    "wbgt": {
        "unit": "°C",
        "source": "Adapted from US Army / ACSM WBGT flag guidance (82/85/88/90 °F). "
                  "General-population outdoor guidance, not an occupational exposure limit.",
        "anchors": [(20, 0), (27.8, 25), (29.4, 45), (31.1, 65), (32.2, 80), (35, 100)],
        "valid_range": {},
    },
    "heat_index": {
        "unit": "°C",
        "source": "US National Weather Service heat-index categories (Rothfusz regression). "
                  "Defined by NWS only from about 27.0 °C (80 °F) upward; pythermalcomfort enforces 27.0 °C.",
        "anchors": [(27.0, 25), (32.2, 45), (39.4, 65), (51.7, 80), (58, 100)],
        "valid_range": {"tdb_min_c": 27.0},
    },
}

# ---- Human Thermal Stress: blend of the three metrics ------------------------
# A weighted MEAN (not a sum) of the normalised metric scores. UTCI, WBGT and
# heat index are all functions of the same temperature/humidity/wind/radiation,
# so adding them would count the same heat two or three times. A mean cannot
# exceed its largest input. Weights are renormalised over the metrics that are
# actually available for that hour.
HTS_WEIGHTS = {"utci": 0.60, "wbgt": 0.25, "heat_index": 0.15}   # PROVISIONAL

# ---- Radiant environment (estimated Tmrt / globe temperature) ---------------
RADIANT = {
    "shortwave_absorptivity": 0.70,     # standard human-body value (SOLWEIG / Lindberg)
    "longwave_emissivity": 0.97,
    "ground_albedo": 0.20,              # generic urban surface, PROVISIONAL
    "sky_and_ground_view_factor": 0.5,  # standing person, open site
    "person_height_wind_ratio": 0.577,  # (1.1 m / 10 m) ** 0.25 power-law
    "globe_diameter_m": 0.15,
    "globe_emissivity": 0.95,
    "utci_min_wind_mps": 0.5,           # lower bound of UTCI's validity range
}

# ---- Persistence -------------------------------------------------------------
PERSISTENCE = {
    "high_score": 45,        # HTS score at which an hour counts as "high stress"
    "very_high_score": 65,
    "run_high_cap_h": 8,     # hours of unbroken high stress that saturate the term
    "run_vh_cap_h": 4,
    "days_cap": 3,           # consecutive high-stress days that saturate the term
    "weights": {"run_high": 60, "run_very_high": 20, "consecutive_days": 20},  # PROVISIONAL
    "recovery_target_score": 25,   # "recovered" = HTS back to the Low band
}

# ---- Night-time heat ---------------------------------------------------------
NIGHT = {
    "start_hour": 20,        # night window 20:00 -> 06:00 local  (PROVISIONAL)
    "end_hour": 6,
    "stress_hour_score": 25, # a night hour is "stressed" once HTS reaches Moderate
                             # (== UTCI >= 26 °C, Bröde 2012 moderate heat stress)
}

# ---- Heat-health impact risk -------------------------------------------------
IMPACT = {
    # Weather-only weights (used while vulnerability data is unavailable).
    "weights": {"thermal_stress": 0.60, "persistence": 0.25, "night_heat": 0.15},  # PROVISIONAL
    # When a real vulnerability/exposure provider is connected (each index 0-1),
    # the weather-based score is scaled by 1 + gain * (2*index - 1), per factor.
    "vulnerability_gain": 0.20,
    "exposure_gain": 0.15,
    "alert_at": 65,
}

FORECAST_DAYS_SHOWN = 5


def level_for_score(score):
    if score is None:
        return None
    name = SCORE_BANDS[0][1]
    for lo, n in SCORE_BANDS:
        if score >= lo:
            name = n
    return name


def level_index(level):
    return LEVELS.index(level) if level in LEVELS else None


def score_from_value(metric, value):
    """Piecewise-linear map of a metric value onto 0-100 using its anchors."""
    if value is None:
        return None
    pts = METRICS[metric]["anchors"]
    if value <= pts[0][0]:
        return float(pts[0][1])
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return float(pts[-1][1])


def methodology():
    return {
        "levels": LEVELS, "score_bands": SCORE_BANDS, "metrics": METRICS,
        "hts_weights": HTS_WEIGHTS, "radiant": RADIANT, "persistence": PERSISTENCE,
        "night": NIGHT, "impact": IMPACT,
        "note": "Values tagged PROVISIONAL in thermal_config.py are operational choices, "
                "not published standards, and are pending calibration.",
    }

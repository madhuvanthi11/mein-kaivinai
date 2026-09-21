"""Deterministic guidance keyed off the assessed risk level.

Returned as stable codes; the frontend i18n bundle renders them in English or
Tamil. Government items are decision support for an officer to act on, never
official orders -- LABEL is shown next to them everywhere.
"""
from .. import config
from . import thermal_config as cfg
from ..data.wards import Ward

CITIZEN = {
    "Low": ["normal_precaution", "hydrate"],
    "Moderate": ["hydrate", "shade", "avoid_outdoor_peak"],
    "High": ["hydrate", "avoid_outdoor_peak", "shade", "check_vulnerable"],
    "Very High": ["avoid_outdoor_peak", "hydrate", "check_vulnerable", "symptoms"],
    "Extreme": ["stay_indoors", "hydrate", "check_vulnerable", "symptoms"],
}

GOVERNMENT = {
    "Low": ["gov_monitor"],
    "Moderate": ["gov_monitor", "gov_hydration_comms"],
    "High": ["gov_increase_monitoring", "gov_public_advisory", "gov_vulnerable_groups"],
    "Very High": ["gov_field_monitoring", "gov_cooling_water", "gov_outdoor_work_review"],
    "Extreme": ["gov_escalate_planning", "gov_emergency_coordination", "gov_cooling_water"],
}

LABEL = "AI-generated decision-support recommendations"


def for_level(level: str) -> list:
    return CITIZEN.get(level, [])


def for_ward(assessment: dict, ward: Ward) -> list:
    """Citizen guidance plus advice specific to this ward's land cover.

    Only triggers on the ward profile that is actually present, so a green
    riverside ward does not get shade-scarcity advice written for a market ward.
    """
    if not assessment:
        return []
    items = list(CITIZEN.get(assessment["level"], []))
    elevated = assessment["score"] >= 45
    if elevated and ward.green < 0.15 and ward.built_up >= 0.80:
        items.append("ward_low_shade")
    if elevated and ward.industrial >= 0.55:
        items.append("ward_industrial")
    if elevated and ward.density >= 0.85:
        items.append("ward_crowded")
    if ward.water >= 0.50 and elevated:
        items.append("ward_breeze")
    return items


def for_government(level: str, ward_profiles: list | None = None) -> list:
    """Officer actions for the worst level currently present in the city."""
    items = list(GOVERNMENT.get(level, []))
    if ward_profiles and level in ("High", "Very High", "Extreme"):
        if any(w.built_up >= 0.85 and w.green < 0.12 for w in ward_profiles):
            items.append("gov_shade_deficit_wards")
        if any(w.industrial >= 0.60 for w in ward_profiles):
            items.append("gov_outdoor_worker_wards")
    return items


# ------------------------------------------------------------------ impact-driven
URGENCY_ORDER = {"immediate": 0, "today": 1, "tonight": 2, "advance": 3, "routine": 4}


def citizen_for_impact(impact: dict, night_heat: dict | None, persistence: dict | None) -> list:
    """Citizen advisory codes from the impact level plus persistence/night evidence."""
    level = impact.get("level")
    items = list(CITIZEN.get(level, [])) if level else []
    nl = (night_heat or {}).get("level")
    if nl and cfg.level_index(nl) >= cfg.level_index(config.RECOMMEND["night_level_min"]):
        items.append("night_recovery")
    if (persistence or {}).get("consecutive_high_stress_days", 0) >= config.RECOMMEND["repeat_high_days"]:
        items.append("multi_day_heat")
    return items


def _fmt_t(t):
    return t[11:16] if t else None


def government_actions(locality: str, impact: dict, window: dict, forecast: list,
                       ward: Ward | None = None) -> list:
    """Recommendations driven by the calculated conditions. Each carries its action,
    trigger, evidence, urgency and locality. Exposure/vulnerability are unavailable,
    so every item is a GENERAL heat-action recommendation, flagged as such."""
    R = config.RECOMMEND
    out = []
    if not impact or impact.get("impact_risk") is None:
        return out
    generic = impact.get("vulnerability_data") != "available"

    def add(code, trigger, evidence, urgency):
        out.append({"code": code, "action": ACTIONS[code], "trigger": trigger, "evidence": evidence,
                    "urgency": urgency, "locality": locality, "personalised": not generic})

    pers, night = window["persistence"], window["night_heat"]
    hw = pers.get("high_stress_window")
    if hw:
        a, b = int(hw["start"][11:13]), int(hw["end"][11:13])
        if a < R["afternoon_to_h"] and b >= R["afternoon_from_h"]:
            add("shift_outdoor_work",
                "High thermal stress during the midday/afternoon hours",
                f"Human Thermal Stress ≥ high from {_fmt_t(hw['start'])} to {_fmt_t(hw['end'])}; "
                f"peak {window['max_human_thermal_stress']}/100 at {_fmt_t(window['peak_time'])}"
                + (f"; peak UTCI {window['max_utci']} °C" if window.get("max_utci") is not None else ""),
                "today")
    if pers["longest_high_stress_run_h"] >= R["persistent_run_hours"]:
        add("cooling_centres_water",
            "High thermal stress persisting for several consecutive hours",
            f"{pers['longest_high_stress_run_h']} consecutive high-stress hour(s)"
            + (f", of which {pers['longest_very_high_run_h']} very high" if pers["longest_very_high_run_h"] else ""),
            "today")
    nl = night.get("level")
    if nl and cfg.level_index(nl) >= cfg.level_index(R["night_level_min"]):
        add("night_recovery_messaging",
            "Elevated night-time heat limits overnight recovery",
            f"{night['stressed_hours']} stressed night hour(s); overnight minimum "
            f"{night['min_temperature_c']} °C; mean night stress {night['mean_thermal_stress']}/100",
            "tonight")
    hi_days = [d for d in forecast if (d.get("max_human_thermal_stress") or 0) >= cfg.PERSISTENCE["high_score"]]
    if len(hi_days) >= R["repeat_high_days"]:
        add("advance_preparedness",
            "Repeated high thermal-stress days in the forecast",
            f"{len(hi_days)} of {len(forecast)} forecast days reach high stress or worse ("
            + ", ".join(d["date"][5:] for d in hi_days) + ")",
            "advance")
    score = impact["impact_risk"]
    if score >= cfg.IMPACT["alert_at"]:
        add("escalate_review",
            "Heat-Health Impact Risk at or above the alert threshold",
            f"Impact risk {score}/100 ({impact['level']}); alert threshold {cfg.IMPACT['alert_at']}",
            "immediate" if score >= 80 else "today")
    # land-cover (model-estimated profile) refinements, as before
    if ward is not None and score >= 45:
        if ward.green < 0.15 and ward.built_up >= 0.80:
            add("shade_deficit",
                "Low-shade, highly built-up locality (indicative land-cover profile)",
                f"built-up {ward.built_up:.2f}, green cover {ward.green:.2f} (model profile)", "today")
        if ward.industrial >= 0.55:
            add("industrial_workers",
                "Industrial locality (indicative land-cover profile)",
                f"industrial {ward.industrial:.2f} (model profile)", "today")
    out.sort(key=lambda r: URGENCY_ORDER.get(r["urgency"], 9))
    return out


ACTIONS = {
    "shift_outdoor_work": "Advise shifting outdoor work away from the peak thermal-stress hours.",
    "cooling_centres_water": "Open cooling centres and ensure drinking-water access; check readiness.",
    "night_recovery_messaging": "Issue overnight cooling and recovery messaging (ventilation, hydration, check on neighbours).",
    "advance_preparedness": "Begin advance heat-preparedness across the coming days (staffing, water, health-facility readiness).",
    "escalate_review": "Review the case for a formal heat alert through the approval workflow.",
    "shade_deficit": "Prioritise temporary shade and water points in this low-shade locality.",
    "industrial_workers": "Coordinate with employers on heat schedules for industrial and outdoor workers.",
}

"""Threshold alert engine.

An alert is generated when a ward's assessed risk crosses the configured score
threshold. The alert object records what was generated; delivery status comes
back separately from the notification providers and is never assumed.
"""
from datetime import datetime, timezone

from . import risk

DEFAULT_THRESHOLD = risk.ALERT_AT


def evaluate(points: list, threshold: int = DEFAULT_THRESHOLD) -> list:
    """Wards currently at or above the threshold, worst first."""
    return [p for p in points if p["risk"]["score"] >= threshold]


def build(ward_name: str, city: str, assessment: dict, threshold: int = DEFAULT_THRESHOLD) -> dict:
    window = ""
    if assessment.get("peak_start") and assessment.get("peak_end"):
        window = f" Peak window {assessment['peak_start'][11:16]}-{assessment['peak_end'][11:16]}."
    return {
        "ward": ward_name,
        "city": city,
        "level": assessment["level"],
        "score": assessment["score"],
        "threshold": threshold,
        "message": (f"{assessment['level']} heat risk ({assessment['score']}/100) "
                    f"forecast for {ward_name}, {city}.{window}"),
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "basis": "Rule-based assessment from live Open-Meteo forecast",
    }

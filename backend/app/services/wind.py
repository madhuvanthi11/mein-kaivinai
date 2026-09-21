from collections import defaultdict
DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(deg):
    if deg is None:
        return None
    return DIRS[int(round((deg % 360) / 45.0)) % 8]


def analyze(current: dict, hourly: list) -> dict:
    w = defaultdict(float)
    for h in hourly:
        d = compass(h.get("wind_direction_deg"))
        if d:
            w[d] += h.get("wind_speed_kmh") or 0.0
    speeds = [h["wind_speed_kmh"] for h in hourly if h.get("wind_speed_kmh") is not None]
    return {"current_speed_kmh": current.get("wind_speed_kmh"), "current_direction": compass(current.get("wind_direction_deg")),
            "current_direction_deg": current.get("wind_direction_deg"), "gust_kmh": current.get("wind_gust_kmh"),
            "dominant_direction": max(w, key=w.get) if w else None,
            "max_speed_kmh": max(speeds) if speeds else None,
            "trend": [{"time": h["time"], "speed_kmh": h.get("wind_speed_kmh"), "direction": compass(h.get("wind_direction_deg"))} for h in hourly]}

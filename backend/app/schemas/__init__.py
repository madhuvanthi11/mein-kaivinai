"""Response/request shapes. Documents the contract the frontend relies on."""
from pydantic import BaseModel, Field


class LocationOut(BaseModel):
    name: str
    latitude: float
    longitude: float
    timezone: str | None = None


class CurrentOut(BaseModel):
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    dew_point_c: float | None = None
    apparent_temperature_c: float | None = None
    apparent_temperature_baseline_c: float | None = None
    uhi_offset_c: float | None = None
    wind_speed_kmh: float | None = None
    wind_direction_deg: float | None = None
    wind_gust_kmh: float | None = None
    surface_pressure_hpa: float | None = None
    precipitation_mm: float | None = None
    cloud_cover_pct: float | None = None
    solar_radiation_wm2: float | None = None


class RiskOut(BaseModel):
    score: int
    level: str
    drivers: list
    confidence: str
    peak_start: str | None = None
    peak_end: str | None = None
    peak_score: int | None = None


class AlertIn(BaseModel):
    ward_id: str | None = None
    ward: str | None = None
    city: str | None = None
    level: str
    message: str
    score: int | None = None
    threshold: int | None = None


class AlertOut(BaseModel):
    alert: dict
    delivery: list
    note: str = Field(default="Delivery status reflects what each provider actually did.")

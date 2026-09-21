"""Optional historical baseline (ERA5). Never required at startup.

The app imports this module, sees the provider is unavailable, and carries on.
No credential check, no download, no blocking call happens on import.
"""
from abc import ABC, abstractmethod

from .. import config


class HistoricalWeatherProvider(ABC):
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def temperature_baseline(self, lat: float, lon: float, month: int) -> dict | None:
        """Long-run mean temperature for the location and month."""

    @abstractmethod
    def heat_anomaly(self, lat: float, lon: float, temperature_c: float, month: int) -> dict | None:
        """Today's departure from that baseline."""

    def baseline(self, lat: float, lon: float, period: str) -> dict | None:
        """Historical thermal baseline / anomaly for a period. Return None if unknown.

        ERA5 integration point: implement this (and the abstract methods) to
        return {"status": "available", "source": "ERA5", "period": ..., "baseline": {...},
        "anomaly": {...}}. Nothing else in the application needs to change.
        """
        return None

    @abstractmethod
    def seasonal_climatology(self, lat: float, lon: float) -> dict | None: ...

    @abstractmethod
    def wind_climatology(self, lat: float, lon: float) -> dict | None: ...


class ERA5Provider(HistoricalWeatherProvider):
    """Stub. Wire to the Copernicus CDS API when credentials exist.

    Returns None rather than an estimate whenever it cannot answer, so no
    fabricated baseline can ever reach the UI.
    """

    def available(self) -> bool:
        return config.ERA5_CONFIGURED

    def temperature_baseline(self, lat, lon, month):
        return None

    def heat_anomaly(self, lat, lon, temperature_c, month):
        return None

    def seasonal_climatology(self, lat, lon):
        return None

    def wind_climatology(self, lat, lon):
        return None


class NullHistoricalProvider(HistoricalWeatherProvider):
    def available(self) -> bool:
        return False

    def temperature_baseline(self, lat, lon, month): return None
    def heat_anomaly(self, lat, lon, temperature_c, month): return None
    def seasonal_climatology(self, lat, lon): return None
    def wind_climatology(self, lat, lon): return None


_provider: HistoricalWeatherProvider = ERA5Provider() if config.ERA5_CONFIGURED else NullHistoricalProvider()


def provider() -> HistoricalWeatherProvider:
    return _provider


def status() -> dict:
    p = provider()
    return {
        "provider": type(p).__name__,
        "available": p.available(),
        "detail": ("ERA5 historical baselines available"
                   if p.available() else
                   "ERA5 not configured. Live forecasting is unaffected."),
    }


UNAVAILABLE_MESSAGE = "Historical comparison unavailable"


def get_historical_baseline(location: dict, period: str = "climatology") -> dict:
    """Ask for a historical baseline. Never fabricates: without a connected
    provider the answer is an explicit 'unavailable' record."""
    p = provider()
    lat, lon = (location or {}).get("latitude"), (location or {}).get("longitude")
    if p.available() and lat is not None and lon is not None:
        try:
            r = p.baseline(lat, lon, period)
        except Exception:  # a provider failure must not break the dashboard
            r = None
        if r:
            return r
        return {"status": "unavailable", "source": "ERA5", "period": period,
                "reason": "Provider returned no baseline for this location/period",
                "message": UNAVAILABLE_MESSAGE}
    return {"status": "unavailable", "source": "ERA5", "period": period,
            "reason": "Historical dataset not connected",
            "message": UNAVAILABLE_MESSAGE}

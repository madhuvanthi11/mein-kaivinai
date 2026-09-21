"""Extension points for calibrated health-outcome models. Deliberately disabled.

Weather alone cannot support a claim about deaths or admissions. A model needs
historical health-outcome data (for example daily all-cause mortality or heat-
related hospital admissions) to fit exposure-response curves. Until such data is
connected these classes report "unavailable" and never return a number.
"""
from abc import ABC, abstractmethod

NOT_CALIBRATED = ("Health outcome model: not yet calibrated — requires historical "
                  "health outcome data.")


class HealthOutcomeModel(ABC):
    name = "health_outcome"

    @abstractmethod
    def predict(self, thermal: dict, location_id: str | None = None) -> dict: ...


class _Disabled(HealthOutcomeModel):
    def predict(self, thermal, location_id=None):
        return {"model": self.name, "status": "unavailable", "value": None,
                "reason": NOT_CALIBRATED}


class MortalityModel(_Disabled):
    name = "mortality"


class HospitalizationModel(_Disabled):
    name = "hospitalization"


def status():
    return {"mortality": MortalityModel().predict({}), "hospitalization": HospitalizationModel().predict({}),
            "message": NOT_CALIBRATED}

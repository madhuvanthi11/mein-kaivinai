"""Mein Kaivinai API.

Hyperlocal, ward-level heat-risk intelligence for Tamil Nadu.
Weather is live from Open-Meteo on every request; nothing is fabricated.
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api.routes import router
from .api.workflow_routes import router as workflow_router

DESCRIPTION = """
Ward-level heat-risk intelligence.

* **Weather** is fetched live from Open-Meteo (free tier, no API key) and cached
  for about ten minutes per coordinate.
* **Thermal metrics** (UTCI, estimated WBGT, Heat Index) are computed with pythermalcomfort from
  Open-Meteo weather and radiation; the radiant environment is estimated, never measured.
* **Risk** is *Heat-Health Impact Risk*: thermal stress + persistence + night-time heat, a published
  deterministic rule set, not a trained model and not a mortality probability. Vulnerability,
  exposure, ERA5 history and health-outcome models are unavailable and reported as such.
* **Hyperlocal resolution** comes from a land-cover urban-heat-island adjustment
  applied on top of the live forecast, and is labelled as a model everywhere.
* **Roles** (citizen / admin / government) are enforced server-side on every
  privileged request; a 403 does not depend on the frontend hiding a button.
* **Alerts** move through an explicit state machine with an append-only audit
  trail, and cannot be issued without Government approval.
* **Delivery** is in-app. SMS is not available -- see the README on DLT.
* Optional services (Firebase, FCM, ERA5) never block startup.
"""

if config.DEV_AUTH:
    logging.getLogger("uvicorn.error").warning(
        "DEV_AUTH is ON: identities are asserted by the client (demo mode). "
        "Set DEV_AUTH=0 and configure Firebase for any real deployment.")

app = FastAPI(title="Mein Kaivinai API", version="1.0.0", description=DESCRIPTION)

origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(workflow_router)


@app.get("/health", tags=["meta"])
def health():
    return {"ok": True, "service": "mein-kaivinai"}

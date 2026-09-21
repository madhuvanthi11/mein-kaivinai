"""Runtime configuration. No secrets live here -- see .env.example."""
import os

# --- Open-Meteo (free non-commercial tier, no API key required) --------------
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Reverse geocoding (coordinates -> place name) is not part of Open-Meteo, so it
# uses OpenStreetMap's Nominatim. Free, real data, ODbL licence -- attribution is
# returned with every lookup. Nominatim's usage policy asks for an identifying
# User-Agent and at most one request per second, both of which are honoured in
# services/open_meteo.py.
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/reverse")
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT", "MeinKaivinai/1.0 (heat-risk early warning, Tamil Nadu)")
REVERSE_GEOCODE_MIN_INTERVAL = float(os.getenv("REVERSE_GEOCODE_MIN_INTERVAL", "1.0"))
FORECAST_DAYS = 7
PAST_HOURS = 24
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "12"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))   # ~10 minutes per location
MAX_CONCURRENT_FETCHES = int(os.getenv("MAX_CONCURRENT_FETCHES", "6"))

# --- Hyperlocal ---------------------------------------------------------------
# How far a searched point may sit from a registered ward centroid and still be
# treated as inside that ward. Beyond this the app runs in plain-location mode.
WARD_MATCH_RADIUS_KM = float(os.getenv("WARD_MATCH_RADIUS_KM", "6"))
DEFAULT_WARD_ID = os.getenv("DEFAULT_WARD_ID", "mdu-meenakshi")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Madurai")

# --- Optional services. Absence must never block startup. ---------------------
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
FIREBASE_CLIENT_EMAIL = os.getenv("FIREBASE_CLIENT_EMAIL", "")
FIREBASE_PRIVATE_KEY = os.getenv("FIREBASE_PRIVATE_KEY", "")
FCM_CONFIGURED = bool(FIREBASE_PROJECT_ID and FIREBASE_CLIENT_EMAIL and FIREBASE_PRIVATE_KEY)

SMS_PROVIDER_API_KEY = os.getenv("SMS_PROVIDER_API_KEY", "")
SMS_PROVIDER_SENDER_ID = os.getenv("SMS_PROVIDER_SENDER_ID", "")
SMS_CONFIGURED = bool(SMS_PROVIDER_API_KEY and SMS_PROVIDER_SENDER_ID)

ERA5_CDS_API_KEY = os.getenv("ERA5_CDS_API_KEY", "")
ERA5_CONFIGURED = bool(ERA5_CDS_API_KEY)

# --- Authentication & roles ---------------------------------------------------
# Tokens are verified against Google's public signing keys using only the
# project id. No service-account key is needed for verification.
FIREBASE_AUTH_CONFIGURED = bool(FIREBASE_PROJECT_ID)
FIREBASE_JWKS_URL = ("https://www.googleapis.com/robot/v1/metadata/x509/"
                     "securetoken@system.gserviceaccount.com")
FIREBASE_ISSUER = "https://securetoken.google.com/"

# Demo identity mode. When on, the server accepts an unsigned X-Dev-User header,
# which is what the in-app role switcher uses. Roles are still enforced
# server-side -- a citizen identity still gets 403 on an officer route -- but the
# IDENTITY behind the role is asserted by the client rather than proved, so
# anyone could claim any role. That is fine for a demo and unacceptable in
# production.
#
# It is ON by default so the three-role workflow is usable with no setup, and
# every surface says so: /api/status reports auth.mode "demo-identity", and the
# app shows a persistent banner. Set DEV_AUTH=0 to require verified Firebase
# tokens and nothing else.
DEV_AUTH = os.getenv("DEV_AUTH", "1") != "0"

# Roles are assigned out of band, never self-service. Two sources, in order:
#   1. Firebase custom claims (role, jurisdiction) set by an administrator.
#   2. This JSON registry file on the server.
ROLE_REGISTRY_PATH = os.getenv(
    "ROLE_REGISTRY_PATH",
    os.path.join(os.path.dirname(__file__), "data", "role_registry.json"))

# --- Persistence --------------------------------------------------------------
# Alerts, audit transitions, subscriptions and the in-app inbox. A JSON-file
# repository by default so the project runs with zero infrastructure; swap the
# Repository implementation for Firestore without touching callers.
STORE_PATH = os.getenv("STORE_PATH",
                       os.path.join(os.path.dirname(__file__), "..", "data", "store.json"))

# --- Delivery channels --------------------------------------------------------
# In-app is the implemented channel. SMS is deliberately deferred: transactional
# SMS in India needs DLT header + template registration under TRAI rules, which
# is an out-of-band approval process, not a coding task. See README.
IN_APP_ENABLED = True
SMS_ENABLED = os.getenv("SMS_ENABLED", "") == "1"
MAX_RECIPIENTS_PER_ALERT = int(os.getenv("MAX_RECIPIENTS_PER_ALERT", "20000"))

# --- Government recommendation triggers (PROVISIONAL operational values) --------
# Evidence for every recommendation cites the actual forecast numbers; these are
# only the trigger points, centralised so they can be reviewed.
RECOMMEND = {
    "persistent_run_hours": 4,     # consecutive high-stress hours = "persistent"
    "repeat_high_days": 2,         # high-stress days in the forecast = "repeated"
    "afternoon_from_h": 10, "afternoon_to_h": 18,
    "night_level_min": "High",
}

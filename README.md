# Mein Kaivinai

Ward-level heat-risk early warning for Tamil Nadu.

Most heat warnings are issued for a whole city. But a market ward of concrete and
tin runs several degrees hotter than a tree-lined riverside ward four kilometres
away, and the person working outdoors in the first one gets the same advisory as
the person in the second. Mein Kaivinai works at the ward, because that is the
scale at which heat actually hurts people.

**54 wards across Chennai, Madurai, Coimbatore and Tiruchirappalli.** Live weather
for every one of them.

And because a heat advisory is a public-safety action rather than a push
notification, it travels through three roles — Citizen, Admin, Government — with
an audited approval chain between them. Nothing reaches a citizen without an
approval record signed by a Government user.

---

## The three roles, in one screen each

| Role | What they get | What the server will not let them do |
|---|---|---|
| **Citizen** | Their ward's risk, peak window, forecast, wind and guidance; issued advisories; an inbox they can subscribe to per ward | Read the alert queue or anyone else's inbox |
| **Admin** | Every ward in their jurisdiction, plus system-detected alert *proposals* with the weather evidence behind each one. Verifies, edits, attaches notes, submits or rejects | **Send anything to a citizen.** There is no such route |
| **Government** | The queue of Admin-verified requests, the evidence, the Admin's notes and the full audit trail. Approves, modifies, rejects, issues, withdraws. Can raise a standalone advisory for a festival or exam day | Issue anything not already in the `approved` state |

The approval chain is an explicit state machine:

```
DRAFT ──submit──▶ SUBMITTED ──approve──▶ APPROVED ──issue──▶ ISSUED ──▶ EXPIRED
  │                   │  ▲                                                  
  └──reject──▶ REJECTED  └── modify (revised, stays in the queue)
```

Illegal edges return `409`. Every transition records who, when, what changed and
why, and the Government UI renders that trail rather than hiding it.

Full detail: `docs/roles-and-workflow.md`.

---

## What is real, and what is modelled

This distinction matters more than any feature, so it comes first.

| Layer | Source | Status |
|---|---|---|
| Current + hourly weather | Open-Meteo, fetched per ward at runtime | **Live measurement/forecast** |
| Location search | Open-Meteo Geocoding API | **Live** |
| Place name for a GPS fix | OpenStreetMap Nominatim reverse geocoding | **Live, attributed** |
| Heat-risk score 0–100 | Published deterministic rule set | **Transparent model, not ML** |
| Peak window | Computed from the actual hourly series | **Derived from live data** |
| Ward heat-island offset | Land-cover urban-heat-island model | **Model, labelled as such in the UI** |
| Ward land-cover profiles | Indicative prototype values | **Not measurements — see below** |
| Historical baselines (ERA5) | Not configured | **Absent, and optional** |
| Sign-in | Firebase ID tokens verified against Google's certificates | **Real, server-side** |
| Role and jurisdiction | Custom claims or a server-side registry | **Enforced on every request** |
| In-app advisory delivery | Written to a per-recipient inbox | **Real, and reported as "available", never "delivered"** |
| SMS delivery | Not implemented; blocked on DLT registration | **Absent, and the UI says so** |
| FCM push | Stub | **Absent, and the UI says so** |

There are no placeholder temperatures, mock forecasts, random risk values or
hardcoded peak windows anywhere in the application. When Open-Meteo cannot be
reached the app says so and shows nothing rather than inventing a number.

The risk engine is a rule set, not a trained model, and the app never claims
otherwise. Confidence is reported as `"Rule-based assessment"` rather than a
fabricated percentage.

### The one thing to review before you present

Each ward carries a land-cover profile — built-up fraction, tree cover, water
proximity, industrial presence, building density — on a 0–1 scale. These are
**indicative values compiled from open reference material** (OpenStreetMap land
use, city master plans, visual survey of satellite imagery). They are not
measurements. They live in `backend/app/data/wards.py` with the scale documented,
and they are the only part of the system that is not live data.

To replace them with real data, implement `LandCoverProvider` in
`backend/app/services/local_context.py` against Bhuvan LULC, Sentinel-2 NDVI or
Landsat thermal. Nothing downstream changes.

---

## Why a ward layer is necessary

Open-Meteo resolves weather at roughly 1–11 km. Two wards 3 km apart frequently
fall in the same grid cell and come back with **identical** weather. Putting ward
coordinates into a weather API does not, by itself, produce a hyperlocal product.

So the ward layer estimates the difference between wards from their land cover:

```
adjusted_apparent_temperature = open_meteo_apparent_temperature + uhi_offset
```

The offset warms for concrete, industry and crowding; cools for vegetation and
water; then shrinks with wind (ventilation flushes trapped heat), grows after
sunset (built surfaces release stored heat while open land has already cooled),
and is suppressed by cloud and rain.

Measured spread in Chennai at 15:00 with light wind:

```
T. Nagar          +2.17 °C     dense commercial, almost no canopy
Meenakshi Temple  +2.11 °C     dense old-city core
BHEL Township     +0.78 °C     large green township
Adyar             +0.35 °C     tree cover plus river and coast
```

Only apparent temperature is shifted. Air temperature, humidity, wind, pressure
and radiation stay exactly as Open-Meteo reported them — the model has no basis
for changing those, and a test asserts it does not.

Coefficients are published in `local_context.py` with their reasoning rather than
hidden, so they can be audited.

---

## Running it

Two terminals. Nothing else to configure.

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Admin control room is at `/admin` and the
Government desk at `/government`. Both require the matching role; without it you
get the same 403 the API returns.

### Signing in

**Out of the box: pick a role.** The sign-in page offers Citizen, Admin and
Government, with an optional display name and — for the two officer roles — a
jurisdiction. The header then carries a role switcher, so you can move between
all three views in a couple of clicks.

This is **demo identity mode**, and the distinction it rests on matters:

- **Roles are enforced.** Picking Admin does not let you issue an alert; the
  issue route is Government-only and returns 403. An officer assigned Madurai
  gets 403 on a Coimbatore ward. All of that is server-side and tested.
- **Identity is not proved.** The role is asserted by the client in a header, so
  anyone could claim any role. That is fine for a demo and unacceptable in
  production. `/api/status` reports `auth.mode: "demo-identity"`, and the
  sign-in page states it plainly.

Set `DEV_AUTH=0` to switch it off. Privileged routes then require a verified
token and nothing else.

**Verified sign-in.** Put your Firebase web config in `.env` (the
`VITE_FIREBASE_*` values) and set `FIREBASE_PROJECT_ID` for the backend — that
alone is enough to *verify* tokens, because ID tokens are checked against
Google's public certificates. No service-account key is needed. The sign-in page
then offers email, password and Google under "Sign in with a verified account".

Officer roles for real accounts are granted out of band. Either set Firebase
custom claims (`role`, `jurisdiction`), or copy
`backend/app/data/role_registry.example.json` to `role_registry.json`:

```json
{
  "admin_users":      { "officer@example.gov.in":   { "jurisdiction": ["Madurai"] } },
  "government_users": { "collector@example.gov.in": { "jurisdiction": ["Madurai"] } }
}
```

Roles are never self-service. Signing up in the app creates a citizen account.

Interactive API docs: <http://localhost:8000/docs>.

No API key, no account, no `.env` needed to see live weather. Copy
`.env.example` to `.env` only when adding Firebase, SMS or ERA5.

**Tests**

```bash
pip install -r backend/requirements.txt
python -m pytest        # 101 tests
```

---

## Acceptance test

Run these against a live network. Steps 5–17 need outbound access to
`api.open-meteo.com`.

1. Start backend, start frontend, open the app.
2. Search **Chennai**. Confirm a real request in the backend log or at
   `GET /api/status` → `cache.entries` increments.
3. Confirm actual temperature, humidity, apparent temperature and wind appear.
4. Confirm the hourly chart and the 24-hour ribbon are populated.
5. Confirm the risk score is derived from those values, and the peak window is a
   real clock range rather than a fixed 12–4 PM.
6. Switch to **Madurai**. Weather, chart, risk, map and guidance all change.
7. Open `/admin`, pick Madurai. Confirm ward ranking, and that two wards in the
   same city show different scores.
8. Change the alert threshold. The "wards above threshold" list responds.
9. Confirm the Admin page has **no send button**. The only outward action is
   *Verify and submit to Government*.
10. Sign in as Government at `/government`. The submitted alert is in the queue
    with its weather evidence and the Admin's notes. Approve it, then press
    *Issue to citizens*.
11. Confirm the delivery report reads **"Available in inbox"** for in-app and
    **"Not configured — nothing sent"** for SMS and push. Nothing anywhere says
    "sent" or "delivered".
12. Confirm the audit trail under the alert lists submit → approve → issue with
    the actor and UTC timestamp for each.
13. As a citizen, subscribe to that ward and confirm the advisory appears in the
    inbox. Sign in as a different citizen and confirm it does not.
14. Call `/api/gov/queue` as a citizen and confirm `403`. Call it signed out and
    confirm `401`.
15. Stop your network. Confirm the app shows *"Live weather data is temporarily
    unavailable. Please retry."* and displays no weather values at all.
16. Confirm ERA5 is absent (`/api/status` → `historical.available: false`) and
    everything above still worked.

---

## Project layout

```
backend/
  app/
    main.py                    FastAPI app, CORS, router
    config.py                  settings; no secrets
    api/routes.py              17 endpoints
    data/wards.py              54-ward registry + land-cover profiles
    schemas/                   response contracts
    services/
      open_meteo.py            fetch, validate, normalize. Raises, never invents.
      local_context.py         urban-heat-island model + LandCoverProvider
      risk.py                  deterministic 0-100 engine, peak detection
      wards.py                 ward orchestration, ranking, spread
      weather.py               plain-location fallback outside pilot wards
      wind.py                  direction conversion, trend, dominant direction
      recommendations.py       citizen + officer guidance by level
      alerts.py                threshold engine
      authz.py                 token verification, roles, jurisdiction
      workflow.py              alert state machine + audit trail
      delivery.py              in-app fan-out, subscriptions, inbox
      store.py                 Repository (JSON file; swap for Firestore)
      notifications.py         provider abstraction (FCM / SMS stubs)
      historical.py            optional ERA5 hook
    data/
      templates.py             versioned advisory templates, DLT id slots
      role_registry.example.json
frontend/
  src/
    pages/       Citizen.jsx, Admin.jsx, Government.jsx, SignIn.jsx
    components/  DayRibbon, HourlyChart, RiskMap, WindPanel, WardContext,
                 LocationSearch, Header, States, AlertCard, ProposalQueue,
                 CitizenAlerts
    services/    api.js
    hooks/       useLang, useSaved, useAuth
    lib/         fmt.js, firebase.js (optional, lazily loaded)
    i18n/        en.js, ta.js, index.js
docs/
tests/           101 tests
```

---

## API

All weather is proxied through FastAPI; the browser never calls Open-Meteo
directly. Responses are cached ~10 minutes per coordinate, and concurrent
callers for the same ward wait on a single request.

| Endpoint | Purpose |
|---|---|
| `GET /api/weather/current` | normalized current conditions |
| `GET /api/weather/hourly` | 7-day hourly series |
| `GET /api/weather/summary` | everything the citizen dashboard needs |
| `GET /api/risk/current` | risk score, level, drivers |
| `GET /api/risk/hourly` | hourly risk series |
| `GET /api/risk/peak` | computed peak window |
| `GET /api/wind/hourly` | wind trend and dominant direction |
| `GET /api/geocode` | location search |
| `GET /api/reverse-geocode` | coordinates to a place name (OpenStreetMap) |
| `GET /api/wards` | ward registry (no weather) |
| `GET /api/wards/nearest` | nearest ward to a coordinate |
| `GET /api/wards/{id}` | full hyperlocal ward view |
| `GET /api/wards/{id}/context` | why the ward runs hot or cool |
| `GET /api/monitor/city` | live ward-by-ward monitoring, ranked |
| `POST /api/alerts/broadcast` | legacy direct dispatch (kept for older clients) |
| `POST /api/alerts/ward/{id}` | build an alert from the live assessment |
| `GET /api/me` | who the server thinks you are, and your role |
| `GET /api/admin/proposals` | Admin queue; detects new threshold crossings |
| `POST /api/admin/proposals/{id}/submit` | verify and forward to Government |
| `POST /api/admin/proposals/{id}/reject` | reject with a recorded reason |
| `GET /api/gov/queue` | Government queue, with audit trails |
| `POST /api/gov/alerts/{id}/approve` | approve |
| `POST /api/gov/alerts/{id}/modify` | revise wording or ward list |
| `POST /api/gov/alerts/{id}/reject` | reject with a recorded reason |
| `POST /api/gov/alerts/{id}/issue` | **the only route that reaches citizens** |
| `POST /api/gov/alerts/{id}/expire` | withdraw an issued advisory |
| `POST /api/gov/advisories` | standalone advisory (festival, exam day) |
| `GET /api/templates` | advisory template catalogue |
| `GET /api/alerts/feed/{ward_id}` | issued advisories for a ward (public) |
| `GET /api/alerts/record/{id}` | full record + audit trail (officers only) |
| `GET /api/notifications` | citizen inbox |
| `POST /api/notifications/{id}/read` | mark read |
| `GET /api/subscriptions/me` | what is stored for you |
| `POST /api/subscriptions` | subscribe wards (explicit consent required) |
| `DELETE /api/subscriptions` | delete it |
| `GET /api/status` | what is live, what is switched off |
| `GET /health` | liveness |

Failure behaviour: `503` with *"Live weather data is temporarily unavailable.
Please retry."* on an Open-Meteo outage, `404` *"Location not found."* on a
geocoding miss, `422` on invalid coordinates, `401` when not signed in, `403` on
a role or jurisdiction violation, `409` on an illegal state transition.

---

## Languages

English and Tamil, both complete. Adding Hindi, Telugu, Kannada or Malayalam is
two lines in `src/i18n/index.js` plus a translated bundle; untranslated keys fall
back to English, so partial bundles are safe to ship.

Those four are deliberately absent rather than machine-translated. A garbled
safety instruction is worse than no translation.

---


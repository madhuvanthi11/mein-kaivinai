"""Three-role workflow API: detection, Admin review, Government approval, delivery.

Every route below re-checks the caller's role and jurisdiction on the server.
Nothing here trusts the frontend to have hidden a button.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..data import templates as tpl
from ..data.wards import BY_ID, CITIES
from ..services import (authz, delivery, risk, wards as ward_svc, workflow)
from ..services.authz import Principal
from ..services.open_meteo import WeatherUnavailable

router = APIRouter(prefix="/api")

UNAVAILABLE = "Live weather data is temporarily unavailable. Please retry."


# ------------------------------------------------------------------ bodies
class SubmitIn(BaseModel):
    template_id: str | None = None
    variables: dict | None = None
    ward_ids: list[str] | None = None
    admin_notes: str | None = None
    reason: str | None = None


class DecisionIn(BaseModel):
    reason: str | None = None


class ModifyIn(SubmitIn):
    level: str | None = None


class StandaloneIn(BaseModel):
    city: str
    ward_ids: list[str] = Field(default_factory=list)
    template_id: str
    variables: dict = Field(default_factory=dict)
    level: str = "Advisory"
    notes: str | None = None


class SubscribeIn(BaseModel):
    ward_ids: list[str] = Field(default_factory=list)
    consent: bool = False


# ------------------------------------------------------------------ identity
@router.get("/me", tags=["auth"])
async def me(user: Principal = Depends(authz.current_user)):
    """Who the server thinks you are. The frontend renders from this, but the
    server never takes the frontend's word for it on a privileged route."""
    return {**user.public(),
            "subscription": delivery.subscription(user.uid),
            "unread": delivery.unread_count(user.uid)}


@router.get("/templates", tags=["alerts"])
async def template_catalogue(user: Principal = Depends(authz.require_officer)):
    return tpl.catalogue()


# ------------------------------------------------------------------ detection
def _cities_for(user: Principal) -> list:
    if authz.ALL_JURISDICTIONS in user.jurisdiction:
        return list(CITIES.keys())
    return [c for c in CITIES if any(j.lower() == c.lower() for j in user.jurisdiction)]


async def _detect(city: str, threshold: int) -> list:
    """Run the live assessment and raise a DRAFT proposal per newly breaching ward.

    Deduplicated: a ward with an open proposal is not proposed again.
    """
    match = next((v for k, v in CITIES.items() if k.lower() == city.lower()), None)
    if match is None:
        return []
    points, _failed = await ward_svc.monitor(match["wards"])
    breaching = [p for p in points if p["risk"]["score"] >= threshold]
    created = []
    for p in breaching:
        ward_id = p["ward"]["id"]
        if workflow.open_proposal_exists(ward_id):
            continue
        a = p["risk"]
        window = "the afternoon"
        if a.get("peak_start") and a.get("peak_end"):
            window = f"{a['peak_start'][11:16]}-{a['peak_end'][11:16]}"
        created.append(workflow.create_proposal(
            ward_id=ward_id,
            ward=p["ward"]["name"],
            city=p["ward"]["city"],
            level=a["level"],
            score=a["score"],
            threshold=threshold,
            peak_start=a.get("peak_start"),
            peak_end=a.get("peak_end"),
            drivers=a.get("drivers", []),
            template_id="heat_warning_ward",
            variables={"level": a["level"], "ward": p["ward"]["name"],
                       "city": p["ward"]["city"], "peak_window": window,
                       "score": a["score"]},
            evidence={
                "temperature_c": p["current"].get("temperature_c"),
                "apparent_temperature_c": p["current"].get("apparent_temperature_c"),
                "apparent_temperature_baseline_c":
                    p["current"].get("apparent_temperature_baseline_c"),
                "uhi_offset_c": p.get("uhi_offset_c"),
                "relative_humidity_pct": p["current"].get("relative_humidity_pct"),
                "wind_speed_kmh": p["current"].get("wind_speed_kmh"),
                "confidence": a.get("confidence"),
                "observed_at": p.get("updated_at"),
                "source": "Open-Meteo",
            },
        ))
    return created


# ------------------------------------------------------------------ admin
@router.get("/admin/proposals", tags=["admin"])
async def admin_proposals(city: str | None = Query(None),
                          threshold: int = Query(risk.ALERT_AT, ge=0, le=100),
                          detect: bool = Query(True),
                          user: Principal = Depends(authz.require_admin)):
    """The Admin's review queue: system-generated proposals for their jurisdiction."""
    allowed = _cities_for(user)
    if city:
        authz.assert_jurisdiction(user, city)
        targets = [city]
    else:
        targets = allowed

    detected, failures = [], []
    if detect:
        for c in targets:
            try:
                detected += await _detect(c, threshold)
            except WeatherUnavailable:
                failures.append(c)

    return {
        "jurisdiction": user.jurisdiction,
        "cities": allowed,
        "threshold": threshold,
        "proposals": [workflow.with_audit(a) for a in workflow.queue(workflow.DRAFT, user)],
        "awaiting_government": workflow.queue(workflow.SUBMITTED, user),
        "recently_issued": workflow.queue(workflow.ISSUED, user)[:10],
        "newly_detected": len(detected),
        "detection_unavailable": failures,
        "label": ("Automated decision-support proposals. Not official orders. "
                  "Nothing here has been sent to any citizen."),
    }


def _load(alert_id: str, user: Principal) -> dict:
    from ..services.store import repo
    a = repo.get("alerts", alert_id)
    if a is None:
        raise HTTPException(404, "Alert not found.")
    authz.assert_jurisdiction(user, a.get("city"))
    return a


def _act(alert_id: str, action: str, user: Principal, reason=None, patch=None) -> dict:
    a = _load(alert_id, user)
    try:
        return workflow.apply(a, action, user, reason=reason, patch=patch)
    except workflow.RoleNotPermitted as exc:
        raise HTTPException(403, str(exc))
    except workflow.IllegalTransition as exc:
        raise HTTPException(409, str(exc))


@router.post("/admin/proposals/{alert_id}/submit", tags=["admin"])
async def admin_submit(alert_id: str, body: SubmitIn,
                       user: Principal = Depends(authz.require_admin)):
    """Verify and forward to Government. An Admin cannot send to citizens."""
    if body.ward_ids:
        for wid in body.ward_ids:
            w = BY_ID.get(wid)
            if w is None:
                raise HTTPException(404, f"Ward not found: {wid}")
            authz.assert_jurisdiction(user, w.city)
    if body.template_id and body.template_id not in tpl.BY_ID:
        raise HTTPException(400, "Unknown advisory template.")
    updated = _act(alert_id, "submit", user, reason=body.reason,
                   patch=body.model_dump(exclude_none=True))
    return {"alert": workflow.with_audit(updated),
            "detail": "Submitted to the Government queue. No citizen has been notified."}


@router.post("/admin/proposals/{alert_id}/reject", tags=["admin"])
async def admin_reject(alert_id: str, body: DecisionIn,
                       user: Principal = Depends(authz.require_admin)):
    if not (body.reason or "").strip():
        raise HTTPException(400, "A reason is required to reject a proposal.")
    return {"alert": workflow.with_audit(_act(alert_id, "admin_reject", user, body.reason))}


# ------------------------------------------------------------------ government
@router.get("/gov/queue", tags=["government"])
async def gov_queue(user: Principal = Depends(authz.require_government)):
    return {
        "jurisdiction": user.jurisdiction,
        "cities": _cities_for(user),
        "awaiting_review": [workflow.with_audit(a)
                            for a in workflow.queue(workflow.SUBMITTED, user)],
        "approved_not_issued": [workflow.with_audit(a)
                                for a in workflow.queue(workflow.APPROVED, user)],
        "issued": [workflow.with_audit(a) for a in workflow.queue(workflow.ISSUED, user)],
        "rejected": workflow.queue(workflow.REJECTED, user)[:20],
        "templates": tpl.catalogue(),
    }


@router.post("/gov/alerts/{alert_id}/approve", tags=["government"])
async def gov_approve(alert_id: str, body: DecisionIn,
                      user: Principal = Depends(authz.require_government)):
    return {"alert": workflow.with_audit(_act(alert_id, "approve", user, body.reason)),
            "detail": "Approved. Not yet issued -- press issue to notify citizens."}


@router.post("/gov/alerts/{alert_id}/modify", tags=["government"])
async def gov_modify(alert_id: str, body: ModifyIn,
                     user: Principal = Depends(authz.require_government)):
    if body.template_id and body.template_id not in tpl.BY_ID:
        raise HTTPException(400, "Unknown advisory template.")
    return {"alert": workflow.with_audit(
        _act(alert_id, "modify", user, body.reason, body.model_dump(exclude_none=True)))}


@router.post("/gov/alerts/{alert_id}/reject", tags=["government"])
async def gov_reject(alert_id: str, body: DecisionIn,
                     user: Principal = Depends(authz.require_government)):
    if not (body.reason or "").strip():
        raise HTTPException(400, "A reason is required to reject an alert.")
    return {"alert": workflow.with_audit(_act(alert_id, "gov_reject", user, body.reason))}


@router.post("/gov/alerts/{alert_id}/issue", tags=["government"])
async def gov_issue(alert_id: str, body: DecisionIn,
                    user: Principal = Depends(authz.require_government)):
    """Issue an approved alert. This is the only route that reaches citizens."""
    updated = _act(alert_id, "issue", user, body.reason)
    from ..services.store import repo
    updated = repo.update("alerts", alert_id, {
        "issued_by": {"uid": user.uid, "name": user.name or user.email,
                      "role": user.role},
    })
    results = delivery.dispatch(updated)
    updated = repo.update("alerts", alert_id, {"delivery": results})
    return {"alert": workflow.with_audit(updated), "delivery": results,
            "note": "Delivery status reflects what each channel actually did."}


@router.post("/gov/alerts/{alert_id}/expire", tags=["government"])
async def gov_expire(alert_id: str, body: DecisionIn,
                     user: Principal = Depends(authz.require_government)):
    return {"alert": workflow.with_audit(_act(alert_id, "expire", user, body.reason))}


@router.post("/gov/advisories", tags=["government"])
async def gov_standalone(body: StandaloneIn,
                         user: Principal = Depends(authz.require_government)):
    """A planned-event advisory with no Admin proposal behind it."""
    authz.assert_jurisdiction(user, body.city)
    if body.template_id not in tpl.BY_ID:
        raise HTTPException(400, "Unknown advisory template.")
    for wid in body.ward_ids:
        w = BY_ID.get(wid)
        if w is None:
            raise HTTPException(404, f"Ward not found: {wid}")
        authz.assert_jurisdiction(user, w.city)
    a = workflow.create_standalone(user=user, city=body.city, ward_ids=body.ward_ids,
                                   template_id=body.template_id, variables=body.variables,
                                   level=body.level, notes=body.notes)
    return {"alert": workflow.with_audit(a),
            "detail": "Created and approved. Press issue to notify citizens."}


# ------------------------------------------------------------------ shared read
@router.get("/alerts/feed/{ward_id}", tags=["alerts"])
async def ward_feed(ward_id: str):
    """Issued advisories for a ward. Public: a safety notice should not sit
    behind a login."""
    if ward_id not in BY_ID:
        raise HTTPException(404, "Ward not found.")
    items = workflow.issued_for_wards([ward_id])
    return {"ward_id": ward_id, "issued": items, "count": len(items)}


@router.get("/alerts/record/{alert_id}", tags=["alerts"])
async def alert_record(alert_id: str, user: Principal = Depends(authz.require_officer)):
    """Full record including the audit trail. Officers only."""
    return workflow.with_audit(_load(alert_id, user))


# ------------------------------------------------------------------ citizen
@router.get("/notifications", tags=["citizen"])
async def notifications_inbox(user: Principal = Depends(authz.current_user)):
    return {"items": delivery.inbox(user.uid), "unread": delivery.unread_count(user.uid)}


@router.post("/notifications/{notification_id}/read", tags=["citizen"])
async def notification_read(notification_id: str,
                            user: Principal = Depends(authz.current_user)):
    doc = delivery.mark_read(user.uid, notification_id)
    if doc is None:
        raise HTTPException(404, "Notification not found.")
    return doc


@router.get("/subscriptions/me", tags=["citizen"])
async def my_subscription(user: Principal = Depends(authz.current_user)):
    return {"subscription": delivery.subscription(user.uid),
            "stored": ("Only the ward ids you subscribed to and the time you consented. "
                       "No location history is kept.")}


@router.post("/subscriptions", tags=["citizen"])
async def subscribe(body: SubscribeIn, user: Principal = Depends(authz.current_user)):
    if not body.consent:
        raise HTTPException(400, "Explicit consent is required to enable alerts.")
    for wid in body.ward_ids:
        if wid not in BY_ID:
            raise HTTPException(404, f"Ward not found: {wid}")
    return {"subscription": delivery.subscribe(user.uid, body.ward_ids),
            "channels": ["in_app"],
            "detail": "You will receive in-app alerts for these wards. SMS is not available."}


@router.delete("/subscriptions", tags=["citizen"])
async def delete_subscription(user: Principal = Depends(authz.current_user)):
    return delivery.unsubscribe(user.uid)

"""The alert approval chain.

A heat advisory is a public-safety action, so the path from "the model noticed
something" to "a citizen was told" is an explicit state machine with an
append-only audit trail. No state can be skipped, no role can perform another
role's transition, and nothing reaches a citizen without an APPROVED record
signed by a Government user.

    DRAFT ──submit──▶ SUBMITTED ──approve──▶ APPROVED ──issue──▶ ISSUED
      │                  │  ▲                                       │
      │                  │  └──modify(revise, stays in queue)       ├─expire──▶ EXPIRED
      └──reject──▶ REJECTED ◀──reject──┘                            └─supersede▶ SUPERSEDED

Every transition records who (uid + role), when (UTC), what changed and why.
"""
from .. import config
from ..data import templates
from .store import new_id, now_utc, repo

DRAFT = "draft"
SUBMITTED = "submitted"
APPROVED = "approved"
ISSUED = "issued"
REJECTED = "rejected"
EXPIRED = "expired"
SUPERSEDED = "superseded"

STATES = (DRAFT, SUBMITTED, APPROVED, ISSUED, REJECTED, EXPIRED, SUPERSEDED)
TERMINAL = (REJECTED, EXPIRED, SUPERSEDED)

# action -> (allowed from-states, resulting state, roles permitted)
TRANSITIONS = {
    "submit":      ((DRAFT,),      SUBMITTED,  ("admin",)),
    "admin_reject": ((DRAFT,),     REJECTED,   ("admin",)),
    "approve":     ((SUBMITTED,),  APPROVED,   ("government",)),
    "modify":      ((SUBMITTED,),  SUBMITTED,  ("government",)),
    "gov_reject":  ((SUBMITTED, APPROVED), REJECTED, ("government",)),
    "issue":       ((APPROVED,),   ISSUED,     ("government",)),
    "expire":      ((ISSUED,),     EXPIRED,    ("government",)),
    "supersede":   ((ISSUED,),     SUPERSEDED, ("government",)),
    # A Government user may raise a standalone advisory with no Admin proposal
    # (festival, exam day). It still has to pass through APPROVED before issue.
    "create_standalone": ((None,), APPROVED,   ("government",)),
}


class IllegalTransition(Exception):
    """Raised when a transition is not permitted from the current state."""


class RoleNotPermitted(Exception):
    """Raised when the caller's role may not perform this transition."""


def _log(alert: dict, action: str, user, before: str | None, after: str,
         reason: str | None = None, changes: dict | None = None) -> dict:
    entry = {
        "id": new_id("txn"),
        "alert_id": alert["id"],
        "action": action,
        "from_state": before,
        "to_state": after,
        "actor_uid": user.uid,
        "actor_role": user.role,
        "actor_name": user.name or user.email,
        "at_utc": now_utc(),
        "reason": reason,
        "changes": changes or {},
    }
    repo.insert("alert_transitions", entry)
    return entry


def transitions_for(alert_id: str) -> list:
    return sorted(repo.query("alert_transitions", alert_id=alert_id),
                  key=lambda t: t["at_utc"])


def with_audit(alert: dict) -> dict:
    return {**alert, "audit": transitions_for(alert["id"])}


def _check(action: str, current: str | None, user) -> str:
    rule = TRANSITIONS.get(action)
    if rule is None:
        raise IllegalTransition(f"Unknown action '{action}'.")
    froms, after, roles = rule
    if user.role not in roles:
        raise RoleNotPermitted(
            f"The {action} action is reserved for the {' or '.join(roles)} role.")
    if current not in froms:
        raise IllegalTransition(
            f"Cannot {action} an alert in state '{current}'. "
            f"Allowed from: {', '.join(str(f) for f in froms)}.")
    return after


# ---------------------------------------------------------------- creation
def create_proposal(*, ward_id, ward, city, level, score, threshold,
                    peak_start, peak_end, drivers, template_id, variables,
                    ward_ids=None, evidence=None) -> dict:
    """A system-detected threshold crossing. Visible to Admin only.

    Created by the detector, not by a person, so it carries no actor. The first
    audited transition is the Admin's review.
    """
    doc = {
        "id": new_id("alt"),
        "state": DRAFT,
        "origin": "system_detection",
        "ward_id": ward_id,
        "ward": ward,
        "city": city,
        "ward_ids": ward_ids or ([ward_id] if ward_id else []),
        "level": level,
        "score": score,
        "threshold": threshold,
        "peak_start": peak_start,
        "peak_end": peak_end,
        "drivers": drivers or [],
        "template_id": template_id,
        "template_version": templates.BY_ID.get(template_id, {}).get("version"),
        "variables": variables,
        "message_en": templates.render(template_id, variables, "en"),
        "message_ta": templates.render(template_id, variables, "ta"),
        "admin_notes": None,
        "created_at_utc": now_utc(),
        "issued_at_utc": None,
        "basis": "Rule-based assessment from live Open-Meteo forecast",
        "label": ("Automated decision-support proposal. Not an official warning "
                  "until issued by a Government authority."),
        "evidence": evidence or {},
        "delivery": None,
    }
    return repo.insert("alerts", doc)


def create_standalone(*, user, city, ward_ids, template_id, variables,
                      level="Advisory", notes=None) -> dict:
    """A Government-raised advisory with no Admin proposal behind it."""
    _check("create_standalone", None, user)
    doc = {
        "id": new_id("alt"),
        "state": APPROVED,
        "origin": "government_standalone",
        "ward_id": ward_ids[0] if ward_ids else None,
        "ward": None,
        "city": city,
        "ward_ids": list(ward_ids or []),
        "level": level,
        "score": None,
        "threshold": None,
        "peak_start": None,
        "peak_end": None,
        "drivers": [],
        "template_id": template_id,
        "template_version": templates.BY_ID.get(template_id, {}).get("version"),
        "variables": variables,
        "message_en": templates.render(template_id, variables, "en"),
        "message_ta": templates.render(template_id, variables, "ta"),
        "admin_notes": notes,
        "created_at_utc": now_utc(),
        "issued_at_utc": None,
        "basis": "Issued by the approving authority. Not derived from a threshold crossing.",
        "label": "Official advisory once issued.",
        "evidence": {},
        "delivery": None,
    }
    repo.insert("alerts", doc)
    _log(doc, "create_standalone", user, None, APPROVED, reason=notes)
    return doc


# ---------------------------------------------------------------- transitions
def apply(alert: dict, action: str, user, *, reason: str | None = None,
          patch: dict | None = None) -> dict:
    """Validate, mutate and audit. The only way an alert changes state."""
    before = alert["state"]
    after = _check(action, before, user)

    changes = {}
    update = {"state": after}
    if patch:
        allowed = ("template_id", "variables", "ward_ids", "admin_notes", "level")
        for key in allowed:
            if key in patch and patch[key] is not None and patch[key] != alert.get(key):
                changes[key] = {"from": alert.get(key), "to": patch[key]}
                update[key] = patch[key]
        if "template_id" in update or "variables" in update:
            tid = update.get("template_id", alert["template_id"])
            variables = update.get("variables", alert["variables"])
            update["template_version"] = templates.BY_ID.get(tid, {}).get("version")
            update["message_en"] = templates.render(tid, variables, "en")
            update["message_ta"] = templates.render(tid, variables, "ta")

    if after == ISSUED:
        update["issued_at_utc"] = now_utc()
        update["label"] = ("Official advisory issued by the approving authority. "
                           "The underlying risk assessment remains automated "
                           "decision support.")

    updated = repo.update("alerts", alert["id"], update)
    _log(updated, action, user, before, after, reason=reason, changes=changes)
    return updated


# ---------------------------------------------------------------- queries
def queue(state: str, user=None) -> list:
    """Alerts in a state, newest first, filtered to the caller's jurisdiction."""
    items = repo.query("alerts", state=state)
    if user is not None:
        items = [a for a in items if user.covers(a.get("city"))]
    return sorted(items, key=lambda a: a["created_at_utc"], reverse=True)


def issued_for_wards(ward_ids: list) -> list:
    wanted = set(ward_ids)
    out = [a for a in repo.query("alerts", state=ISSUED)
           if wanted.intersection(a.get("ward_ids") or [])]
    return sorted(out, key=lambda a: a.get("issued_at_utc") or "", reverse=True)


def open_proposal_exists(ward_id: str) -> dict | None:
    """Stops the detector re-proposing the same ward on every dashboard load."""
    for a in repo.query("alerts", ward_id=ward_id):
        if a["state"] not in TERMINAL:
            return a
    return None


def status() -> dict:
    counts = {s: len(repo.query("alerts", state=s)) for s in STATES}
    return {
        "states": list(STATES),
        "counts": counts,
        "rule": ("An alert cannot be issued without an approved record signed by "
                 "a Government user."),
        "template_catalogue_version": templates.CATALOGUE_VERSION,
        "max_recipients_per_alert": config.MAX_RECIPIENTS_PER_ALERT,
    }

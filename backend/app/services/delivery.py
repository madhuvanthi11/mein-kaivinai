"""Delivery of an issued alert, and the citizen subscriptions it delivers to.

In-app is the channel that is actually implemented, so it is the only one that
ever reports anything other than "not configured".

Status vocabulary, and the distinctions it exists to preserve:

  not_configured  no credentials / no registration. Nothing was sent.
  queued          accepted by us, not yet handed to the channel.
  created         written to the recipient's inbox and available to them.
                  This is NOT proof they have seen it.
  read            the recipient opened it. Recorded when their client fetches it.
  failed          the channel rejected it. Reason included.

Note what is missing: there is no "sent" and no "delivered" for in-app,
because this server cannot observe a handset. `created` is the strongest claim
the evidence supports, and the UI shows it as "available in inbox", never as
"delivered".
"""
from .. import config
from ..data import templates
from . import notifications
from .store import new_id, now_utc, repo

NOT_CONFIGURED = "not_configured"
QUEUED = "queued"
CREATED = "created"
READ = "read"
FAILED = "failed"


# ------------------------------------------------------------- subscriptions
def subscription(uid: str) -> dict | None:
    found = repo.query("subscriptions", uid=uid)
    return found[0] if found else None


def subscribe(uid: str, ward_ids: list) -> dict:
    """Stores the ward ids a citizen asked to hear about -- not a location trail.

    A GPS fix is used for the lookup and discarded. What persists is only the
    ward the user chose to subscribe to, and they can delete it.
    """
    ward_ids = sorted(set(w for w in ward_ids if w))
    existing = subscription(uid)
    if existing:
        return repo.update("subscriptions", existing["id"],
                           {"ward_ids": ward_ids, "updated_at_utc": now_utc()})
    return repo.insert("subscriptions", {
        "id": new_id("sub"),
        "uid": uid,
        "ward_ids": ward_ids,
        "channels": ["in_app"],
        "consent_at_utc": now_utc(),
        "updated_at_utc": now_utc(),
    })


def unsubscribe(uid: str) -> dict:
    existing = subscription(uid)
    if existing:
        repo.update("subscriptions", existing["id"],
                    {"ward_ids": [], "updated_at_utc": now_utc()})
    return {"uid": uid, "ward_ids": [], "detail": "Subscription cleared."}


def recipients_for(ward_ids: list) -> list:
    wanted = set(ward_ids or [])
    if not wanted:
        return []
    return [s["uid"] for s in repo.query("subscriptions")
            if wanted.intersection(s.get("ward_ids") or [])]


# ------------------------------------------------------------- inbox
def inbox(uid: str, limit: int = 50) -> list:
    items = sorted(repo.query("notifications", uid=uid),
                   key=lambda n: n["created_at_utc"], reverse=True)
    return items[:limit]


def unread_count(uid: str) -> int:
    return sum(1 for n in repo.query("notifications", uid=uid) if not n.get("read_at_utc"))


def mark_read(uid: str, notification_id: str) -> dict | None:
    doc = repo.get("notifications", notification_id)
    if doc is None or doc["uid"] != uid:
        return None
    if doc.get("read_at_utc"):
        return doc
    return repo.update("notifications", notification_id,
                       {"read_at_utc": now_utc(), "status": READ})


# ------------------------------------------------------------- dispatch
def _in_app(alert: dict) -> dict:
    uids = recipients_for(alert.get("ward_ids") or [])
    cap = config.MAX_RECIPIENTS_PER_ALERT
    capped = len(uids) > cap
    uids = uids[:cap]

    already = {n["uid"] for n in repo.query("notifications", alert_id=alert["id"])}
    created = 0
    for uid in uids:
        if uid in already:
            continue
        repo.insert("notifications", {
            "id": new_id("ntf"),
            "uid": uid,
            "alert_id": alert["id"],
            "ward_ids": alert.get("ward_ids") or [],
            "city": alert.get("city"),
            "level": alert.get("level"),
            "message_en": alert.get("message_en"),
            "message_ta": alert.get("message_ta"),
            "issued_by": alert.get("issued_by"),
            "created_at_utc": now_utc(),
            "read_at_utc": None,
            "status": CREATED,
        })
        created += 1

    if not uids:
        return {"channel": "in_app", "status": CREATED, "recipients": 0, "created": 0,
                "delivered": False,
                "detail": ("No citizen has subscribed to these wards yet. The advisory "
                           "is still published and visible to anyone viewing the ward.")}
    detail = (f"Written to {created} subscriber inbox(es). Available to read; "
              f"this is not confirmation that anyone has opened it.")
    if capped:
        detail += f" Recipient list capped at {cap}."
    return {"channel": "in_app", "status": CREATED, "recipients": len(uids),
            "created": created, "delivered": False, "detail": detail}


def _public() -> dict:
    return {"channel": "public_feed", "status": CREATED, "delivered": False,
            "detail": ("Published to the ward's public advisory feed. Visible to any "
                       "citizen viewing an affected ward, subscribed or not.")}


def _fcm() -> dict:
    res = notifications.FCMProvider().send({})
    return {"channel": "fcm_push", "status": res["status"], "delivered": False,
            "detail": res["detail"]}


def _sms() -> dict:
    if not config.SMS_ENABLED:
        return {"channel": "sms", "status": NOT_CONFIGURED, "delivered": False,
                "detail": ("SMS delivery is switched off in this deployment. "
                           "No SMS was sent. " + templates.SMS_NOTE)}
    res = notifications.providers()[-1].send({})
    return {"channel": "sms", "status": res["status"], "delivered": False,
            "detail": res["detail"]}


def dispatch(alert: dict) -> list:
    """Fan an issued alert out across channels and report what each one did."""
    return [_in_app(alert), _public(), _fcm(), _sms()]


def status() -> dict:
    return {
        "channels": {
            "in_app": {"implemented": True,
                       "detail": "Writes to the recipient's inbox. Reports 'created', "
                                 "never 'delivered'."},
            "public_feed": {"implemented": True,
                            "detail": "Issued advisories are readable on the ward view."},
            "fcm_push": {"implemented": False, "detail": "Firebase Cloud Messaging is not wired."},
            "sms": {"implemented": False, "enabled": config.SMS_ENABLED,
                    "detail": templates.SMS_NOTE},
        },
        "vocabulary": {
            "not_configured": "No credentials or registration. Nothing was sent.",
            "queued": "Accepted by this system, not yet handed to the channel.",
            "created": "Written to the recipient's inbox. Not proof it was seen.",
            "read": "The recipient opened it.",
            "failed": "The channel rejected it.",
        },
        "subscriptions": len(repo.query("subscriptions")),
    }

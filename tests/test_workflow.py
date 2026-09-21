"""Roles, the approval chain, jurisdiction scoping and delivery honesty.

These run against the dev authenticator (DEV_AUTH=1, set in conftest). The role
checks under test are the real server-side ones -- the dev path only supplies
an identity, it does not bypass `require_role` or `assert_jurisdiction`.
"""
import pytest

from conftest import as_role

CITIZEN = as_role("cit1", "citizen")
ADMIN_MDU = as_role("adm1", "admin", "Madurai")
ADMIN_CBE = as_role("adm2", "admin", "Coimbatore")
GOV_MDU = as_role("gov1", "government", "Madurai")
GOV_ALL = as_role("gov2", "government", "all")


def proposals(client, headers=ADMIN_MDU, city="Madurai", threshold=0):
    r = client.get(f"/api/admin/proposals?city={city}&threshold={threshold}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def first_proposal(client):
    return proposals(client)["proposals"][0]


# ------------------------------------------------------------------ identity
def test_unauthenticated_privileged_request_is_401(client):
    assert client.get("/api/admin/proposals").status_code == 401
    assert client.get("/api/gov/queue").status_code == 401
    assert client.get("/api/me").status_code == 401


def test_me_reports_role_and_jurisdiction(client):
    me = client.get("/api/me", headers=ADMIN_MDU).json()
    assert me["role"] == "admin"
    assert me["jurisdiction"] == ["Madurai"]
    assert me["auth_source"] == "demo-identity"


def test_status_announces_demo_identity_mode(client):
    """Demo identity mode is usable, but it must never look like real auth."""
    auth = client.get("/api/status").json()["auth"]
    assert auth["mode"] == "demo-identity"
    assert auth["demo_identities_accepted"] is True
    assert auth["verified_tokens_accepted"] is False
    assert auth["roles_enforced_server_side"] is True
    assert "DO NOT RUN THIS WAY IN PRODUCTION" in auth["warning"].upper()


def test_demo_identities_can_be_switched_off(monkeypatch, client):
    """DEV_AUTH=0 makes the header worthless; roles then need a real token."""
    from app import config
    monkeypatch.setattr(config, "DEV_AUTH", False)
    assert client.get("/api/me", headers=GOV_ALL).status_code == 401
    assert client.get("/api/gov/queue", headers=GOV_ALL).status_code == 401


# ------------------------------------------------------------------ role gates
@pytest.mark.parametrize("path", ["/api/admin/proposals", "/api/gov/queue", "/api/templates"])
def test_citizen_is_403_on_officer_routes(client, path):
    assert client.get(path, headers=CITIZEN).status_code == 403


def test_admin_cannot_use_government_routes(client):
    p = first_proposal(client)
    r = client.post(f"/api/gov/alerts/{p['id']}/approve", json={}, headers=ADMIN_MDU)
    assert r.status_code == 403


def test_government_cannot_use_admin_submit(client):
    p = first_proposal(client)
    r = client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=GOV_MDU)
    assert r.status_code == 403


def test_jurisdiction_is_enforced(client):
    """A Madurai admin cannot see or act on Coimbatore."""
    assert client.get("/api/admin/proposals?city=Coimbatore",
                      headers=ADMIN_MDU).status_code == 403
    p = first_proposal(client)
    r = client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=ADMIN_CBE)
    assert r.status_code == 403


def test_admin_queue_only_shows_own_jurisdiction(client):
    proposals(client, ADMIN_MDU, "Madurai", 0)
    proposals(client, ADMIN_CBE, "Coimbatore", 0)
    mine = proposals(client, ADMIN_MDU, "Madurai", 0)["proposals"]
    assert mine and all(a["city"] == "Madurai" for a in mine)


# ------------------------------------------------------------------ detection
def test_proposals_are_drafts_built_from_live_assessment(client):
    p = first_proposal(client)
    assert p["state"] == "draft"
    assert p["origin"] == "system_detection"
    assert isinstance(p["score"], int)
    assert p["evidence"]["source"] == "Open-Meteo"
    assert p["evidence"]["confidence"] == "Rule-based assessment"
    assert p["delivery"] is None


def test_detection_does_not_duplicate_open_proposals(client):
    first = proposals(client)
    again = proposals(client)
    assert again["newly_detected"] == 0
    assert len(again["proposals"]) == len(first["proposals"])


def test_proposal_message_comes_from_a_template(client):
    p = first_proposal(client)
    assert p["template_id"] == "heat_warning_ward"
    assert p["ward"] in p["message_en"]
    assert p["message_ta"] and p["message_ta"] != p["message_en"]


# ------------------------------------------------------------------ state machine
def test_full_chain_draft_to_issued(client):
    p = first_proposal(client)
    sub = client.post(f"/api/admin/proposals/{p['id']}/submit",
                      json={"admin_notes": "Verified against the ward map."},
                      headers=ADMIN_MDU).json()["alert"]
    assert sub["state"] == "submitted"

    app_ = client.post(f"/api/gov/alerts/{p['id']}/approve", json={"reason": "Concur."},
                       headers=GOV_MDU).json()["alert"]
    assert app_["state"] == "approved"
    assert app_["issued_at_utc"] is None

    out = client.post(f"/api/gov/alerts/{p['id']}/issue", json={}, headers=GOV_MDU).json()
    assert out["alert"]["state"] == "issued"
    assert out["alert"]["issued_at_utc"]
    assert out["alert"]["issued_by"]["role"] == "government"


def test_alert_cannot_skip_states(client):
    p = first_proposal(client)
    # draft -> issued is not a legal edge.
    assert client.post(f"/api/gov/alerts/{p['id']}/issue", json={},
                       headers=GOV_MDU).status_code == 409
    # draft -> approved is not a legal edge either.
    assert client.post(f"/api/gov/alerts/{p['id']}/approve", json={},
                       headers=GOV_MDU).status_code == 409


def test_approved_alert_cannot_be_issued_twice(client):
    p = first_proposal(client)
    client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=ADMIN_MDU)
    client.post(f"/api/gov/alerts/{p['id']}/approve", json={}, headers=GOV_MDU)
    assert client.post(f"/api/gov/alerts/{p['id']}/issue", json={},
                       headers=GOV_MDU).status_code == 200
    assert client.post(f"/api/gov/alerts/{p['id']}/issue", json={},
                       headers=GOV_MDU).status_code == 409


def test_rejection_records_a_reason_and_is_terminal(client):
    p = first_proposal(client)
    assert client.post(f"/api/admin/proposals/{p['id']}/reject", json={},
                       headers=ADMIN_MDU).status_code == 400
    a = client.post(f"/api/admin/proposals/{p['id']}/reject",
                    json={"reason": "Sensor mast shading the reading."},
                    headers=ADMIN_MDU).json()["alert"]
    assert a["state"] == "rejected"
    assert a["audit"][-1]["reason"].startswith("Sensor mast")
    assert client.post(f"/api/admin/proposals/{p['id']}/submit", json={},
                       headers=ADMIN_MDU).status_code == 409


def test_government_modify_keeps_it_in_the_queue_and_rewrites_the_message(client):
    p = first_proposal(client)
    client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=ADMIN_MDU)
    a = client.post(f"/api/gov/alerts/{p['id']}/modify",
                    json={"template_id": "heat_advisory_outdoor_workers",
                          "variables": {"ward": p["ward"], "city": "Madurai",
                                        "peak_window": "12:00-16:00"},
                          "reason": "Targeting outdoor workers."},
                    headers=GOV_MDU).json()["alert"]
    assert a["state"] == "submitted"
    assert "Outdoor work" in a["message_en"]


def test_every_transition_is_audited_with_actor_and_time(client):
    p = first_proposal(client)
    client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=ADMIN_MDU)
    client.post(f"/api/gov/alerts/{p['id']}/approve", json={}, headers=GOV_MDU)
    rec = client.get(f"/api/alerts/record/{p['id']}", headers=GOV_MDU).json()
    actions = [t["action"] for t in rec["audit"]]
    assert actions == ["submit", "approve"]
    for t in rec["audit"]:
        assert t["actor_uid"] and t["actor_role"] and t["at_utc"].endswith("+00:00")
    assert rec["audit"][0]["actor_role"] == "admin"
    assert rec["audit"][1]["actor_role"] == "government"


def test_standalone_advisory_still_passes_through_approved(client):
    a = client.post("/api/gov/advisories",
                    json={"city": "Madurai", "ward_ids": ["mdu-meenakshi"],
                          "template_id": "planned_event_advisory",
                          "variables": {"event": "Chithirai festival", "ward": "Meenakshi",
                                        "city": "Madurai", "date": "2026-04-20",
                                        "instruction": "Water points every 200 m."},
                          "notes": "Planned event."},
                    headers=GOV_MDU).json()["alert"]
    assert a["state"] == "approved"
    assert a["origin"] == "government_standalone"
    assert a["audit"][0]["action"] == "create_standalone"
    issued = client.post(f"/api/gov/alerts/{a['id']}/issue", json={},
                         headers=GOV_MDU).json()["alert"]
    assert issued["state"] == "issued"


def test_standalone_advisory_outside_jurisdiction_is_403(client):
    r = client.post("/api/gov/advisories",
                    json={"city": "Chennai", "ward_ids": [], "template_id": "all_clear",
                          "variables": {"ward": "x", "city": "Chennai"}},
                    headers=GOV_MDU)
    assert r.status_code == 403


# ------------------------------------------------------------------ delivery
def _issue(client):
    p = first_proposal(client)
    client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=ADMIN_MDU)
    client.post(f"/api/gov/alerts/{p['id']}/approve", json={}, headers=GOV_MDU)
    return p, client.post(f"/api/gov/alerts/{p['id']}/issue", json={}, headers=GOV_MDU).json()


def test_sms_channel_never_claims_a_message_was_sent(client):
    _p, out = _issue(client)
    sms = next(c for c in out["delivery"] if c["channel"] == "sms")
    assert sms["status"] == "not_configured"
    assert sms["delivered"] is False
    assert "no sms was sent" in sms["detail"].lower()


def test_in_app_reports_created_not_delivered(client):
    _p, out = _issue(client)
    in_app = next(c for c in out["delivery"] if c["channel"] == "in_app")
    assert in_app["status"] == "created"
    assert in_app["delivered"] is False
    # "created" means written to an inbox. It must never be dressed up as a
    # confirmed read or a handset delivery.
    assert in_app["status"] not in ("sent", "delivered", "read")


def test_no_channel_ever_reports_sent(client):
    _p, out = _issue(client)
    for channel in out["delivery"]:
        assert channel["status"] != "sent"
        assert channel["delivered"] is False


def test_subscribed_citizen_receives_the_alert_in_their_inbox(client):
    client.post("/api/subscriptions", json={"ward_ids": ["mdu-meenakshi"], "consent": True},
                headers=CITIZEN)
    _p, out = _issue(client)
    in_app = next(c for c in out["delivery"] if c["channel"] == "in_app")
    assert in_app["recipients"] >= 1

    inbox = client.get("/api/notifications", headers=CITIZEN).json()
    assert inbox["unread"] >= 1
    item = inbox["items"][0]
    assert item["status"] == "created"
    read = client.post(f"/api/notifications/{item['id']}/read", headers=CITIZEN).json()
    assert read["status"] == "read" and read["read_at_utc"]
    assert client.get("/api/notifications", headers=CITIZEN).json()["unread"] == 0


def test_a_citizen_cannot_read_another_citizens_inbox(client):
    client.post("/api/subscriptions", json={"ward_ids": ["mdu-meenakshi"], "consent": True},
                headers=CITIZEN)
    _issue(client)
    item = client.get("/api/notifications", headers=CITIZEN).json()["items"][0]
    other = as_role("cit2", "citizen")
    assert client.get("/api/notifications", headers=other).json()["items"] == []
    assert client.post(f"/api/notifications/{item['id']}/read",
                       headers=other).status_code == 404


def test_subscription_requires_explicit_consent(client):
    r = client.post("/api/subscriptions", json={"ward_ids": ["mdu-meenakshi"]},
                    headers=CITIZEN)
    assert r.status_code == 400


def test_subscription_stores_only_ward_ids(client):
    client.post("/api/subscriptions", json={"ward_ids": ["mdu-meenakshi"], "consent": True},
                headers=CITIZEN)
    sub = client.get("/api/subscriptions/me", headers=CITIZEN).json()["subscription"]
    assert sub["ward_ids"] == ["mdu-meenakshi"]
    assert not any(k in sub for k in ("latitude", "longitude", "history", "phone"))
    client.delete("/api/subscriptions", headers=CITIZEN)
    assert client.get("/api/subscriptions/me",
                      headers=CITIZEN).json()["subscription"]["ward_ids"] == []


def test_unsubscribed_citizen_gets_nothing_in_their_inbox(client):
    _issue(client)
    assert client.get("/api/notifications", headers=CITIZEN).json()["items"] == []


def test_public_feed_shows_issued_alerts_only(client):
    p = first_proposal(client)
    feed = client.get(f"/api/alerts/feed/{p['ward_id']}").json()
    assert feed["count"] == 0          # still a draft
    client.post(f"/api/admin/proposals/{p['id']}/submit", json={}, headers=ADMIN_MDU)
    client.post(f"/api/gov/alerts/{p['id']}/approve", json={}, headers=GOV_MDU)
    assert client.get(f"/api/alerts/feed/{p['ward_id']}").json()["count"] == 0
    client.post(f"/api/gov/alerts/{p['id']}/issue", json={}, headers=GOV_MDU)
    assert client.get(f"/api/alerts/feed/{p['ward_id']}").json()["count"] == 1


def test_citizen_cannot_read_the_alert_queue(client):
    p = first_proposal(client)
    assert client.get(f"/api/alerts/record/{p['id']}", headers=CITIZEN).status_code == 403


# ------------------------------------------------------------------ honesty
def test_templates_carry_no_dlt_registration(client):
    cat = client.get("/api/templates", headers=GOV_MDU).json()
    assert all(t["dlt_template_id"] is None for t in cat["templates"])
    assert "dlt" in cat["sms_note"].lower()


def test_status_does_not_claim_sms_or_push_are_available(client):
    d = client.get("/api/status").json()["delivery"]
    assert d["channels"]["in_app"]["implemented"] is True
    assert d["channels"]["sms"]["implemented"] is False
    assert d["channels"]["fcm_push"]["implemented"] is False


def test_issued_alert_label_separates_authority_from_automation(client):
    _p, out = _issue(client)
    label = out["alert"]["label"].lower()
    assert "issued by the approving authority" in label
    assert "decision support" in label

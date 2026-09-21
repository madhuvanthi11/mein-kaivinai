# Roles and the approval chain

A heat advisory is a public-safety action. The path from "the model noticed
something" to "a citizen was told" is therefore an explicit, audited state
machine rather than a button that sends a message.

## The three roles

| Role | Sees | Can do | Cannot do |
|---|---|---|---|
| **Citizen** | Their own ward: risk, peak window, hourly forecast, wind, guidance, and any issued advisory | Subscribe a ward for in-app alerts, read their inbox, delete what is stored | See proposals, see anyone else's inbox, see the queue |
| **Admin** | Every ward dashboard in their jurisdiction, plus system-generated proposals | Verify, edit the advisory, adjust the ward list, attach notes, submit to Government, or reject with a reason | **Send anything to a citizen.** There is no such route |
| **Government** | The queue of Admin-verified requests, with the weather evidence and the Admin's notes | Approve, modify, reject, issue; raise a standalone advisory for a planned event; withdraw an issued one | Issue anything that is not in the `approved` state |

Roles are assigned out of band — Firebase custom claims set by an administrator,
or the server-side registry at `backend/app/data/role_registry.json`. Signing up
through the app creates a citizen account and nothing else.

## The state machine

```
  system detects threshold crossing
          │
          ▼
       DRAFT ────────────────────► visible to Admin only
          │
     Admin verifies / edits ──── Admin rejects ──► REJECTED (reason recorded)
          │
          ▼
    SUBMITTED ──────────────────► in the Government queue
          │
    Government reviews ───────── Govt rejects ───► REJECTED (reason recorded)
          │            └───────── Govt modifies ─► SUBMITTED (revised, stays queued)
          ▼
     APPROVED
          │
        issue
          ▼
      ISSUED ───────────────────► delivery attempted, per-channel result recorded
          │
          ▼
   EXPIRED / SUPERSEDED
```

Illegal edges are rejected with `409 Conflict`. `DRAFT → ISSUED` and
`DRAFT → APPROVED` are both tested as failures.

Every transition writes a row to `alert_transitions` carrying the actor's uid
and role, the UTC timestamp, the from/to states, the fields that changed, and
the free-text reason. The Government UI renders that trail under each alert
rather than hiding it in a log file.

## Where enforcement actually lives

`require_role` and `assert_jurisdiction` in `backend/app/services/authz.py`,
applied as FastAPI dependencies on every privileged route. Two consequences
worth stating plainly:

- A citizen calling `/api/gov/queue` gets `403` regardless of what the frontend
  rendered. The role tabs in the header are a convenience, not a boundary.
- An Admin scoped to Madurai gets `403` on a Coimbatore ward, on read and on
  write. Jurisdiction is re-checked per alert, not just per request.

`tests/test_workflow.py` asserts both, plus every illegal transition.

## Identity

Firebase ID tokens are verified server-side against Google's published x509
certificates (`securetoken@system.gserviceaccount.com`), checking signature,
audience, issuer and expiry. This needs only `FIREBASE_PROJECT_ID` — no
service-account key — so verification works with the web config alone.

### Demo identity mode

By default (`DEV_AUTH=1`) the server also accepts an unsigned
`X-Dev-User: uid|role|Area|Name` header. This is what the in-app role picker and
the header's role switcher send, and it is why the three-role workflow is usable
with no setup at all.

The line it draws is worth being precise about:

- **Role and jurisdiction rules still apply.** Every route runs the same
  `require_role` and `assert_jurisdiction` checks. Claiming Admin does not let
  you issue an alert; claiming Madurai does not let you touch Coimbatore.
- **Identity is claimed, not proved.** Anyone can assert any role. That is the
  whole of the weakness, and it is the reason this cannot ship to production.

`/api/status` reports `auth.mode = "demo-identity"` with an explicit warning
string, and the sign-in page states it in the same words.
`DEV_AUTH=0` disables it: privileged routes then require a verified token, and
`test_demo_identities_can_be_switched_off` asserts that they do.

## Delivery

See `docs/notifications.md`. Short version: in-app is implemented, SMS is not,
and the status vocabulary is careful about the difference between *written to an
inbox* and *read*.

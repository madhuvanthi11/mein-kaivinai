# Notifications

## Channels, and which of them work

| Channel | Implemented | What it does |
|---|---|---|
| **In-app inbox** | Yes | Writes a notification row per subscribed citizen. They read it in the app. |
| **Public ward feed** | Yes | Issued advisories appear on the ward view for anyone, signed in or not. A safety notice should not sit behind a login. |
| **FCM push** | No | The provider stub reports `not_configured`. Nothing is sent. |
| **SMS** | No | Not wired, and blocked on DLT registration. See below. |

## The status vocabulary

The words are chosen to keep three genuinely different things apart:

| Status | Meaning |
|---|---|
| `not_configured` | No credentials or no registration. **Nothing was sent.** |
| `queued` | Accepted by this system, not yet handed to the channel. |
| `created` | Written to the recipient's inbox and available to them. **Not proof anyone has seen it.** |
| `read` | The recipient opened it. Recorded when their client marks it read. |
| `failed` | The channel rejected it. Reason included. |

Note what is absent: there is no `sent` and no `delivered` for in-app, because
this server cannot observe a handset. `created` is the strongest claim the
evidence supports, and the UI renders it as "Available in inbox".
`test_no_channel_ever_reports_sent` asserts this across every channel.

## Why SMS is not in this build

Transactional SMS in India is governed by TRAI's DLT (Distributed Ledger
Technology) framework. Before a single message can reach a handset:

1. The **sending entity** must be registered on a DLT platform (Jio, Airtel,
   Vodafone-Idea, BSNL and others each operate one).
2. A **header** — the 6-character sender ID — must be registered and approved.
3. Every **message template** must be pre-registered and approved. Variable
   content is permitted only in the slots the template declares.
4. Unregistered templates are rejected **by the operator**, not by your code.
   A perfectly correct integration still delivers nothing.

Steps 1–3 are an approval process measured in days to weeks and require entity
documentation. That is why SMS is not in this build: it is a paperwork
dependency, not a coding one, and shipping a gateway integration that cannot
legally deliver would be worse than shipping nothing.

**What has been built anyway, so the work is not wasted:**

- Advisory text is composed from a **versioned template catalogue** with named
  variable slots (`backend/app/data/templates.py`), never free-typed. This is
  exactly the shape DLT requires.
- Each template carries a `dlt_template_id` field, currently `None` on all of
  them. `test_templates_carry_no_dlt_registration` asserts that, so the moment
  a real id is filled in, the test will say so.
- `NotificationProvider` in `services/notifications.py` still defines
  `RealSMSProvider` behind the interface. Wiring a gateway means implementing
  one `send`, not restructuring anything.
- The delivery report already has a per-channel shape with room for
  per-recipient ids and receipt callbacks.

To add SMS later: register the entity, header and these four templates; fill in
each `dlt_template_id`; implement `RealSMSProvider.send` against the gateway
sandbox; add a delivery-receipt webhook that moves a recipient from `accepted`
to `delivered` or `failed`; set `SMS_ENABLED=1`.

**Do not let a demo imply arbitrary free-text SMS will reach handsets.** It will
not.

## Citizen subscription and privacy

- Subscription requires explicit consent; `POST /api/subscriptions` without
  `consent: true` returns `400`.
- What is stored: the ward ids the citizen chose, the channel, and the consent
  timestamp. That is all.
- What is **not** stored: coordinates, location history, phone number. A GPS fix
  is used to resolve the ward and then discarded.
- The panel shows the user exactly what is held and offers a one-press delete.
- `test_subscription_stores_only_ward_ids` and
  `test_a_citizen_cannot_read_another_citizens_inbox` cover both.

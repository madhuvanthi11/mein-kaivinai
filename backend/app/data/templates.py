"""Advisory template catalogue.

Advisory text is built from a pre-registered template plus named variable
slots, never composed as free text. That structure is required for SMS in
India (a DLT-registered template id must accompany every transactional
message), and it is worth keeping for in-app delivery too: it keeps the Tamil
and English wording consistent and reviewable.

`dlt_template_id` is deliberately `None` on every entry. No template has been
registered on a DLT platform, so no SMS can be sent. The field exists so the
id can be filled in later without a schema change, and the UI reads it to
explain why SMS is unavailable.
"""

CATALOGUE_VERSION = "2026-09-21.1"

TEMPLATES = [
    {
        "id": "heat_warning_ward",
        "version": 1,
        "title": "Ward heat warning",
        "category": "warning",
        "dlt_template_id": None,
        "variables": ["level", "ward", "city", "peak_window", "score"],
        "body_en": ("{level} heat risk ({score}/100) forecast for {ward}, {city}. "
                    "Peak heat expected {peak_window}. Avoid outdoor work during "
                    "this window, drink water regularly, and check on elderly "
                    "neighbours."),
        "body_ta": ("{ward}, {city} பகுதியில் {level} வெப்ப ஆபத்து ({score}/100) "
                    "கணிக்கப்பட்டுள்ளது. {peak_window} நேரத்தில் அதிக வெப்பம். அந்த "
                    "நேரத்தில் வெளிப்புற வேலையைத் தவிர்க்கவும், அடிக்கடி தண்ணீர் "
                    "குடிக்கவும், வயதானவர்களைக் கவனிக்கவும்."),
    },
    {
        "id": "heat_advisory_outdoor_workers",
        "version": 1,
        "title": "Outdoor worker advisory",
        "category": "advisory",
        "dlt_template_id": None,
        "variables": ["ward", "city", "peak_window"],
        "body_en": ("Heat advisory for {ward}, {city}. Outdoor work should be "
                    "rescheduled away from {peak_window}. Employers must provide "
                    "shade, drinking water and rest breaks."),
        "body_ta": ("{ward}, {city} பகுதிக்கு வெப்ப அறிவுரை. {peak_window} "
                    "நேரத்தில் வெளிப்புற வேலையை ஒத்திவைக்கவும். நிழல், குடிநீர், "
                    "ஓய்வு இடைவெளி வழங்கப்பட வேண்டும்."),
    },
    {
        "id": "planned_event_advisory",
        "version": 1,
        "title": "Planned event / examination day advisory",
        "category": "advisory",
        "dlt_template_id": None,
        "variables": ["event", "ward", "city", "date", "instruction"],
        "body_en": ("Heat precautions for {event} at {ward}, {city} on {date}. "
                    "{instruction}"),
        "body_ta": ("{date} அன்று {ward}, {city} இல் நடைபெறும் {event} "
                    "நிகழ்வுக்கான வெப்ப முன்னெச்சரிக்கை. {instruction}"),
    },
    {
        "id": "all_clear",
        "version": 1,
        "title": "Advisory withdrawn",
        "category": "all_clear",
        "dlt_template_id": None,
        "variables": ["ward", "city"],
        "body_en": "The heat advisory for {ward}, {city} has been withdrawn.",
        "body_ta": "{ward}, {city} பகுதிக்கான வெப்ப அறிவுரை திரும்பப் பெறப்பட்டது.",
    },
]

BY_ID = {t["id"]: t for t in TEMPLATES}

SMS_NOTE = (
    "No template in this catalogue carries a DLT template id, so none of them "
    "can be sent as transactional SMS in India. Delivery is in-app only."
)


def render(template_id: str, variables: dict, lang: str = "en") -> str:
    """Fill a template's declared slots. Unknown slots are left visible rather
    than silently dropped, so a missing value is obvious during review."""
    tpl = BY_ID.get(template_id)
    if tpl is None:
        raise KeyError(template_id)
    body = tpl["body_ta"] if lang == "ta" else tpl["body_en"]
    for name in tpl["variables"]:
        value = variables.get(name)
        body = body.replace("{" + name + "}", str(value) if value not in (None, "") else f"[{name}]")
    return body


def catalogue() -> dict:
    return {
        "version": CATALOGUE_VERSION,
        "templates": [{k: v for k, v in t.items()} for t in TEMPLATES],
        "sms_note": SMS_NOTE,
    }

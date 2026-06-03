from sqlalchemy.orm import Session

from .models import Event


def get_funnel(db: Session, store_id: str):

    events = db.query(Event).filter(
        Event.store_id == store_id
    ).all()

    entries = set()
    zones = set()
    billing = set()

    for e in events:

        if e.is_staff:
            continue

        if e.event_type in ["ENTRY", "REENTRY"]:
            entries.add(e.visitor_id)

        if e.event_type == "ZONE_ENTER":
            zones.add(e.visitor_id)

        if e.event_type == "BILLING_QUEUE_JOIN":
            billing.add(e.visitor_id)

    purchase = len(billing)

    return {
        "entry": len(entries),
        "zone_visit": len(zones),
        "billing": len(billing),
        "purchase": purchase
    }
from sqlalchemy.orm import Session

from .models import Event


def get_metrics(db: Session, store_id: str):

    events = db.query(Event).filter(
        Event.store_id == store_id
    ).all()

    customer_events = [
        e for e in events
        if not e.is_staff
    ]

    visitors = set(
        e.visitor_id
        for e in customer_events
    )

    queue_events = [
        e for e in customer_events
        if e.event_type == "BILLING_QUEUE_JOIN"
    ]

    dwell_events = [
        e for e in customer_events
        if e.event_type == "ZONE_DWELL"
    ]

    avg_dwell = {}

    for event in dwell_events:

        zone = event.zone_id

        if zone not in avg_dwell:
            avg_dwell[zone] = []

        avg_dwell[zone].append(event.dwell_ms)

    avg_dwell = {
        k: round(sum(v) / len(v), 2)
        for k, v in avg_dwell.items()
    }

    return {
        "unique_visitors": len(visitors),
        "conversion_rate": 0,
        "avg_dwell_per_zone": avg_dwell,
        "queue_depth": len(queue_events),
        "abandonment_rate": 0
    }
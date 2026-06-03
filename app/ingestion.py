from datetime import datetime

from sqlalchemy.orm import Session

from .models import Event


def ingest_events(db: Session, events: list):

    inserted = 0
    duplicates = 0
    failed = 0

    for e in events:

        try:

            existing = db.query(Event).filter(
                Event.event_id == e["event_id"]
            ).first()

            if existing:
                duplicates += 1
                continue

            event = Event(
                event_id=e["event_id"],
                store_id=e["store_id"],
                camera_id=e["camera_id"],
                visitor_id=e["visitor_id"],
                event_type=e["event_type"],
                timestamp=datetime.fromisoformat(
                    e["timestamp"].replace("Z", "+00:00")
                ),
                zone_id=e.get("zone_id"),
                dwell_ms=e.get("dwell_ms", 0),
                is_staff=e.get("is_staff", False),
                confidence=e.get("confidence", 0.0),
                event_metadata=e.get("metadata", {})
            )

            db.add(event)

            inserted += 1

        except Exception:
            failed += 1

    db.commit()

    return {
        "received": len(events),
        "inserted": inserted,
        "duplicates": duplicates,
        "failed": failed
    }
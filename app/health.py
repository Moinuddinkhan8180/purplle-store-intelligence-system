from sqlalchemy.orm import Session

from .models import Event


def get_health(db: Session):

    latest = db.query(Event).order_by(
        Event.timestamp.desc()
    ).first()

    return {
        "status": "healthy",
        "last_event_timestamp":
            str(latest.timestamp) if latest else None,
        "stale_feed": False
    }
from sqlalchemy.orm import Session

from .models import Event


def detect_anomalies(db: Session, store_id: str):

    anomalies = []

    queue = db.query(Event).filter(
        Event.store_id == store_id,
        Event.event_type == "BILLING_QUEUE_JOIN"
    ).count()

    if queue > 10:

        anomalies.append({
            "type": "QUEUE_SPIKE",
            "severity": "WARN",
            "suggested_action":
                "Open additional billing counter"
        })

    visitors = db.query(Event).filter(
        Event.store_id == store_id,
        Event.event_type == "ENTRY"
    ).count()

    if visitors == 0:

        anomalies.append({
            "type": "DEAD_ZONE",
            "severity": "INFO",
            "suggested_action":
                "No visitor activity detected"
        })

    return anomalies
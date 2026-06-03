# app/heatmap.py

from .models import Event


def get_heatmap(db, store_id):

    events = db.query(Event).filter(
        Event.store_id == store_id
    ).all()

    zones = {}

    for e in events:

        if e.zone_id is None:
            continue

        zones.setdefault(
            e.zone_id,
            {
                "visits":0,
                "avg_dwell":0
            }
        )

        zones[e.zone_id]["visits"] += 1

        zones[e.zone_id]["avg_dwell"] += e.dwell_ms

    for zone in zones:

        visits = max(
            zones[zone]["visits"],
            1
        )

        zones[zone]["avg_dwell"] /= visits

    return zones
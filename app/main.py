from fastapi import FastAPI
from fastapi import Depends

from sqlalchemy.orm import Session

from .database import engine
from .database import get_db

from .models import Base

from .schemas import EventSchema

from .ingestion import ingest_events

from .metrics import get_metrics

from .funnel import get_funnel

from .anomalies import detect_anomalies

from .health import get_health

from .heatmap import get_heatmap

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Store Intelligence API",
    version="1.0.0"
)


@app.get("/")
def root():

    return {
        "status": "running"
    }


@app.post("/events/ingest")
def ingest(
    events: list[EventSchema],
    db: Session = Depends(get_db)
):

    payload = [
        e.model_dump()
        for e in events
    ]

    return ingest_events(
        db,
        payload
    )


@app.get("/stores/{store_id}/metrics")
def metrics(
    store_id: str,
    db: Session = Depends(get_db)
):

    return get_metrics(
        db,
        store_id
    )


@app.get("/stores/{store_id}/funnel")
def funnel(
    store_id: str,
    db: Session = Depends(get_db)
):

    return get_funnel(
        db,
        store_id
    )


@app.get("/stores/{store_id}/anomalies")
def anomalies(
    store_id: str,
    db: Session = Depends(get_db)
):

    return detect_anomalies(
        db,
        store_id
    )


@app.get("/health")
def health(
    db: Session = Depends(get_db)
):

    return get_health(db)

@app.get("/stores/{store_id}/heatmap")
def heatmap(
    store_id:str,
    db: Session = Depends(get_db)
):

    return get_heatmap(
        db,
        store_id
    )
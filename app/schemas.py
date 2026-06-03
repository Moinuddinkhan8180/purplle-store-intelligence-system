from typing import Optional

from pydantic import BaseModel


class EventSchema(BaseModel):

    event_id: str

    store_id: str

    camera_id: str

    visitor_id: str

    event_type: str

    timestamp: str

    zone_id: Optional[str] = None

    dwell_ms: int = 0

    is_staff: bool = False

    confidence: float

    metadata: dict


class IngestResponse(BaseModel):

    received: int

    inserted: int

    duplicates: int

    failed: int
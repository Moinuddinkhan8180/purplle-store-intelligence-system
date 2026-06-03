# PROMPT:
# Generate FastAPI ingest tests

# CHANGES MADE:
# Added duplicate validation

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_ingest():

    payload = [
        {
            "event_id":"1",
            "store_id":"STORE_BLR_001",
            "camera_id":"CAM_1",
            "visitor_id":"VIS_1",
            "event_type":"ENTRY",
            "timestamp":"2026-03-03T10:00:00Z",
            "zone_id":None,
            "dwell_ms":0,
            "is_staff":False,
            "confidence":0.9,
            "metadata":{}
        }
    ]

    response = client.post(
        "/events/ingest",
        json=payload
    )

    assert response.status_code == 200
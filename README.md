# Store Intelligence System

## Setup

Clone repository.

Install dependencies:

pip install -r requirements.txt

Run services:

docker compose up --build

API:

http://localhost:8000/docs

Dashboard:

streamlit run dashboard/dashboard.py

## Detection Pipeline

Run:

python pipeline/detect.py 
--video clips/entry.mp4 
--store-id STORE_BLR_001 
--camera-id CAM_ENTRY_01 
--camera-type ENTRY 
--output events.jsonl

## API Endpoints

POST /events/ingest

GET /stores/{store_id}/metrics

GET /stores/{store_id}/funnel

GET /stores/{store_id}/anomalies

GET /health

## Tests

pytest

## Architecture

YOLOv8 → Tracking → Event Generation → FastAPI → PostgreSQL → Dashboard

## Results

### Detection Pipeline

Processed CCTV footage from multiple store cameras:

* Entry Camera
* Floor/Zone Camera
* Billing Camera

Generated structured visitor events including:

* ENTRY
* EXIT
* ZONE_ENTER
* ZONE_EXIT
* BILLING_QUEUE_JOIN
* BILLING_QUEUE_EXIT

### Analytics Output

Sample Metrics:

```json
{
  "unique_visitors": 16,
  "queue_depth": 0
}
```

### System Validation

* FastAPI APIs operational
* Event ingestion successful
* SQLite persistence working
* Swagger documentation available
* Automated tests passing (3/3)

# Engineering Choices

## Choice 1: Detection Model

Options Considered:

* YOLOv8
* YOLOv9
* RT-DETR

AI Recommendation:

RT-DETR for accuracy.

Final Choice:

YOLOv8.

Reason:

Better inference speed and easier deployment under time constraints.

---

## Choice 2: Event Schema

Options Considered:

* Batch analytics
* Event-driven architecture

AI Recommendation:

Event-driven architecture.

Final Choice:

Event-driven.

Reason:

Supports real-time analytics and anomaly detection.

Direction estimation on entry cameras is heuristic-based and may occasionally emit EXIT before ENTRY during tracker initialization.
---

## Choice 3: API Architecture

Options Considered:

* Flask
* FastAPI

AI Recommendation:

FastAPI.

Final Choice:

FastAPI.

Reason:

Automatic validation, OpenAPI support, strong async ecosystem and production readiness.

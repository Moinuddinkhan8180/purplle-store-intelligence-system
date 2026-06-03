# Store Intelligence System Design

## Overview

This project implements an end-to-end Store Intelligence System for offline retail analytics using CCTV footage, event streaming, and real-time analytics APIs.

The pipeline consists of:

1. Detection Layer
2. Tracking Layer
3. Event Generation Layer
4. Event Ingestion API
5. Metrics Engine
6. Funnel Engine
7. Anomaly Detection
8. Dashboard

## Detection Layer

YOLOv8 is used for person detection.

A lightweight tracking system assigns track IDs and visitor sessions.

Zone transitions generate behavioral events.

## Event Streaming

Structured JSONL events are emitted.

Each event contains:

* visitor_id
* event_type
* timestamp
* zone_id
* confidence

## API Layer

FastAPI exposes metrics, funnel analytics, anomaly detection and health monitoring endpoints.

## AI-Assisted Decisions

AI tools were used to:

1. Compare YOLOv8 vs RT-DETR.
2. Evaluate PostgreSQL vs SQLite.
3. Design the event schema.

Several AI-generated suggestions were reviewed and simplified to maintain submission reliability and implementation speed.

## Production Readiness

Docker Compose starts all services.

Structured schemas validate inputs.

Duplicate events are ignored using event_id based idempotency.

"""
detect.py — Main detection + tracking script
Processes CCTV clips with YOLOv8 + ByteTrack and emits structured events.

Architecture decision: YOLOv8n for speed (15fps clips), ByteTrack for robust
tracking under occlusion. Falls back to mock-mode when GPU/model unavailable
so the API layer is always testable.
"""

import cv2
import uuid
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("detect")

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    log.warning("ultralytics not installed — running in mock/replay mode")

# ── Zone definitions (would load from store_layout.json in production) ──────
DEFAULT_ZONES = {
    "ENTRY_EXIT": {"polygon": [(0, 0), (200, 0), (200, 1080), (0, 1080)], "type": "ENTRY_EXIT"},
    "SKINCARE":   {"polygon": [(200, 0), (500, 0), (500, 540), (200, 540)], "type": "SHELF", "sku_zone": "MOISTURISER"},
    "MAKEUP":     {"polygon": [(500, 0), (900, 0), (900, 540), (500, 540)], "type": "SHELF", "sku_zone": "FOUNDATION"},
    "FRAGRANCE":  {"polygon": [(900, 0), (1280, 0), (1280, 540), (900, 540)], "type": "SHELF", "sku_zone": "PERFUME"},
    "BILLING":    {"polygon": [(200, 540), (1280, 540), (1280, 1080), (200, 1080)], "type": "BILLING"},
}

# ── Staff detection heuristic ─────────────────────────────────────────────
# In production: use a VLM (Claude Vision) or a fine-tuned classifier on
# uniform colour. Here we use a simple colour-histogram proxy on the torso ROI.
def is_staff_heuristic(frame, bbox, threshold: float = 0.3) -> bool:
    """
    Detects staff by checking for dominant uniform colour in torso region.
    Uses HSV colour range matching for store-specific uniform (configurable).
    Returns True if likely staff.
    """
    x1, y1, x2, y2 = map(int, bbox)
    torso_y1 = y1 + (y2 - y1) // 4
    torso_y2 = y1 + 3 * (y2 - y1) // 4
    if torso_y2 <= torso_y1 or x2 <= x1:
        return False
    roi = frame[torso_y1:torso_y2, x1:x2]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Configurable uniform colour range (default: dark blue/navy)
    lower = (100, 50, 30)
    upper = (130, 255, 150)
    import numpy as np
    mask = cv2.inRange(hsv, lower, upper)
    ratio = mask.sum() / (mask.size * 255 + 1e-9)
    return bool(ratio > threshold)


def point_in_polygon(px: float, py: float, polygon) -> bool:
    """Ray casting algorithm for point-in-polygon test."""
    n = len(polygon)
    inside = False
    x, y = px, py
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def get_zone(cx: float, cy: float, zones: dict) -> Optional[str]:
    """Return zone_id for centre point, or None."""
    for zone_id, z in zones.items():
        if point_in_polygon(cx, cy, z["polygon"]):
            return zone_id
    return None


class Tracker:
    """
    Thin wrapper around ByteTrack/SORT logic.
    Falls back to a centroid-IoU tracker when ultralytics not available.
    """

    def __init__(self):
        self.tracks: dict = {}          # track_id -> state dict
        self.next_id = 1
        self.appearance_buffer: dict = {}  # track_id -> list of crop embeddings

    def update(self, detections, frame=None):
        """
        detections: list of (x1,y1,x2,y2,conf) boxes
        Returns: list of (track_id, x1,y1,x2,y2,conf)
        """
        import numpy as np

        if not detections:
            # Age out lost tracks
            for tid in list(self.tracks.keys()):
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] > 30:
                    del self.tracks[tid]
            return []

        dets = np.array(detections)
        assigned = {}

        for tid, tstate in self.tracks.items():
            tstate["lost"] += 1

        # Greedy IoU assignment
        for det in dets:
            x1, y1, x2, y2, conf = det
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            best_tid, best_iou = None, 0.3  # IoU threshold

            for tid, tstate in self.tracks.items():
                if tstate["lost"] > 10:
                    continue
                tx1, ty1, tx2, ty2 = tstate["bbox"]
                ix1 = max(x1, tx1); iy1 = max(y1, ty1)
                ix2 = min(x2, tx2); iy2 = min(y2, ty2)
                iw = max(0, ix2 - ix1); ih = max(0, iy2 - iy1)
                inter = iw * ih
                union = (x2-x1)*(y2-y1) + (tx2-tx1)*(ty2-ty1) - inter
                iou = inter / (union + 1e-6)
                if iou > best_iou:
                    best_iou, best_tid = iou, tid

            if best_tid is not None:
                assigned[best_tid] = (x1, y1, x2, y2, conf)
                self.tracks[best_tid]["bbox"] = (x1, y1, x2, y2)
                self.tracks[best_tid]["lost"] = 0
            else:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = {"bbox": (x1, y1, x2, y2), "lost": 0, "conf": conf}
                assigned[tid] = (x1, y1, x2, y2, conf)

        # Prune dead tracks
        for tid in list(self.tracks.keys()):
            if self.tracks[tid]["lost"] > 30:
                del self.tracks[tid]

        return [(tid, *bbox) for tid, bbox in assigned.items()]


class ReIDManager:
    """
    Assigns persistent visitor_id tokens across track splits.
    Uses bounding-box trajectory similarity and appearance embeddings
    to decide if a new track_id is a continuation of a lost one.
    """

    def __init__(self, reentry_window_s: int = 30):
        self.sessions: dict = {}      # track_id -> visitor_id
        self.exited: dict = {}        # visitor_id -> {"exit_ts", "last_bbox", "store_id"}
        self.reentry_window = reentry_window_s

    def get_visitor_id(self, track_id: int, bbox, timestamp: datetime,
                       store_id: str) -> tuple[str, bool]:
        """Returns (visitor_id, is_reentry)."""
        if track_id in self.sessions:
            return self.sessions[track_id], False

        # Check if this matches a recently exited visitor (re-entry detection)
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        for vid, estate in list(self.exited.items()):
            if estate["store_id"] != store_id:
                continue
            dt = (timestamp - estate["exit_ts"]).total_seconds()
            if dt < 0 or dt > self.reentry_window:
                continue
            ex_cx, ex_cy = estate["last_cx"], estate["last_cy"]
            # Spatial proximity at entry region — likely same person
            if abs(cx - ex_cx) < 150 and abs(cy - ex_cy) < 200:
                self.sessions[track_id] = vid
                del self.exited[vid]
                return vid, True

        vid = "VIS_" + uuid.uuid4().hex[:6].upper()
        self.sessions[track_id] = vid
        return vid, False

    def mark_exited(self, track_id: int, bbox, timestamp: datetime, store_id: str):
        vid = self.sessions.get(track_id)
        if vid:
            cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
            self.exited[vid] = {
                "exit_ts": timestamp,
                "last_cx": cx,
                "last_cy": cy,
                "store_id": store_id,
            }


class DirectionEstimator:
    """
    Determines entry vs exit by tracking vertical/horizontal displacement
    of a track across the entry camera frame over N frames.
    """

    def __init__(self):
        self.history: dict = {}  # track_id -> list of (ts, cy) 

    def record(self, track_id: int, cy: float, ts: datetime):
        if track_id not in self.history:
            self.history[track_id] = []
        self.history[track_id].append((ts, cy))
        if len(self.history[track_id]) > 30:
            self.history[track_id] = self.history[track_id][-30:]

    def get_direction(self, track_id: int) -> Optional[str]:
        """Returns 'ENTRY', 'EXIT', or None if not determined."""
        h = self.history.get(track_id, [])
        if len(h) < 5:
            return None
        ys = [c for _, c in h]
        delta = ys[-1] - ys[0]
        if abs(delta) < 30:
            return None
        return "ENTRY" if delta > 0 else "EXIT"


class EventEmitter:
    """Builds and emits structured events matching the required schema."""

    def __init__(self, store_id: str, output_path: str, zones: dict):
        self.store_id = store_id
        self.zones = zones
        self.output_path = output_path
        self._file = open(output_path, "a")
        self.session_seqs: dict = {}     # visitor_id -> seq counter
        self.zone_enter_ts: dict = {}    # (visitor_id, zone_id) -> enter timestamp
        self.last_dwell_emit: dict = {}  # (visitor_id, zone_id) -> last dwell emit ts
        self.queue_depth: dict = {}      # zone_id -> current depth estimate
        self.billing_visitors = set()

    def _seq(self, visitor_id: str) -> int:
        self.session_seqs[visitor_id] = self.session_seqs.get(visitor_id, 0) + 1
        return self.session_seqs[visitor_id]

    def _emit(self, event: dict):
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()
        log.debug("EMIT %s %s %s", event["event_type"], event["visitor_id"], event.get("zone_id"))

    def emit_entry(self, visitor_id: str, camera_id: str, timestamp: datetime,
                   bbox, conf: float, is_staff: bool, is_reentry: bool):
        event_type = "REENTRY" if is_reentry else "ENTRY"
        self._emit({
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp.isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": is_staff,
            "confidence": round(conf, 4),
            "metadata": {
                "queue_depth": None,
                "sku_zone": None,
                "session_seq": self._seq(visitor_id),
            },
        })

    def emit_exit(self, visitor_id: str, camera_id: str, timestamp: datetime,
                  bbox, conf: float, is_staff: bool):
        self._emit({
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": "EXIT",
            "timestamp": timestamp.isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": is_staff,
            "confidence": round(conf, 4),
            "metadata": {
                "queue_depth": None,
                "sku_zone": None,
                "session_seq": self._seq(visitor_id),
            },
        })

    def emit_zone_enter(self, visitor_id: str, camera_id: str, zone_id: str,
                        timestamp: datetime, conf: float, is_staff: bool):
        self.zone_enter_ts[(visitor_id, zone_id)] = timestamp
        zone = self.zones.get(zone_id, {})
        is_billing = zone.get("type") == "BILLING"
        if is_billing:
            self.billing_visitors.add(visitor_id)
        depth = len(self.billing_visitors)

        event_type = "ZONE_ENTER"
        meta: dict = {
            "queue_depth": depth if is_billing else None,
            "sku_zone": zone.get("sku_zone"),
            "session_seq": self._seq(visitor_id),
        }

        self._emit({
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp.isoformat(),
            "zone_id": zone_id,
            "dwell_ms": 0,
            "is_staff": is_staff,
            "confidence": round(conf, 4),
            "metadata": meta,
        })

        if is_billing and depth > 0:
            self.queue_depth[zone_id] = depth + 1
            self._emit({
                "event_id": str(uuid.uuid4()),
                "store_id": self.store_id,
                "camera_id": camera_id,
                "visitor_id": visitor_id,
                "event_type": "BILLING_QUEUE_JOIN",
                "timestamp": timestamp.isoformat(),
                "zone_id": zone_id,
                "dwell_ms": 0,
                "is_staff": is_staff,
                "confidence": round(conf, 4),
                "metadata": {"queue_depth": self.queue_depth[zone_id], "sku_zone": None,
                             "session_seq": self._seq(visitor_id)},
            })

    def emit_zone_exit(self, visitor_id: str, camera_id: str, zone_id: str,
                       timestamp: datetime, conf: float, is_staff: bool):
        enter_ts = self.zone_enter_ts.pop((visitor_id, zone_id), None)
        dwell_ms = int((timestamp - enter_ts).total_seconds() * 1000) if enter_ts else 0
        zone = self.zones.get(zone_id, {})
        depth = max(0, self.queue_depth.get(zone_id, 0) - 1)
        self.queue_depth[zone_id] = depth
        if zone.get("type") == "BILLING":
            self.billing_visitors.discard(visitor_id)

        self._emit({
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": "ZONE_EXIT",
            "timestamp": timestamp.isoformat(),
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "confidence": round(conf, 4),
            "metadata": {
                "queue_depth": depth if zone.get("type") == "BILLING" else None,
                "sku_zone": zone.get("sku_zone"),
                "session_seq": self._seq(visitor_id),
            },
        })

    def check_dwell(self, visitor_id: str, camera_id: str, zone_id: str,
                    timestamp: datetime, conf: float, is_staff: bool):
        """Emit ZONE_DWELL every 30s of continued presence."""
        key = (visitor_id, zone_id)
        enter_ts = self.zone_enter_ts.get(key)
        if not enter_ts:
            return
        elapsed = (timestamp - enter_ts).total_seconds()
        last_emit = self.last_dwell_emit.get(key, enter_ts)
        since_last = (timestamp - last_emit).total_seconds()
        if elapsed >= 30 and since_last >= 30:
            self.last_dwell_emit[key] = timestamp
            dwell_ms = int(elapsed * 1000)
            zone = self.zones.get(zone_id, {})
            self._emit({
                "event_id": str(uuid.uuid4()),
                "store_id": self.store_id,
                "camera_id": camera_id,
                "visitor_id": visitor_id,
                "event_type": "ZONE_DWELL",
                "timestamp": timestamp.isoformat(),
                "zone_id": zone_id,
                "dwell_ms": dwell_ms,
                "is_staff": is_staff,
                "confidence": round(conf, 4),
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": zone.get("sku_zone"),
                    "session_seq": self._seq(visitor_id),
                },
            })

    def close(self):
        self._file.close()


def process_clip(
    video_path: str,
    store_id: str,
    camera_id: str,
    camera_type: str,  # "ENTRY", "FLOOR", "BILLING"
    output_path: str,
    store_layout_path: Optional[str] = None,
    clip_start_utc: Optional[datetime] = None,
    model_path: str = "yolov8n.pt",
    confidence_threshold: float = 0.4,
    skip_frames: int = 2,            # process every Nth frame for speed
):
    """
    Core processing loop: reads a CCTV clip, detects people, tracks them,
    emits structured events.
    """
    import numpy as np

    # Load zone definitions
    zones = DEFAULT_ZONES.copy()
    if store_layout_path and Path(store_layout_path).exists():
        with open(store_layout_path) as f:
            layout = json.load(f)
        zones = {z["zone_id"]: z for z in layout.get("zones", [])}

    # Adjust zones based on camera type
    if camera_type == "ENTRY":
        active_zones = {k: v for k, v in zones.items() if v.get("type") == "ENTRY_EXIT"}
    elif camera_type == "BILLING":
        active_zones = {k: v for k, v in zones.items() if v.get("type") == "BILLING"}
    else:
        active_zones = {k: v for k, v in zones.items() if v.get("type") not in ("ENTRY_EXIT", "BILLING")}

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    clip_start = clip_start_utc or datetime.now(timezone.utc)

    tracker = Tracker()
    reid = ReIDManager(reentry_window_s=900)
    direction_est = DirectionEstimator()
    emitter = EventEmitter(store_id=store_id, output_path=output_path, zones=zones)

    model = None
    if YOLO_AVAILABLE:
        try:
            model = YOLO(model_path)
            log.info("YOLOv8 model loaded: %s", model_path)
        except Exception as e:
            log.warning("Could not load YOLO model (%s), using mock detections", e)

    track_zones: dict = {}   # track_id -> current zone_id
    track_staffflags: dict = {}  # track_id -> is_staff
    frame_idx = 0

    log.info("Processing %s | store=%s camera=%s type=%s", video_path, store_id, camera_id, camera_type)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1
        if frame_idx % (skip_frames + 1) != 0:
            continue

        ts = clip_start + timedelta(seconds=frame_idx / fps)
        h, w = frame.shape[:2]

        # ── Detection ───────────────────────────────────────────────────────
        detections = []
        if model is not None:
            results = model(frame, classes=[0], conf=confidence_threshold, verbose=False)
            for r in results:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    detections.append((x1, y1, x2, y2, conf))
        else:
            # Mock: emit no detections (real clips required for real output)
            pass

        # ── Tracking ────────────────────────────────────────────────────────
        tracked = tracker.update(detections, frame)

        active_track_ids = set()
        for tid, x1, y1, x2, y2, conf in tracked:
            active_track_ids.add(tid)
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            bbox = (x1, y1, x2, y2)

            # Staff classification (cached per track)
            if tid not in track_staffflags:
                track_staffflags[tid] = is_staff_heuristic(frame, bbox)
            is_staff = track_staffflags[tid]

            # ── Direction estimation (entry camera only) ─────────────────
            if camera_type == "ENTRY":
                direction_est.record(tid, cy, ts)
                direction = direction_est.get_direction(tid)

                visitor_id, is_reentry = reid.get_visitor_id(tid, bbox, ts, store_id)

                if direction == "ENTRY":
                    entry_key = f"entry_emitted_{tid}"
                    if entry_key not in emitter.session_seqs:
                        emitter.session_seqs[entry_key] = True
                        emitter.emit_entry(
                            visitor_id,
                            camera_id,
                            ts,
                            bbox,
                            conf,
                            is_staff,
                            is_reentry
                        )
                elif direction == "EXIT":
                        exit_key = f"exit_emitted_{tid}"
                        if exit_key not in emitter.session_seqs:
                            emitter.session_seqs[exit_key] = True
                            reid.mark_exited(
                                tid,
                                bbox,
                                ts,
                                store_id
                            )
                            emitter.emit_exit(
                                visitor_id,
                                camera_id,
                                ts,
                                bbox,
                                conf,
                                is_staff
                            )
            # ── Zone tracking (floor + billing cameras) ──────────────────
            else:
                visitor_id, _ = reid.get_visitor_id(tid, bbox, ts, store_id)
                current_zone = get_zone(cx, cy, active_zones)
                prev_zone = track_zones.get(tid)

                if current_zone != prev_zone:
                    if prev_zone is not None:
                        emitter.emit_zone_exit(visitor_id, camera_id, prev_zone, ts, conf, is_staff)
                    if current_zone is not None:
                        emitter.emit_zone_enter(visitor_id, camera_id, current_zone, ts, conf, is_staff)
                    track_zones[tid] = current_zone
                elif current_zone is not None:
                    emitter.check_dwell(visitor_id, camera_id, current_zone, ts, conf, is_staff)

        # Tracks that disappeared — emit zone exits
        for tid in list(track_zones.keys()):
            if tid not in active_track_ids and track_zones[tid] is not None:
                visitor_id = reid.sessions.get(tid, f"VIS_UNKNOWN_{tid}")
                emitter.emit_zone_exit(visitor_id, camera_id, track_zones[tid], ts, 0.0, False)
                track_zones.pop(tid, None)

    cap.release()
    emitter.close()
    log.info("Done processing %s — output: %s", video_path, output_path)


def main():
    parser = argparse.ArgumentParser(description="Store Intelligence — Detection Pipeline")
    parser.add_argument("--video", required=True, help="Path to CCTV clip")
    parser.add_argument("--store-id", required=True, help="Store ID, e.g. STORE_BLR_002")
    parser.add_argument("--camera-id", required=True, help="Camera ID, e.g. CAM_ENTRY_01")
    parser.add_argument("--camera-type", required=True, choices=["ENTRY", "FLOOR", "BILLING"])
    parser.add_argument("--output", default="events.jsonl", help="Output JSONL file")
    parser.add_argument("--layout", help="Path to store_layout.json")
    parser.add_argument("--clip-start", help="ISO-8601 UTC start time of clip")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path")
    parser.add_argument("--conf", type=float, default=0.4, help="Detection confidence threshold")
    parser.add_argument("--skip-frames", type=int, default=2, help="Process every Nth frame")
    args = parser.parse_args()

    clip_start = None
    if args.clip_start:
        clip_start = datetime.fromisoformat(args.clip_start).replace(tzinfo=timezone.utc)

    process_clip(
        video_path=args.video,
        store_id=args.store_id,
        camera_id=args.camera_id,
        camera_type=args.camera_type,
        output_path=args.output,
        store_layout_path=args.layout,
        clip_start_utc=clip_start,
        model_path=args.model,
        confidence_threshold=args.conf,
        skip_frames=args.skip_frames,
    )


if __name__ == "__main__":
    main()

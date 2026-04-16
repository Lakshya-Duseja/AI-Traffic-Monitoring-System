"""
video_processor.py — headless per-frame processor for dashboard demo mode.
Returns annotated frames + violation events without needing cv2.imshow().
"""

import cv2
import numpy as np
import os
import time
from datetime import datetime
from collections import deque, defaultdict

import config as cfg
from db_manager import log_violation, log_count, log_speed
from challan_generator import generate_challan
from utils.speed_estimator import SpeedEstimator
from utils.dwell_tracker import DwellTracker
from utils.tailgating_detector import TailgatingDetector
from utils.plate_reader import read_plate

# ── Optional YOLO ─────────────────────────────────────────────────────────────
try:
    from ultralytics import YOLO
    _model = YOLO("yolov8n.pt")
    YOLO_OK = True
except Exception:
    YOLO_OK = False
    _model = None

# ── Optional DeepSORT ─────────────────────────────────────────────────────────
try:
    from deep_sort_realtime.deepsort_tracker import DeepSort
    _tracker = DeepSort(max_age=cfg.MAX_AGE, n_init=cfg.N_INIT,
                        max_iou_distance=cfg.MAX_IOU_DIST)
    SORT_OK = True
except Exception:
    SORT_OK = False
    _tracker = None

COCO_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
COLORS     = {"car": (0,200,0), "motorcycle": (200,0,200),
              "bus": (0,150,255), "truck": (0,100,200)}
VIO_COLOR  = (0, 0, 255)

# ── Module-level state (reset per video) ──────────────────────────────────────
_speed_est   = None
_dwell       = None
_tailgate    = None
_track_dirs  = {}
_frame_count = 0


def reset_state(fps: float):
    global _speed_est, _dwell, _tailgate, _track_dirs, _frame_count
    _speed_est   = SpeedEstimator(fps)
    _dwell       = DwellTracker()
    _tailgate    = TailgatingDetector()
    _track_dirs  = {}
    _frame_count = 0
    if SORT_OK and _tracker:
        # Re-instantiate tracker to clear state
        pass   # DeepSort doesn't expose a reset; new instance per video in process_video()


def _get_direction(track_id, cy):
    if track_id not in _track_dirs:
        _track_dirs[track_id] = deque(maxlen=10)
    q = _track_dirs[track_id]
    q.append(cy)
    if len(q) < 3:
        return "unknown"
    delta = q[-1] - q[0]
    if abs(delta) < cfg.DIRECTION_THRESHOLD_PX:
        return "stationary"
    return "down" if delta > 0 else "up"


def _detect(frame):
    if not YOLO_OK or _model is None:
        return []
    results = _model(frame, conf=cfg.YOLO_CONF, iou=cfg.YOLO_IOU,
                     classes=cfg.YOLO_CLASSES, verbose=False)
    dets = []
    for r in results:
        for box in r.boxes:
            x1,y1,x2,y2 = box.xyxy[0].tolist()
            dets.append([x1,y1,x2,y2, float(box.conf), int(box.cls)])
    return dets


def _draw_hud(frame, count, avg_speed, congestion, violations_this_frame):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0,0), (w,38), (10,10,10), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

    cv2.putText(frame, f"Vehicles: {count}", (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,220,0), 1)
    cv2.putText(frame, f"Avg Speed: {avg_speed:.0f} km/h", (200, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,200,255), 1)
    cv2.putText(frame, datetime.now().strftime("%H:%M:%S"), (w-100, 24),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180,180,180), 1)

    if congestion:
        cv2.rectangle(frame, (0, h-32), (w, h), (0,0,180), -1)
        cv2.putText(frame, "⚠  CONGESTION DETECTED", (10, h-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255,255,0), 2)

    # Zone lines
    for name, info in cfg.ZONES.items():
        y = info["y_range"][1]
        if y < h:
            cv2.line(frame, (0,y), (w,y), (80,80,80), 1)
            cv2.putText(frame, f"{name} limit:{info['limit']}km/h",
                        (5, y-4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (130,130,130), 1)

    # Violation ticker (bottom-left)
    for i, v in enumerate(violations_this_frame[-4:]):
        cv2.putText(frame, v, (10, h - 40 - i*18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0,200,255), 1)


def process_frame(frame, tracker, camera_id="CAM-DEMO"):
    """Process one frame. Returns (annotated_frame, list_of_violation_dicts)."""
    global _frame_count
    _frame_count += 1

    dets   = _detect(frame)
    tracks = []

    if tracker and dets:
        ds_in = [([d[0],d[1],d[2]-d[0],d[3]-d[1]], d[4], d[5]) for d in dets]
        try:
            raw = tracker.update_tracks(ds_in, frame=frame)
            for t in raw:
                if not t.is_confirmed():
                    continue
                ltrb = t.to_ltrb()
                tracks.append({"track_id": t.track_id,
                                "bbox": (ltrb[0],ltrb[1],ltrb[2],ltrb[3]),
                                "cx": (ltrb[0]+ltrb[2])/2,
                                "cy": (ltrb[1]+ltrb[3])/2,
                                "cls": getattr(t,"det_class",2)})
        except Exception:
            pass
    elif dets:
        for i,d in enumerate(dets):
            tracks.append({"track_id": i,
                           "bbox": (d[0],d[1],d[2],d[3]),
                           "cx": (d[0]+d[2])/2, "cy": (d[1]+d[3])/2,
                           "cls": d[5]})

    speeds          = []
    violation_events= []
    ticker_lines    = []
    active_list     = []

    for t in tracks:
        tid  = t["track_id"]
        cx,cy= t["cx"], t["cy"]
        bbox = t["bbox"]
        x1,y1,x2,y2 = [int(v) for v in bbox]
        vname= COCO_NAMES.get(t["cls"], "vehicle")
        color= COLORS.get(vname, (0,200,0))

        speed = _speed_est.update(tid, cx, cy)
        zone_name, limit = _speed_est.get_zone(cy)
        t["speed_kmph"] = speed
        speeds.append(speed)

        viols = []
        if speed > limit:                                          viols.append("speeding")
        direction = _get_direction(tid, cy)
        if direction not in ("unknown","stationary",cfg.ALLOWED_DIRECTION): viols.append("wrong_way")
        if _dwell.update(tid, cx, cy):                            viols.append("obstruction")

        bbox_color = VIO_COLOR if viols else color
        cv2.rectangle(frame, (x1,y1),(x2,y2), bbox_color, 2)
        label = f"#{tid} {vname} {speed:.0f}km/h"
        cv2.putText(frame, label, (x1, y1-6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, bbox_color, 1)

        for viol in viols:
            snap = _save_snap(frame, tid, viol)
            plate= read_plate(frame, bbox)
            fine = cfg.FINE_MAP.get(viol, 1000)
            log_violation(tid, plate, vname, viol, speed,
                          zone_name, fine, snap, camera_id)
            rec = {"track_id": tid, "plate": plate, "vtype": vname,
                   "violation": viol, "speed_kmph": speed,
                   "zone": zone_name, "fine_inr": fine,
                   "snapshot": snap, "camera_id": camera_id,
                   "timestamp": datetime.now().isoformat(timespec="seconds")}
            violation_events.append(rec)
            ticker_lines.append(f"[#{tid}] {viol.upper()} — {plate} — ₹{fine:,}")
            try:
                generate_challan(rec)
            except Exception:
                pass

        active_list.append(t)

    # Tailgating
    for lid, fid in _tailgate.check(active_list):
        snap = _save_snap(frame, fid, "tailgating")
        log_violation(fid,"UNKNOWN","vehicle","tailgating",0,
                      "main_road",cfg.FINE_MAP["tailgating"],snap,camera_id)
        violation_events.append({"track_id":fid,"violation":"tailgating",
                                  "fine_inr":cfg.FINE_MAP["tailgating"]})
        ticker_lines.append(f"[#{fid}] TAILGATING — ₹{cfg.FINE_MAP['tailgating']:,}")

    count     = len(tracks)
    avg_speed = float(np.mean(speeds)) if speeds else 0.0
    congestion= (count >= cfg.CONGESTION_COUNT_THRESHOLD and
                 avg_speed < cfg.CONGESTION_SPEED_THRESHOLD)

    if _frame_count % 60 == 0:
        log_count(count, avg_speed, camera_id)

    _draw_hud(frame, count, avg_speed, congestion, ticker_lines)
    return frame, violation_events


def _save_snap(frame, track_id, violation):
    os.makedirs(cfg.SNAPSHOT_DIR, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = f"{cfg.SNAPSHOT_DIR}/{violation}_{track_id}_{ts}.jpg"
    cv2.imwrite(path, frame)
    return path


def process_video(video_path: str, camera_id: str = "CAM-DEMO",
                  max_frames: int = 0, skip_frames: int = 2):
    """
    Generator — yields (annotated_frame_bytes, violation_list, progress_pct).
    Designed for Streamlit: iterate and display each yielded frame.
    skip_frames=2 means process every 2nd frame (faster preview).
    """
    from deep_sort_realtime.deepsort_tracker import DeepSort as DS
    tracker = DS(max_age=cfg.MAX_AGE, n_init=cfg.N_INIT,
                 max_iou_distance=cfg.MAX_IOU_DIST) if SORT_OK else None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return

    fps        = cap.get(cv2.CAP_PROP_FPS) or 25
    total      = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    reset_state(fps)

    fn = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        fn += 1
        if max_frames and fn > max_frames:
            break
        if fn % skip_frames != 0:
            continue

        annotated, viols = process_frame(frame, tracker, camera_id)

        # Encode to JPEG bytes for Streamlit
        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        pct = (fn / total * 100) if total else 0
        yield buf.tobytes(), viols, pct

    cap.release()

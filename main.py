"""
main.py — Smart Traffic Monitoring System
Run:  python main.py [--source 0] [--camera CAM-01] [--headless]

Features integrated:
  ✅ YOLOv5 detection
  ✅ DeepSORT tracking
  ✅ Zone-aware speed estimation
  ✅ Wrong-way detection
  ✅ Dwell / obstruction detection
  ✅ Tailgating detection
  ✅ Congestion alerts
  ✅ License plate OCR
  ✅ SQLite violation logging (deduplicated)
  ✅ PDF challan generation
  ✅ Snapshot saving
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import deque

import cv2
import numpy as np

# ── Local modules ──────────────────────────────────────────────────────────────
import config as cfg
from db_manager import init_db, log_violation, log_count, log_speed
from challan_generator import generate_challan
from utils.speed_estimator import SpeedEstimator
from utils.dwell_tracker import DwellTracker
from utils.tailgating_detector import TailgatingDetector
from utils.plate_reader import read_plate

# ── Optional heavy deps ────────────────────────────────────────────────────────
try:
    import torch
    from deep_sort_realtime.deepsort_tracker import DeepSort
    DEEPSORT_AVAILABLE = True
except ImportError:
    DEEPSORT_AVAILABLE = False
    print("[WARN] deep_sort_realtime not installed — tracking disabled.")

try:
    from ultralytics import YOLO as UltralyticsYOLO
    YOLO_BACKEND = "ultralytics"
except ImportError:
    try:
        import torch
        YOLO_BACKEND = "torch_hub"
    except ImportError:
        YOLO_BACKEND = None
        print("[WARN] No YOLO backend found — running in demo mode.")

# ─────────────────────────────────────────────────────────────────────────────
COCO_NAMES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
COLORS = {
    "car": (0, 200, 0), "motorcycle": (200, 0, 200),
    "bus": (0, 150, 255), "truck": (0, 100, 200),
}
VIOLATION_COLOR = (0, 0, 255)


# ══════════════════════════════════════════════════════════════════════════════
class TrafficMonitor:
    def __init__(self, source, camera_id="CAM-01", headless=False):
        self.source    = source
        self.camera_id = camera_id
        self.headless  = headless

        init_db()
        os.makedirs(cfg.SNAPSHOT_DIR, exist_ok=True)

        # ── Load YOLO ─────────────────────────────────────────────────────────
        self.model = self._load_yolo()

        # ── Tracker ───────────────────────────────────────────────────────────
        self.tracker = None
        if DEEPSORT_AVAILABLE:
            self.tracker = DeepSort(
                max_age=cfg.MAX_AGE,
                n_init=cfg.N_INIT,
                max_iou_distance=cfg.MAX_IOU_DIST,
            )

        # ── Sub-modules ───────────────────────────────────────────────────────
        self.dwell     = DwellTracker()
        self.tailgate  = TailgatingDetector()

        # ── State ─────────────────────────────────────────────────────────────
        self.track_dirs:   dict[int, deque]  = {}   # track_id -> recent cy
        self.active_tracks: dict[int, dict]  = {}   # track_id -> info
        self.fps           = cfg.FPS_CAP
        self.frame_count   = 0
        self.speed_est     = None                   # init after cap opens

    # ── YOLO loader ──────────────────────────────────────────────────────────
    def _load_yolo(self):
        if YOLO_BACKEND == "ultralytics":
            print("[INFO] Loading YOLOv8 via ultralytics …")
            return UltralyticsYOLO("yolov8n.pt")
        elif YOLO_BACKEND == "torch_hub":
            print("[INFO] Loading YOLOv5 via torch.hub …")
            return torch.hub.load("ultralytics/yolov5", "yolov5s", pretrained=True)
        else:
            return None

    # ── Detection → list of [x1,y1,x2,y2,conf,cls] ──────────────────────────
    def _detect(self, frame):
        if self.model is None:
            return []
        if YOLO_BACKEND == "ultralytics":
            results = self.model(frame, conf=cfg.YOLO_CONF, iou=cfg.YOLO_IOU,
                                 classes=cfg.YOLO_CLASSES, verbose=False)
            dets = []
            for r in results:
                for box in r.boxes:
                    x1,y1,x2,y2 = box.xyxy[0].tolist()
                    dets.append([x1,y1,x2,y2, float(box.conf), int(box.cls)])
            return dets
        elif YOLO_BACKEND == "torch_hub":
            res  = self.model(frame)
            dets = []
            for *xyxy, conf, cls in res.xyxy[0].tolist():
                if int(cls) in cfg.YOLO_CLASSES and conf >= cfg.YOLO_CONF:
                    dets.append([*xyxy, conf, int(cls)])
            return dets
        return []

    # ── Determine direction from cy history ──────────────────────────────────
    def _get_direction(self, track_id, cy):
        if track_id not in self.track_dirs:
            self.track_dirs[track_id] = deque(maxlen=10)
        q = self.track_dirs[track_id]
        q.append(cy)
        if len(q) < 3:
            return "unknown"
        delta = q[-1] - q[0]
        if abs(delta) < cfg.DIRECTION_THRESHOLD_PX:
            return "stationary"
        return "down" if delta > 0 else "up"

    # ── Save snapshot ─────────────────────────────────────────────────────────
    def _save_snapshot(self, frame, track_id, violation):
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{cfg.SNAPSHOT_DIR}/{violation}_{track_id}_{ts}.jpg"
        cv2.imwrite(name, frame)
        return name

    # ── Draw HUD overlay ──────────────────────────────────────────────────────
    def _draw_hud(self, frame, vehicle_count, avg_speed, congestion):
        h, w = frame.shape[:2]
        # Semi-transparent top bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 36), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        cv2.putText(frame, f"Camera: {self.camera_id}", (10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
        cv2.putText(frame, f"Vehicles: {vehicle_count}", (200, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 0), 1)
        cv2.putText(frame, f"Avg Speed: {avg_speed:.0f} km/h", (370, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1)
        cv2.putText(frame, datetime.now().strftime("%H:%M:%S"), (w - 90, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)

        if congestion:
            cv2.rectangle(frame, (0, h - 32), (w, h), (0, 0, 200), -1)
            cv2.putText(frame, "⚠  CONGESTION DETECTED", (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        # Zone lines
        for zone_name, info in cfg.ZONES.items():
            y = info["y_range"][1]
            if y < h:
                cv2.line(frame, (0, y), (w, y), (100, 100, 100), 1)
                cv2.putText(frame, f"{zone_name} limit:{info['limit']}",
                            (5, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1)

    # ── Process single frame ──────────────────────────────────────────────────
    def _process_frame(self, frame):
        dets      = self._detect(frame)
        tracks    = []

        if self.tracker and dets:
            # DeepSORT expects [[x1,y1,w,h], conf, cls]
            ds_input = [
                ([d[0], d[1], d[2]-d[0], d[3]-d[1]], d[4], d[5])
                for d in dets
            ]
            raw_tracks = self.tracker.update_tracks(ds_input, frame=frame)
            for t in raw_tracks:
                if not t.is_confirmed():
                    continue
                ltrb = t.to_ltrb()
                tracks.append({
                    "track_id": t.track_id,
                    "bbox":     (ltrb[0], ltrb[1], ltrb[2], ltrb[3]),
                    "cx": (ltrb[0]+ltrb[2])/2,
                    "cy": (ltrb[1]+ltrb[3])/2,
                    "cls": getattr(t, "det_class", 2),
                })
        elif dets:
            # No tracker — use raw dets
            for i, d in enumerate(dets):
                tracks.append({
                    "track_id": i,
                    "bbox":     (d[0], d[1], d[2], d[3]),
                    "cx": (d[0]+d[2])/2,
                    "cy": (d[1]+d[3])/2,
                    "cls": d[5],
                })

        speeds = []
        active_track_list = []

        for t in tracks:
            tid  = t["track_id"]
            cx, cy = t["cx"], t["cy"]
            bbox   = t["bbox"]
            x1,y1,x2,y2 = [int(v) for v in bbox]
            vname  = COCO_NAMES.get(t["cls"], "vehicle")
            color  = COLORS.get(vname, (0, 200, 0))

            # Speed
            speed = self.speed_est.update(tid, cx, cy)
            zone_name, limit = self.speed_est.get_zone(cy)
            t["speed_kmph"] = speed
            speeds.append(speed)

            # Log speed every 30 frames
            if self.frame_count % 30 == 0 and speed > 0:
                log_speed(tid, speed, zone_name)

            violations_this = []

            # ── Speeding ──────────────────────────────────────────────────────
            if speed > limit:
                violations_this.append("speeding")

            # ── Wrong-way ─────────────────────────────────────────────────────
            direction = self._get_direction(tid, cy)
            if direction not in ("unknown", "stationary", cfg.ALLOWED_DIRECTION):
                violations_this.append("wrong_way")

            # ── Dwell / obstruction ───────────────────────────────────────────
            if self.dwell.update(tid, cx, cy):
                violations_this.append("obstruction")

            # ── Draw bbox ─────────────────────────────────────────────────────
            bbox_color = VIOLATION_COLOR if violations_this else color
            cv2.rectangle(frame, (x1, y1), (x2, y2), bbox_color, 2)
            label = f"#{tid} {vname} {speed:.0f}km/h"
            cv2.putText(frame, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, bbox_color, 1)

            if violations_this:
                viol_text = " | ".join(violations_this).upper()
                cv2.putText(frame, viol_text, (x1, y2 + 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, VIOLATION_COLOR, 1)

            # ── Log violations ────────────────────────────────────────────────
            for viol in violations_this:
                snap  = self._save_snapshot(frame, tid, viol)
                plate = read_plate(frame, bbox)
                fine  = cfg.FINE_MAP.get(viol, 1000)
                log_violation(tid, plate, vname, viol, speed,
                              zone_name, fine, snap, self.camera_id)
                challan_data = {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "track_id": tid, "plate": plate,
                    "vtype": vname, "violation": viol,
                    "speed_kmph": speed, "zone": zone_name,
                    "fine_inr": fine, "snapshot": snap,
                    "camera_id": self.camera_id,
                }
                try:
                    generate_challan(challan_data)
                except Exception as e:
                    print(f"[WARN] Challan generation failed: {e}")

            active_track_list.append(t)

        # ── Tailgating ────────────────────────────────────────────────────────
        tail_events = self.tailgate.check(active_track_list)
        for leader_id, follower_id in tail_events:
            snap  = self._save_snapshot(frame, follower_id, "tailgating")
            log_violation(follower_id, "UNKNOWN", "vehicle", "tailgating",
                          0, "main_road", cfg.FINE_MAP["tailgating"], snap, self.camera_id)

        # ── Congestion check ──────────────────────────────────────────────────
        count     = len(tracks)
        avg_speed = float(np.mean(speeds)) if speeds else 0.0
        congestion = (count >= cfg.CONGESTION_COUNT_THRESHOLD and
                      avg_speed < cfg.CONGESTION_SPEED_THRESHOLD)

        if self.frame_count % 60 == 0:
            log_count(count, avg_speed, self.camera_id)

        self._draw_hud(frame, count, avg_speed, congestion)
        return frame

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open source: {self.source}")
            return

        self.fps      = cap.get(cv2.CAP_PROP_FPS) or cfg.FPS_CAP
        self.speed_est = SpeedEstimator(self.fps)

        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg.FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)

        print(f"[INFO] Running on source={self.source}  fps={self.fps:.1f}")
        print("[INFO] Press Q to quit.")

        while True:
            ret, frame = cap.read()
            if not ret:
                print("[INFO] Stream ended.")
                break

            self.frame_count += 1
            processed = self._process_frame(frame)

            if not self.headless:
                cv2.imshow("Smart Traffic Monitor", processed)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cap.release()
        cv2.destroyAllWindows()
        print("[INFO] Done.")


# ══════════════════════════════════════════════════════════════════════════════
def parse_args():
    p = argparse.ArgumentParser(description="Smart Traffic Monitor")
    p.add_argument("--source",   default=str(cfg.SOURCE),
                   help="Video source: 0 for webcam or path to video file")
    p.add_argument("--camera",   default="CAM-01", help="Camera ID label")
    p.add_argument("--headless", action="store_true",
                   help="Run without display (server mode)")
    return p.parse_args()


if __name__ == "__main__":
    args   = parse_args()
    source = int(args.source) if args.source.isdigit() else args.source
    monitor = TrafficMonitor(source=source, camera_id=args.camera,
                             headless=args.headless)
    monitor.run()

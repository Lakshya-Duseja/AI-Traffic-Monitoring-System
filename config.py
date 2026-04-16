"""
Traffic Monitor — Central Configuration
All tunable parameters in one place.
"""

# ── Camera / Input ─────────────────────────────────────────────────────────────
SOURCE = 0                          # 0 = webcam | "path/to/video.mp4"
FRAME_WIDTH  = 1280
FRAME_HEIGHT = 720
FPS_CAP      = 30

# ── YOLO ───────────────────────────────────────────────────────────────────────
YOLO_WEIGHTS   = "yolov5s.pt"       # auto-downloaded on first run
YOLO_CONF      = 0.40
YOLO_IOU       = 0.45
YOLO_CLASSES   = [2, 3, 5, 7]      # car, motorcycle, bus, truck
YOLO_IMG_SIZE  = 640

# ── DeepSORT ───────────────────────────────────────────────────────────────────
MAX_AGE        = 30                 # frames before track is dropped
N_INIT         = 3                  # detections before track confirmed
MAX_IOU_DIST   = 0.7

# ── Speed Estimation ───────────────────────────────────────────────────────────
PIXELS_PER_METER   = 8.0           # calibrate with known road marking
SPEED_SMOOTH_N     = 5             # rolling-average window (frames)
SPEED_KMPH_FACTOR  = 3.6

# ── Zone Speed Limits (km/h) ────────────────────────────────────────────────--
ZONES = {
    "highway":    {"y_range": (0,   240), "limit": 100},
    "main_road":  {"y_range": (240, 480), "limit":  60},
    "school_zone":{"y_range": (480, 720), "limit":  30},
}

# ── Direction / Wrong-Way ──────────────────────────────────────────────────────
ALLOWED_DIRECTION = "down"          # "down" | "up" | "left" | "right"
DIRECTION_THRESHOLD_PX = 15        # min pixel movement to register direction

# ── Dwell / Obstruction ────────────────────────────────────────────────────────
DWELL_TIME_SECONDS   = 30          # flag vehicle stopped > this
DWELL_MOVE_THRESHOLD = 5           # pixels moved to reset dwell timer

# ── Tailgating ─────────────────────────────────────────────────────────────────
TAILGATE_MIN_SPEED_KMPH = 20       # only check at speed
TAILGATE_MIN_DIST_PX    = 80       # flag if gap < this
TAILGATE_SAME_LANE_TOL  = 60       # horizontal tolerance (pixels)

# ── Congestion ─────────────────────────────────────────────────────────────────
CONGESTION_COUNT_THRESHOLD = 15
CONGESTION_SPEED_THRESHOLD = 20    # km/h average

# ── OCR / Plate ────────────────────────────────────────────────────────────────
PLATE_CONF_THRESHOLD = 0.5
OCR_LANGUAGES        = ["en"]

# ── Violation Fine Map (INR) ────────────────────────────────────────────────────
FINE_MAP = {
    "speeding":     2000,
    "wrong_way":    5000,
    "obstruction":  1000,
    "tailgating":   1500,
    "red_light":    3000,
}

# ── Database ───────────────────────────────────────────────────────────────────
DB_PATH = "violations_db/violations.db"

# ── Snapshots ─────────────────────────────────────────────────────────────────
SNAPSHOT_DIR = "snapshots"

# ── Dashboard ─────────────────────────────────────────────────────────────────
DASHBOARD_REFRESH_SEC = 2

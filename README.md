# 🚦 Smart Traffic Monitoring System

A college-project-grade traffic enforcement system with YOLOv8 detection, DeepSORT tracking,
real-time violation detection, SQLite logging, PDF challan generation, and a Streamlit dashboard.

---

## 📁 Project Structure

```
traffic_monitor/
├── main.py                    ← Main pipeline (run this for live/video monitoring)
├── dashboard.py               ← Streamlit dashboard (analytics & challan UI)
├── generate_demo_videos.py    ← Creates 10 synthetic demo videos
├── config.py                  ← All tunable parameters
├── db_manager.py              ← SQLite database (replaces old CSV)
├── challan_generator.py       ← PDF e-challan generator
├── requirements.txt
├── utils/
│   ├── speed_estimator.py     ← Zone-aware optical flow speed
│   ├── dwell_tracker.py       ← Obstruction / stopped vehicle detection
│   ├── tailgating_detector.py ← Following-distance enforcement
│   └── plate_reader.py        ← EasyOCR license plate reader
├── violations_db/
│   └── violations.db          ← Auto-created SQLite database
├── snapshots/                 ← Violation frame captures
├── challans/                  ← Auto-generated PDF challans
└── demo_videos/               ← 10 test videos (generated)
```

---

## ✅ Features Implemented

| Feature | Status | File |
|---|---|---|
| YOLOv8 object detection | ✅ | `main.py` |
| DeepSORT multi-object tracking | ✅ | `main.py` |
| Zone-aware speed estimation | ✅ | `utils/speed_estimator.py` |
| Wrong-way detection | ✅ | `main.py` |
| Dwell / obstruction detection | ✅ | `utils/dwell_tracker.py` |
| Tailgating detection | ✅ | `utils/tailgating_detector.py` |
| Congestion alerts | ✅ | `main.py` |
| License plate OCR | ✅ | `utils/plate_reader.py` |
| SQLite violation logging (deduped) | ✅ | `db_manager.py` |
| PDF challan generation | ✅ | `challan_generator.py` |
| Snapshot capture | ✅ | `main.py` |
| Real analytics dashboard | ✅ | `dashboard.py` |
| 10 synthetic demo videos | ✅ | `generate_demo_videos.py` |

---

## 🚀 Quick Start (VS Code)

### 1. Create virtual environment
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```
> **Note:** `easyocr` downloads ~300 MB of models on first run. If you want to skip OCR,
> it degrades gracefully (plates show as "UNKNOWN").

### 3. Generate demo videos (no camera needed)
```bash
python generate_demo_videos.py
```
This creates 10 `.mp4` files in `demo_videos/`.

### 4. Run the main pipeline on a demo video
```bash
# Speeding demo
python main.py --source demo_videos/02_speeding_violation.mp4 --camera CAM-01

# Full system demo
python main.py --source demo_videos/10_full_system_demo.mp4

# Your webcam
python main.py --source 0

# Headless (server mode, no window)
python main.py --source demo_videos/04_congestion_detection.mp4 --headless
```
Press **Q** to quit. Violations are auto-saved to the database and snapshots folder.

### 5. Launch the dashboard
Open a second terminal (keep main.py running in the first):
```bash
streamlit run dashboard.py
```
Open http://localhost:8501 in your browser.

---

## 🎬 Demo Videos

| File | Features Showcased |
|---|---|
| `01_normal_traffic_flow.mp4` | Tracking, speed display, no violations |
| `02_speeding_violation.mp4` | Speed detection, zone limits, violation alert |
| `03_wrong_way_detection.mp4` | Direction tracking, wrong-way flag |
| `04_congestion_detection.mp4` | Congestion threshold, vehicle counting |
| `05_dwell_obstruction.mp4` | Dwell timer, obstruction flag |
| `06_tailgating_detection.mp4` | Following distance check |
| `07_multi_lane_multi_violation.mp4` | Multiple simultaneous violations |
| `08_zone_aware_speed_limits.mp4` | Highway / main road / school zone |
| `09_license_plate_ocr.mp4` | Plate crop + OCR overlay |
| `10_full_system_demo.mp4` | All features combined |

---

## ⚙️ Configuration (`config.py`)

Key parameters you can tune:

```python
SOURCE = "demo_videos/02_speeding_violation.mp4"  # default source

ZONES = {
    "highway":     {"y_range": (0,   240), "limit": 100},
    "main_road":   {"y_range": (240, 480), "limit":  60},
    "school_zone": {"y_range": (480, 720), "limit":  30},
}

DWELL_TIME_SECONDS = 30       # obstruction threshold
TAILGATE_MIN_DIST_PX = 80     # tailgating gap threshold
CONGESTION_COUNT_THRESHOLD = 15
PIXELS_PER_METER = 8.0        # calibrate with known road marking
```

---

## 🗄️ Database Schema

SQLite at `violations_db/violations.db`:

- **violations** — track_id, plate, violation type, speed, zone, fine, snapshot path, camera_id, timestamp
- **vehicle_counts** — periodic count + avg_speed per camera
- **speed_log** — per-track speed samples

Query directly:
```bash
sqlite3 violations_db/violations.db "SELECT * FROM violations ORDER BY timestamp DESC LIMIT 10;"
```

---

## 📄 Challan (E-Ticket) Generation

Challans are auto-generated as PDFs in the `challans/` folder when a violation is logged.
You can also generate them manually from the dashboard's **Challans** tab.

Install: `pip install fpdf2`

---

## 🔧 Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: ultralytics` | `pip install ultralytics` |
| `No module named deep_sort_realtime` | `pip install deep-sort-realtime` |
| Black window / no display | Use `--headless` flag |
| EasyOCR slow on first run | It downloads models once; subsequent runs are fast |
| YOLOv8 weights not found | Auto-downloaded on first run (needs internet) |
| Dashboard shows no data | Run `main.py` on a video first to populate DB |

---

## 📚 College Project Notes

- **No GPU required** — runs on CPU (slower but functional)
- **No external APIs** — fully offline after initial model download
- **SQLite** — built-in to Python, no database server needed
- **Demo videos** — generated synthetically, no real traffic footage required for demo

---

## 🏗️ Architecture

```
Video Frame
    │
    ▼
YOLOv8 Detection ──► [car, bus, truck, motorcycle]
    │
    ▼
DeepSORT Tracking ──► Persistent track IDs across frames
    │
    ├──► Speed Estimator ──► Zone check ──► Speeding violation?
    ├──► Direction Check ──► Wrong-way violation?
    ├──► Dwell Tracker   ──► Obstruction violation?
    ├──► Tailgate Check  ──► Tailgating violation?
    └──► Congestion Check
    │
    ▼
Violation Logged ──► SQLite DB (deduplicated)
    │
    ├──► Snapshot saved (JPG)
    ├──► PDF Challan generated
    └──► Plate OCR attempted
    │
    ▼
Streamlit Dashboard ──► Real-time analytics from DB
```

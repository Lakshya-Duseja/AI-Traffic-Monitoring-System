"""
Database Manager — SQLite backend replacing the old flat CSV.
Handles violations, vehicle counts, and speed logs.
"""

import sqlite3, os, json
from datetime import datetime
from config import DB_PATH


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS violations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            track_id    INTEGER,
            plate       TEXT    DEFAULT 'UNKNOWN',
            vtype       TEXT,
            violation   TEXT    NOT NULL,
            speed_kmph  REAL    DEFAULT 0,
            zone        TEXT,
            fine_inr    INTEGER DEFAULT 0,
            snapshot    TEXT,
            camera_id   TEXT    DEFAULT 'CAM-01'
        );

        CREATE TABLE IF NOT EXISTS vehicle_counts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            camera_id   TEXT,
            count       INTEGER,
            avg_speed   REAL
        );

        CREATE TABLE IF NOT EXISTS speed_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            track_id    INTEGER,
            speed_kmph  REAL,
            zone        TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_viol_ts  ON violations(timestamp);
        CREATE INDEX IF NOT EXISTS idx_viol_plate ON violations(plate);
        CREATE INDEX IF NOT EXISTS idx_count_ts ON vehicle_counts(timestamp);
    """)
    conn.commit()
    conn.close()


def log_violation(track_id, plate, vtype, violation, speed_kmph,
                  zone, fine_inr, snapshot, camera_id="CAM-01"):
    conn = _connect()
    ts = datetime.now().isoformat(timespec="seconds")
    # Deduplicate: same track + same violation within 10 s
    existing = conn.execute(
        "SELECT id FROM violations WHERE track_id=? AND violation=? "
        "AND timestamp > datetime(?, '-10 seconds')",
        (track_id, violation, ts)
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO violations (timestamp,track_id,plate,vtype,violation,"
            "speed_kmph,zone,fine_inr,snapshot,camera_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ts, track_id, plate, vtype, violation, speed_kmph,
             zone, fine_inr, snapshot, camera_id)
        )
        conn.commit()
    conn.close()


def log_count(count, avg_speed, camera_id="CAM-01"):
    conn = _connect()
    ts = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO vehicle_counts (timestamp,camera_id,count,avg_speed) VALUES (?,?,?,?)",
        (ts, camera_id, count, avg_speed)
    )
    conn.commit()
    conn.close()


def log_speed(track_id, speed_kmph, zone):
    conn = _connect()
    ts = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO speed_log (timestamp,track_id,speed_kmph,zone) VALUES (?,?,?,?)",
        (ts, track_id, speed_kmph, zone)
    )
    conn.commit()
    conn.close()


def get_violations(limit=500, violation_type=None, date_from=None, date_to=None):
    conn = _connect()
    query = "SELECT * FROM violations WHERE 1=1"
    params = []
    if violation_type:
        query += " AND violation=?"; params.append(violation_type)
    if date_from:
        query += " AND timestamp >= ?"; params.append(date_from)
    if date_to:
        query += " AND timestamp <= ?"; params.append(date_to)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_summary_stats():
    conn = _connect()
    total   = conn.execute("SELECT COUNT(*) FROM violations").fetchone()[0]
    today   = conn.execute(
        "SELECT COUNT(*) FROM violations WHERE date(timestamp)=date('now')"
    ).fetchone()[0]
    avg_spd = conn.execute("SELECT AVG(speed_kmph) FROM speed_log").fetchone()[0] or 0
    by_type = conn.execute(
        "SELECT violation, COUNT(*) as cnt FROM violations GROUP BY violation"
    ).fetchall()
    fines   = conn.execute("SELECT SUM(fine_inr) FROM violations").fetchone()[0] or 0
    conn.close()
    return {
        "total_violations": total,
        "today_violations": today,
        "avg_speed": round(avg_spd, 1),
        "by_type": {r["violation"]: r["cnt"] for r in by_type},
        "total_fines": fines,
    }


def get_hourly_counts(days=1):
    conn = _connect()
    rows = conn.execute(
        "SELECT strftime('%H', timestamp) as hr, AVG(count) as avg_count "
        "FROM vehicle_counts "
        "WHERE timestamp >= datetime('now', ? ) "
        "GROUP BY hr ORDER BY hr",
        (f"-{days} days",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

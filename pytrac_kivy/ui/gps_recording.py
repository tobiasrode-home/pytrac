"""Dauerhafte lokale GPS-Arbeitspunktaufzeichnung (SQLite).

Nur Punkte bei bestätigtem aktivem Anbaugerät und eingeschalteter Aufnahme.
Keine automatischen Geräte-/Lenkaktionen.
"""
from datetime import datetime, timezone
from pathlib import Path
import math
import sqlite3
import threading

class GpsRecordingStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS gps_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                planning_id INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                phase TEXT NOT NULL,
                track_id TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                speed_mps REAL,
                accuracy_m REAL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ix_gps_points_plan ON gps_points(planning_id, id)")

    def _connect(self):
        return sqlite3.connect(str(self.path), timeout=10)

    def add(self, planning_id, phase, track_id, latitude, longitude,
            speed_mps=None, accuracy_m=None, recorded_at=None):
        lat, lon = float(latitude), float(longitude)
        if not all(math.isfinite(v) for v in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Ungültige GPS-Koordinaten")
        timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
        def optional(value):
            if value is None: return None
            v = float(value)
            return v if math.isfinite(v) else None
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """INSERT INTO gps_points
                   (planning_id, recorded_at, phase, track_id, latitude, longitude, speed_mps, accuracy_m)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(planning_id), timestamp, str(phase), str(track_id),
                 lat, lon, optional(speed_mps), optional(accuracy_m)))
            return cursor.lastrowid

    def count(self, planning_id):
        with self._lock, self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM gps_points WHERE planning_id=?",
                              (int(planning_id),)).fetchone()[0]

    def points(self, planning_id):
        with self._lock, self._connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                "SELECT * FROM gps_points WHERE planning_id=? ORDER BY id",
                (int(planning_id),))]

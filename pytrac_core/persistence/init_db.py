from pytrac_core.persistence.base import Base
from pytrac_core.persistence.models import Field, Implement, Tractor, WorkSession, GpsTrackPoint, WorkPlanning
from pytrac_core.persistence.database import engine
from sqlalchemy import inspect, text
from sqlalchemy import inspect, text

def init_db() -> None:
    """Erstellt fehlende Tabellen; bestehende Tabellen werden nicht migriert."""
    Base.metadata.create_all(bind=engine)
    # Kleine additive Bestandsmigration; vorhandene Arbeitsplanungen bleiben erhalten.
    inspector = inspect(engine)
    if 'work_plannings' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('work_plannings')}
        with engine.begin() as conn:
            for name in ('headland_start_passes', 'headland_end_passes'):
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE work_plannings ADD COLUMN {name} INTEGER'))
    # Kleine additive Bestandsmigration; vorhandene Arbeitsplanungen bleiben erhalten.
    inspector = inspect(engine)
    if 'work_plannings' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('work_plannings')}
        with engine.begin() as conn:
            for name in ('headland_start_passes', 'headland_end_passes'):
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE work_plannings ADD COLUMN {name} INTEGER'))

    # V33: additive Spalten in der bestehenden tractor.db.
    inspector = inspect(engine)
    if 'work_plannings' in inspector.get_table_names():
        existing = {col['name'] for col in inspector.get_columns('work_plannings')}
        with engine.begin() as conn:
            if 'guidance_mode' not in existing:
                conn.execute(text("ALTER TABLE work_plannings ADD COLUMN guidance_mode VARCHAR(30) NOT NULL DEFAULT 'straight'"))
            if 'reference_edge_count' not in existing:
                conn.execute(text("ALTER TABLE work_plannings ADD COLUMN reference_edge_count INTEGER NOT NULL DEFAULT 1"))

    # V40: gespeicherte manuell editierte Fahrspuren in derselben tractor.db.
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS work_planning_manual_tracks (
            planning_id INTEGER PRIMARY KEY,
            tracks_json TEXT NOT NULL,
            FOREIGN KEY(planning_id) REFERENCES work_plannings(id) ON DELETE CASCADE
        )"""))

    # V71: Antennenhöhe und IMU-Neigungsoffset in bestehender tractor.db.
    inspector=inspect(engine)
    with engine.begin() as conn:
        if 'tractors' in inspector.get_table_names():
            existing={col['name'] for col in inspector.get_columns('tractors')}
            if 'gps_offset_height_m' not in existing:
                conn.execute(text("ALTER TABLE tractors ADD COLUMN gps_offset_height_m FLOAT NOT NULL DEFAULT 0.0"))
        if 'navigation_settings' in inspector.get_table_names():
            existing={col['name'] for col in inspector.get_columns('navigation_settings')}
            if 'imu_roll_offset_deg' not in existing:
                conn.execute(text("ALTER TABLE navigation_settings ADD COLUMN imu_roll_offset_deg FLOAT NOT NULL DEFAULT 0.0"))

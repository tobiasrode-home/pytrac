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

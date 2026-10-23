from pytrac_core.persistence.base import Base
from pytrac_core.persistence.models import Field, Implement, Tractor, WorkSession, GpsTrackPoint, WorkPlanning
from pytrac_core.persistence.database import engine

def init_db() -> None:
    """Erstellt fehlende Tabellen; bestehende Tabellen werden nicht migriert."""
    Base.metadata.create_all(bind=engine)

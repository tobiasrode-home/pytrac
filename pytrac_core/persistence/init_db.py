
from pytrac_core.persistence.base import Base

# Alle Modelle importieren, damit SQLAlchemy sie registriert.
from pytrac_core.persistence.models import (
    Field,
    GpsTrackPoint,
    Implement,
    Tractor,
    WorkSession,
)
from pytrac_core.persistence.database import engine


def init_db() -> None:
    """Erstellt alle noch nicht vorhandenen Tabellen."""
    Base.metadata.create_all(bind=engine)

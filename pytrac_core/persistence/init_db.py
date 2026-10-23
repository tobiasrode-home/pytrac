from pytrac_core.persistence.base import Base
from pytrac_core.persistence.models import (
    Field,
    GpsTrackPoint,
    Implement,
    Tractor,
 )
from pytrac_core.persistence.database import engine


def init_db() -> None:
    """Erstellt alle noch nicht vorhandenen Tabellen."""
    Base.metadata.create_all(bind=engine)

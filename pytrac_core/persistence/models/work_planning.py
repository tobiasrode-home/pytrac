
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from pytrac_core.persistence.database import Base


class WorkPlanning(Base):
    """Persistiertes Modell einer Arbeitsplanung."""

    __tablename__ = "work_plannings"

    # Eindeutige ID des Planungslaufs
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )

    # Allgemeine Angaben
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    # Referenzen auf die vorhandenen Stammdaten
    tractor_id: Mapped[int] = mapped_column(
        ForeignKey("tractors.id"),
        nullable=False,
        index=True,
    )

    implement_id: Mapped[int] = mapped_column(
        ForeignKey("implements.id"),
        nullable=False,
        index=True,
    )

    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id"),
        nullable=False,
        index=True,
    )

    # Optionale Sollgeschwindigkeit in km/h
    speed: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # U-Turn oder Y-Wendung
    turn_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # all_around oder headlands_only
    headland_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Beetbearbeitung ist nur bei U-Turn zulässig
    bed_working: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Ausrichtung der regulären Fahrspuren
    alignment_boundary_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Grenzen zur Bestimmung des Startbereichs
    start_boundary_a_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    start_boundary_b_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Anzahl der Arbeitsbreiten im Vorgewende
    headland_working_widths: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Serverseitiger Erstellungszeitpunkt
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

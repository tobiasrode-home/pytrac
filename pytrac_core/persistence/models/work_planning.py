"""Persistenz einer Arbeitsplanung und ihrer berechneten Startposition."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from pytrac_core.persistence.base import Base

class WorkPlanning(Base):
    __tablename__ = 'work_plannings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    tractor_id: Mapped[int] = mapped_column(ForeignKey('tractors.id'), nullable=False)
    implement_id: Mapped[int] = mapped_column(ForeignKey('implements.id'), nullable=False)
    field_id: Mapped[int] = mapped_column(ForeignKey('fields.id'), nullable=False)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    turn_type: Mapped[str] = mapped_column(String(20), nullable=False)
    headland_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    bed_working: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alignment_boundary_id: Mapped[str] = mapped_column(String(30), nullable=False)
    start_boundary_a_id: Mapped[str] = mapped_column(String(30), nullable=False)
    start_boundary_b_id: Mapped[str] = mapped_column(String(30), nullable=False)
    headland_working_widths: Mapped[int] = mapped_column(Integer, nullable=False)
    headland_start_passes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headland_end_passes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headland_start_passes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headland_end_passes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_point_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Reserviert für die spätere Fahrspur-/Wendemanöver-Geometrie.
    guidance_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

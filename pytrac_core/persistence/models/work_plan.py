from datetime import date, datetime, time

from sqlalchemy import (
    Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Time,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pytrac_core.persistence.base import Base


class WorkPlan(Base):
    """Arbeitsplanung; fachlicher Schlüssel umfasst Geräte, Feld und Zeitpunkt."""

    __tablename__ = "work_plans"
    __table_args__ = (
        UniqueConstraint(
            "field_id", "tractor_id", "implement_id",
            "planning_date", "planning_time",
            name="uq_work_plan_combination_datetime",
        ),
    )

    # Stabile Primär-ID, damit Positionen eindeutig auf genau eine Planung zeigen.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_id: Mapped[int] = mapped_column(
        ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tractor_id: Mapped[int] = mapped_column(
        ForeignKey("tractors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    implement_id: Mapped[int] = mapped_column(
        ForeignKey("implements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    planning_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    planning_time: Mapped[time] = mapped_column(Time, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Arbeitsplanung")
    maneuver_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="u_turn")
    headland_depth_m: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    headland_depth_widths: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    headland_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="all_around")
    target_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    beet_farming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reference_edge_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_point: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    field = relationship("Field")
    tractor = relationship("Tractor")
    implement = relationship("Implement")
    positions: Mapped[list["WorkPlanPosition"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="WorkPlanPosition.position_no",
    )


class WorkPlanPosition(Base):
    """Gespeicherte Geometrie-/Spurpositionen einer Arbeitsplanung."""

    __tablename__ = "work_plan_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("work_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="track")
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    plan: Mapped[WorkPlan] = relationship(back_populates="positions")

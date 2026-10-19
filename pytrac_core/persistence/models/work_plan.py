from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pytrac_core.persistence.base import Base


class WorkPlan(Base):
    __tablename__ = "work_plans"
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id", ondelete="CASCADE"), primary_key=True)
    tractor_id: Mapped[int] = mapped_column(ForeignKey("tractors.id", ondelete="CASCADE"), primary_key=True)
    implement_id: Mapped[int] = mapped_column(ForeignKey("implements.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    maneuver_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="u_turn")
    headland_depth_m: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    target_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False, default=8.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    field = relationship("Field")
    tractor = relationship("Tractor")
    implement = relationship("Implement")
    positions: Mapped[list["WorkPlanPosition"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="WorkPlanPosition.position_no"
    )


class WorkPlanPosition(Base):
    __tablename__ = "work_plan_positions"
    __table_args__ = (ForeignKeyConstraint(
        ["field_id", "tractor_id", "implement_id"],
        ["work_plans.field_id", "work_plans.tractor_id", "work_plans.implement_id"],
        ondelete="CASCADE",
    ),)
    field_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tractor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    implement_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="track")
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    plan: Mapped[WorkPlan] = relationship(back_populates="positions")

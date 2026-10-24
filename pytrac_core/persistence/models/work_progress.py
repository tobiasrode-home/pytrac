"""GPS-Arbeitsfortschritt in tractor.db."""
from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from pytrac_core.persistence.base import Base

class WorkProgressPoint(Base):
    __tablename__ = "work_progress_points"
    __table_args__ = (UniqueConstraint("planning_id","fix_key",name="uq_work_progress_fix"),)
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    planning_id: Mapped[int] = mapped_column(ForeignKey("work_plannings.id",ondelete="CASCADE"),nullable=False,index=True)
    fix_key: Mapped[str] = mapped_column(String(180),nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,default=lambda:datetime.now(timezone.utc))
    phase: Mapped[str] = mapped_column(String(20),nullable=False)
    track_id: Mapped[str] = mapped_column(String(100),nullable=False)
    latitude: Mapped[float] = mapped_column(Float,nullable=False)
    longitude: Mapped[float] = mapped_column(Float,nullable=False)
    speed_mps: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)

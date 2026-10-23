
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pytrac_core.persistence.base import Base


class WorkSession(Base):
    __tablename__ = "work_sessions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

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

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    tractor = relationship("Tractor")
    implement = relationship("Implement")
    field = relationship("Field")

    track_points = relationship(
        "GpsTrackPoint",
        back_populates="work_session",
        cascade="all, delete-orphan",
        order_by="GpsTrackPoint.recorded_at",
    )

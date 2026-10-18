
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pytrac_core.persistence.base import Base


class GpsTrackPoint(Base):
    __tablename__ = "gps_track_points"

    __table_args__ = (
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_gps_track_points_latitude",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_gps_track_points_longitude",
        ),
        CheckConstraint(
            "heading_deg >= 0 AND heading_deg < 360",
            name="ck_gps_track_points_heading",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    work_session_id: Mapped[int] = mapped_column(
        ForeignKey("work_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    heading_deg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    accuracy_m: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    work_session = relationship(
        "WorkSession",
        back_populates="track_points",
    )

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pytrac_core.persistence.base import Base


class Tractor(Base):
    __tablename__ = "tractors"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    length_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    width_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    wheelbase_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    max_steering_angle_deg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    gps_offset_length_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    gps_offset_width_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

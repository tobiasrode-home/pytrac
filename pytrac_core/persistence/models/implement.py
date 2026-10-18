
from enum import Enum

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pytrac_core.persistence.base import Base


class MountType(str, Enum):
    FRONT = "front"
    REAR = "rear"
    TOWED = "towed"


class Implement(Base):
    __tablename__ = "implements"

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

    working_width_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    mount_type: Mapped[MountType] = mapped_column(
        SQLAlchemyEnum(
            MountType,
            name="implement_mount_type",
            values_callable=lambda enum: [
                item.value for item in enum
            ],
        ),
        nullable=False,
    )

    work_offset_m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

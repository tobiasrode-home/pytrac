from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pytrac_core.persistence.base import Base


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    boundary_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    area_m2: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    reference_line_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

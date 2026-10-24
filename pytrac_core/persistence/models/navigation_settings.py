"""Persistente Anzeige-/Navigationsoptionen in tractor.db."""
from sqlalchemy import Boolean, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from pytrac_core.persistence.base import Base

class NavigationSettings(Base):
    __tablename__ = 'navigation_settings'
    id: Mapped[int] = mapped_column(Integer,primary_key=True)
    gps_smoothing_enabled: Mapped[bool] = mapped_column(Boolean,nullable=False,default=False)
    imu_heading_offset_deg: Mapped[float] = mapped_column(Float,nullable=False,default=0.0)

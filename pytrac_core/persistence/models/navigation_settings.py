"""Persistente IMU-Kalibrierung in tractor.db."""
from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from pytrac_core.persistence.base import Base

class NavigationSettings(Base):
    __tablename__ = 'navigation_settings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    imu_heading_offset_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    imu_roll_offset_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    display_brightness_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=75)
    work_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="confirmed")

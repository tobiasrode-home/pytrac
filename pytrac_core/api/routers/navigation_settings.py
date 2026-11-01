"""Persistente IMU-Kalibrierung."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Literal, Optional
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.navigation_settings import NavigationSettings

router = APIRouter(prefix='/api/navigation-settings', tags=['Navigation'])

class NavigationSettingsData(BaseModel):
    imu_heading_offset_deg: float = Field(default=0., ge=-180., le=180., allow_inf_nan=False)
    imu_roll_offset_deg: float = Field(default=0., ge=-45., le=45., allow_inf_nan=False)
    work_mode: Literal["manual", "confirmed", "automatic"] = "confirmed"
    display_brightness_percent: int = Field(default=75, ge=10, le=100)

def get_or_create(db):
    # Additive Bestandsmigration für bereits vorhandene tractor.db.
    bind=db.get_bind()
    inspector=inspect(bind)
    if 'navigation_settings' in inspector.get_table_names():
        existing={col['name'] for col in inspector.get_columns('navigation_settings')}
        if 'imu_roll_offset_deg' not in existing:
            with bind.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE navigation_settings ADD COLUMN "
                    "imu_roll_offset_deg FLOAT NOT NULL DEFAULT 0.0"))
    if "navigation_settings" in inspector.get_table_names():
        existing={col["name"] for col in inspect(bind).get_columns("navigation_settings")}
        if "work_mode" not in existing:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE navigation_settings ADD COLUMN work_mode VARCHAR(24) NOT NULL DEFAULT 'confirmed'"))
    if "navigation_settings" in inspector.get_table_names():
        existing={col["name"] for col in inspect(bind).get_columns("navigation_settings")}
        if "display_brightness_percent" not in existing:
            with bind.begin() as conn:
                conn.execute(text("ALTER TABLE navigation_settings ADD COLUMN display_brightness_percent INTEGER NOT NULL DEFAULT 75"))
    item=db.get(NavigationSettings,1)
    if item is None:
        item=NavigationSettings(id=1,imu_heading_offset_deg=0.,imu_roll_offset_deg=0.)
        db.add(item)
        db.commit()
        db.refresh(item)
    return item

@router.get('')
def read_settings(db:Session=Depends(get_db)):
    item=get_or_create(db)
    return NavigationSettingsData(
        imu_heading_offset_deg=item.imu_heading_offset_deg,
        imu_roll_offset_deg=item.imu_roll_offset_deg,
        work_mode=item.work_mode or "confirmed",
        display_brightness_percent=item.display_brightness_percent)

@router.put('')
def update_settings(data:NavigationSettingsData,db:Session=Depends(get_db)):
    item=get_or_create(db)
    item.imu_heading_offset_deg=data.imu_heading_offset_deg
    item.imu_roll_offset_deg=data.imu_roll_offset_deg
    item.work_mode=data.work_mode
    item.display_brightness_percent=data.display_brightness_percent
    db.commit()
    return data

class WorkModeUpdate(BaseModel):
    work_mode: Literal["manual", "confirmed", "automatic"]

@router.patch('/work-mode')
def update_work_mode(data: WorkModeUpdate, db: Session = Depends(get_db)):
    """Nur Arbeitsmodus ändern; bestehende IMU-Offsets nicht überschreiben."""
    item = get_or_create(db)
    item.work_mode = data.work_mode
    db.commit()
    return {"work_mode": item.work_mode}


class DeviceSettingsUpdate(BaseModel):
    """Partial update, so no setting is silently reset by a stale client."""
    work_mode: Optional[Literal["manual", "confirmed", "automatic"]] = None
    imu_heading_offset_deg: Optional[float] = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    imu_roll_offset_deg: Optional[float] = Field(default=None, ge=-45, le=45, allow_inf_nan=False)
    display_brightness_percent: Optional[int] = Field(default=None, ge=10, le=100)

@router.patch('/device-settings')
def update_device_settings(data: DeviceSettingsUpdate, db: Session = Depends(get_db)):
    item=get_or_create(db)
    changes=data.model_dump(exclude_unset=True)
    for name,value in changes.items():
        if value is not None:
            setattr(item,name,value)
    db.commit()
    db.refresh(item)
    return NavigationSettingsData(
        imu_heading_offset_deg=item.imu_heading_offset_deg,
        imu_roll_offset_deg=item.imu_roll_offset_deg,
        work_mode=item.work_mode or 'confirmed',
        display_brightness_percent=item.display_brightness_percent)

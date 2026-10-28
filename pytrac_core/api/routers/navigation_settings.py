"""Persistente IMU-Kalibrierung."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.navigation_settings import NavigationSettings

router = APIRouter(prefix='/api/navigation-settings', tags=['Navigation'])

class NavigationSettingsData(BaseModel):
    imu_heading_offset_deg: float = Field(default=0., ge=-180., le=180., allow_inf_nan=False)
    imu_roll_offset_deg: float = Field(default=0., ge=-45., le=45., allow_inf_nan=False)

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
        imu_roll_offset_deg=item.imu_roll_offset_deg)

@router.put('')
def update_settings(data:NavigationSettingsData,db:Session=Depends(get_db)):
    item=get_or_create(db)
    item.imu_heading_offset_deg=data.imu_heading_offset_deg
    item.imu_roll_offset_deg=data.imu_roll_offset_deg
    db.commit()
    return data

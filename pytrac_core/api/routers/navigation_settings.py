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
    imu_zero_yaw_deg: float = Field(default=0., ge=-180., le=180., allow_inf_nan=False)
    imu_zero_pitch_deg: float = Field(default=0., ge=-180., le=180., allow_inf_nan=False)
    imu_zero_roll_deg: float = Field(default=0., ge=-180., le=180., allow_inf_nan=False)
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
        for name in ('imu_zero_yaw_deg','imu_zero_pitch_deg','imu_zero_roll_deg'):
            if name not in existing:
                with bind.begin() as conn:
                    conn.execute(text(f'ALTER TABLE navigation_settings ADD COLUMN {name} FLOAT NOT NULL DEFAULT 0.0'))
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
        imu_zero_yaw_deg=item.imu_zero_yaw_deg,
        imu_zero_pitch_deg=item.imu_zero_pitch_deg,
        imu_zero_roll_deg=item.imu_zero_roll_deg)

@router.put('')
def update_settings(data:NavigationSettingsData,db:Session=Depends(get_db)):
    item=get_or_create(db)
    item.imu_heading_offset_deg=data.imu_heading_offset_deg
    item.imu_roll_offset_deg=data.imu_roll_offset_deg
    item.imu_zero_yaw_deg=data.imu_zero_yaw_deg
    item.imu_zero_pitch_deg=data.imu_zero_pitch_deg
    item.imu_zero_roll_deg=data.imu_zero_roll_deg
    db.commit()
    return data


class ImuZeroData(BaseModel):
    yaw_deg: float = Field(ge=-180., le=180., allow_inf_nan=False)
    pitch_deg: float = Field(ge=-180., le=180., allow_inf_nan=False)
    roll_deg: float = Field(ge=-180., le=180., allow_inf_nan=False)

@router.put('/imu-zero')
def save_imu_zero(data: ImuZeroData, db: Session = Depends(get_db)):
    """Save installation reference without touching navigation offsets."""
    item = get_or_create(db)
    item.imu_zero_yaw_deg = data.yaw_deg
    item.imu_zero_pitch_deg = data.pitch_deg
    item.imu_zero_roll_deg = data.roll_deg
    db.commit()
    return {'yaw_deg': item.imu_zero_yaw_deg,
            'pitch_deg': item.imu_zero_pitch_deg,
            'roll_deg': item.imu_zero_roll_deg}

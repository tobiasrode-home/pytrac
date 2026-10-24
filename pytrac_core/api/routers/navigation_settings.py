"""Gemeinsame GPS- und IMU-Einstellungen in tractor.db."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.navigation_settings import NavigationSettings

router=APIRouter(prefix='/api/navigation-settings',tags=['Navigation'])

class NavigationSettingsData(BaseModel):
    gps_smoothing_enabled: bool = False
    imu_heading_offset_deg: float = Field(default=0.,ge=-180.,le=180.,allow_inf_nan=False)

def get_or_create(db):
    item=db.get(NavigationSettings,1)
    if item is None:
        item=NavigationSettings(id=1,gps_smoothing_enabled=False,imu_heading_offset_deg=0.)
        db.add(item);db.commit();db.refresh(item)
    return item

@router.get('')
def read_settings(db:Session=Depends(get_db)):
    item=get_or_create(db)
    return NavigationSettingsData(gps_smoothing_enabled=item.gps_smoothing_enabled,
                                  imu_heading_offset_deg=item.imu_heading_offset_deg)

@router.put('')
def update_settings(data:NavigationSettingsData,db:Session=Depends(get_db)):
    item=get_or_create(db)
    item.gps_smoothing_enabled=data.gps_smoothing_enabled
    item.imu_heading_offset_deg=data.imu_heading_offset_deg
    db.commit()
    return data

"""Gemeinsame GPS-Arbeitsaufzeichnung in tractor.db."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.work_planning import WorkPlanning
from pytrac_core.persistence.models.work_progress import WorkProgressPoint

router=APIRouter(prefix="/api/work-plannings",tags=["Work Progress"])

class ProgressCreate(BaseModel):
    fix_key: str = Field(min_length=1,max_length=180)
    recorded_at: datetime | None = None
    phase: str = Field(pattern="^(main|headland)$")
    track_id: str = Field(min_length=1,max_length=100)
    latitude: float = Field(ge=-90,le=90,allow_inf_nan=False)
    longitude: float = Field(ge=-180,le=180,allow_inf_nan=False)
    speed_mps: float | None = Field(default=None,allow_inf_nan=False)
    accuracy_m: float | None = Field(default=None,ge=0,allow_inf_nan=False)

def require_plan(db,planning_id):
    if db.get(WorkPlanning,planning_id) is None:
        raise HTTPException(status_code=404,detail="Arbeitsauftrag nicht gefunden")

def serialize(p):
    return dict(id=p.id,planning_id=p.planning_id,fix_key=p.fix_key,
                recorded_at=p.recorded_at.isoformat(),phase=p.phase,track_id=p.track_id,
                latitude=p.latitude,longitude=p.longitude,
                speed_mps=p.speed_mps,accuracy_m=p.accuracy_m)

@router.get("/{planning_id}/progress")
def get_progress(planning_id:int,db:Session=Depends(get_db)):
    require_plan(db,planning_id)
    points=db.scalars(select(WorkProgressPoint).where(WorkProgressPoint.planning_id==planning_id).order_by(WorkProgressPoint.id)).all()
    return {"planning_id":planning_id,"count":len(points),"points":[serialize(p) for p in points]}

@router.post("/{planning_id}/progress",status_code=201)
def add_progress(planning_id:int,data:ProgressCreate,db:Session=Depends(get_db)):
    require_plan(db,planning_id)
    existing=db.scalar(select(WorkProgressPoint).where(WorkProgressPoint.planning_id==planning_id,WorkProgressPoint.fix_key==data.fix_key))
    if existing:return serialize(existing)
    p=WorkProgressPoint(planning_id=planning_id,**data.model_dump(exclude={"recorded_at"}),
                        recorded_at=data.recorded_at or datetime.now(timezone.utc))
    db.add(p)
    try:db.commit()
    except IntegrityError:
        db.rollback()
        existing=db.scalar(select(WorkProgressPoint).where(WorkProgressPoint.planning_id==planning_id,WorkProgressPoint.fix_key==data.fix_key))
        if existing:return serialize(existing)
        raise
    db.refresh(p)
    return serialize(p)

@router.delete("/{planning_id}/progress",status_code=204)
def delete_progress(planning_id:int,db:Session=Depends(get_db)):
    """Nur aufgezeichnete GPS-Punkte löschen, Arbeitsauftrag und Soll-Spuren behalten."""
    require_plan(db,planning_id)
    db.execute(delete(WorkProgressPoint).where(WorkProgressPoint.planning_id==planning_id))
    db.commit()
    return Response(status_code=204)

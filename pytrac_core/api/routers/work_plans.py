from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.work_plan import WorkPlan, WorkPlanPosition

router = APIRouter(prefix="/api/work-plans", tags=["Work Plans"])


class PositionInput(BaseModel):
    position_no: int = Field(ge=0)
    kind: Literal["track", "turn", "headland", "other"] = "track"
    geometry: dict
    properties: dict = Field(default_factory=dict)


class WorkPlanInput(BaseModel):
    field_id: int = Field(gt=0)
    tractor_id: int = Field(gt=0)
    implement_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=100)
    maneuver_mode: Literal["u_turn", "y_turn", "k_turn", "beet"] = "u_turn"
    headland_depth_m: float = Field(gt=0, le=100)
    target_speed_kmh: float = Field(gt=0, le=30)
    positions: list[PositionInput]


def serialize(plan):
    return {
        "field_id": plan.field_id, "tractor_id": plan.tractor_id,
        "implement_id": plan.implement_id, "name": plan.name,
        "maneuver_mode": plan.maneuver_mode, "headland_depth_m": plan.headland_depth_m,
        "target_speed_kmh": plan.target_speed_kmh,
        "created_at": plan.created_at, "updated_at": plan.updated_at,
        "positions": [{
            "position_no": p.position_no, "kind": p.kind,
            "geometry": p.geometry, "properties": p.properties
        } for p in plan.positions],
    }


@router.get("")
def list_plans(db: Session = Depends(get_db)):
    plans = db.scalars(select(WorkPlan).options(selectinload(WorkPlan.positions)).order_by(WorkPlan.updated_at.desc())).all()
    return [serialize(p) for p in plans]


@router.get("/{field_id}/{tractor_id}/{implement_id}")
def get_plan(field_id: int, tractor_id: int, implement_id: int, db: Session = Depends(get_db)):
    plan = db.scalar(select(WorkPlan).options(selectinload(WorkPlan.positions)).where(
        WorkPlan.field_id == field_id, WorkPlan.tractor_id == tractor_id, WorkPlan.implement_id == implement_id))
    if plan is None:
        raise HTTPException(404, "Kein gespeicherter Plan gefunden.")
    return serialize(plan)


@router.put("")
def save_plan(data: WorkPlanInput, db: Session = Depends(get_db)):
    if len({p.position_no for p in data.positions}) != len(data.positions):
        raise HTTPException(422, "position_no muss eindeutig sein.")
    for p in data.positions:
        if p.geometry.get("type") not in {"LineString", "MultiLineString"} or not p.geometry.get("coordinates"):
            raise HTTPException(422, "Fahrspur benötigt eine LineString-Geometrie mit Koordinaten.")
    key = (data.field_id, data.tractor_id, data.implement_id)
    plan = db.get(WorkPlan, key)
    if plan is None:
        plan = WorkPlan(field_id=data.field_id, tractor_id=data.tractor_id, implement_id=data.implement_id,
                        name=data.name, maneuver_mode=data.maneuver_mode,
                        headland_depth_m=data.headland_depth_m, target_speed_kmh=data.target_speed_kmh)
        db.add(plan)
        db.flush()
    else:
        plan.name = data.name
        plan.maneuver_mode = data.maneuver_mode
        plan.headland_depth_m = data.headland_depth_m
        plan.target_speed_kmh = data.target_speed_kmh
        plan.positions.clear()
        db.flush()
    for p in data.positions:
        plan.positions.append(WorkPlanPosition(
            field_id=data.field_id, tractor_id=data.tractor_id, implement_id=data.implement_id,
            position_no=p.position_no, kind=p.kind, geometry=p.geometry, properties=p.properties))
    db.commit()
    db.refresh(plan)
    return serialize(plan)


@router.delete("/{field_id}/{tractor_id}/{implement_id}", status_code=204)
def delete_plan(field_id: int, tractor_id: int, implement_id: int, db: Session = Depends(get_db)):
    plan = db.get(WorkPlan, (field_id, tractor_id, implement_id))
    if plan is None:
        raise HTTPException(404, "Kein gespeicherter Plan gefunden.")
    db.delete(plan)
    db.commit()

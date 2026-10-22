from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pytrac_core.api.schemas import WorkPlanCreate
from pytrac_core.persistence.database import get_db
from pytrac_core.persistence.models.field import Field as FieldModel
from pytrac_core.persistence.models.tractor import Tractor
from pytrac_core.persistence.models.implement import Implement
from pytrac_core.persistence.models.work_plan import WorkPlan

router = APIRouter(prefix="/api/work-plans", tags=["Arbeitsplanung"])


def serialize_plan(plan: WorkPlan) -> dict:
    return {
        "id": plan.id,
        "field_id": plan.field_id,
        "tractor_id": plan.tractor_id,
        "implement_id": plan.implement_id,
        "planning_date": plan.planning_date.isoformat(),
        "planning_time": plan.planning_time.strftime("%H:%M:%S"),
        "name": plan.name,
        "maneuver_mode": plan.maneuver_mode,
        "headland_depth_m": plan.headland_depth_m,
        "headland_depth_widths": plan.headland_depth_widths,
        "headland_mode": plan.headland_mode,
        "target_speed_kmh": plan.target_speed_kmh,
        "beet_farming": plan.beet_farming,
        "reference_edge_index": plan.reference_edge_index,
        "start_point": plan.start_point,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


@router.get("")
def list_work_plans(db: Session = Depends(get_db)):
    plans = db.query(WorkPlan).order_by(
        WorkPlan.planning_date.desc(),
        WorkPlan.planning_time.desc(),
        WorkPlan.id.desc(),
    ).all()
    return [serialize_plan(plan) for plan in plans]


@router.get("/{plan_id}")
def get_work_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(WorkPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Arbeitsplanung nicht gefunden.")
    return serialize_plan(plan)


@router.post("", status_code=201)
def create_work_plan(data: WorkPlanCreate, db: Session = Depends(get_db)):
    for model, item_id, label in (
        (FieldModel, data.field_id, "Feld"),
        (Tractor, data.tractor_id, "Traktor"),
        (Implement, data.implement_id, "Anbaugerät"),
    ):
        if db.get(model, item_id) is None:
            raise HTTPException(status_code=404, detail=f"{label} nicht gefunden.")

    plan = WorkPlan(**data.model_dump())
    db.add(plan)
    try:
        db.commit()
        db.refresh(plan)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Für diese Feld-/Traktor-/Anbaugerät-Kombination existiert "
                "zu diesem Datum und dieser Uhrzeit bereits eine Planung."
            ),
        ) from exc
    return serialize_plan(plan)


@router.delete("/{plan_id}", status_code=204)
def delete_work_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(WorkPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Arbeitsplanung nicht gefunden.")
    db.delete(plan)
    db.commit()
    return Response(status_code=204)

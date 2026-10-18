from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from pytrac_core.api.schemas import (
    WorkPlanningPreviewRead,
    WorkPlanningPreviewRequest,
)
from pytrac_core.persistence.database import get_db
from pytrac_core.services.work_planning_service import (
    WorkPlanningError,
    WorkPlanningService,
)

router = APIRouter(
    prefix="/api/work-planning",
    tags=["Work Planning"],
)


@router.post(
    "/preview",
    response_model=WorkPlanningPreviewRead,
)
def preview_work_plan(
    data: WorkPlanningPreviewRequest,
    db: Session = Depends(get_db),
):
    try:
        return WorkPlanningService(db).preview(
            field_id=data.field_id,
            tractor_id=data.tractor_id,
            implement_id=data.implement_id,
            maneuver_mode=data.maneuver_mode,
            headland_depth_override_m=(
                data.headland_depth_override_m
            ),
            target_speed_kmh=data.target_speed_kmh,
        )
    except WorkPlanningError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

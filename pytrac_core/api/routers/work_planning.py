"""REST-Endpunkte für die Arbeitsplanung."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from pytrac_core.api.schemas import (WorkPlanningCreate, WorkPlanningDefaults, WorkPlanningDefaultsRequest, WorkPlanningPreview, WorkPlanningPreviewRequest, WorkPlanningRead, GuidanceRequest, GuidanceSavedRequest)
from pytrac_core.persistence.database import get_db
from pytrac_core.services.work_planning_service import WorkPlanningService, WorkPlanningValidationError, WorkPlanningNotFoundError

router = APIRouter(prefix='/api/work-plannings', tags=['Work Planning'])

def service(db): return WorkPlanningService(db)

def run(fn):
    try: return fn()
    except WorkPlanningValidationError as exc: raise HTTPException(422, detail=str(exc)) from exc
    except WorkPlanningNotFoundError as exc: raise HTTPException(404, detail=str(exc)) from exc

@router.post('/defaults', response_model=WorkPlanningDefaults)
def defaults(data: WorkPlanningDefaultsRequest, db: Session=Depends(get_db)):
    return run(lambda: service(db).defaults(data))

@router.post('/preview', response_model=WorkPlanningPreview)
def preview(data: WorkPlanningPreviewRequest, db: Session=Depends(get_db)):
    return run(lambda: service(db).preview(data))

@router.post('', response_model=WorkPlanningRead, status_code=status.HTTP_201_CREATED)
def create(data: WorkPlanningCreate, db: Session=Depends(get_db)):
    return run(lambda: service(db).create(data))

@router.get('', response_model=list[WorkPlanningRead])
def list_plannings(db: Session=Depends(get_db)):
    return service(db).list()

@router.get('/{planning_id}', response_model=WorkPlanningRead)
def get(planning_id: int, db: Session=Depends(get_db)):
    return run(lambda: service(db).get(planning_id))

@router.delete('/{planning_id}', status_code=204)
def delete(planning_id: int, db: Session=Depends(get_db)):
    run(lambda: service(db).delete(planning_id))
    return Response(status_code=204)


@router.post('/guidance')
def guidance(data: GuidanceRequest, db: Session=Depends(get_db)):
    """Spurplanung inkl. optionaler Wendeskizzen, ohne Speicherung."""
    return run(lambda: service(db).guidance(data))

@router.post('/{planning_id}/guidance')
def saved_guidance(planning_id: int, data: GuidanceSavedRequest, db: Session=Depends(get_db)):
    """Spurplanung aus gespeicherten Parametern, Modus nur für diese Anfrage."""
    return run(lambda: service(db).guidance_for_saved(planning_id, data.output_mode, data.implement_lead_m, data.use_recorded_reference))

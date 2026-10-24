"""REST-Endpunkte für die Arbeitsplanung."""
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
import json
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


class ManualTracksPayload(BaseModel):
    tracks: list[list[list[float]]] = Field(max_length=500)

@router.put('/{planning_id}/manual-tracks')
def save_manual_tracks(planning_id: int, data: ManualTracksPayload, db: Session=Depends(get_db)):
    from pytrac_core.persistence.models.work_planning import WorkPlanning
    from pytrac_core.persistence.models.field import Field
    from pytrac_core.services.work_planning_service import WorkPlanningService
    from shapely.geometry import Point, Polygon, LineString
    from shapely.ops import transform
    import math
    plan=db.get(WorkPlanning,planning_id)
    if plan is None: raise HTTPException(404,'Arbeitsplanung nicht gefunden.')
    field=db.get(Field,plan.field_id)
    vertices=WorkPlanningService._edges(field)
    forward,_=WorkPlanningService._projector(vertices)
    boundary=transform(forward,Polygon(vertices))
    if not data.tracks: raise HTTPException(422,'Mindestens eine Fahrspur erforderlich.')
    for track in data.tracks:
        if len(track)<2 or len(track)>2000:
            raise HTTPException(422,'Jede Spur benötigt 2 bis 2000 Punkte.')
        for point in track:
            if len(point)!=2 or not all(math.isfinite(v) for v in point) or not (-180<=point[0]<=180 and -90<=point[1]<=90):
                raise HTTPException(422,'Ungültige Koordinaten.')
        line=transform(forward,LineString(track))
        if line.length<1 or not boundary.buffer(.05).covers(line):
            raise HTTPException(422,'Spur muss mindestens 1 m lang sein und innerhalb der Feldgrenze liegen.')
    payload=json.dumps(data.tracks,separators=(',',':'))
    db.execute(text("""INSERT INTO work_planning_manual_tracks(planning_id,tracks_json)
        VALUES (:id,:tracks) ON CONFLICT(planning_id) DO UPDATE SET tracks_json=excluded.tracks_json"""),
        {'id':planning_id,'tracks':payload})
    db.commit()
    return {'planning_id':planning_id,'track_count':len(data.tracks)}

@router.get('/{planning_id}/manual-tracks')
def get_manual_tracks(planning_id: int, db: Session=Depends(get_db)):
    service(db).get(planning_id)
    row=db.execute(text('SELECT tracks_json FROM work_planning_manual_tracks WHERE planning_id=:id'),{'id':planning_id}).scalar_one_or_none()
    return {'tracks':json.loads(row) if row else []}

@router.delete('/{planning_id}/manual-tracks',status_code=204)
def clear_manual_tracks(planning_id: int,db: Session=Depends(get_db)):
    service(db).get(planning_id)
    db.execute(text('DELETE FROM work_planning_manual_tracks WHERE planning_id=:id'),{'id':planning_id})
    db.commit()
    return Response(status_code=204)

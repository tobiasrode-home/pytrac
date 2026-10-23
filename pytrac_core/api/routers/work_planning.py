
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from pytrac_core.api.schemas import (
    WorkPlanningCreate,
    WorkPlanningPreview,
    WorkPlanningPreviewRequest,
    WorkPlanningRead,
)
from pytrac_core.persistence.database import get_db
from pytrac_core.services.work_planning_service import (
    WorkPlanningNotFoundError,
    WorkPlanningService,
    WorkPlanningValidationError,
)


router = APIRouter(
    prefix="/api/work-plannings",
    tags=["Work Planning"],
)


@router.post(
    "/preview",
    response_model=WorkPlanningPreview,
)
def preview_work_planning(
    data: WorkPlanningPreviewRequest,
    db: Session = Depends(get_db),
):
    """
    Berechnet die Planungsparameter für die Vorschau.

    Die fachliche Berechnung erfolgt vollständig im Backend-Service.
    Es wird dabei noch keine Arbeitsplanung gespeichert.
    """
    try:
        return WorkPlanningService(db).preview(data)
    except WorkPlanningValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "",
    response_model=WorkPlanningRead,
    status_code=status.HTTP_201_CREATED,
)
def create_work_planning(
    data: WorkPlanningCreate,
    db: Session = Depends(get_db),
):
    """
    Erstellt und speichert eine Arbeitsplanung.

    Der Service erzeugt den Zeitstempel beim Speichern
    und vergibt eine eindeutige ID für den Planungslauf.
    """
    try:
        return WorkPlanningService(db).create(data)
    except WorkPlanningValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[WorkPlanningRead],
)
def list_work_plannings(
    db: Session = Depends(get_db),
):
    """Gibt alle gespeicherten Arbeitsplanungen zurück."""
    return WorkPlanningService(db).list()


@router.get(
    "/{planning_id}",
    response_model=WorkPlanningRead,
)
def get_work_planning(
    planning_id: int,
    db: Session = Depends(get_db),
):
    """Lädt eine einzelne Arbeitsplanung anhand ihrer ID."""
    try:
        return WorkPlanningService(db).get(planning_id)
    except WorkPlanningNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{planning_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_work_planning(
    planning_id: int,
    db: Session = Depends(get_db),
):
    """Löscht eine gespeicherte Arbeitsplanung."""
    try:
        WorkPlanningService(db).delete(planning_id)
    except WorkPlanningNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)

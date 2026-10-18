
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from pytrac_core.api.schemas import (
    ImplementCreate,
    ImplementRead,
    ImplementUpdate,
)
from pytrac_core.persistence.database import get_db
from pytrac_core.services.implement_service import (
    ImplementAlreadyExistsError,
    ImplementNotFoundError,
    ImplementService,
)

router = APIRouter(prefix="/api/implements", tags=["Implements"])


@router.post("", response_model=ImplementRead, status_code=201)
def create_implement(
    data: ImplementCreate,
    db: Session = Depends(get_db),
):
    try:
        return ImplementService(db).create(data.model_dump())
    except ImplementAlreadyExistsError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.get("", response_model=list[ImplementRead])
def list_implements(db: Session = Depends(get_db)):
    return ImplementService(db).list()


@router.get("/{implement_id}", response_model=ImplementRead)
def get_implement(
    implement_id: int,
    db: Session = Depends(get_db),
):
    try:
        return ImplementService(db).get(implement_id)
    except ImplementNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.put("/{implement_id}", response_model=ImplementRead)
def update_implement(
    implement_id: int,
    data: ImplementUpdate,
    db: Session = Depends(get_db),
):
    try:
        return ImplementService(db).update(
            implement_id,
            data.model_dump(),
        )
    except ImplementNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ImplementAlreadyExistsError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.delete("/{implement_id}", status_code=204)
def delete_implement(
    implement_id: int,
    db: Session = Depends(get_db),
):
    try:
        ImplementService(db).delete(implement_id)
    except ImplementNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    return Response(status_code=204)

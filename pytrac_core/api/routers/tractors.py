
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from pytrac_core.persistence.database import get_db
from pytrac_core.api.schemas import TractorCreate, TractorRead, TractorUpdate
from pytrac_core.services.tractor_service import (
    TractorAlreadyExistsError,
    TractorNotFoundError,
    TractorService,
)

router = APIRouter(prefix="/api/tractors", tags=["Tractors"])


@router.post(
    "",
    response_model=TractorRead,
    status_code=status.HTTP_201_CREATED,
)
def create_tractor(
    data: TractorCreate,
    db: Session = Depends(get_db),
):
    try:
        return TractorService(db).create(data.model_dump())
    except TractorAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[TractorRead])
def list_tractors(db: Session = Depends(get_db)):
    return TractorService(db).list()


@router.get("/{tractor_id}", response_model=TractorRead)
def get_tractor(tractor_id: int, db: Session = Depends(get_db)):
    try:
        return TractorService(db).get(tractor_id)
    except TractorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{tractor_id}", response_model=TractorRead)
def update_tractor(
    tractor_id: int,
    data: TractorUpdate,
    db: Session = Depends(get_db),
):
    try:
        return TractorService(db).update(
            tractor_id,
            data.model_dump(),
        )
    except TractorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TractorAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{tractor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tractor(tractor_id: int, db: Session = Depends(get_db)):
    try:
        TractorService(db).delete(tractor_id)
    except TractorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)

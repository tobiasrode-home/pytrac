
import json

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from pytrac_core.api.schemas import (
    FieldBoundaryUpdate,
    FieldCreate,
    FieldRead,
    FieldReferenceLineUpdate,
)
from pytrac_core.persistence.database import get_db
from pytrac_core.services.field_service import (
    FieldAlreadyExistsError,
    FieldGeometryError,
    FieldNotFoundError,
    FieldService,
)

router = APIRouter(prefix="/api/fields", tags=["Fields"])


def serialize_field(field) -> dict:
    return {
        "id": field.id,
        "name": field.name,
        "boundary": json.loads(field.boundary_json),
        "area_m2": field.area_m2,
        "reference_line": json.loads(field.reference_line_json),
    }


@router.post("", status_code=201, response_model=FieldRead)
def create_field(
    data: FieldCreate,
    db: Session = Depends(get_db),
):
    try:
        field = FieldService(db).create(
            name=data.name,
            boundary=data.boundary,
            reference_line=data.reference_line,
        )
        return serialize_field(field)
    except FieldGeometryError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except FieldAlreadyExistsError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.get("", response_model=list[FieldRead])
def list_fields(db: Session = Depends(get_db)):
    return [serialize_field(field) for field in FieldService(db).list()]


@router.get("/{field_id}", response_model=FieldRead)
def get_field(field_id: int, db: Session = Depends(get_db)):
    try:
        return serialize_field(FieldService(db).get(field_id))
    except FieldNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.put("/{field_id}/boundary", response_model=FieldRead)
def update_boundary(
    field_id: int,
    data: FieldBoundaryUpdate,
    db: Session = Depends(get_db),
):
    try:
        field = FieldService(db).update_boundary(
            field_id, data.boundary
        )
        return serialize_field(field)
    except FieldNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except FieldGeometryError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.put("/{field_id}/reference-line", response_model=FieldRead)
def update_reference_line(
    field_id: int,
    data: FieldReferenceLineUpdate,
    db: Session = Depends(get_db),
):
    try:
        field = FieldService(db).set_reference_line(
            field_id, data.reference_line
        )
        return serialize_field(field)
    except FieldNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except FieldGeometryError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.delete("/{field_id}", status_code=204)
def delete_field(field_id: int, db: Session = Depends(get_db)):
    try:
        FieldService(db).delete(field_id)
    except FieldNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc

    return Response(status_code=204)

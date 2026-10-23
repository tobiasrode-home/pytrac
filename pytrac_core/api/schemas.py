from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pytrac_core.persistence.models.implement import MountType


class TractorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    wheelbase_m: float = Field(gt=0)
    max_steering_angle_deg: float = Field(gt=0, lt=90)
    gps_offset_length_m: float = 0.0
    gps_offset_width_m: float = 0.0


class TractorUpdate(TractorCreate):
    pass


class TractorRead(TractorCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ImplementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    length_m: float = Field(gt=0)
    working_width_m: float = Field(gt=0)
    mount_type: MountType
    work_offset_m: float


class ImplementUpdate(ImplementCreate):
    pass


class ImplementRead(ImplementCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class FieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    boundary: list[list[float]]
    reference_line: list[list[float]] = []

    @model_validator(mode="after")
    def validate_boundary(self):
        if len(self.boundary) < 4:
            raise ValueError(
                "Die Feldgrenze benötigt mindestens drei Punkte "
                "und einen abschließenden Punkt zur Ringschließung."
            )
        if self.boundary[0] != self.boundary[-1]:
            raise ValueError(
                "Der erste und letzte Punkt der Feldgrenze müssen identisch sein."
            )
        return self


class FieldBoundaryUpdate(BaseModel):
    boundary: list[list[float]]


class FieldReferenceLineUpdate(BaseModel):
    reference_line: list[list[float]]


class FieldRead(BaseModel):
    id: int
    name: str
    boundary: list[list[float]]
    area_m2: float
    reference_line: list[list[float]]
    model_config = ConfigDict(from_attributes=True)



from pydantic import BaseModel, ConfigDict, Field
from pytrac_core.persistence.models.implement import MountType
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal

class TractorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    gps_offset_length_m: float = 0.0
    gps_offset_width_m: float = 0.0
    turning_radius_m: float = Field(gt=0)


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
                "Der erste und letzte Punkt der Feldgrenze "
                "müssen identisch sein."
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

class WorkPlanningPreviewRequest(BaseModel):
    field_id: int = Field(gt=0)
    tractor_id: int = Field(gt=0)
    implement_id: int = Field(gt=0)

    maneuver_mode: Literal[
        "u_turn",
        "y_turn",
        "k_turn",
        "beet",
    ] = "u_turn"

    headland_depth_override_m: float | None = Field(
        default=None,
        gt=0,
    )

    target_speed_kmh: float = Field(
        default=8.0,
        gt=0,
        le=30,
    )


class WorkPlanningPreviewRead(BaseModel):
    field_id: int
    field_name: str
    field_area_m2: float

    boundary: list[list[float]]
    reference_line: list[list[float]]
    has_reference_line: bool

    tractor_id: int
    tractor_name: str
    tractor_length_m: float
    turning_radius_m: float

    implement_id: int
    implement_name: str
    implement_length_m: float
    working_width_m: float
    mount_type: str

    estimated_combination_length_m: float
    maneuver_mode: str

    suggested_headland_depth_m: float
    headland_depth_m: float
    headland_overridden: bool

    target_speed_kmh: float
    planning_status: str
    planning_notes: list[str]

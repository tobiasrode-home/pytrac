"""API-Datenmodelle für Stammdaten und Arbeitsplanung."""
from datetime import datetime
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
class TractorUpdate(TractorCreate): pass
class TractorRead(TractorCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
class ImplementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    length_m: float = Field(gt=0)
    working_width_m: float = Field(gt=0)
    mount_type: MountType
    work_offset_m: float
class ImplementUpdate(ImplementCreate): pass
class ImplementRead(ImplementCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
class FieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    boundary: list[list[float]]
    reference_line: list[list[float]] = Field(default_factory=list)
    @model_validator(mode='after')
    def validate_boundary(self):
        if len(self.boundary) < 4 or self.boundary[0] != self.boundary[-1]:
            raise ValueError('Die Feldgrenze muss mindestens drei Punkte haben und geschlossen sein.')
        return self
class FieldBoundaryUpdate(BaseModel): boundary: list[list[float]]
class FieldReferenceLineUpdate(BaseModel): reference_line: list[list[float]]
class FieldRead(BaseModel):
    id: int
    name: str
    boundary: list[list[float]]
    area_m2: float
    reference_line: list[list[float]]
    model_config = ConfigDict(from_attributes=True)

class WorkPlanningBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    tractor_id: int = Field(gt=0)
    implement_id: int = Field(gt=0)
    field_id: int = Field(gt=0)
    speed: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    turn_type: Literal['u_turn','y_turn'] = 'u_turn'
    headland_mode: Literal['all_around','headlands_only'] = 'all_around'
    bed_working: bool = False
    alignment_boundary_id: str = Field(pattern=r'^edge-[0-9]+$')
    start_boundary_a_id: str = Field(pattern=r'^edge-[0-9]+$')
    start_boundary_b_id: str = Field(pattern=r'^edge-[0-9]+$')
    headland_working_widths: int | None = Field(default=None, gt=0)
    @model_validator(mode='after')
    def validate_rules(self):
        if self.bed_working and self.turn_type != 'u_turn':
            raise ValueError('Beetbearbeitung ist nur mit U-Turn möglich.')
        if self.start_boundary_a_id == self.start_boundary_b_id:
            raise ValueError('Es müssen zwei unterschiedliche Startgrenzen gewählt werden.')
        return self
class WorkPlanningCreate(WorkPlanningBase): pass
class WorkPlanningPreviewRequest(WorkPlanningBase): pass
class WorkPlanningDefaultsRequest(BaseModel):
    tractor_id: int = Field(gt=0)
    implement_id: int = Field(gt=0)
class WorkPlanningDefaults(BaseModel):
    default_headland_working_widths: int
    tractor_length: float
    implement_length: float
    working_width: float
class WorkPlanningPreview(WorkPlanningDefaults):
    headland_working_widths: int
    start_point: list[float]
    start_boundary_ids: list[str]
class WorkPlanningRead(WorkPlanningBase):
    id: int
    headland_working_widths: int
    start_point: list[float]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class GuidanceRequest(WorkPlanningPreviewRequest):
    """Darstellungsmodus wird nur für diese Anfrage verwendet und nie gespeichert."""
    output_mode: Literal['turns', 'targets'] = 'turns'


class GuidanceSavedRequest(BaseModel):
    output_mode: Literal['turns', 'targets'] = 'turns'

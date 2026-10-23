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

# ---------------------------------------------------------------------------
# Work Planning
# ---------------------------------------------------------------------------


class WorkPlanningBase(BaseModel):
    """Gemeinsame Eingabefelder einer Arbeitsplanung."""

    name: str = Field(
        min_length=1,
        max_length=150,
        description="Bezeichnung der Arbeitsplanung",
    )

    tractor_id: int = Field(
        gt=0,
        description="ID des ausgewählten Traktors",
    )

    implement_id: int = Field(
        gt=0,
        description="ID des ausgewählten Anbaugeräts",
    )

    field_id: int = Field(
        gt=0,
        description="ID des ausgewählten Feldes",
    )

    speed: float | None = Field(
        default=None,
        gt=0,
        description="Optionale Fahrgeschwindigkeit in km/h",
    )

    turn_type: Literal["u_turn", "y_turn"] = Field(
        description="Gewähltes Wendemanöver",
    )

    headland_mode: Literal["all_around", "headlands_only"] = Field(
        description="Vorgewende rund um das Feld oder nur an den Stirnseiten",
    )

    bed_working: bool = Field(
        default=False,
        description="Feld in Beeten bearbeiten; nur beim U-Turn zulässig",
    )

    # Referenz auf eine Grenze des Feldes, die zur Ausrichtung
    # der regulären Fahrspuren verwendet wird.
    alignment_boundary_id: str = Field(
        min_length=1,
        description="ID der Ausrichtungskante des Feldes",
    )

    # Zwei Grenzen, die den gewünschten Startbereich bestimmen.
    start_boundary_a_id: str = Field(
        min_length=1,
        description="Erste Grenze zur Bestimmung des Startbereichs",
    )

    start_boundary_b_id: str = Field(
        min_length=1,
        description="Zweite Grenze zur Bestimmung des Startbereichs",
    )

    @model_validator(mode="after")
    def validate_bed_working(self):
        if self.bed_working and self.turn_type != "u_turn":
            raise ValueError(
                "Die Beetbearbeitung ist nur beim U-Turn möglich."
            )

        if self.start_boundary_a_id == self.start_boundary_b_id:
            raise ValueError(
                "Für den Startbereich müssen zwei unterschiedliche "
                "Feldgrenzen ausgewählt werden."
            )

        return self


class WorkPlanningPreviewRequest(WorkPlanningBase):
    """Eingaben für die unverbindliche Planungsvorschau."""

    headland_working_widths: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Manuelle Anzahl der Vorgewende-Arbeitsbreiten. "
            "Wenn nicht angegeben, berechnet das Backend den Standardwert."
        ),
    )


class WorkPlanningCreate(WorkPlanningBase):
    """Eingaben zum Speichern einer Arbeitsplanung."""

    headland_working_widths: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Gewünschte Anzahl der Vorgewende-Arbeitsbreiten. "
            "Wenn nicht angegeben, wird der Standardwert verwendet."
        ),
    )

    # Der Erstellungszeitpunkt wird ausschließlich serverseitig gesetzt.
    # Dieses Feld wird absichtlich nicht als Eingabefeld angeboten.


class WorkPlanningPreview(BaseModel):
    """Ergebnis der serverseitigen Planungsvorschau."""

    tractor_id: int
    implement_id: int
    field_id: int

    tractor_length: float = Field(
        gt=0,
        description="Traktorlänge in Metern",
    )

    implement_length: float = Field(
        gt=0,
        description="Länge des Anbaugeräts in Metern",
    )

    working_width: float = Field(
        gt=0,
        description="Arbeitsbreite des Anbaugeräts in Metern",
    )

    default_headland_working_widths: int = Field(
        gt=0,
        description="Vom Backend berechneter Standardwert",
    )

    headland_working_widths: int = Field(
        gt=0,
        description="Tatsächlich gewählte Anzahl der Arbeitsbreiten",
    )

    speed: float | None = Field(
        default=None,
        gt=0,
        description="Optionale Fahrgeschwindigkeit in km/h",
    )


class WorkPlanningRead(WorkPlanningBase):
    """Daten einer gespeicherten Arbeitsplanung."""

    id: int = Field(
        gt=0,
        description="Eindeutige ID der Arbeitsplanung",
    )

    headland_working_widths: int = Field(
        gt=0,
        description="Gespeicherte Anzahl der Vorgewende-Arbeitsbreiten",
    )

    created_at: datetime = Field(
        description="Serverseitiger Erstellungszeitpunkt mit Zeitzone",
    )

    model_config = ConfigDict(from_attributes=True)


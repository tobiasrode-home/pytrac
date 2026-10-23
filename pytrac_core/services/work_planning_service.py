
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from pytrac_core.api.schemas import (
    WorkPlanningCreate,
    WorkPlanningPreview,
    WorkPlanningPreviewRequest,
)
from pytrac_core.persistence.models.work_planning import WorkPlanning
from pytrac_core.persistence.repositories.work_planning_repository import (
    WorkPlanningRepository,
)


class WorkPlanningValidationError(Exception):
    """Fehler bei fachlich ungültigen Planungsdaten."""


class WorkPlanningNotFoundError(Exception):
    """Eine angeforderte Arbeitsplanung wurde nicht gefunden."""


class WorkPlanningService:
    """
    Fachlogik für Arbeitsplanungen.

    Die Klasse ist unabhängig von einem bestimmten Frontend.
    Sie kann daher später auch aus einer Kivy-Anwendung verwendet werden.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repository = WorkPlanningRepository(db)

    def preview(
        self,
        data: WorkPlanningPreviewRequest,
    ) -> WorkPlanningPreview:
        """
        Validiert die Eingaben und berechnet die Standardanzahl
        der Vorgewende-Arbeitsbreiten.

        Die Länge des Traktors und die Länge des Anbaugeräts
        werden entlang der Fahrtrichtung addiert. Die Summe wird
        durch die Arbeitsbreite geteilt und auf die nächste ganze
        Zahl aufgerundet.
        """
        tractor = self._get_tractor(data.tractor_id)
        implement = self._get_implement(data.implement_id)
        field = self._get_field(data.field_id)

        tractor_length = self._positive_number(
            getattr(tractor, "length", None),
            "Die Traktorlänge ist nicht vorhanden oder ungültig.",
        )

        implement_length = self._positive_number(
            getattr(implement, "length", None),
            "Die Anbaugerätelänge ist nicht vorhanden oder ungültig.",
        )

        working_width = self._positive_number(
            getattr(implement, "working_width", None),
            "Die Arbeitsbreite des Anbaugeräts ist nicht vorhanden oder ungültig.",
        )

        default_headland_widths = self.calculate_headland_widths(
            tractor_length=tractor_length,
            implement_length=implement_length,
            working_width=working_width,
        )

        requested_widths = getattr(
            data,
            "headland_working_widths",
            None,
        )

        headland_working_widths = (
            requested_widths
            if requested_widths is not None
            else default_headland_widths
        )

        if (
            isinstance(headland_working_widths, bool)
            or not isinstance(headland_working_widths, int)
            or headland_working_widths < 1
        ):
            raise WorkPlanningValidationError(
                "Die Anzahl der Vorgewende-Arbeitsbreiten muss "
                "eine positive ganze Zahl sein."
            )

        turn_type = getattr(data, "turn_type", None)
        bed_working = bool(getattr(data, "bed_working", False))

        if bed_working and turn_type != "u_turn":
            raise WorkPlanningValidationError(
                "Die Beetbearbeitung ist nur beim U-Turn möglich."
            )

        speed = getattr(data, "speed", None)

        if speed is not None:
            speed = self._positive_number(
                speed,
                "Die Fahrgeschwindigkeit muss größer als 0 sein.",
            )

        return WorkPlanningPreview(
            tractor_id=data.tractor_id,
            implement_id=data.implement_id,
            field_id=data.field_id,
            tractor_length=tractor_length,
            implement_length=implement_length,
            working_width=working_width,
            default_headland_working_widths=default_headland_widths,
            headland_working_widths=headland_working_widths,
            speed=speed,
        )

    def create(self, data: WorkPlanningCreate) -> WorkPlanning:
        """
        Validiert und speichert eine neue Arbeitsplanung.

        Der Erstellungszeitpunkt wird serverseitig gesetzt.
        Die Datenbank-ID identifiziert den Datensatz eindeutig.
        """
        self.preview(data)

        planning_data = data.model_dump(exclude_unset=True)

        # Keine vom Client gelieferten Erstellungszeitpunkte übernehmen.
        planning_data.pop("created_at", None)
        planning_data["created_at"] = datetime.now(timezone.utc)

        planning = self.repository.create(planning_data)

        return planning

    def list(self) -> list[WorkPlanning]:
        """Liefert alle gespeicherten Arbeitsplanungen."""
        return self.repository.list()

    def get(self, planning_id: int) -> WorkPlanning:
        """Liefert eine Arbeitsplanung anhand ihrer ID."""
        planning = self.repository.get(planning_id)

        if planning is None:
            raise WorkPlanningNotFoundError(
                f"Arbeitsplanung {planning_id} wurde nicht gefunden."
            )

        return planning

    def delete(self, planning_id: int) -> None:
        """Löscht eine Arbeitsplanung anhand ihrer ID."""
        planning = self.repository.get(planning_id)

        if planning is None:
            raise WorkPlanningNotFoundError(
                f"Arbeitsplanung {planning_id} wurde nicht gefunden."
            )

        self.repository.delete(planning)

    @staticmethod
    def calculate_headland_widths(
        tractor_length: float,
        implement_length: float,
        working_width: float,
    ) -> int:
        """
        Berechnet die erforderlichen Arbeitsbreiten für das Vorgewende.

        Beispiele:
        - (4 m + 2 m) / 3 m = 2 Arbeitsbreiten
        - (4 m + 2 m) / 2,5 m = 3 Arbeitsbreiten
        """
        tractor_length = WorkPlanningService._positive_number(
            tractor_length,
            "Die Traktorlänge muss größer als 0 sein.",
        )
        implement_length = WorkPlanningService._positive_number(
            implement_length,
            "Die Anbaugerätelänge muss größer als 0 sein.",
        )
        working_width = WorkPlanningService._positive_number(
            working_width,
            "Die Arbeitsbreite muss größer als 0 sein.",
        )

        total_length = tractor_length + implement_length

        # ceil(total_length / working_width), ohne Rundungsfehler
        # bei mathematisch ganzzahligen Ergebnissen.
        from math import ceil

        return ceil(total_length / working_width - 1e-12)

    def _get_tractor(self, tractor_id: int):
        """
        Lädt den Traktor über das bestehende Datenmodell.

        Der konkrete Import wird an die vorhandene Modellstruktur
        angepasst, sobald diese verbindlich vorliegt.
        """
        from pytrac_core.persistence.models.tractor import Tractor

        tractor = self.db.get(Tractor, tractor_id)

        if tractor is None:
            raise WorkPlanningValidationError(
                f"Traktor {tractor_id} wurde nicht gefunden."
            )

        return tractor

    def _get_implement(self, implement_id: int):
        """Lädt das ausgewählte Anbaugerät."""
        from pytrac_core.persistence.models.implement import Implement

        implement = self.db.get(Implement, implement_id)

        if implement is None:
            raise WorkPlanningValidationError(
                f"Anbaugerät {implement_id} wurde nicht gefunden."
            )

        return implement

    def _get_field(self, field_id: int):
        """Lädt das ausgewählte Feld."""
        from pytrac_core.persistence.models.field import Field

        field = self.db.get(Field, field_id)

        if field is None:
            raise WorkPlanningValidationError(
                f"Feld {field_id} wurde nicht gefunden."
            )

        return field

    @staticmethod
    def _positive_number(value, error_message: str) -> float:
        """Validiert eine positive, endliche Zahl."""
        import math

        if isinstance(value, bool) or value is None:
            raise WorkPlanningValidationError(error_message)

        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise WorkPlanningValidationError(error_message) from exc

        if not math.isfinite(number) or number <= 0:
            raise WorkPlanningValidationError(error_message)

        return number

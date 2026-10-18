import json
import math

from sqlalchemy.orm import Session

from pytrac_core.persistence.models.field import Field
from pytrac_core.persistence.models.tractor import Tractor
from pytrac_core.persistence.models.implement import Implement


class WorkPlanningError(Exception):
    """Fehler bei der Arbeitsplanung."""


class WorkPlanningService:
    def __init__(self, db: Session):
        self.db = db

    def preview(
        self,
        field_id: int,
        tractor_id: int,
        implement_id: int,
        maneuver_mode: str = "u_turn",
        headland_depth_override_m: float | None = None,
        target_speed_kmh: float = 8.0,
    ) -> dict:
        field = self.db.get(Field, field_id)
        tractor = self.db.get(Tractor, tractor_id)
        implement = self.db.get(Implement, implement_id)

        if field is None:
            raise WorkPlanningError(
                f"Feld mit ID {field_id} wurde nicht gefunden."
            )

        if tractor is None:
            raise WorkPlanningError(
                f"Traktor mit ID {tractor_id} wurde nicht gefunden."
            )

        if implement is None:
            raise WorkPlanningError(
                f"Anbaugerät mit ID {implement_id} wurde nicht gefunden."
            )

        modes = {"u_turn", "y_turn", "k_turn", "beet"}

        if maneuver_mode not in modes:
            raise WorkPlanningError(
                "Unbekanntes Wendemanöver."
            )

        if not math.isfinite(target_speed_kmh) or target_speed_kmh <= 0:
            raise WorkPlanningError(
                "Die Sollgeschwindigkeit muss größer als 0 sein."
            )

        if headland_depth_override_m is not None:
            if (
                not math.isfinite(headland_depth_override_m)
                or headland_depth_override_m <= 0
            ):
                raise WorkPlanningError(
                    "Die Vorgewendetiefe muss größer als 0 sein."
                )

        boundary = json.loads(field.boundary_json)
        reference_line = json.loads(field.reference_line_json)

        # Vorläufige Näherung: Beide Längen werden addiert.
        # Die tatsächliche Gespannlänge hängt von der
        # Kupplungsposition und Anbauart ab.
        estimated_length = tractor.length_m + implement.length_m

        # Vorläufige geometrische Schätzung, noch keine
        # validierte Wendekurvenberechnung.
        suggested_headland_depth = max(
            2.0 * tractor.turning_radius_m + implement.length_m,
            2.0 * implement.working_width_m,
        )

        effective_headland_depth = (
            headland_depth_override_m
            if headland_depth_override_m is not None
            else suggested_headland_depth
        )

        return {
            "field_id": field.id,
            "field_name": field.name,
            "field_area_m2": field.area_m2,
            "boundary": boundary,
            "reference_line": reference_line,
            "has_reference_line": len(reference_line) >= 2,
            "tractor_id": tractor.id,
            "tractor_name": tractor.name,
            "tractor_length_m": tractor.length_m,
            "turning_radius_m": tractor.turning_radius_m,
            "implement_id": implement.id,
            "implement_name": implement.name,
            "implement_length_m": implement.length_m,
            "working_width_m": implement.working_width_m,
            "mount_type": implement.mount_type.value,
            "estimated_combination_length_m": estimated_length,
            "maneuver_mode": maneuver_mode,
            "suggested_headland_depth_m": suggested_headland_depth,
            "headland_depth_m": effective_headland_depth,
            "headland_overridden": (
                headland_depth_override_m is not None
            ),
            "target_speed_kmh": target_speed_kmh,
            "planning_status": "preliminary",
            "planning_notes": [
                "Gespannlänge ist eine Näherung.",
                "Vorgewendetiefe ist noch nicht anhand "
                "berechneter Wendekurven validiert.",
                "Fahrspuren und Wendemanöver werden in "
                "einem späteren Planungsschritt berechnet.",
            ],
        }


from __future__ import annotations

from math import ceil, hypot, isfinite
from typing import Sequence, TypeAlias


Point: TypeAlias = tuple[float, float]
Ring: TypeAlias = list[Point]


class WorkPlanningGeometryError(ValueError):
    """Fehler bei ungültigen geometrischen Planungsdaten."""


def _validate_point(point: Point) -> Point:
    """Prüft einen zweidimensionalen Punkt."""
    if len(point) != 2:
        raise WorkPlanningGeometryError(
            "Ein Punkt muss aus genau zwei Koordinaten bestehen."
        )

    x, y = point

    if not isfinite(x) or not isfinite(y):
        raise WorkPlanningGeometryError(
            "Punktkoordinaten müssen endlich sein."
        )

    return float(x), float(y)


def _validate_positive(value: float, name: str) -> float:
    """Prüft einen positiven, endlichen Zahlenwert."""
    if isinstance(value, bool):
        raise WorkPlanningGeometryError(
            f"{name} muss eine positive Zahl sein."
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise WorkPlanningGeometryError(
            f"{name} muss eine positive Zahl sein."
        ) from exc

    if not isfinite(result) or result <= 0:
        raise WorkPlanningGeometryError(
            f"{name} muss größer als 0 sein."
        )

    return result


def calculate_headland_widths(
    tractor_length: float,
    implement_length: float,
    working_width: float,
) -> int:
    """
    Berechnet die Anzahl der Arbeitsbreiten für das Vorgewende.

    Beispiel:
        Traktor: 4 m
        Anbaugerät: 2 m
        Arbeitsbreite: 3 m
        Ergebnis: 2 Arbeitsbreiten

    Die Berechnung erfolgt mit Aufrundung.
    """
    tractor_length = _validate_positive(
        tractor_length,
        "Traktorlänge",
    )
    implement_length = _validate_positive(
        implement_length,
        "Anbaugerätelänge",
    )
    working_width = _validate_positive(
        working_width,
        "Arbeitsbreite",
    )

    combined_length = tractor_length + implement_length

    return ceil(combined_length / working_width - 1e-12)


def calculate_distance(point_a: Point, point_b: Point) -> float:
    """Berechnet den euklidischen Abstand zweier Punkte."""
    ax, ay = _validate_point(point_a)
    bx, by = _validate_point(point_b)

    return hypot(bx - ax, by - ay)


def calculate_distance_to_segment(
    point: Point,
    segment_start: Point,
    segment_end: Point,
) -> float:
    """Berechnet den kürzesten Abstand eines Punktes zu einer Strecke."""
    px, py = _validate_point(point)
    ax, ay = _validate_point(segment_start)
    bx, by = _validate_point(segment_end)

    dx = bx - ax
    dy = by - ay
    length_squared = dx * dx + dy * dy

    if length_squared == 0:
        return hypot(px - ax, py - ay)

    projection = (
        (px - ax) * dx + (py - ay) * dy
    ) / length_squared

    projection = max(0.0, min(1.0, projection))

    closest_x = ax + projection * dx
    closest_y = ay + projection * dy

    return hypot(px - closest_x, py - closest_y)


def find_nearest_point_index(
    point: Point,
    points: Sequence[Point],
) -> int:
    """
    Liefert den Index des nächstgelegenen Punktes einer Punktfolge.

    Diese Funktion eignet sich beispielsweise für die Auswahl des
    nächstgelegenen Punktes einer bereits berechneten Fahrspur.
    """
    if not points:
        raise WorkPlanningGeometryError(
            "Die Punktfolge darf nicht leer sein."
        )

    target = _validate_point(point)

    return min(
        range(len(points)),
        key=lambda index: calculate_distance(
            target,
            points[index],
        ),
    )


def calculate_polygon_area(ring: Sequence[Point]) -> float:
    """
    Berechnet die Fläche eines einfachen Polygons mittels Shoelace-Formel.

    Die Punkte müssen in der Reihenfolge entlang des Polygonrandes
    angegeben sein. Die Fläche wird in Quadratkoordinateneinheiten
    zurückgegeben.
    """
    if len(ring) < 3:
        raise WorkPlanningGeometryError(
            "Ein Polygon benötigt mindestens drei Punkte."
        )

    points = [_validate_point(point) for point in ring]

    area_twice = 0.0

    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area_twice += x1 * y2 - x2 * y1

    return abs(area_twice) / 2.0


def validate_polygon(ring: Sequence[Point]) -> Ring:
    """
    Prüft die grundlegenden Voraussetzungen einer Feldgrenze.

    Diese Prüfung erkennt zu wenige Punkte und Flächen von null.
    Sie ersetzt keine vollständige Prüfung auf Selbstüberschneidungen.
    """
    if len(ring) < 3:
        raise WorkPlanningGeometryError(
            "Die Feldgrenze benötigt mindestens drei Punkte."
        )

    points = [_validate_point(point) for point in ring]

    # Ein wiederholter Schlusspunkt ist erlaubt.
    if points[0] == points[-1]:
        points = points[:-1]

    if len(points) < 3:
        raise WorkPlanningGeometryError(
            "Die Feldgrenze enthält zu wenige unterschiedliche Punkte."
        )

    if calculate_polygon_area(points) == 0:
        raise WorkPlanningGeometryError(
            "Die Feldgrenze besitzt keine Fläche."
        )

    return points

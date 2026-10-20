"""Kartenebenen für PyTrac: Feldgrenzen und gefahrene Spuren."""

from kivy.graphics import Color, Line
from kivy_garden.mapview import MapLayer


def _rings_from_field(field):
    """Normalisiert Backend-Koordinatenlisten und GeoJSON auf Ringe."""
    boundary = (field or {}).get("boundary") or []
    if isinstance(boundary, dict):
        geometry_type = boundary.get("type")
        coordinates = boundary.get("coordinates") or []
        if geometry_type == "Polygon":
            return coordinates
        if geometry_type == "MultiPolygon":
            return [ring for polygon in coordinates for ring in polygon]
        return []
    # Aktuelles Backend: [[longitude, latitude], ...]
    if isinstance(boundary, list) and boundary and isinstance(boundary[0], (list, tuple)):
        if len(boundary[0]) >= 2 and all(
            isinstance(value, (int, float)) for value in boundary[0][:2]
        ):
            return [boundary]
    return []


def field_center(field):
    """Ermittelt den Mittelpunkt der Feldgrenze."""
    rings = _rings_from_field(field)
    if not rings:
        return None
    points = rings[0]
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if not points:
        return None
    try:
        longitude = sum(float(point[0]) for point in points) / len(points)
        latitude = sum(float(point[1]) for point in points) / len(points)
        return latitude, longitude
    except (IndexError, TypeError, ValueError):
        return None


class FieldOverlay(MapLayer):
    """Zeichnet Feldgrenzen und GPS-Spuren über MapView."""

    def __init__(self, map_view, **kwargs):
        super().__init__(**kwargs)
        self.map_view = map_view
        self.field = None
        self.track_points = []

    def set_data(self, field=None, track_points=None):
        self.field = field
        self.track_points = track_points or []
        self.draw()

    def reposition(self):
        """Wird von MapView beim Verschieben und Zoomen aufgerufen."""
        self.draw()

    def _project(self, longitude, latitude):
        return self.map_view.get_window_xy_from(
            latitude,
            longitude,
            self.map_view.zoom,
        )

    def draw(self):
        self.canvas.clear()

        with self.canvas:
            if self.field:
                for ring in _rings_from_field(self.field):
                    points = []

                    for coordinate in ring:
                        try:
                            lon = float(coordinate[0])
                            lat = float(coordinate[1])
                            x, y = self._project(lon, lat)
                            points.extend([x, y])
                        except (IndexError, TypeError, ValueError):
                            continue

                    if len(points) >= 6:
                        Color(0.20, 0.95, 0.42, 1)
                        Line(points=points, width=2.2, close=True)

            track = []

            for point in self.track_points:
                try:
                    lat = float(point["latitude"])
                    lon = float(point["longitude"])
                    x, y = self._project(lon, lat)
                    track.extend([x, y])
                except (KeyError, IndexError, TypeError, ValueError):
                    continue

            if len(track) >= 4:
                Color(1.0, 0.72, 0.12, 1)
                Line(points=track, width=2.5)

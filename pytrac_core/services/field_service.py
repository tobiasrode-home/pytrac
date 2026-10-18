from __future__ import annotations
import json

from shapely.geometry import LineString, Polygon
from shapely.validation import explain_validity
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


from pytrac_core.persistence.models.field import Field


class FieldNotFoundError(Exception):
    """Das Feld existiert nicht."""


class FieldAlreadyExistsError(Exception):
    """Ein Feld mit diesem Namen existiert bereits."""


class FieldGeometryError(ValueError):
    """Die übermittelte Feldgeometrie ist ungültig."""


class FieldService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _parse_boundary(boundary: list[list[float]]) -> Polygon:
        if len(boundary) < 3:
            raise FieldGeometryError(
                "Ein Feld benötigt mindestens drei Grenzpunkte."
            )

        for point in boundary:
            if len(point) != 2:
                raise FieldGeometryError(
                    "Jeder Punkt muss [longitude, latitude] enthalten."
                )

            lon, lat = point
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise FieldGeometryError(
                    "Ungültige geografische Koordinaten."
                )

        # GeoJSON verwendet [longitude, latitude].
        polygon = Polygon(boundary)

        if not polygon.is_valid:
            raise FieldGeometryError(
                f"Ungültiges Feldpolygon: {explain_validity(polygon)}"
            )

        if polygon.is_empty or polygon.area == 0:
            raise FieldGeometryError(
                "Das Feldpolygon hat keine Fläche."
            )

        return polygon

    @staticmethod
    def _area_m2(polygon: Polygon) -> float:
        """Näherungsweise Flächenberechnung in einer lokalen UTM-Zone."""
        from pyproj import Transformer
        from shapely.ops import transform

        lon, lat = polygon.representative_point().x, (
            polygon.representative_point().y
        )

        zone = int((lon + 180) // 6) + 1
        epsg = (32600 if lat >= 0 else 32700) + zone

        transformer = Transformer.from_crs(
            "EPSG:4326",
            f"EPSG:{epsg}",
            always_xy=True,
        )

        projected = transform(transformer.transform, polygon)
        return float(projected.area)

    @staticmethod
    def _boundary_json(boundary: list[list[float]]) -> str:
        # JSON-Array der Punkte, jeweils [longitude, latitude].
        return json.dumps(boundary)

    @staticmethod
    def _reference_line_json(points: list[list[float]]) -> str:
        return json.dumps(points)

    def list(self) -> list[Field]:
        return list(
            self.db.scalars(select(Field).order_by(Field.name))
        )

    def get(self, field_id: int) -> Field:
        field = self.db.get(Field, field_id)
        if field is None:
            raise FieldNotFoundError(
                f"Feld mit ID {field_id} wurde nicht gefunden."
            )
        return field

    def create(
        self,
        name: str,
        boundary: list[list[float]],
        reference_line: list[list[float]] | None = None,
    ) -> Field:
        polygon = self._parse_boundary(boundary)
        area = self._area_m2(polygon)

        if reference_line is None:
            reference_line = []

        self._validate_reference_line(reference_line)

        field = Field(
            name=name,
            boundary_json=self._boundary_json(boundary),
            area_m2=area,
            reference_line_json=self._reference_line_json(reference_line),
        )
        self.db.add(field)

        try:
            self.db.commit()
            self.db.refresh(field)
        except IntegrityError as exc:
            self.db.rollback()
            raise FieldAlreadyExistsError(
                "Ein Feld mit diesem Namen existiert bereits."
            ) from exc

        return field

    def update_boundary(
        self,
        field_id: int,
        boundary: list[list[float]],
    ) -> Field:
        field = self.get(field_id)
        polygon = self._parse_boundary(boundary)

        field.boundary_json = self._boundary_json(boundary)
        field.area_m2 = self._area_m2(polygon)

        self.db.commit()
        self.db.refresh(field)
        return field

    def set_reference_line(
        self,
        field_id: int,
        points: list[list[float]],
    ) -> Field:
        field = self.get(field_id)
        self._validate_reference_line(points)

        field.reference_line_json = self._reference_line_json(points)
        self.db.commit()
        self.db.refresh(field)
        return field

    def delete(self, field_id: int) -> None:
        field = self.get(field_id)
        self.db.delete(field)
        self.db.commit()

    @staticmethod
    def _validate_reference_line(points: list[list[float]]) -> None:
        if not points:
            return

        if len(points) < 2:
            raise FieldGeometryError(
                "Eine Referenzlinie benötigt mindestens zwei Punkte."
            )

        for point in points:
            if len(point) != 2:
                raise FieldGeometryError(
                    "Jeder Referenzpunkt muss [longitude, latitude] enthalten."
                )

            lon, lat = point
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise FieldGeometryError(
                    "Ungültige Koordinaten in der Referenzlinie."
                )

        line = LineString(points)
        if line.is_empty or line.length == 0:
            raise FieldGeometryError(
                "Die Referenzlinie muss eine Länge größer null haben."
            )

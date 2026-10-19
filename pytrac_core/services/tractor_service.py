import math

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pytrac_core.persistence.models.tractor import Tractor


class TractorNotFoundError(Exception):
    """Der angeforderte Traktor existiert nicht."""


class TractorAlreadyExistsError(Exception):
    """Ein Traktor mit diesem Namen existiert bereits."""


class TractorService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _validate(data: dict) -> None:
        for key in ("length_m", "width_m", "wheelbase_m"):
            value = data.get(key)

            if value is not None:
                if (
                    not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    raise ValueError(
                        f"{key} muss eine endliche Zahl "
                        "größer als 0 sein."
                    )

        angle = data.get("max_steering_angle_deg")

        if angle is not None:
            if (
                not isinstance(angle, (int, float))
                or not math.isfinite(angle)
                or not 0 < angle < 90
            ):
                raise ValueError(
                    "max_steering_angle_deg muss größer als 0 "
                    "und kleiner als 90 Grad sein."
                )

        for key in ("gps_offset_length_m", "gps_offset_width_m"):
            value = data.get(key)

            if value is not None:
                if (
                    not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError(
                        f"{key} muss eine endliche Zahl sein."
                    )

    def list(self) -> list[Tractor]:
        return list(
            self.db.scalars(
                select(Tractor).order_by(Tractor.name)
            )
        )

    def get(self, tractor_id: int) -> Tractor:
        tractor = self.db.get(Tractor, tractor_id)

        if tractor is None:
            raise TractorNotFoundError(
                f"Traktor mit ID {tractor_id} wurde nicht gefunden."
            )

        return tractor

    def create(self, data: dict) -> Tractor:
        self._validate(data)

        tractor = Tractor(**data)
        self.db.add(tractor)

        try:
            self.db.commit()
            self.db.refresh(tractor)
        except IntegrityError as exc:
            self.db.rollback()
            raise TractorAlreadyExistsError(
                "Ein Traktor mit diesem Namen existiert bereits."
            ) from exc

        return tractor

    def update(self, tractor_id: int, data: dict) -> Tractor:
        tractor = self.get(tractor_id)
        self._validate(data)

        for key, value in data.items():
            if key != "id" and hasattr(tractor, key):
                setattr(tractor, key, value)

        try:
            self.db.commit()
            self.db.refresh(tractor)
        except IntegrityError as exc:
            self.db.rollback()
            raise TractorAlreadyExistsError(
                "Ein Traktor mit diesem Namen existiert bereits."
            ) from exc

        return tractor

    def delete(self, tractor_id: int) -> None:
        tractor = self.get(tractor_id)
        self.db.delete(tractor)
        self.db.commit()


from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pytrac_core.persistence.models.implement import Implement


class ImplementNotFoundError(Exception):
    """Das Anbaugerät existiert nicht."""


class ImplementAlreadyExistsError(Exception):
    """Ein Anbaugerät mit diesem Namen existiert bereits."""


class ImplementService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _validate(data: dict) -> None:
        for key in ("length_m", "working_width_m"):
            value = data.get(key)
            if value is not None and value <= 0:
                raise ValueError(f"{key} muss größer als 0 sein.")

        value = data.get("work_offset_m")
        if value is not None and not isinstance(value, (int, float)):
            raise ValueError("work_offset_m muss eine Zahl sein.")

    def list(self) -> list[Implement]:
        return list(
            self.db.scalars(
                select(Implement).order_by(Implement.name)
            )
        )

    def get(self, implement_id: int) -> Implement:
        implement = self.db.get(Implement, implement_id)
        if implement is None:
            raise ImplementNotFoundError(
                f"Anbaugerät mit ID {implement_id} wurde nicht gefunden."
            )
        return implement

    def create(self, data: dict) -> Implement:
        self._validate(data)
        implement = Implement(**data)
        self.db.add(implement)

        try:
            self.db.commit()
            self.db.refresh(implement)
        except IntegrityError as exc:
            self.db.rollback()
            raise ImplementAlreadyExistsError(
                "Ein Anbaugerät mit diesem Namen existiert bereits."
            ) from exc

        return implement

    def update(self, implement_id: int, data: dict) -> Implement:
        implement = self.get(implement_id)
        self._validate(data)

        for key, value in data.items():
            if key != "id" and hasattr(implement, key):
                setattr(implement, key, value)

        try:
            self.db.commit()
            self.db.refresh(implement)
        except IntegrityError as exc:
            self.db.rollback()
            raise ImplementAlreadyExistsError(
                "Ein Anbaugerät mit diesem Namen existiert bereits."
            ) from exc

        return implement

    def delete(self, implement_id: int) -> None:
        implement = self.get(implement_id)
        self.db.delete(implement)
        self.db.commit()


"""Stellt den aktuellen Fahrzeugzustand im Arbeitsspeicher bereit."""

import threading
from datetime import datetime, timezone

from pytrac_core.sensors.models import VehicleState


class VehicleService:
    """Verwaltet den zuletzt empfangenen Fahrzeugzustand."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_state: VehicleState | None = None
        self._last_received_at: datetime | None = None

    def update_state(self, state: VehicleState) -> None:
        """
        Übernimmt einen neuen synchronisierten Fahrzeugzustand.

        Diese Methode wird vom SensorManager über den Callback
        des Synchronisierers aufgerufen.
        """
        with self._lock:
            # Keine älteren Zustände übernehmen.
            if (
                self._last_state is not None
                and state.timestamp < self._last_state.timestamp
            ):
                return

            self._last_state = state
            self._last_received_at = datetime.now(timezone.utc)

    def get_last_state(self) -> VehicleState | None:
        """Gibt den zuletzt empfangenen Fahrzeugzustand zurück."""
        with self._lock:
            return self._last_state

    def get_last_received_at(self) -> datetime | None:
        """Gibt den Empfangszeitpunkt des letzten Zustands zurück."""
        with self._lock:
            return self._last_received_at

    def is_available(self, max_age_s: float = 2.0) -> bool:
        """
        Prüft, ob ein Fahrzeugzustand vorhanden und aktuell ist.

        max_age_s bezieht sich auf den Empfang im Backend,
        nicht auf den GPS-Zeitstempel.
        """
        with self._lock:
            if self._last_state is None:
                return False

            if self._last_received_at is None:
                return False

            age = (
                datetime.now(timezone.utc) - self._last_received_at
            ).total_seconds()

            return 0 <= age <= max_age_s

    def clear(self) -> None:
        """Setzt den gespeicherten Fahrzeugzustand zurück."""
        with self._lock:
            self._last_state = None
            self._last_received_at = None

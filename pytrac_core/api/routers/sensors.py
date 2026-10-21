"""HTTP-Endpunkte für den zuletzt synchronisierten Fahrzeugzustand."""

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["Sensors"])


def _state_payload(request: Request) -> dict[str, Any]:
    service = getattr(request.app.state, "vehicle_service", None)
    if service is None:
        return {
            "available": False,
            "gps_valid": False,
            "imu_valid": False,
            "reason": "Sensor-Service ist noch nicht gestartet.",
            "timestamp": None,
            "latitude": None,
            "longitude": None,
            "heading_deg": None,
            "pitch_deg": None,
            "roll_deg": None,
            "speed_mps": None,
            "altitude_m": None,
            "gps_accuracy_m": None,
        }

    state = service.get_last_state()
    available = service.is_available()
    if state is None:
        payload: dict[str, Any] = {
            "available": False,
            "gps_valid": False,
            "imu_valid": False,
            "reason": "Noch keine Sensordaten empfangen.",
            "timestamp": None,
            "latitude": None,
            "longitude": None,
            "heading_deg": None,
            "pitch_deg": None,
            "roll_deg": None,
            "speed_mps": None,
            "altitude_m": None,
            "gps_accuracy_m": None,
        }
    else:
        payload = asdict(state)
        timestamp = payload.get("timestamp")
        if isinstance(timestamp, datetime):
            payload["timestamp"] = timestamp.isoformat()
        for key in ("gps_timestamp", "imu_timestamp"):
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        payload["available"] = available
        if not available:
            payload["gps_valid"] = False
            payload["reason"] = "Sensordaten sind nicht mehr aktuell."
        elif not payload.get("gps_valid", False):
            payload["reason"] = "Kein gültiger GPS-Fix."
    received_at = service.get_last_received_at()
    payload["received_at"] = received_at.isoformat() if received_at else None
    return payload


@router.get("/vehicle/state")
def vehicle_state(request: Request) -> dict[str, Any]:
    """Liefert den letzten Zustand samt Aktualitäts- und GPS-Status."""
    return _state_payload(request)



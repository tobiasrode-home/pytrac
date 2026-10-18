
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pytrac_core.config import settings
from pytrac_core.sensors.models import VehicleState
from pytrac_core.sensors.sensor_manager import SensorManager
from pytrac_core.services.vehicle_service import VehicleService
from pytrac_core.persistence.init_db import init_db
from pytrac_core.api.routers.tractors import router as tractors_router
from pytrac_core.api.routers.implements import router as implements_router
from pytrac_core.api.routers.fields import router as fields_router
from pytrac_core.api.routers.work_planning import (
    router as work_planning_router,
)
from pathlib import Path
from fastapi.responses import FileResponse
import logging

#logging.basicConfig(
#    level=logging.INFO,
#    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
#)
vehicle_service = VehicleService()

def print_vehicle_state(state: VehicleState) -> None:
    """Gibt den aktuellen Fahrzeugzustand in der Konsole aus."""

    vehicle_service.update_state(state)

    print(
        f"[PYTRAC] "
        f"Zeit: {state.timestamp.isoformat()} | "
        f"Position: {state.latitude:.7f}, {state.longitude:.7f} | "
        f"Richtung: {state.heading_deg:.1f}° | "
        f"Geschwindigkeit: "
        f"{state.speed_mps if state.speed_mps is not None else 0.0:.2f} m/s | "
        f"Pitch: {state.pitch_deg:.1f}° | "
        f"Roll: {state.roll_deg:.1f}°",
        flush=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    sensor_manager = SensorManager(
        gps_port=settings.gps_port,
        imu_port=settings.imu_port,
        gps_baudrate=settings.gps_baudrate,
        imu_baudrate=settings.imu_baudrate,
        output_rate_hz=settings.sensor_output_rate_hz,
        on_state=print_vehicle_state,
    )

    app.state.vehicle_service = vehicle_service
    app.state.sensor_manager = sensor_manager

    sensor_manager.start()

    print("[PYTRAC] Sensoren gestartet.", flush=True)

    try:
        yield
    finally:
        sensor_manager.stop()
        print("[PYTRAC] Sensoren gestoppt.", flush=True)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(tractors_router)
app.include_router(implements_router)
app.include_router(fields_router)
app.include_router(work_planning_router)



WEB_DIR = Path(__file__).resolve().parent / "pytrac_web"

@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(WEB_DIR / "index.html")



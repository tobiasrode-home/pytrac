from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pytrac_core.config import settings
from pytrac_core.sensors.models import VehicleState
from pytrac_core.sensors.sensor_manager import SensorManager
from pytrac_core.services.vehicle_service import VehicleService
from pytrac_core.persistence.init_db import init_db
from pytrac_core.api.routers.tractors import router as tractors_router
from pytrac_core.api.routers.implements import router as implements_router
from pytrac_core.api.routers.fields import router as fields_router
from pytrac_core.api.routers.sensors import router as sensors_router
from pytrac_core.api.routers.work_planning import router as work_planning_router

from pytrac_core.api.routers.work_progress import router as work_progress_router

from pytrac_core.api.routers.navigation_settings import router as navigation_settings_router
from pytrac_core.api.routers.data_import import router as data_import_router

vehicle_service = VehicleService()

def print_vehicle_state(state: VehicleState) -> None:
    vehicle_service.update_state(state)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    sensor_manager = SensorManager(gps_port=settings.gps_port, imu_port=settings.imu_port,
        gps_baudrate=settings.gps_baudrate, imu_baudrate=settings.imu_baudrate,
        output_rate_hz=settings.sensor_output_rate_hz, on_state=print_vehicle_state)
    app.state.vehicle_service = vehicle_service
    app.state.sensor_manager = sensor_manager
    sensor_manager.start()
    print('[PYTRAC] Sensoren gestartet.', flush=True)
    try: yield
    finally:
        sensor_manager.stop()
        print('[PYTRAC] Sensoren gestoppt.', flush=True)

app = FastAPI(title=settings.app_name, version='0.1.0', lifespan=lifespan)
app.include_router(tractors_router)
app.include_router(implements_router)
app.include_router(fields_router)
app.include_router(sensors_router)
app.include_router(work_planning_router)
app.include_router(work_progress_router)
app.include_router(navigation_settings_router)
app.include_router(data_import_router)
WEB_DIR = Path(__file__).resolve().parent / 'pytrac_web'
app.mount('/js', StaticFiles(directory=WEB_DIR / 'js'), name='js')
app.mount('/css', StaticFiles(directory=WEB_DIR / 'css'), name='css')
@app.get('/', include_in_schema=False)
async def serve_frontend():
    return FileResponse(WEB_DIR / 'index.html')

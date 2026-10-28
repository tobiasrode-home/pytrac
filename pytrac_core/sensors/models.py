from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class GpsMeasurement:
    timestamp: datetime
    received_monotonic: float
    latitude: float | None
    longitude: float | None
    altitude_m: float | None = None
    speed_mps: float | None = None
    course_deg: float | None = None
    fix_quality: int = 0
    satellites: int | None = None
    hdop: float | None = None
    gps_fix_quality: int | None = None

    @property
    def valid(self) -> bool:
        return (self.fix_quality > 0 and self.latitude is not None and
                self.longitude is not None and -90 <= self.latitude <= 90 and
                -180 <= self.longitude <= 180)

@dataclass(frozen=True, slots=True)
class ImuMeasurement:
    timestamp: datetime
    received_monotonic: float
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    accel_x_mps2: float
    accel_y_mps2: float
    accel_z_mps2: float

@dataclass(frozen=True, slots=True)
class VehicleState:
    timestamp: datetime
    latitude: float
    longitude: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float
    speed_mps: float | None = None
    altitude_m: float | None = None
    gps_accuracy_m: float | None = None
    gps_fix_quality: int | None = None
    gps_valid: bool = True
    imu_valid: bool = True
    gps_timestamp: datetime | None = None
    imu_timestamp: datetime | None = None

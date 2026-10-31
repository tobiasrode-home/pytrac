"""Robuste GPS-geführte Fahrzeugzustände mit optionaler BNO085-IMU.

GPS und IMU werden unabhängig empfangen. Ein IMU-Ausfall darf GPS nicht
blockieren. Empfangsalter wird ausschließlich mit monotonic gemessen.
"""
from collections import deque
from collections.abc import Callable
import logging
import math
import threading
import time
from pytrac_core.sensors.models import GpsMeasurement, ImuMeasurement, VehicleState

logger = logging.getLogger(__name__)
VehicleStateCallback = Callable[[VehicleState], None]


class SensorSynchronizer:
    def __init__(self, on_state: VehicleStateCallback, output_rate_hz: float = 5.0,
                 max_time_difference_s: float = 0.15,
                 max_measurement_age_s: float = 0.5):
        if output_rate_hz <= 0 or max_time_difference_s <= 0 or max_measurement_age_s <= 0:
            raise ValueError('Sensor-Zeitparameter müssen größer als 0 sein.')
        self.on_state = on_state
        self.interval_s = 1.0 / output_rate_hz
        self.max_time_difference_s = max_time_difference_s
        self.max_measurement_age_s = max_measurement_age_s
        self._lock = threading.Lock()
        self._gps_buffer = deque(maxlen=20)
        self._imu_buffer = deque(maxlen=100)
        self._last_emitted_gps_time = None
        self._last_heading = 0.0
        self._last_imu_valid = None
        self._last_gps_quality = None

    def add_gps(self, measurement: GpsMeasurement):
        if not measurement.valid:
            return
        with self._lock:
            if self._gps_buffer and measurement.received_monotonic <= self._gps_buffer[-1].received_monotonic:
                return
            self._gps_buffer.append(measurement)

    def add_imu(self, measurement: ImuMeasurement):
        if not all(math.isfinite(v) for v in (measurement.yaw_deg, measurement.pitch_deg, measurement.roll_deg)):
            return
        with self._lock:
            if self._imu_buffer and measurement.received_monotonic <= self._imu_buffer[-1].received_monotonic:
                return
            self._imu_buffer.append(measurement)

    def _next_state(self, now: float) -> VehicleState | None:
        with self._lock:
            if not self._gps_buffer:
                return None
            gps = self._gps_buffer[-1]
            gps_time = gps.received_monotonic
            if gps_time == self._last_emitted_gps_time:
                return None
            if not 0 <= now - gps_time <= self.max_measurement_age_s:
                return None

            imu = None
            if self._imu_buffer:
                candidate = min(self._imu_buffer, key=lambda m: abs(m.received_monotonic - gps_time))
                if (abs(candidate.received_monotonic - gps_time) <= self.max_time_difference_s
                        and 0 <= now - candidate.received_monotonic <= self.max_measurement_age_s):
                    imu = candidate

            if imu is not None:
                heading = imu.yaw_deg % 360.0
                pitch, roll = imu.pitch_deg, imu.roll_deg
                self._last_heading = heading
            else:
                # GNSS course-over-ground ist nur bei ausreichender Fahrt brauchbar.
                if (gps.course_deg is not None and math.isfinite(gps.course_deg)
                        and gps.speed_mps is not None and gps.speed_mps >= 0.8):
                    heading = gps.course_deg % 360.0
                    self._last_heading = heading
                else:
                    heading = self._last_heading
                pitch = roll = 0.0  # Keine alten IMU-Neigungen als aktuelle Werte ausgeben.

            quality = gps.gps_fix_quality if gps.gps_fix_quality is not None else gps.fix_quality
            if quality != self._last_gps_quality:
                logger.info('GNSS-Fixqualität: %s -> %s', self._last_gps_quality, quality)
                self._last_gps_quality = quality
            if (imu is not None) != self._last_imu_valid:
                logger.warning('IMU-Synchronstatus: %s', 'aktuell' if imu is not None else 'nicht synchron/veraltet')
                self._last_imu_valid = imu is not None

            self._last_emitted_gps_time = gps_time
            while self._gps_buffer and self._gps_buffer[0].received_monotonic < gps_time:
                self._gps_buffer.popleft()
            cutoff = gps_time - self.max_time_difference_s
            while self._imu_buffer and self._imu_buffer[0].received_monotonic < cutoff:
                self._imu_buffer.popleft()

            return VehicleState(
                timestamp=gps.timestamp, latitude=gps.latitude, longitude=gps.longitude,
                heading_deg=heading, pitch_deg=pitch, roll_deg=roll,
                speed_mps=gps.speed_mps, altitude_m=gps.altitude_m,
                gps_accuracy_m=None, gps_fix_quality=quality, gps_valid=True,
                imu_valid=imu is not None, gps_timestamp=gps.timestamp,
                imu_timestamp=imu.timestamp if imu is not None else None,
            )

    def run(self, stop_event: threading.Event):
        next_tick = time.monotonic()
        while not stop_event.is_set():
            now = time.monotonic()
            if now < next_tick:
                stop_event.wait(next_tick - now)
                continue
            next_tick = max(next_tick + self.interval_s, now + self.interval_s)
            state = self._next_state(now)
            if state is not None:
                try:
                    self.on_state(state)
                except Exception:
                    logger.exception('Fehler beim Verarbeiten des Fahrzeugzustands.')

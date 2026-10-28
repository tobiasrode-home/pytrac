"""Synchronisiert GPS- und IMU-Messungen zu einem Fahrzeugzustand."""
from collections import deque
from collections.abc import Callable
import logging
import threading
import time
from pytrac_core.sensors.models import GpsMeasurement, ImuMeasurement, VehicleState
logger = logging.getLogger(__name__)
VehicleStateCallback = Callable[[VehicleState], None]

class SensorSynchronizer:
    def __init__(self,on_state:VehicleStateCallback,output_rate_hz:float=5.0,
                 max_time_difference_s:float=0.15,max_measurement_age_s:float=0.5):
        if output_rate_hz<=0:raise ValueError('output_rate_hz muss größer als 0 sein.')
        self.on_state=on_state
        self.interval_s=1.0/output_rate_hz
        self.max_time_difference_s=max_time_difference_s
        self.max_measurement_age_s=max_measurement_age_s
        self._lock=threading.Lock()
        self._gps_buffer:deque[GpsMeasurement]=deque(maxlen=20)
        self._imu_buffer:deque[ImuMeasurement]=deque(maxlen=100)
        self._last_emitted_gps_time:float|None=None
    def add_gps(self,measurement:GpsMeasurement):
        if not measurement.valid:return
        with self._lock:self._gps_buffer.append(measurement)
    def add_imu(self,measurement:ImuMeasurement):
        with self._lock:self._imu_buffer.append(measurement)
    def _create_state(self,gps:GpsMeasurement,imu:ImuMeasurement)->VehicleState:
        return VehicleState(timestamp=gps.timestamp,latitude=gps.latitude,longitude=gps.longitude,
            heading_deg=imu.yaw_deg%360.0,pitch_deg=imu.pitch_deg,roll_deg=imu.roll_deg,
            speed_mps=gps.speed_mps,altitude_m=gps.altitude_m,gps_accuracy_m=None,
            gps_fix_quality=gps.gps_fix_quality if gps.gps_fix_quality is not None else gps.fix_quality,
            gps_valid=gps.valid,imu_valid=True,gps_timestamp=gps.timestamp,imu_timestamp=imu.timestamp)
    def run(self,stop_event:threading.Event):
        next_tick=time.monotonic()
        while not stop_event.is_set():
            now=time.monotonic()
            if now<next_tick:
                stop_event.wait(next_tick-now);continue
            next_tick+=self.interval_s
            if next_tick<now:next_tick=now+self.interval_s
            state=self._next_state(now)
            if state is not None:
                try:self.on_state(state)
                except Exception:logger.exception('Fehler beim Verarbeiten des Fahrzeugzustands.')
    def _next_state(self,now:float)->VehicleState|None:
        with self._lock:
            if not self._gps_buffer or not self._imu_buffer:return None
            gps=self._gps_buffer[-1];gps_received=gps.received_monotonic
            if self._last_emitted_gps_time==gps_received:return None
            gps_age=now-gps_received
            if not 0<=gps_age<=self.max_measurement_age_s:return None
            imu=min(self._imu_buffer,key=lambda item:abs(item.received_monotonic-gps_received))
            time_difference=abs(imu.received_monotonic-gps_received)
            imu_age=now-imu.received_monotonic
            if time_difference>self.max_time_difference_s:return None
            if not 0<=imu_age<=self.max_measurement_age_s:return None
            self._last_emitted_gps_time=gps_received
            while self._gps_buffer and self._gps_buffer[0].received_monotonic<gps_received:
                self._gps_buffer.popleft()
            oldest_needed=gps_received-self.max_time_difference_s
            while self._imu_buffer and self._imu_buffer[0].received_monotonic<oldest_needed:
                self._imu_buffer.popleft()
            return self._create_state(gps,imu)

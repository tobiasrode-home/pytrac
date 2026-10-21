
"""BNO085-Leser für PyTrac mit Diagnoseausgaben."""

from collections.abc import Callable
import logging
import math
import threading
import time
from datetime import datetime, timezone

import serial
from adafruit_bno08x_rvc import BNO08x_RVC

from pytrac_core.sensors.models import ImuMeasurement


logger = logging.getLogger(__name__)

MeasurementCallback = Callable[[ImuMeasurement], None]


class Bno085Reader:
    """Liest den BNO085 über USB-UART im RVC-Modus."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        reconnect_delay_s: float = 2.0,
        on_measurement: MeasurementCallback | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.reconnect_delay_s = reconnect_delay_s
        self.on_measurement = on_measurement

        self._uart: serial.Serial | None = None
        self._imu: BNO08x_RVC | None = None

    def _open(self) -> None:
        logger.info(
            "[IMU] Öffne Port %s mit %s Baud.",
            self.port,
            self.baudrate,
        )

        self._uart = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
        )

        self._imu = BNO08x_RVC(self._uart)

        logger.info("[IMU] Serielle Verbindung geöffnet.")

    def read_measurement(self) -> ImuMeasurement:
        """Liest einen Messdatensatz vom BNO085."""

        if self._uart is None or not self._uart.is_open:
            raise RuntimeError("IMU-UART ist nicht geöffnet.")

        if self._imu is None:
            raise RuntimeError("BNO085 ist nicht initialisiert.")

        yaw, pitch, roll, accel_x, accel_y, accel_z = (
            self._imu.heading
        )

        values = (
            yaw,
            pitch,
            roll,
            accel_x,
            accel_y,
            accel_z,
        )

        if not all(math.isfinite(value) for value in values):
            raise ValueError("BNO085 lieferte ungültige Messwerte.")

        return ImuMeasurement(
            timestamp=datetime.now(timezone.utc),
            received_monotonic=time.monotonic(),
            yaw_deg=yaw,
            pitch_deg=pitch,
            roll_deg=roll,
            accel_x_mps2=accel_x,
            accel_y_mps2=accel_y,
            accel_z_mps2=accel_z,
        )

    def _close(self) -> None:
        uart = self._uart
        self._uart = None
        self._imu = None

        if uart is not None and uart.is_open:
            uart.close()

        logger.info("[IMU] Serielle Verbindung geschlossen.")

    def run(self, stop_event: threading.Event) -> None:
        """Liest kontinuierlich IMU-Daten bis zum Stoppsignal."""

        while not stop_event.is_set():
            try:
                self._open()

                while not stop_event.is_set():
                    measurement = self.read_measurement()

                    #logger.info(
                    #    "[IMU] yaw=%.1f pitch=%.1f roll=%.1f "
                    #    "accel=(%.2f, %.2f, %.2f) m/s²",
                    #    measurement.yaw_deg,
                    #    measurement.pitch_deg,
                    #    measurement.roll_deg,
                    #    measurement.accel_x_mps2,
                    #    measurement.accel_y_mps2,
                    #    measurement.accel_z_mps2,
                    #)

                    if self.on_measurement is not None:
                        self.on_measurement(measurement)

            except (
                serial.SerialException,
                OSError,
                ValueError,
                RuntimeError,
            ):
                logger.exception("[IMU] Fehler beim Lesen des BNO085.")

            finally:
                self._close()

            if not stop_event.is_set():
                logger.warning(
                    "[IMU] Neuer Verbindungsversuch in %.1f Sekunden.",
                    self.reconnect_delay_s,
                )
                stop_event.wait(self.reconnect_delay_s)

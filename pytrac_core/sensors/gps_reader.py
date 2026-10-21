"""GPS-Leser für den u-blox NEO-6M.

- UBX-Konfiguration mit ACK/NAK-Prüfung
- Navigationsrate 5 Hz
- GGA/RMC als Messdatenquelle
- Statusmeldung alle fünf Sekunden
- Keine Datenbankspeicherung
- Automatische Wiederverbindung bei Verbindungsfehlern
"""

from collections.abc import Callable
import logging
import threading
import time
from datetime import datetime, timezone

import pynmea2
import serial

from pytrac_core.sensors.models import GpsMeasurement


logger = logging.getLogger(__name__)

GpsCallback = Callable[[GpsMeasurement], None]

UBX_SYNC = b"\xB5\x62"

# UBX-CFG-RATE: 200 ms = 5 Hz
UBX_RATE_PAYLOAD = bytes((0xC8, 0x00, 0x01, 0x00, 0x00, 0x00))

# UBX-CFG-MSG: Nachrichtentyp, Rate auf dem aktuellen UART-Port
NMEA_MESSAGES = [
    (0xF0, 0x00, 1),  # GGA: jede Navigationslösung
    (0xF0, 0x04, 1),  # RMC: jede Navigationslösung
    (0xF0, 0x01, 0),  # GLL aus
    (0xF0, 0x02, 0),  # GSA aus
    (0xF0, 0x03, 0),  # GSV aus
    (0xF0, 0x05, 0),  # VTG aus
    (0xF0, 0x41, 0),  # TXT aus
]


def make_ubx_packet(
    msg_class: int,
    msg_id: int,
    payload: bytes,
) -> bytes:
    """Erzeugt ein UBX-Paket inklusive Fletcher-Prüfsumme."""
    header = bytes((
        0xB5,
        0x62,
        msg_class,
        msg_id,
        len(payload) & 0xFF,
        (len(payload) >> 8) & 0xFF,
    ))

    checksum_a = 0
    checksum_b = 0

    for byte in header[2:] + payload:
        checksum_a = (checksum_a + byte) & 0xFF
        checksum_b = (checksum_b + checksum_a) & 0xFF

    return header + payload + bytes((checksum_a, checksum_b))


def wait_for_ubx_ack(
    uart: serial.Serial,
    expected_class: int,
    expected_id: int,
    timeout_s: float = 1.0,
) -> bool | None:
    """Wartet auf ACK-ACK oder ACK-NAK für einen UBX-Befehl.

    True  = ACK
    False = NAK
    None  = keine passende Antwort innerhalb des Zeitlimits
    """
    deadline = time.monotonic() + timeout_s
    buffer = bytearray()

    while time.monotonic() < deadline:
        waiting = uart.in_waiting

        if waiting:
            buffer.extend(uart.read(min(waiting, 256)))
        else:
            time.sleep(0.005)
            continue

        while True:
            start = buffer.find(UBX_SYNC)

            if start < 0:
                if buffer and buffer[-1] == UBX_SYNC[0]:
                    buffer[:] = UBX_SYNC[:1]
                else:
                    buffer.clear()
                break

            if start > 0:
                del buffer[:start]

            if len(buffer) < 6:
                break

            payload_length = buffer[4] | (buffer[5] << 8)

            if payload_length > 1024:
                del buffer[0]
                continue

            packet_length = 6 + payload_length + 2

            if len(buffer) < packet_length:
                break

            packet = bytes(buffer[:packet_length])
            del buffer[:packet_length]

            checksum_a = 0
            checksum_b = 0

            for byte in packet[2:-2]:
                checksum_a = (checksum_a + byte) & 0xFF
                checksum_b = (checksum_b + checksum_a) & 0xFF

            if packet[-2:] != bytes((checksum_a, checksum_b)):
                continue

            msg_class = packet[2]
            msg_id = packet[3]
            payload = packet[6:-2]

            if (
                msg_class == 0x05
                and msg_id in (0x00, 0x01)
                and len(payload) >= 2
                and payload[0] == expected_class
                and payload[1] == expected_id
            ):
                return msg_id == 0x01

    return None


def send_ubx_config(
    uart: serial.Serial,
    msg_class: int,
    msg_id: int,
    payload: bytes,
) -> bool:
    """Sendet einen UBX-Befehl und prüft dessen Bestätigung."""
    packet = make_ubx_packet(msg_class, msg_id, payload)

    uart.write(packet)
    uart.flush()

    result = wait_for_ubx_ack(uart, msg_class, msg_id)
    command = f"UBX {msg_class:02X}/{msg_id:02X}"

    if result is True:
        #logger.info("[GPS CONFIG] %s: ACK", command)
        return True

    if result is False:
        logger.error("[GPS CONFIG] %s: NAK", command)
    else:
        logger.warning(
            "[GPS CONFIG] %s: keine ACK-Antwort",
            command,
        )

    return False


def configure_gps(uart: serial.Serial) -> bool:
    """Konfiguriert den NEO-6M auf 5 Hz und GGA/RMC."""
    #logger.info(
    #    "[GPS CONFIG] Konfiguriere Navigationsrate auf 5 Hz."
    #)

    rate_ok = send_ubx_config(
        uart,
        0x06,
        0x08,
        UBX_RATE_PAYLOAD,
    )

    message_results = []

    for msg_class, msg_id, rate in NMEA_MESSAGES:
        ok = send_ubx_config(
            uart,
            0x06,
            0x01,
            bytes((msg_class, msg_id, rate)),
        )
        message_results.append(ok)

    configured = rate_ok and all(message_results)

    if configured:
        #logger.info(
        #    "[GPS CONFIG] Konfiguration vollständig bestätigt."
        #)
    else:
        logger.warning(
            "[GPS CONFIG] Konfiguration nicht vollständig bestätigt."
        )

    return configured


class GpsReader:
    """Liest GPS-Messungen und übergibt sie an einen Callback."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        on_measurement: GpsCallback | None = None,
        reconnect_delay_s: float = 2.0,
        configure_receiver: bool = True,
        status_interval_s: float = 5.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_measurement = on_measurement
        self.reconnect_delay_s = reconnect_delay_s
        self.configure_receiver = configure_receiver
        self.status_interval_s = status_interval_s

        self._last_gga: dict | None = None

        self._gga_count = 0
        self._rmc_count = 0
        self._last_status_time = 0.0
        self._last_gga_time: float | None = None
        self._gga_times: list[float] = []

        self._last_fix = False
        self._last_satellites: int | None = None
        self._last_hdop: float | None = None

    def _reset_stats(self) -> None:
        self._last_gga = None
        self._gga_count = 0
        self._rmc_count = 0
        self._last_status_time = time.monotonic()
        self._last_gga_time = None
        self._gga_times.clear()
        self._last_fix = False
        self._last_satellites = None
        self._last_hdop = None

    def _log_status(self, now: float) -> None:
        """Gibt höchstens alle fünf Sekunden einen Status aus."""
        if now - self._last_status_time < self.status_interval_s:
            return

        rate = None

        if len(self._gga_times) >= 2:
            elapsed = self._gga_times[-1] - self._gga_times[0]

            if elapsed > 0:
                rate = (len(self._gga_times) - 1) / elapsed

        rate_text = (
            f"{rate:.2f} Hz"
            if rate is not None
            else "messe ..."
        )

        #logger.info(
        #    "[GPS STATUS] %s | GGA-Rate=%s | GGA=%d | RMC=%d "
        #    "| Satelliten=%s | HDOP=%s",
        #    "FIX" if self._last_fix else "NO_FIX",
        #    rate_text,
        #    self._gga_count,
        #    self._rmc_count,
        #    self._last_satellites,
        #    self._last_hdop,
        #)

        self._last_status_time = now

        # Begrenzte Messhistorie für die Ratenberechnung.
        self._gga_times = self._gga_times[-50:]

    def _handle_sentence(
        self,
        line: str,
    ) -> GpsMeasurement | None:
        """Verarbeitet eine NMEA-Zeile und erstellt ggf. eine Messung."""
        try:
            message = pynmea2.parse(line, check=True)
        except (pynmea2.ParseError, ValueError):
            logger.debug(
                "[GPS] Ungültige NMEA-Nachricht verworfen."
            )
            return None

        received_at = time.monotonic()

        if message.sentence_type == "GGA":
            self._gga_count += 1
            self._last_gga_time = received_at
            self._gga_times.append(received_at)

            try:
                quality = int(message.gps_qual or 0)

                satellites = (
                    int(message.num_sats)
                    if message.num_sats
                    else None
                )

                hdop = (
                    float(message.horizontal_dil)
                    if message.horizontal_dil
                    else None
                )

                self._last_satellites = satellites
                self._last_hdop = hdop
                self._last_fix = quality > 0

                if quality <= 0:
                    self._last_gga = None
                    #self._log_status(received_at)
                    return None

                self._last_gga = {
                    "altitude_m": (
                        float(message.altitude)
                        if message.altitude
                        else None
                    ),
                    "fix_quality": quality,
                    "satellites": satellites,
                    "hdop": hdop,
                    "received_monotonic": received_at,
                }

            except (TypeError, ValueError):
                self._last_gga = None
                logger.warning(
                    "[GPS] GGA konnte nicht ausgewertet werden."
                )

            self._log_status(received_at)
            return None

        if message.sentence_type != "RMC":
            return None

        self._rmc_count += 1

        if message.status != "A":
            self._log_status(received_at)
            return None

        try:
            if not message.datestamp or not message.timestamp:
                return None

            timestamp = datetime.combine(
                message.datestamp,
                message.timestamp,
                tzinfo=timezone.utc,
            )

            latitude = float(message.latitude)
            longitude = float(message.longitude)

            speed_mps = (
                float(message.spd_over_grnd) * 0.514444
                if message.spd_over_grnd
                else 0.0
            )

            course_deg = (
                float(message.true_course)
                if message.true_course
                else None
            )

        except (TypeError, ValueError):
            logger.debug(
                "[GPS] RMC konnte nicht ausgewertet werden."
            )
            return None

        gga = self._last_gga or {}

        gga_age = (
            received_at - gga["received_monotonic"]
            if gga
            else float("inf")
        )

        use_gga = 0 <= gga_age <= 0.5

        measurement = GpsMeasurement(
            timestamp=timestamp,
            received_monotonic=received_at,
            latitude=latitude,
            longitude=longitude,
            altitude_m=(
                gga.get("altitude_m") if use_gga else None
            ),
            speed_mps=speed_mps,
            course_deg=course_deg,
            fix_quality=(
                gga.get("fix_quality", 1) if use_gga else 1
            ),
            satellites=(
                gga.get("satellites") if use_gga else None
            ),
            hdop=gga.get("hdop") if use_gga else None,
        )

        if not measurement.valid:
            logger.debug(
                "[GPS] Messung als ungültig verworfen."
            )
            return None

        logger.debug(
            "[GPS FIX] lat=%.7f lon=%.7f speed=%.2f m/s",
            measurement.latitude,
            measurement.longitude,
            measurement.speed_mps or 0.0,
        )

        return measurement

    def run(self, stop_event: threading.Event) -> None:
        """Liest kontinuierlich GPS-Daten bis zum Stoppsignal."""
        while not stop_event.is_set():
            try:
                #logger.info(
                #    "[GPS] Öffne %s mit %d Baud.",
                #    self.port,
                #    self.baudrate,
                #)

                with serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.2,
                    write_timeout=1.0,
                ) as uart:
                    #logger.info("[GPS] UART geöffnet.")

                    time.sleep(0.2)

                    if self.configure_receiver:
                        configure_gps(uart)

                    # Daten aus der Konfigurationsphase verwerfen.
                    uart.reset_input_buffer()

                    self._reset_stats()

                    while not stop_event.is_set():
                        raw_line = uart.readline()

                        if not raw_line:
                            self._log_status(time.monotonic())
                            continue

                        try:
                            line = raw_line.decode("ascii").strip()
                        except UnicodeDecodeError:
                            logger.debug(
                                "[GPS] Binärdaten statt NMEA."
                            )
                            continue

                        if not line.startswith("$"):
                            continue

                        logger.debug("[GPS RAW] %s", line)

                        measurement = self._handle_sentence(line)

                        if (
                            measurement is not None
                            and self.on_measurement is not None
                        ):
                            try:
                                self.on_measurement(measurement)
                            except Exception:
                                logger.exception(
                                    "[GPS] Fehler im Messdaten-Callback."
                                )

            except (serial.SerialException, OSError):
                logger.exception("[GPS] Verbindungsfehler.")

            finally:
                self._last_gga = None

            if not stop_event.is_set():
                logger.warning(
                    "[GPS] Neuer Verbindungsversuch in %.1f Sekunden.",
                    self.reconnect_delay_s,
                )
                stop_event.wait(self.reconnect_delay_s)

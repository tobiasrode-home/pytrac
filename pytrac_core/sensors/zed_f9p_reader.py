"""Standalone ZED-F9P NMEA reader with optional NTRIP RTCM forwarding.

No dependency on gps_reader.py. Keeps the GpsMeasurement callback contract.
"""
import base64
from datetime import datetime, timezone, timedelta
import logging
import struct
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

import pynmea2
import serial

from pytrac_core.sensors.models import GpsMeasurement

log = logging.getLogger(__name__)


class UbxStreamDecoder:
    """Mixed NMEA/UBX stream decoder; validates UBX checksum."""
    def __init__(self):
        self.buffer = bytearray()
        self.bad_checksums = 0

    def feed(self, data):
        self.buffer.extend(data)
        while self.buffer:
            if self.buffer.startswith(b'\xb5\x62'):
                if len(self.buffer) < 6:
                    break
                length = self.buffer[4] | (self.buffer[5] << 8)
                if length > 4096:
                    del self.buffer[0]
                    continue
                end = 8 + length
                if len(self.buffer) < end:
                    break
                packet = bytes(self.buffer[:end])
                del self.buffer[:end]
                a = b = 0
                for v in packet[2:-2]:
                    a = (a + v) & 255
                    b = (b + a) & 255
                if packet[-2:] != bytes((a, b)):
                    self.bad_checksums += 1
                    continue
                yield ('ubx', packet[2], packet[3], packet[6:-2])
            elif self.buffer[0] == 36:  # NMEA '$'
                newline = self.buffer.find(b'\n')
                if newline < 0:
                    if len(self.buffer) > 1024:
                        del self.buffer[0]
                    break
                line = bytes(self.buffer[:newline + 1])
                del self.buffer[:newline + 1]
                try:
                    yield ('nmea', line.decode('ascii').strip())
                except UnicodeDecodeError:
                    continue
            else:
                next_nmea = self.buffer.find(b'$', 1)
                next_ubx = self.buffer.find(b'\xb5\x62', 1)
                offsets = [x for x in (next_nmea, next_ubx) if x >= 0]
                if offsets:
                    del self.buffer[:min(offsets)]
                else:
                    # Keep possible first byte of UBX sync for next read.
                    keep = 1 if self.buffer[-1] == 0xb5 else 0
                    del self.buffer[:len(self.buffer) - keep]
                    break


def ubx_packet(cls, msg_id, payload=b''):
    body = bytes((cls, msg_id)) + struct.pack('<H', len(payload)) + payload
    a = b = 0
    for v in body:
        a = (a + v) & 255
        b = (b + a) & 255
    return b'\xb5\x62' + body + bytes((a, b))


class ZedF9pReader:
    def __init__(self, port, baudrate=9600, on_measurement=None,
                 reconnect_delay_s=2.0, configure_receiver=False,
                 status_interval_s=5.0, *, ntrip_url='', ntrip_username='',
                 ntrip_password='', ntrip_send_gga=True,
                 gps_rate_hz=10, **kwargs):
        # Keep old constructor arguments compatible with existing startup code.
        self.port = port
        self.baudrate = baudrate
        self.on_measurement = on_measurement
        self.reconnect_delay_s = reconnect_delay_s
        self.configure_receiver = False  # Do not send NEO-6M configuration to F9P.
        self.status_interval_s = status_interval_s
        self.ntrip_url = (ntrip_url or '').strip()
        self.ntrip_username = ntrip_username or ''
        self.ntrip_password = ntrip_password or ''
        self.ntrip_send_gga = ntrip_send_gga
        self.gps_rate_hz = int(gps_rate_hz)
        if self.gps_rate_hz not in (1, 5, 10):
            raise ValueError("gps_rate_hz muss 1, 5 oder 10 sein")
        self._gga_line = None
        self._gga_lock = threading.Lock()
        self._serial_write_lock = threading.Lock()
        self._last_gga = None
        self._rtk_quality = 0
        self._last_pvt_monotonic = None
        self._pvt_last_itow = None

    def _configure_gnss_rate(self, uart):
        """Set measurement interval, keep one navigation solution per measurement.

        CFG-RATE applies to the receiver (RAM until restart). On USB the
        serial baudrate parameter does not limit the transport bitrate.
        """
        period_ms = 1000 // self.gps_rate_hz
        # UBX-CFG-RATE: measRate (ms), navRate (cycles), timeRef (GPS=1).
        payload = struct.pack('<HHH', period_ms, 1, 1)
        with self._serial_write_lock:
            self._write_config_packet(uart, ubx_packet(0x06, 0x08, payload))
            # GGA remains for NTRIP. RMC is disabled on USB to avoid duplicate
            # position sources; NAV-PVT becomes the sole measurement source.
            # CFG-MSG legacy per-port layout: I2C, UART1, UART2, USB, SPI, reserved.
            # Does not persist across a power cycle; sent on each connection.
            for nmea_id, rate in ((0x00, 1), (0x04, 0)):  # GGA, RMC
                msg_rates = bytes((0xF0, nmea_id, 0, 0, 0, rate, 0, 0))
                self._write_config_packet(uart, ubx_packet(0x06, 0x01, msg_rates))

    @staticmethod
    def _write_config_packet(uart, packet):
        offset = 0
        while offset < len(packet):
            n = uart.write(packet[offset:])
            if n is None or n <= 0:
                raise serial.SerialTimeoutException('UBX-Konfiguration nicht vollstaendig geschrieben')
            offset += n

    def _configure_nav_pvt(self, uart):
        """Enable only UBX-NAV-PVT on USB; disable old diagnostic streams."""
        for cls, msg_id, rate in ((0x01, 0x07, 1), (0x02, 0x32, 0), (0x01, 0x35, 0)):
            packet = ubx_packet(0x06, 0x01, bytes((cls, msg_id, 0, 0, 0, rate, 0, 0)))
            with self._serial_write_lock:
                self._write_config_packet(uart, packet)

    def _measurement_from_pvt(self, payload):
        """Convert one verified UBX-NAV-PVT payload into one GPS solution.

        The UBX stream decoder already validated the packet checksum. NAV-PVT
        carries position, velocity and fix flags from the same navigation epoch.
        """
        if len(payload) < 92:
            return None
        itow = struct.unpack_from('<I', payload, 0)[0]
        if itow == self._pvt_last_itow:
            return None
        self._pvt_last_itow = itow
        valid = payload[11]
        fix_type, flags, num_sv = payload[20], payload[21], payload[23]
        carrier = (flags >> 6) & 3
        if not (valid & 3) == 3 or not (flags & 1) or fix_type not in (2, 3, 4):
            return None
        try:
            year = struct.unpack_from('<H', payload, 4)[0]
            month, day, hour, minute, second = payload[6:11]
            stamp = datetime(year, month, day, hour, minute, min(second, 59),
                             tzinfo=timezone.utc)
            if second == 60:
                stamp += timedelta(seconds=1)
            nanosecond = struct.unpack_from('<i', payload, 16)[0]
            stamp += timedelta(microseconds=nanosecond / 1000)
            lon, lat = struct.unpack_from('<ii', payload, 24)
            h_msl = struct.unpack_from('<i', payload, 36)[0]
            speed = struct.unpack_from('<i', payload, 60)[0]
            heading = struct.unpack_from('<i', payload, 64)[0]
            pdop = struct.unpack_from('<H', payload, 76)[0]
            lat, lon = lat * 1e-7, lon * 1e-7
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError('PVT coordinates out of range')
        except (ValueError, OverflowError, struct.error):
            return None
        # Carrier phase flags are authoritative for RTK Float/Fixed.
        # A valid 3D fix without carrier solution is GNSS or DGNSS.
        quality = 4 if carrier == 2 else 5 if carrier == 1 else (2 if flags & 2 else 1)
        if quality != self._rtk_quality:
            self._rtk_quality = quality
            log.warning('[ZED-F9P] NAV-PVT Fixqualitaet=%d (carrier=%s)', quality,
                        {0: 'NONE', 1: 'FLOAT', 2: 'FIXED'}.get(carrier, 'UNKNOWN'))
        now = time.monotonic()
        measurement = GpsMeasurement(
            timestamp=stamp, received_monotonic=now,
            latitude=lat, longitude=lon, altitude_m=h_msl / 1000.0,
            speed_mps=speed / 1000.0, course_deg=(heading * 1e-5) % 360,
            fix_quality=quality, gps_fix_quality=quality,
            satellites=num_sv, hdop=None)
        if measurement.valid:
            self._last_pvt_monotonic = now
            return measurement
        return None

    def _reset_stats(self):
        self._last_gga = None
        self._rtk_quality = 0
        self._last_pvt_monotonic = None
        self._pvt_last_itow = None
        with self._gga_lock:
            self._gga_line = None

    def _handle_sentence(self, line):
        try:
            msg = pynmea2.parse(line, check=True)
        except (pynmea2.ParseError, ValueError, TypeError):
            return None
        now = time.monotonic()
        if msg.sentence_type == 'GGA':
            try:
                quality = int(msg.gps_qual or 0)
                sats = int(msg.num_sats) if msg.num_sats else None
                hdop = float(msg.horizontal_dil) if msg.horizontal_dil else None
                altitude = float(msg.altitude) if msg.altitude else None
            except (ValueError, TypeError):
                return None
            if self._last_pvt_monotonic is None and quality != self._rtk_quality:
                self._rtk_quality = quality
                label = {0: 'NO FIX', 1: 'GNSS', 2: 'DGNSS', 4: 'RTK FIX', 5: 'RTK FLOAT'}.get(quality, str(quality))
                log.warning('[ZED-F9P] Positionierungsstatus: %s', label)
            self._last_gga = dict(quality=quality, satellites=sats, hdop=hdop,
                                  altitude=altitude, received=now)
            with self._gga_lock:
                self._gga_line = line if quality > 0 else None
            return None
        # RMC is intentionally ignored: NAV-PVT is the only GPS source.
        return None

    def _write_rtcm(self, uart, data):
        """Write every RTCM byte or fail; serial.write may return a short count."""
        written = 0
        with self._serial_write_lock:
            while written < len(data):
                count = uart.write(data[written:])
                if count is None or count <= 0:
                    raise serial.SerialTimeoutException(
                        'RTCM-Schreibvorgang ohne Fortschritt')
                written += count
        return written

    def _ntrip_worker(self, uart, stop_event, disconnected):
        if not self.ntrip_url:
            log.warning('[ZED-F9P] NTRIP nicht konfiguriert')
            return
        try:
            parsed = urlsplit(self.ntrip_url)
            if parsed.scheme not in ('ntrip', 'http', 'https') or not parsed.hostname or not parsed.path.strip('/'):
                raise ValueError('Ungültige NTRIP_URL')
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'https' else 2101)
            mount = parsed.path.lstrip('/')
        except (ValueError, TypeError):
            log.error('[ZED-F9P] Ungültige NTRIP-Konfiguration')
            return
        while not stop_event.is_set() and not disconnected.is_set():
            try:
                sock = socket.create_connection((host, port), timeout=10)
                if parsed.scheme == 'https':
                    try:
                        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                    except Exception:
                        sock.close()
                        raise
                with sock:
                    sock.settimeout(2)
                    credentials = base64.b64encode(
                        f'{self.ntrip_username}:{self.ntrip_password}'.encode()
                    ).decode()
                    request = (f'GET /{mount} HTTP/1.0\r\nHost: {host}\r\n'
                               f'User-Agent: NTRIP PyTrac/1.0\r\n'
                               f'Authorization: Basic {credentials}\r\n'
                               'Accept: */*\r\nConnection: close\r\n\r\n').encode('ascii')
                    sock.sendall(request)
                    response = bytearray()
                    while b'\r\n\r\n' not in response and b'\n\n' not in response:
                        chunk = sock.recv(4096)
                        if not chunk:
                            raise OSError('NTRIP hat Verbindung geschlossen')
                        response.extend(chunk)
                        if len(response) > 16384:
                            raise OSError('NTRIP-Antwort zu groß')
                    sep = b'\r\n\r\n' if b'\r\n\r\n' in response else b'\n\n'
                    header, pending = bytes(response).split(sep, 1)
                    first = header.splitlines()[0]
                    if not (first.startswith(b'ICY 200') or b' 200 ' in first):
                        raise OSError('NTRIP abgelehnt: ' + first.decode('ascii', 'replace'))
                    log.warning('[ZED-F9P] NTRIP verbunden: %s/%s', host, mount)
                    received_bytes = 0
                    written_bytes = 0
                    last_report = time.monotonic()
                    last_rtcm = None
                    if pending:
                        received_bytes += len(pending)
                        written_bytes += self._write_rtcm(uart, pending)
                        last_rtcm = time.monotonic()
                    next_gga = 0.0
                    while not stop_event.is_set() and not disconnected.is_set():
                        now = time.monotonic()
                        if self.ntrip_send_gga and now >= next_gga:
                            with self._gga_lock:
                                gga = self._gga_line
                            if gga:
                                sock.sendall((gga + '\r\n').encode('ascii'))
                                log.info('[ZED-F9P] NTRIP GGA an Server gesendet')
                            else:
                                log.info('[ZED-F9P] NTRIP wartet auf GGA vom Empfänger')
                            next_gga = now + 5
                        try:
                            rtcm = sock.recv(4096)
                        except socket.timeout:
                            rtcm = None
                        if rtcm == b'':
                            raise OSError('NTRIP-Stream beendet')
                        if rtcm:
                            received_bytes += len(rtcm)
                            written_bytes += self._write_rtcm(uart, rtcm)
                            last_rtcm = time.monotonic()
                        now = time.monotonic()
                        if now - last_report >= 10:
                            age = (f'{now - last_rtcm:.1f} s' if last_rtcm is not None
                                   else 'noch keine Daten')
                            log.info('[ZED-F9P] NTRIP empfangen=%d Bytes, '
                                     'an USB uebergeben=%d Bytes, letzte RTCM-Daten=%s, '
                                     'GGA-Fixqualitaet=%d',
                                     received_bytes, written_bytes, age, self._rtk_quality)
                            last_report = now
            except (OSError, ValueError, serial.SerialException) as exc:
                if not stop_event.is_set() and not disconnected.is_set():
                    log.warning('[ZED-F9P] NTRIP/RTCM: %s; neuer Versuch in 5 s', exc)
                    disconnected.wait(5)

    def run(self, stop_event: threading.Event):
        if not self.port:
            log.error('[ZED-F9P] GPS_PORT fehlt')
            return
        while not stop_event.is_set():
            disconnected = threading.Event()
            try:
                with serial.Serial(self.port, self.baudrate, timeout=0.05, write_timeout=2) as uart:
                    log.warning('[ZED-F9P] USB-GNSS verbunden: %s', self.port)
                    self._reset_stats()
                    decoder = UbxStreamDecoder()
                    self._configure_gnss_rate(uart)
                    self._configure_nav_pvt(uart)
                    next_report = time.monotonic() + 10
                    worker = threading.Thread(target=self._ntrip_worker,
                                              args=(uart, stop_event, disconnected), daemon=True)
                    worker.start()
                    try:
                        while not stop_event.is_set():
                            raw = uart.read(512)
                            if raw:
                                for item in decoder.feed(raw):
                                    if item[0] == 'ubx':
                                        cls, msg_id, payload = item[1:]
                                        if (cls, msg_id) == (0x01, 0x07):
                                            measurement = self._measurement_from_pvt(payload)
                                            if measurement is not None and self.on_measurement:
                                                try:
                                                    self.on_measurement(measurement)
                                                except Exception:
                                                    log.exception('[ZED-F9P] Fehler im GPS-Callback')
                                        continue
                                    measurement = self._handle_sentence(item[1])
                                    if measurement is not None and self.on_measurement:
                                        try:
                                            self.on_measurement(measurement)
                                        except Exception:
                                            log.exception('[ZED-F9P] Fehler im Messdaten-Callback')
                    finally:
                        disconnected.set()
                        worker.join(timeout=12)
            except (serial.SerialException, OSError) as exc:
                log.warning('[ZED-F9P] USB-Verbindung: %s', exc)
            if not stop_event.is_set():
                stop_event.wait(self.reconnect_delay_s)

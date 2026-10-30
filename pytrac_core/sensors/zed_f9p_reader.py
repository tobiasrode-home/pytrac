"""Standalone ZED-F9P NMEA reader with optional NTRIP RTCM forwarding.

No dependency on gps_reader.py. Keeps the GpsMeasurement callback contract.
"""
import base64
from datetime import datetime, timezone
import logging
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

import pynmea2
import serial

from pytrac_core.sensors.models import GpsMeasurement

log = logging.getLogger(__name__)


class ZedF9pReader:
    def __init__(self, port, baudrate=9600, on_measurement=None,
                 reconnect_delay_s=2.0, configure_receiver=False,
                 status_interval_s=5.0, *, ntrip_url='', ntrip_username='',
                 ntrip_password='', ntrip_send_gga=True, **kwargs):
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
        self._gga_line = None
        self._gga_lock = threading.Lock()
        self._serial_write_lock = threading.Lock()
        self._last_gga = None
        self._rtk_quality = 0

    def _reset_stats(self):
        self._last_gga = None
        self._rtk_quality = 0
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
            if quality != self._rtk_quality:
                self._rtk_quality = quality
                label = {0: 'NO FIX', 1: 'GNSS', 2: 'DGNSS', 4: 'RTK FIX', 5: 'RTK FLOAT'}.get(quality, str(quality))
                log.warning('[ZED-F9P] Positionierungsstatus: %s', label)
            self._last_gga = dict(quality=quality, satellites=sats, hdop=hdop,
                                  altitude=altitude, received=now)
            with self._gga_lock:
                self._gga_line = line if quality > 0 else None
            return None
        if msg.sentence_type != 'RMC' or msg.status != 'A':
            return None
        try:
            if not msg.datestamp or not msg.timestamp:
                return None
            stamp = datetime.combine(msg.datestamp, msg.timestamp, tzinfo=timezone.utc)
            lat, lon = float(msg.latitude), float(msg.longitude)
            speed = float(msg.spd_over_grnd) * 0.514444 if msg.spd_over_grnd else 0.0
            course = float(msg.true_course) if msg.true_course else None
        except (TypeError, ValueError):
            return None
        # GGA and RMC may arrive in either order. Allow a recent GGA to supply
        # RTK quality even if it is more than 0.5 seconds before the RMC.
        gga = self._last_gga
        fresh = gga is not None and 0 <= now - gga['received'] <= 3.0
        quality = gga['quality'] if fresh else 1
        measurement = GpsMeasurement(
            timestamp=stamp, received_monotonic=now, latitude=lat, longitude=lon,
            altitude_m=gga['altitude'] if fresh else None,
            speed_mps=speed, course_deg=course, fix_quality=quality,
            satellites=gga['satellites'] if fresh else None,
            hdop=gga['hdop'] if fresh else None, gps_fix_quality=quality,
        )
        return measurement if measurement.valid else None

    def _ntrip_worker(self, uart, stop_event, disconnected):
        if not self.ntrip_url:
            return
        try:
            parsed = urlsplit(self.ntrip_url)
            if parsed.scheme not in ('ntrip', 'http', 'https') or not parsed.hostname or not parsed.path.strip('/'):
                raise ValueError('Ungültige NTRIP_URL')
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == 'https' else 2101)
            mount = parsed.path.lstrip('/')
        except (ValueError, TypeError):
            log.exception('[ZED-F9P] NTRIP-Konfiguration fehlgeschlagen')
            return
        while not stop_event.is_set() and not disconnected.is_set():
            try:
                sock = socket.create_connection((host, port), timeout=10)
                if parsed.scheme == 'https':
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                with sock:
                    sock.settimeout(2)
                    credentials = base64.b64encode(f'{self.ntrip_username}:{self.ntrip_password}'.encode()).decode()
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
                    total = 0
                    last_report = time.monotonic()
                    if pending:
                        with self._serial_write_lock:
                            uart.write(pending)
                        total += len(pending)
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
                            continue
                        if not rtcm:
                            raise OSError('NTRIP-Stream beendet')
                        with self._serial_write_lock:
                            uart.write(rtcm)
                        total += len(rtcm)
                        if time.monotonic() - last_report >= 10:
                            log.info('[ZED-F9P] NTRIP Daten empfangen: %d Bytes gesamt', total)
                            last_report = time.monotonic()
            except (OSError, ValueError, serial.SerialException) as exc:
                if not stop_event.is_set() and not disconnected.is_set():
                    log.warning('[ZED-F9P] NTRIP: %s; neuer Versuch in 5 s', exc)
                    disconnected.wait(5)

    def run(self, stop_event: threading.Event):
        if not self.port:
            log.error('[ZED-F9P] GPS_PORT fehlt')
            return
        while not stop_event.is_set():
            disconnected = threading.Event()
            try:
                with serial.Serial(self.port, self.baudrate, timeout=0.2, write_timeout=2) as uart:
                    log.warning('[ZED-F9P] USB-GNSS verbunden: %s', self.port)
                    self._reset_stats()
                    worker = threading.Thread(target=self._ntrip_worker,
                                              args=(uart, stop_event, disconnected), daemon=True)
                    worker.start()
                    try:
                        while not stop_event.is_set():
                            raw = uart.readline()
                            if not raw:
                                continue
                            try:
                                line = raw.decode('ascii').strip()
                            except UnicodeDecodeError:
                                continue
                            if not line.startswith('$'):
                                continue
                            measurement = self._handle_sentence(line)
                            if measurement is not None and self.on_measurement:
                                try:
                                    self.on_measurement(measurement)
                                except Exception:
                                    log.exception('[ZED-F9P] Fehler im Messdaten-Callback')
                    finally:
                        disconnected.set()
                        worker.join(timeout=3)
            except (serial.SerialException, OSError) as exc:
                log.warning('[ZED-F9P] USB-Verbindung: %s', exc)
            if not stop_event.is_set():
                stop_event.wait(self.reconnect_delay_s)

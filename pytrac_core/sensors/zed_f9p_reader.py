"""USB ZED-F9P GNSS + optional NTRIP RTCM forwarding; existing GPS callback contract."""
import base64
from dataclasses import replace
import logging
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit

import serial

from pytrac_core.sensors.gps_reader import GpsReader

log = logging.getLogger(__name__)

class ZedF9pReader(GpsReader):
    def __init__(self, *, ntrip_url='', ntrip_username='', ntrip_password='',
                 ntrip_send_gga=True, **kwargs):
        kwargs['configure_receiver'] = False  # Never send legacy NEO-6M UBX-CFG commands.
        super().__init__(**kwargs)
        self.ntrip_url=ntrip_url.strip()
        self.ntrip_username=ntrip_username
        self.ntrip_password=ntrip_password
        self.ntrip_send_gga=ntrip_send_gga
        self._gga_line=None
        self._gga_lock=threading.Lock()
        self._serial_write_lock=threading.Lock()
        self._rtk_quality=0
        self._last_fix_log=0.0

    def _handle_sentence(self,line):
        if line.startswith(('$GPGGA,','$GNGGA,','$GAGGA,','$GBGGA,','$GLGGA,')):
            with self._gga_lock:self._gga_line=line
            try:
                quality=int(line.split(',')[6] or '0')
                if quality != self._rtk_quality:
                    self._rtk_quality=quality
                    label={0:'NO FIX',1:'GNSS',2:'DGNSS',4:'RTK FIX',5:'RTK FLOAT'}.get(quality,f'GPS Qualität {quality}')
                    log.warning('[ZED-F9P] Positionierungsstatus: %s',label)
            except (ValueError,IndexError):pass
        measurement=super()._handle_sentence(line)
        if measurement is not None:
            return replace(measurement,gps_fix_quality=measurement.fix_quality)
        return None

    def _ntrip_worker(self,uart,stop_event,disconnected):
        if not self.ntrip_url:return
        try:
            parsed=urlsplit(self.ntrip_url)
            if parsed.scheme not in ('ntrip','http','https') or not parsed.hostname or not parsed.path.strip('/'):
                raise ValueError('NTRIP_URL muss ntrip://host:port/mountpoint oder https://host/mountpoint sein')
            port=parsed.port or (443 if parsed.scheme=='https' else 2101)
            host=parsed.hostname
            mount=parsed.path.lstrip('/')
            while not stop_event.is_set() and not disconnected.is_set():
                try:
                    sock=socket.create_connection((host,port),timeout=10)
                    if parsed.scheme=='https':sock=ssl.create_default_context().wrap_socket(sock,server_hostname=host)
                    with sock:
                        sock.settimeout(2)
                        credentials=base64.b64encode(f'{self.ntrip_username}:{self.ntrip_password}'.encode()).decode()
                        request=(f'GET /{mount} HTTP/1.0\r\nHost: {host}\r\nUser-Agent: NTRIP PyTrac/1.0\r\n'
                                 f'Authorization: Basic {credentials}\r\nAccept: */*\r\nConnection: close\r\n\r\n').encode('ascii')
                        sock.sendall(request)
                        response=bytearray()
                        while b'\r\n\r\n' not in response and b'\n\n' not in response:
                            block=sock.recv(4096)
                            if not block:raise OSError('NTRIP hat Verbindung geschlossen')
                            response.extend(block)
                            if len(response)>16384:raise OSError('NTRIP-Antwort zu groß')
                        sep=b'\r\n\r\n' if b'\r\n\r\n' in response else b'\n\n'
                        header,pending=bytes(response).split(sep,1)
                        first=header.splitlines()[0]
                        if not (first.startswith(b'ICY 200') or b' 200 ' in first):
                            raise OSError('NTRIP-Verbindung abgelehnt: '+first.decode('ascii','replace'))
                        log.warning('[ZED-F9P] NTRIP verbunden: %s/%s',host,mount)
                        if pending:
                            with self._serial_write_lock:uart.write(pending)
                        next_gga=0
                        while not stop_event.is_set() and not disconnected.is_set():
                            if self.ntrip_send_gga and time.monotonic()>=next_gga:
                                with self._gga_lock:gga=self._gga_line
                                if gga:
                                    sock.sendall((gga+'\r\n').encode('ascii'))
                                next_gga=time.monotonic()+5
                            try:rtcm=sock.recv(4096)
                            except socket.timeout:continue
                            if not rtcm:raise OSError('NTRIP-Stream beendet')
                            with self._serial_write_lock:uart.write(rtcm)
                except (OSError,ValueError) as exc:
                    log.warning('[ZED-F9P] NTRIP: %s; neuer Versuch in 5 s',exc)
                    disconnected.wait(5)
        except Exception:
            log.exception('[ZED-F9P] NTRIP-Konfiguration fehlgeschlagen')

    def run(self,stop_event:threading.Event):
        if not self.port:
            log.error('[ZED-F9P] GPS_PORT fehlt. Beispiel /dev/serial/by-id/...')
            return
        while not stop_event.is_set():
            disconnected=threading.Event()
            try:
                with serial.Serial(self.port,self.baudrate,timeout=0.2,write_timeout=2) as uart:
                    log.warning('[ZED-F9P] USB-GNSS verbunden: %s',self.port)
                    self._reset_stats()
                    worker=threading.Thread(target=self._ntrip_worker,args=(uart,stop_event,disconnected),daemon=True)
                    worker.start()
                    try:
                        while not stop_event.is_set():
                            raw=uart.readline()
                            if not raw:continue
                            try:line=raw.decode('ascii').strip()
                            except UnicodeDecodeError:continue
                            if not line.startswith('$'):continue
                            measurement=self._handle_sentence(line)
                            if measurement and self.on_measurement:self.on_measurement(measurement)
                    finally:
                        disconnected.set()
                        worker.join(timeout=3)
            except (serial.SerialException,OSError) as exc:
                log.warning('[ZED-F9P] USB-Verbindung: %s',exc)
            stop_event.wait(self.reconnect_delay_s)

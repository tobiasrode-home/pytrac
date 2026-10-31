"""Eigenständige, rotierende GNSS-/IMU-/NTRIP-Diagnoselogdatei."""
import logging
import os
from logging.handlers import RotatingFileHandler


def configure_sensor_diagnostics():
    path = os.environ.get('PYTRAC_SENSOR_LOG', '/var/log/pytrac/gps_ntrip.log')
    directory = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(directory, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024,
                                      backupCount=5, encoding='utf-8')
    except OSError as exc:
        logging.getLogger(__name__).warning('Sensordiagnose-Log nicht verfügbar: %s', exc)
        return
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    handler.setLevel(logging.INFO)
    # Nur gezielte Sensormodule, keine NTRIP-Zugangsdaten protokollieren.
    for name in ('pytrac_core.sensors.synchronizer', 'pytrac_core.sensors.zed_f9p_reader',
                 'pytrac_core.sensors.bno085_reader', 'pytrac_core.sensors.gps_reader'):
        log = logging.getLogger(name)
        if not any(getattr(h, '_pytrac_diagnostic', False) for h in log.handlers):
            log.addHandler(handler)
            log.setLevel(logging.INFO)
    handler._pytrac_diagnostic = True

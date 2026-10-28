"""Startet und verwaltet die PyTrac-Sensoren."""
import logging
import threading
from collections.abc import Callable
from pytrac_core.config import settings
from pytrac_core.sensors.bno085_reader import Bno085Reader
from pytrac_core.sensors.gps_reader import GpsReader
from pytrac_core.sensors.zed_f9p_reader import ZedF9pReader
from pytrac_core.sensors.models import VehicleState
from pytrac_core.sensors.synchronizer import SensorSynchronizer

logger=logging.getLogger(__name__)

class SensorManager:
    def __init__(self,gps_port:str,imu_port:str,on_state:Callable[[VehicleState],None],
                 gps_baudrate:int=9600,imu_baudrate:int=115200,output_rate_hz:float=5.0)->None:
        self.stop_event=threading.Event()
        self.synchronizer=SensorSynchronizer(on_state=on_state,output_rate_hz=output_rate_hz)
        if settings.gps_receiver.lower()=='zed_f9p':
            self.gps_reader=ZedF9pReader(port=gps_port,baudrate=gps_baudrate,
                on_measurement=self.synchronizer.add_gps,
                ntrip_url=settings.ntrip_url,ntrip_username=settings.ntrip_username,
                ntrip_password=settings.ntrip_password,ntrip_send_gga=settings.ntrip_send_gga)
        elif settings.gps_receiver.lower()=='legacy':
            self.gps_reader=GpsReader(port=gps_port,baudrate=gps_baudrate,
                on_measurement=self.synchronizer.add_gps)
        else:raise ValueError('GPS_RECEIVER muss zed_f9p oder legacy sein')
        self.imu_reader=Bno085Reader(port=imu_port,baudrate=imu_baudrate,
            on_measurement=self.synchronizer.add_imu)
        self._threads=[]
    def start(self)->None:
        if any(t.is_alive() for t in self._threads):return
        self.stop_event.clear()
        workers=[('pytrac-gps',self.gps_reader.run),('pytrac-imu',self.imu_reader.run),
                 ('pytrac-synchronizer',self.synchronizer.run)]
        self._threads=[threading.Thread(target=target,args=(self.stop_event,),name=name,daemon=True)
                       for name,target in workers]
        for thread in self._threads:thread.start()
        logger.info('SensorManager gestartet.')
    def stop(self)->None:
        self.stop_event.set()
        for thread in self._threads:thread.join(timeout=3.0)
        self._threads.clear()
        logger.info('SensorManager beendet.')

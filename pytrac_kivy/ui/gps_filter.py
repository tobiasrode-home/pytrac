"""Adaptiver Alpha-Beta-GPS-Filter, nur Standardbibliothek.

Verarbeitet WGS84-Messungen mit Zeitstempel, Position und Geschwindigkeit.
Keine RTK-Genauigkeit; glättet zufälliges Rauschen, nicht systematische Fehler.
"""
from datetime import datetime
from math import cos, radians, hypot, isfinite

class AdaptiveGpsFilter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.lat=self.lon=self.time=None
        self.vx=self.vy=0.0
        self.last_input=None

    def update(self,lat,lon,timestamp,speed_mps=None,accuracy_m=None):
        lat=float(lat);lon=float(lon)
        if not (isfinite(lat) and isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
            raise ValueError("Ungültige GPS-Koordinaten")
        if timestamp is None:
            raise ValueError("GPS-Zeitstempel fehlt")
        if isinstance(timestamp,(float,int)):
            t=float(timestamp)
        else:
            t=datetime.fromisoformat(str(timestamp).replace("Z","+00:00")).timestamp()
        if not isfinite(t):raise ValueError("GPS-Zeitstempel ungültig")
        signature=(t,lat,lon)
        if signature==self.last_input and self.lat is not None:
            return self.lat,self.lon
        if self.time is None or t-self.time>3 or t<=self.time:
            self.lat,self.lon,self.time=lat,lon,t
            self.vx=self.vy=0.
            self.last_input=signature
            return lat,lon
        dt=t-self.time
        meters_lat=111_132.
        meters_lon=max(1000.,111_320.*cos(radians(lat)))
        dx=(lon-self.lon)*meters_lon
        dy=(lat-self.lat)*meters_lat
        residual_x=dx-self.vx*dt
        residual_y=dy-self.vy*dt
        speed=float(speed_mps) if speed_mps is not None else hypot(self.vx,self.vy)
        if not isfinite(speed):speed=0.
        # Extreme Ausreißer verwerfen; keinen alten Fix unbegrenzt extrapolieren.
        accuracy=max(1.,float(accuracy_m)) if accuracy_m is not None else 5.
        if not isfinite(accuracy):accuracy=5.
        max_jump=max(12.,4*accuracy+max(0.,speed)*dt*3)
        if hypot(residual_x,residual_y)>max_jump:
            self.time=t
            self.last_input=signature
            return self.lat,self.lon
        # Bei Stillstand kräftiger glätten; bei Fahrt schneller reagieren.
        alpha=.20 if speed<.35 else .65 if speed<2.5 else .82
        beta=.025 if speed<.35 else .12
        self.lon+=(self.vx*dt+alpha*residual_x)/meters_lon
        self.lat+=(self.vy*dt+alpha*residual_y)/meters_lat
        self.vx+=beta*residual_x/dt
        self.vy+=beta*residual_y/dt
        self.time=t
        self.last_input=signature
        return self.lat,self.lon

def adjusted_heading(raw_heading,offset_deg):
    if raw_heading is None:return None
    return (float(raw_heading)+float(offset_deg))%360.

"""Backend-unabhängige GPS-Spurführung für gespeicherte V8-Arbeitsplanungen.

Koordinaten der API sind immer [longitude, latitude]. Keine Lenksteuerung.
"""
from dataclasses import dataclass
from math import cos, hypot, radians, sqrt

EARTH_M = 6371008.8


def xy(lonlat, origin):
    lon, lat = map(float, lonlat)
    lon0, lat0 = map(float, origin)
    return ((radians(lon - lon0) * EARTH_M * cos(radians(lat0))),
            radians(lat - lat0) * EARTH_M)


def nearest_on_polyline(position, coordinates):
    """Abstand, Reststrecke und Seite relativ zur *Fahrtrichtung*.

    Positive Seitenabweichung = links der Spur; negative = rechts.
    """
    if len(coordinates) < 2:
        raise ValueError('Mindestens zwei Koordinaten erforderlich')
    origin = position
    p = (0., 0.)
    pts = [xy(q, origin) for q in coordinates]
    total = sum(hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(pts,pts[1:]))
    best = None
    travelled = 0.
    for a,b in zip(pts,pts[1:]):
        vx,vy=b[0]-a[0],b[1]-a[1]
        length=hypot(vx,vy)
        if length < 1e-6:
            continue
        t=max(0.,min(1.,(-(a[0]*vx+a[1]*vy))/(length*length)))
        qx,qy=a[0]+t*vx,a[1]+t*vy
        distance=hypot(qx,qy)
        signed=(vx*(-a[1])-vy*(-a[0]))/length
        candidate=(distance, signed, max(0.,total-travelled-t*length),travelled+t*length)
        if best is None or candidate[0] < best[0]:
            best=candidate
        travelled += length
    if best is None:
        raise ValueError('Spur hat keine Länge')
    return {'distance_m':best[0], 'signed_offset_m':best[1],
            'remaining_m':best[2], 'progress_m':best[3], 'length_m':total}


@dataclass
class GuidanceState:
    phase: str = 'main'
    track_index: int = 0
    pending_action: str | None = None
    confirmed_lower: bool = False
    confirmed_raise: bool = False
    active: bool = False


class GuidanceNavigator:
    """Explizite Bedienung; GPS löst keine Geräteaktion automatisch aus."""
    def __init__(self, guidance, planning):
        self.guidance=guidance
        self.planning=planning
        self.state=GuidanceState()
        self.completed=set()
        self.last_fix=None

    @property
    def tracks(self):
        return self.guidance.get('tracks',[]) if self.state.phase=='main' else self.guidance.get('headland_tracks',[])

    @property
    def track(self):
        return self.tracks[self.state.track_index] if self.tracks and self.state.track_index<len(self.tracks) else None

    @property
    def events(self):
        return self.guidance.get('implement_events',[]) if self.state.phase=='main' else self.guidance.get('headland_implement_events',[])

    def event(self, action):
        if self.track is None:
            return None
        return next((e for e in self.events if e.get('track_id')==self.track.get('id') and e.get('action')==action),None)

    def select(self, phase, index=0):
        if phase not in ('main','headland'):
            raise ValueError('Unbekannte Arbeitsphase')
        if self.state.active:
            raise ValueError('Gerät zuerst deaktivieren')
        self.state=GuidanceState(phase=phase,track_index=index)
        if self.track is None:
            raise ValueError('Keine Spur in dieser Phase')
        return self.track

    def next_track(self):
        if self.state.active:
            raise ValueError('Gerät zuerst deaktivieren')
        if self.track is not None and self.state.confirmed_raise:
            self.completed.add((self.state.phase,self.track['id']))
        if self.state.track_index+1>=len(self.tracks):
            return False
        self.select(self.state.phase,self.state.track_index+1)
        return True

    def update(self, lon, lat, gps_valid=True):
        if not gps_valid or self.track is None:
            self.last_fix=None
            return None
        position=[float(lon),float(lat)]
        projection=nearest_on_polyline(position,self.track['coordinates'])
        action=None
        event_distance=None
        if not self.state.confirmed_lower:
            action='lower'
        elif not self.state.confirmed_raise:
            action='raise'
        event=self.event(action) if action else None
        if event:
            target=event.get('vehicle_stop_coordinate') or event.get('coordinate')
            if target:
                event_distance=hypot(*xy(target,position))
        self.last_fix={**projection,'event_action':action,'event_distance_m':event_distance,
                       'track_id':self.track['id'],'phase':self.state.phase}
        return self.last_fix

    def confirm(self, action, stopped, distance_tolerance_m=3.0):
        """Bestätigung nur bei GPS-Fix und am Stopppunkt; Gerät bleibt manuell."""
        if action not in ('lower','raise') or self.track is None:
            raise ValueError('Ungültige Geräteaktion')
        if not stopped:
            raise ValueError('Zum Bestätigen zuerst anhalten')
        if self.last_fix is None or self.last_fix['event_action']!=action:
            raise ValueError('Kein gültiger GPS-Fix oder Aktion nicht fällig')
        if self.last_fix['event_distance_m'] is None or self.last_fix['event_distance_m']>distance_tolerance_m:
            raise ValueError('Stopppunkt noch nicht erreicht')
        if action=='lower':
            self.state.confirmed_lower=True
            self.state.active=True
        else:
            self.state.confirmed_raise=True
            self.state.active=False
            self.completed.add((self.state.phase,self.track['id']))
        return True

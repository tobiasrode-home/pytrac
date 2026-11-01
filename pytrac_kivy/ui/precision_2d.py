"""Modernes minimalistisches PyTrac-2D-Terminal (reine Anzeige)."""
import math
from datetime import datetime
from pathlib import Path
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line, Ellipse, RoundedRectangle
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp

_ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'precision'

class Precision2D(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dark_mode = True
        self.state = None
        self.navigator = None
        self.progress_points = []
        self.working_width_m = 0.0
        self.hud_status = ("N/A", "—/—", "Bereit")
        self.guidance_text = "Lenkhilfe: kein GPS / keine Spur"
        self.zoom_m = 65.0
        self._textures = {}
        for name in ('tractor', 'terrain'):
            try:
                self._textures[name] = CoreImage(str(_ASSETS / (name + '.png'))).texture
                if name == 'terrain':
                    self._textures[name].wrap = 'repeat'
            except Exception:
                self._textures[name] = None
        self.bind(pos=self.redraw, size=self.redraw)

    def set_dark_mode(self, dark):
        self.dark_mode = bool(dark)
        self.redraw()

    def set_status(self, gps, track, implement):
        status = (str(gps), str(track), str(implement))
        if status != self.hud_status:
            self.hud_status = status
            self.redraw()

    def set_progress(self, points, working_width_m):
        """Gespeicherte, bei aktivem Gerät aufgezeichnete GPS-Arbeitspunkte."""
        self.progress_points = list(points or [])
        try:
            self.working_width_m = max(0.0, float(working_width_m or 0))
        except (ValueError, TypeError):
            self.working_width_m = 0.0
        self.redraw()

    def set_guidance_text(self, value):
        self.guidance_text = str(value)

    def update(self, state, navigator):
        self.state = state
        self.navigator = navigator
        try:
            speed = max(0.0, float(state.get('speed_mps') or 0))
            target = 25.0 if speed < 1.5 else 38.0 if speed < 3.5 else 55.0 if speed < 7 else 75.0
            self.zoom_m += (target - self.zoom_m) * .17
        except (ValueError, TypeError, AttributeError):
            pass
        self.redraw()

    def _text(self, value, x, y, size=15, color=None, bold=True):
        if color is None: color=(.89,.96,.96,1) if self.dark_mode else (.06,.08,.10,1)
        label = CoreLabel(text=str(value), font_size=dp(size), color=color, bold=bold)
        label.refresh()
        texture = label.texture
        Color(1,1,1,1)
        Rectangle(texture=texture, pos=(x-texture.width/2,y-texture.height/2), size=texture.size)

    def _panel(self, x,y,w,h,alpha=.95):
        Color(*((.055,.105,.14,alpha) if self.dark_mode else (.97,.98,1,alpha)))
        RoundedRectangle(pos=(x,y),size=(w,h),radius=[dp(12)])
        Color(*((.20,.35,.38,.65) if self.dark_mode else (.53,.59,.65,.8)))
        Line(rounded_rectangle=(x,y,w,h,dp(12)),width=1)

    def redraw(self, *_):
        self.canvas.clear()
        x0,y0=self.pos
        w,h=self.size
        if w < 10 or h < 10:
            return
        with self.canvas:
            Color(*((.047,.092,.12,1) if self.dark_mode else (1,1,1,1)))
            Rectangle(pos=self.pos,size=self.size)
            terrain=self._textures.get('terrain')
            if terrain is not None and self.dark_mode:
                Color(1,1,1,.54)
                Rectangle(texture=terrain,pos=self.pos,size=self.size,tex_coords=(0,0,w/dp(512),0,w/dp(512),h/dp(512),0,h/dp(512)))
            scale=h/max(20.0,self.zoom_m)
            cx=x0+w*.5
            cy=y0+h*.29
            # Orientierungsgitter, Maßstab und Distanzlinien
            for offset in range(-10,11):
                xx=cx+offset*10*scale
                if x0 <= xx <= x0+w:
                    Color(*((.24,.41,.43,.19 if offset else .36) if self.dark_mode else (.37,.42,.47,.18 if offset else .32)))
                    Line(points=[xx,y0,xx,y0+h],width=1)
            for meters in (10,20,30,50,75,100,150):
                yy=cy+meters*scale
                if yy > y0+h-dp(100):continue
                Color(*((.25,.42,.44,.36) if self.dark_mode else (.39,.44,.49,.30)))
                Line(points=[x0+dp(15),yy,x0+w-dp(15),yy],width=1)
                self._text(f'{meters} m',x0+dp(40),yy+dp(12),10,(.50,.69,.71,1) if self.dark_mode else (.24,.29,.34,1),False)
            state=self.state or {}
            nav=self.navigator
            coords_ok=False
            try:
                lat=float(state['latitude']);lon=float(state['longitude'])
                heading=float(state.get('heading_deg') or 0)
                coords_ok=all(math.isfinite(v) for v in (lat,lon,heading))
            except (KeyError,ValueError,TypeError):pass
            if coords_ok:
                a=math.radians(heading)
                east=math.cos(a);north=-math.sin(a)
                ahead_e=math.sin(a);ahead_n=math.cos(a)
                lat_scale=111132.92
                lon_scale=111319.49*math.cos(math.radians(lat))
                def xy(p):
                    dx=(float(p[0])-lon)*lon_scale
                    dy=(float(p[1])-lat)*lat_scale
                    return (cx+(dx*east+dy*north)*scale,cy+(dx*ahead_e+dy*ahead_n)*scale)
                # Arbeitsbreite: nur gespeicherte Arbeitspunkte verwenden. Kein
                # "Live-Streifen" hinter dem Traktor bei ausgeschaltetem Gerät.
                width_m = self.working_width_m
                if width_m > 0 and self.progress_points:
                    half = width_m * scale / 2
                    previous = None
                    for point in self.progress_points:
                        try:
                            pos = xy((point['longitude'], point['latitude']))
                            lat_p = float(point['latitude'])
                            lon_p = float(point['longitude'])
                            key = (str(point.get('phase')), str(point.get('track_id')))
                            timestamp = point.get('recorded_at')
                        except (KeyError, TypeError, ValueError, OverflowError):
                            previous = None
                            continue
                        if previous is not None and key == previous[2]:
                            # Große Sprünge nicht als bearbeitete Fläche verbinden.
                            dx = (lon_p-previous[3])*lon_scale
                            dy = (lat_p-previous[4])*lat_scale
                            distance = math.hypot(dx,dy)
                            time_ok = True
                            try:
                                t0 = datetime.fromisoformat(previous[1].replace('Z','+00:00'))
                                t1 = datetime.fromisoformat(timestamp.replace('Z','+00:00'))
                                time_ok = 0 <= (t1-t0).total_seconds() <= 15
                            except (AttributeError, ValueError, TypeError):
                                time_ok = False
                            if time_ok and 0 < distance <= max(8.0, width_m * 2.5):
                                x1,y1 = previous[0]
                                x2,y2 = pos
                                vx,vy = x2-x1,y2-y1
                                length = math.hypot(vx,vy)
                                if length > .01:
                                    nx,ny = -vy/length*half, vx/length*half
                                    from kivy.graphics import Mesh
                                    Color(.49,.68,.64,.31)
                                    Mesh(vertices=[x1+nx,y1+ny,0,0,
                                                   x1-nx,y1-ny,0,0,
                                                   x2+nx,y2+ny,0,0,
                                                   x2-nx,y2-ny,0,0],
                                         indices=[0,1,2,2,1,3],mode='triangles')
                        previous = (pos,timestamp,key,lon_p,lat_p)
                tracks=nav.tracks if nav else []
                active=nav.track if nav else None
                active_id=active.get('id') if active else None
                try:
                    next_id=tracks[nav.state.track_index+1].get('id')
                except (AttributeError, IndexError, TypeError):
                    next_id=None
                for track in tracks:
                    coords=track.get('coordinates') or []
                    if len(coords)<2:continue
                    points=[]
                    for p in coords:
                        try:points.append(xy(p))
                        except (TypeError,ValueError,IndexError):continue
                    if len(points)<2:continue
                    pts=[v for point in points for v in point]
                    selected=str(track.get('id'))==str(active_id)
                    following=next_id is not None and str(track.get('id'))==str(next_id)
                    if selected:
                        color=(.39,1,.75,.95)
                        Color(.14,.98,.69,.12)
                        Line(points=pts,width=dp(11),joint='round')
                        Color(*color)
                        Line(points=pts,width=dp(3.5),joint='round')
                    elif following:
                        color=(.98,.76,.30,.94)
                        Color(*color)
                        Line(points=pts,width=dp(3),joint='round')
                    else:
                        color=(.37,.62,.67,.60) if self.dark_mode else (.22,.38,.47,.85)
                        Color(*color)
                        Line(points=pts,width=dp(1.7),joint='round')
                    # Pfeil am gespeicherten Spuranfang; zeigt zur zweiten Koordinate.
                    start=points[0]
                    target=next((p for p in points[1:]
                                 if math.hypot(p[0]-start[0],p[1]-start[1])>dp(3)),None)
                    if target is not None:
                        vx,vy=target[0]-start[0],target[1]-start[1]
                        length=math.hypot(vx,vy)
                        ux,uy=vx/length,vy/length
                        arrow=dp(12)
                        tip=(start[0]+ux*arrow,start[1]+uy*arrow)
                        left=(start[0]-uy*arrow*.48,start[1]+ux*arrow*.48)
                        right=(start[0]+uy*arrow*.48,start[1]-ux*arrow*.48)
                        Color(*color)
                        Line(points=[left[0],left[1],tip[0],tip[1],right[0],right[1]],
                             width=dp(2.4),joint='round',cap='round')
                # Fahrzeug-Schatten und freigestelltes, hochauflösendes Symbol
                # Traktorsymbol an den echten Kartenmassstab koppeln.
                # 4.5 m Fahrzeuglaenge; Symbol bleibt nur bei grossem Zoom
                # durch eine kleine Mindestgroesse lesbar.
                tractor_length_m = 4.5
                th = max(dp(38), min(dp(100), tractor_length_m * scale))
                tw = th * 240 / 340
                Color(.01,.03,.05,.40)
                Ellipse(pos=(cx-tw*.57,cy-th*.43-dp(5)),size=(tw*1.14,th*.95))
                tractor=self._textures.get('tractor')
                if tractor is not None:
                    Color(1,1,1,1)
                    Rectangle(texture=tractor,pos=(cx-tw/2,cy-th*.45),size=(tw,th))
                else:
                    Color(.30,.89,.63,1)
                    RoundedRectangle(pos=(cx-tw*.32,cy-th*.40),size=(tw*.64,th*.8),radius=[dp(10)])
                Color(.60,1,.80,.9)
                Line(circle=(cx,cy,dp(7)),width=dp(1.4))
            # Statuskarten an festen Bildschirmecken, ohne separate Statusleiste.
            pad = dp(12)
            status_width = min(dp(142), max(dp(95), w * .25))
            status_height = dp(58)
            def status_card(caption, value, sx, sy):
                self._panel(sx, sy, status_width, status_height, .93)
                self._text(caption, sx + status_width / 2, sy + dp(43),
                           10, (.49, .70, .71, 1) if self.dark_mode else (.24,.29,.34,1), False)
                self._text(value, sx + status_width / 2, sy + dp(18),
                           14, (.89, .96, .96, 1) if self.dark_mode else (.06,.08,.10,1))

            gps, track, implement = self.hud_status
            # GPS oben links, Arbeitsgerät oben rechts.
            status_card('GPS', gps, x0 + pad, y0 + h - pad - status_height)
            status_card('ARBEITSGERÄT', implement,
                        x0 + w - pad - status_width, y0 + h - pad - status_height)
            # Spur unten links, direkt über der Geschwindigkeitskarte.
            status_card('SPUR', track, x0 + pad, y0 + pad + dp(63) + dp(8))
            # HUD-Elemente unabhängig von gültigen GPS-Daten
            pad=dp(12)
            self._panel(x0+pad,y0+pad,dp(148),dp(63))
            try:speed=f'{float(state.get("speed_mps") or 0)*3.6:.1f}'
            except (ValueError,TypeError):speed='–'
            self._text(speed+' km/h',x0+pad+dp(74),y0+pad+dp(36),18)
            self._text('GESCHWINDIGKEIT',x0+pad+dp(74),y0+pad+dp(14),9,(.49,.70,.71,1) if self.dark_mode else (.24,.29,.34,1),False)
            self._panel(x0+w-dp(160),y0+pad,dp(148),dp(63))
            self._text(f'{self.zoom_m:.0f} m',x0+w-dp(86),y0+pad+dp(36),18)
            self._text('SICHTBEREICH',x0+w-dp(86),y0+pad+dp(14),9,(.49,.70,.71,1) if self.dark_mode else (.24,.29,.34,1),False)
            # Gleiche Korrekturanweisung wie die obere Lenkhilfe, kein zweites Vorzeichenmodell.
            guidance = self.guidance_text
            if guidance.startswith('Lenkhilfe:'):
                guidance = 'KEIN GPS / KEINE SPUR'
            elif 'korrigieren' in guidance:
                guidance = guidance.replace(' korrigieren · ', ' · ').upper()
            else:
                guidance = guidance.upper()
            self._panel(cx-dp(135), y0+h-dp(73), dp(270), dp(53))
            self._text(guidance, cx, y0+h-dp(46), 18, (.65,1,.79,1) if self.dark_mode else (.04,.15,.11,1))

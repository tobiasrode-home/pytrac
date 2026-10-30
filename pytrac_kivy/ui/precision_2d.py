"""Modernes minimalistisches PyTrac-2D-Terminal (reine Anzeige)."""
import math
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
        self.state = None
        self.navigator = None
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

    def update(self, state, navigator):
        self.state = state
        self.navigator = navigator
        try:
            speed = max(0.0, float(state.get('speed_mps') or 0))
            target = 32.0 if speed < 1.5 else 55.0 if speed < 3.5 else 85.0 if speed < 7 else 125.0
            self.zoom_m += (target - self.zoom_m) * .17
        except (ValueError, TypeError, AttributeError):
            pass
        self.redraw()

    def _text(self, value, x, y, size=15, color=(.89,.96,.96,1), bold=True):
        label = CoreLabel(text=str(value), font_size=dp(size), color=color, bold=bold)
        label.refresh()
        texture = label.texture
        Color(1,1,1,1)
        Rectangle(texture=texture, pos=(x-texture.width/2,y-texture.height/2), size=texture.size)

    def _panel(self, x,y,w,h,alpha=.95):
        Color(.055,.105,.14,alpha)
        RoundedRectangle(pos=(x,y),size=(w,h),radius=[dp(12)])
        Color(.20,.35,.38,.65)
        Line(rounded_rectangle=(x,y,w,h,dp(12)),width=1)

    def redraw(self, *_):
        self.canvas.clear()
        x0,y0=self.pos
        w,h=self.size
        if w < 10 or h < 10:
            return
        with self.canvas:
            Color(.047,.092,.12,1)
            Rectangle(pos=self.pos,size=self.size)
            terrain=self._textures.get('terrain')
            if terrain is not None:
                Color(1,1,1,.54)
                Rectangle(texture=terrain,pos=self.pos,size=self.size,tex_coords=(0,0,w/dp(512),0,w/dp(512),h/dp(512),0,h/dp(512)))
            scale=h/max(20.0,self.zoom_m)
            cx=x0+w*.5
            cy=y0+h*.29
            # Orientierungsgitter, Maßstab und Distanzlinien
            for offset in range(-10,11):
                xx=cx+offset*10*scale
                if x0 <= xx <= x0+w:
                    Color(.24,.41,.43,.19 if offset else .36)
                    Line(points=[xx,y0,xx,y0+h],width=1)
            for meters in (10,20,30,50,75,100,150):
                yy=cy+meters*scale
                if yy > y0+h-dp(100):continue
                Color(.25,.42,.44,.36)
                Line(points=[x0+dp(15),yy,x0+w-dp(15),yy],width=1)
                self._text(f'{meters} m',x0+dp(40),yy+dp(12),10,(.50,.69,.71,1),False)
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
                try:
                    imp=nav.planning.get('working_width_m') if nav else None
                    band=max(dp(18),min(w*.5,float(imp or 3)*scale))
                except (TypeError,ValueError,AttributeError):band=dp(24)
                Color(.12,.84,.61,.11)
                Rectangle(pos=(cx-band/2,y0),size=(band,max(0,cy-y0)))
                Color(.32,.91,.69,.48)
                Line(points=[cx-band/2,y0,cx-band/2,cy],width=dp(1.2))
                Line(points=[cx+band/2,y0,cx+band/2,cy],width=dp(1.2))
                tracks=nav.tracks if nav else []
                active=nav.track if nav else None
                active_id=active.get('id') if active else None
                for track in tracks:
                    coords=track.get('coordinates') or []
                    if len(coords)<2:continue
                    pts=[]
                    for p in coords:
                        try:pts.extend(xy(p))
                        except (TypeError,ValueError,IndexError):continue
                    if len(pts)<4:continue
                    selected=track.get('id')==active_id
                    if selected:
                        Color(.14,.98,.69,.12)
                        Line(points=pts,width=dp(11),joint='round')
                        Color(.39,1,.75,.95)
                        Line(points=pts,width=dp(3.5),joint='round')
                    else:
                        Color(.37,.62,.67,.52)
                        Line(points=pts,width=dp(1.7),joint='round')
                # Fahrzeug-Schatten und freigestelltes, hochauflösendes Symbol
                tw=max(dp(74),min(dp(118),w*.19))
                th=tw*340/240
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
            # HUD-Elemente unabhängig von gültigen GPS-Daten
            pad=dp(12)
            self._panel(x0+pad,y0+h-dp(70),w-2*pad,dp(58))
            self._text('PYTRAC   /   SPURFÜHRUNG',cx,y0+h-dp(40),15,(.80,.98,.91,1))
            self._panel(x0+pad,y0+pad,dp(148),dp(63))
            try:speed=f'{float(state.get("speed_mps") or 0)*3.6:.1f}'
            except (ValueError,TypeError):speed='–'
            self._text(speed+' km/h',x0+pad+dp(74),y0+pad+dp(36),18)
            self._text('GESCHWINDIGKEIT',x0+pad+dp(74),y0+pad+dp(14),9,(.49,.70,.71,1),False)
            self._panel(x0+w-dp(160),y0+pad,dp(148),dp(63))
            self._text(f'{self.zoom_m:.0f} m',x0+w-dp(86),y0+pad+dp(36),18)
            self._text('SICHTBEREICH',x0+w-dp(86),y0+pad+dp(14),9,(.49,.70,.71,1),False)
            if nav and nav.last_fix:
                try:
                    offset=float(nav.last_fix['signed_offset_m'])
                    direction='LINKS' if offset>0 else 'RECHTS' if offset<0 else 'MITTE'
                    self._panel(cx-dp(115),y0+h-dp(133),dp(230),dp(53))
                    self._text(f'{abs(offset)*100:.0f} cm   {direction}',cx,y0+h-dp(106),20,(.65,1,.79,1))
                except (KeyError,ValueError,TypeError):pass

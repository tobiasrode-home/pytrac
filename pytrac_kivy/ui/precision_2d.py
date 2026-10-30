"""Kartenfreie 2D-Spurführung; ausschließlich Darstellung, keine Lenklogik."""
import math
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line, Ellipse, Triangle
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp

class Precision2D(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.state = None
        self.navigator = None
        self.zoom_m = 65.0
        self.bind(pos=self.redraw, size=self.redraw)

    def update(self, state, navigator):
        self.state = state
        self.navigator = navigator
        try:
            speed = max(0.0, float(state.get('speed_mps') or 0))
            target = 32.0 if speed < 1.5 else 55.0 if speed < 3.5 else 85.0 if speed < 7 else 125.0
            self.zoom_m += (target - self.zoom_m) * .22
        except (ValueError, TypeError):
            pass
        self.redraw()

    def _text(self, value, x, y, size=16, color=(.85,.94,.91,1)):
        label = CoreLabel(text=str(value), font_size=dp(size), color=color, bold=True)
        label.refresh()
        texture = label.texture
        Color(1,1,1,1)
        Rectangle(texture=texture, pos=(x-texture.width/2,y-texture.height/2), size=texture.size)

    def redraw(self, *_):
        self.canvas.clear()
        x0,y0=self.pos
        w,h=self.size
        if w<10 or h<10:return
        with self.canvas:
            Color(.055,.092,.10,1)
            Rectangle(pos=self.pos,size=self.size)
            # Horizontale Entfernungsmarken, Maßstab ist Meter über Displayhöhe.
            scale = h / max(20.0, self.zoom_m)
            cx=x0+w*.5
            cy=y0+h*.31
            for meters in (10,20,30,50,75,100,150):
                yy=cy+meters*scale
                if yy>y0+h-12:continue
                Color(.16,.25,.26,.65)
                Line(points=[x0+dp(15),yy,x0+w-dp(15),yy],width=1)
                self._text(f'{meters} m',x0+dp(43),yy+dp(10),11,(.49,.65,.65,1))
            if not self.state:return
            try:
                lat=float(self.state['latitude']);lon=float(self.state['longitude'])
                heading=float(self.state.get('heading_deg') or 0)
                if not all(math.isfinite(v) for v in (lat,lon,heading)):return
            except (ValueError,TypeError,KeyError):return
            a=math.radians(heading)
            # Kartenloses Display: Fahrtrichtung nach oben, Traktor bleibt fest.
            east=math.cos(a);north=-math.sin(a)
            ahead_e=math.sin(a);ahead_n=math.cos(a)
            lat_scale=111132.92
            lon_scale=111319.49*math.cos(math.radians(lat))
            def xy(p):
                dx=(float(p[0])-lon)*lon_scale
                dy=(float(p[1])-lat)*lat_scale
                return (cx+(dx*east+dy*north)*scale,cy+(dx*ahead_e+dy*ahead_n)*scale)
            nav=self.navigator
            tracks=nav.tracks if nav else []
            active=nav.track if nav else None
            active_id=active.get('id') if active else None
            # Arbeitsbreite als transparentes Band hinter der Fahrzeugposition.
            try:
                imp=nav.planning.get('working_width_m') if nav else None
                band=max(dp(18),min(w*.5,float(imp or 3)*scale))
            except (TypeError,ValueError):band=dp(24)
            Color(.12,.54,.34,.19)
            Rectangle(pos=(cx-band/2,y0),size=(band,max(0,cy-y0)))
            for track in tracks:
                coords=track.get('coordinates') or []
                if len(coords)<2:continue
                pts=[]
                for p in coords:
                    try:pts.extend(xy(p))
                    except (TypeError,ValueError,IndexError):continue
                if len(pts)<4:continue
                selected=track.get('id')==active_id
                Color(.38,.95,.55,1) if selected else Color(.29,.47,.48,.65)
                Line(points=pts,width=dp(3.5) if selected else dp(1.6),joint='round')
            # Traktor mit deutlich erkennbarem Fahrerhaus und vier Rädern.
            tw=max(dp(42),min(dp(78),w*.14));th=tw*1.45
            Color(.02,.03,.04,1)
            for sx in (-1,1):
                for sy in (-1,1):
                    Rectangle(pos=(cx+sx*tw*.44-dp(7),cy+sy*th*.29-dp(12)),size=(dp(14),dp(24)))
            Color(.27,.76,.36,1)
            Rectangle(pos=(cx-tw*.36,cy-th*.45),size=(tw*.72,th*.9))
            Color(.10,.28,.30,1)
            Rectangle(pos=(cx-tw*.29,cy+th*.02),size=(tw*.58,th*.25))
            Color(.82,.98,.73,1)
            Triangle(points=[cx,cy+th*.73,cx-dp(10),cy+th*.45,cx+dp(10),cy+th*.45])
            Color(.9,.96,.91,1)
            Line(rectangle=(cx-tw*.36,cy-th*.45,tw*.72,th*.9),width=dp(1.5))
            Color(.08,.17,.19,.93)
            Rectangle(pos=(x0+dp(8),y0+h-dp(54)),size=(w-dp(16),dp(46)))
            self._text('2D  SPURFÜHRUNG',cx,y0+h-dp(31),17)
            speed=self.state.get('speed_mps')
            if speed is not None:
                try:self._text(f'{float(speed)*3.6:.1f} km/h',x0+w-dp(75),y0+dp(25),15)
                except (ValueError,TypeError):pass
            if nav and nav.last_fix:
                try:
                    offset=float(nav.last_fix['signed_offset_m'])
                    direction='LINKS' if offset>0 else 'RECHTS' if offset<0 else 'MITTE'
                    self._text(f'{abs(offset)*100:.0f} cm  {direction}',cx,y0+h-dp(81),19,(.95,.98,.81,1))
                except (KeyError,ValueError,TypeError):pass

"""Geplante Fahrspuren und Stopppunkte über der bestehenden MapView."""
from kivy.graphics import Color, Line, Ellipse
from kivy_garden.mapview import MapLayer
from pytrac_kivy.ui.map_scale import meters_to_pixels
from kivy.metrics import dp


class GuidanceOverlay(MapLayer):
    def __init__(self, map_view, **kwargs):
        super().__init__(**kwargs)
        self.map_view=map_view
        self.guidance=None
        self.phase='main'
        self.active_id=None

    def set_plan(self, guidance, phase='main', active_id=None):
        self.guidance=guidance
        self.phase=phase
        self.active_id=active_id
        self.reposition()

    def reposition(self):
        self.canvas.clear()
        if not self.guidance:
            return
        tracks=self.guidance.get('tracks' if self.phase=='main' else 'headland_tracks',[])
        events=self.guidance.get('implement_events' if self.phase=='main' else 'headland_implement_events',[])
        with self.canvas:
            for track in tracks:
                coords=[]
                for lon,lat in track.get('coordinates',[]):
                    x,y=self.map_view.get_window_xy_from(float(lat),float(lon),self.map_view.zoom)
                    coords.extend([x,y])
                if len(coords)<4:
                    continue
                if track.get('id')==self.active_id:
                    Color(1.,.86,.12,1.)
                    Line(points=coords,width=4.5)
                elif self.phase=='headland':
                    Color(.15,.78,.37,.9)
                    Line(points=coords,width=2.2)
                else:
                    Color(.23,.55,.95,.9)
                    Line(points=coords,width=2.2)
            for event in events:
                if event.get('track_id')!=self.active_id:
                    continue
                point=event.get('vehicle_stop_coordinate') or event.get('coordinate')
                if not point:
                    continue
                x,y=self.map_view.get_window_xy_from(float(point[1]),float(point[0]),self.map_view.zoom)
                Color(.18,.9,.3,1) if event.get('action')=='lower' else Color(1.,.27,.16,1)
                diameter=max(dp(5),min(dp(48),meters_to_pixels(self.map_view,float(point[1]),float(point[0]),1.0)))
                Ellipse(pos=(x-diameter/2,y-diameter/2),size=(diameter,diameter))

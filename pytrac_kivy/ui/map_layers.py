"""Feldgrenzen mit optionaler abstrakter, kartenfreier Darstellung."""
from kivy.graphics import Color,Line,Rectangle
from kivy_garden.mapview import MapLayer

def _rings_from_field(field):
    boundary=(field or {}).get('boundary') or []
    if isinstance(boundary,dict):
        coords=boundary.get('coordinates') or []
        if boundary.get('type')=='Polygon':return coords
        if boundary.get('type')=='MultiPolygon':return [ring for poly in coords for ring in poly]
        return []
    if isinstance(boundary,list) and boundary and isinstance(boundary[0],(list,tuple)):
        if len(boundary[0])>=2 and all(isinstance(v,(int,float)) for v in boundary[0][:2]):return [boundary]
    return []

def field_center(field):
    rings=_rings_from_field(field)
    if not rings:return None
    pts=rings[0]
    if len(pts)>1 and pts[0]==pts[-1]:pts=pts[:-1]
    if not pts:return None
    return sum(float(p[1]) for p in pts)/len(pts),sum(float(p[0]) for p in pts)/len(pts)

class FieldOverlay(MapLayer):
    def __init__(self,map_view,**kwargs):
        super().__init__(**kwargs)
        self.map_view=map_view;self.field=None;self.track_points=[];self.abstract=False
    def set_abstract(self,enabled):
        self.abstract=bool(enabled);self.draw()
    def set_data(self,field=None,track_points=None):
        self.field=field;self.track_points=track_points or [];self.draw()
    def reposition(self):self.draw()
    def draw(self):
        self.canvas.clear()
        with self.canvas:
            if self.abstract:
                Color(.065,.105,.09,1)
                # Window-Koordinaten der Kartenfläche, keine globalen Screenkoordinaten.
                Rectangle(pos=self.map_view.pos,size=self.map_view.size)
            for ring in _rings_from_field(self.field):
                pts=[]
                for point in ring:
                    try:
                        x,y=self.map_view.get_window_xy_from(float(point[1]),float(point[0]),self.map_view.zoom)
                        pts.extend((x,y))
                    except (ValueError,TypeError,IndexError):continue
                if len(pts)>=6:
                    Color(.18,.95,.43,1);Line(points=pts,width=2.5,close=True)
            coords=[]
            for point in self.track_points:
                try:
                    x,y=self.map_view.get_window_xy_from(float(point['latitude']),float(point['longitude']),self.map_view.zoom)
                    coords.extend((x,y))
                except (KeyError,ValueError,TypeError):continue
            if len(coords)>=4:
                Color(1,.72,.12,1);Line(points=coords,width=2.5)

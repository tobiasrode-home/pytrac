"""Feldgrenzen mit optionaler abstrakter, kartenfreier Darstellung."""
from kivy.graphics import Color,Line,Rectangle,Mesh
from math import hypot
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
        self.map_view=map_view;self.field=None;self.track_points=[];self.working_width_m=0;self.abstract=False
    def set_abstract(self,enabled):
        self.abstract=bool(enabled);self.draw()
    def set_data(self,field=None,track_points=None,working_width_m=0):
        self.field=field;self.track_points=track_points or [];self.working_width_m=float(working_width_m or 0);self.draw()
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
            # Einzelne Spuren/Phasen getrennt zeichnen: kein Verbinden
            # unterschiedlicher Arbeitsbahnen zu fiktiv bearbeiteten Flächen.
            from pytrac_kivy.ui.map_scale import meters_to_pixels
            segments=[]
            current=[]
            previous_key=None
            for point in self.track_points:
                key=(point.get('phase'),point.get('track_id'))
                if key!=previous_key and current:
                    segments.append(current);current=[]
                previous_key=key
                try:
                    lat=float(point['latitude']);lon=float(point['longitude'])
                    x,y=self.map_view.get_window_xy_from(lat,lon,self.map_view.zoom)
                    current.append((x,y,lat,lon))
                except (KeyError,ValueError,TypeError):continue
            if current:segments.append(current)
            for segment in segments:
                if len(segment)<2:continue
                coords=[value for x,y,_,_ in segment for value in (x,y)]
                if self.working_width_m>0:
                    # Jede Strecke als flaches Rechteck mit exakt projizierter
                    # Arbeitsbreite zeichnen: keine kreisförmigen Punktmarker.
                    # Verbundene Rechtecke bilden ein durchgehendes Arbeitsband.
                    Color(.2,.7,.25,.36)
                    for (x0,y0,lat0,lon0),(x1,y1,lat1,lon1) in zip(segment,segment[1:]):
                        length=hypot(x1-x0,y1-y0)
                        if length<.001:continue
                        width=max(1.,min(1000.,meters_to_pixels(
                            self.map_view,(lat0+lat1)/2,(lon0+lon1)/2,self.working_width_m)))
                        nx=-(y1-y0)/length*width/2
                        ny=(x1-x0)/length*width/2
                        vertices=[x0+nx,y0+ny,0,0, x0-nx,y0-ny,0,0,
                                  x1-nx,y1-ny,0,0, x1+nx,y1+ny,0,0]
                        Mesh(vertices=vertices,indices=[0,1,2,0,2,3],mode='triangles')
                Color(1,.72,.12,1)
                Line(points=coords,width=2)

"""Schematische Feldvorschau: jede Kante trägt ihre API-Nummer edge-N."""
from math import cos, radians
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

def boundary_edges(boundary):
    """Backend-Nummerierung: Kante i verbindet Punkt i mit Punkt i+1."""
    if isinstance(boundary,dict):
        boundary=boundary.get("coordinates",[[]])[0]
    points=[(float(p[0]),float(p[1])) for p in (boundary or []) if len(p)>=2]
    if len(points)>1 and points[0]==points[-1]:
        points=points[:-1]
    if len(points)<3:
        return []
    return [(points[i],points[(i+1)%len(points)]) for i in range(len(points))]

class FieldEdgePreview(FloatLayout):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.edges=[]
        self.selection=("edge-0","edge-1","edge-2")
        self.bind(pos=self.redraw,size=self.redraw)

    def set_boundary(self,boundary):
        self.edges=boundary_edges(boundary)
        self.redraw()

    def set_selection(self,alignment,start_a,start_b):
        self.selection=(alignment,start_a,start_b)
        self.redraw()

    def redraw(self,*_):
        self.canvas.before.clear()
        self.clear_widgets()
        if not self.edges or self.width<=0 or self.height<=0:
            return
        points=[p for edge in self.edges for p in edge]
        # Feldpunkte sind [Längengrad, Breitengrad]; Ost-West für die
        # Skizze anhand der mittleren geografischen Breite skalieren.
        lat0=sum(p[1] for p in points)/len(points)
        factor=max(.05,abs(cos(radians(lat0))))
        xs=[p[0]*factor for p in points]
        ys=[p[1] for p in points]
        xmin,xmax=min(xs),max(xs)
        ymin,ymax=min(ys),max(ys)
        margin=dp(39)
        w=max(1,self.width-2*margin)
        h=max(1,self.height-2*margin)
        scale=min(w/max(xmax-xmin,1e-9),h/max(ymax-ymin,1e-9))
        cx=self.x+self.width/2
        cy=self.y+self.height/2
        def project(p):
            return (cx+(p[0]*factor-(xmin+xmax)/2)*scale,
                    cy+(p[1]-(ymin+ymax)/2)*scale)
        with self.canvas.before:
            Color(.07,.12,.1,1)
            Rectangle(pos=self.pos,size=self.size)
            for i,(a,b) in enumerate(self.edges):
                key=f"edge-{i}"
                selected=key in self.selection
                if key==self.selection[0]:
                    Color(.2,.65,1,1)
                elif key==self.selection[1]:
                    Color(1,.7,.2,1)
                elif key==self.selection[2]:
                    Color(.9,.4,.7,1)
                else:
                    Color(.55,.83,.62,1)
                x1,y1=project(a);x2,y2=project(b)
                Line(points=[x1,y1,x2,y2],width=dp(3.5 if selected else 2))
        for i,(a,b) in enumerate(self.edges):
            x1,y1=project(a);x2,y2=project(b)
            label=Label(text=str(i),font_size="16sp",bold=True,
                        size_hint=(None,None),size=(dp(35),dp(35)),
                        color=(1,1,1,1))
            label.center=(.5*(x1+x2),.5*(y1+y2))
            self.add_widget(label)

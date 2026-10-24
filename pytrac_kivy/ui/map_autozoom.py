"""Berechnet eine Karten-Zoomstufe für eine Feldgrenze ohne Kivy-Abhängigkeit."""
import math

def fit_field_zoom(field, width_px, height_px, min_zoom=3, max_zoom=20, padding=0.78):
    boundary=(field or {}).get("boundary") or []
    if isinstance(boundary,dict):
        typ=boundary.get("type")
        coords=boundary.get("coordinates") or []
        rings=coords if typ=="Polygon" else [r for poly in coords for r in poly] if typ=="MultiPolygon" else []
    elif isinstance(boundary,list):
        rings=[boundary]
    else:
        rings=[]
    pts=[]
    for ring in rings:
        for point in ring:
            try:
                lon,lat=float(point[0]),float(point[1])
                if math.isfinite(lon) and math.isfinite(lat) and -180<=lon<=180 and -85<=lat<=85:
                    pts.append((lon,lat))
            except (ValueError,TypeError,IndexError):
                continue
    if len(pts)<2 or width_px<=0 or height_px<=0:
        return None
    xs=[(lon+180)/360 for lon,_ in pts]
    ys=[(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2 for _,lat in pts]
    span_x=max(xs)-min(xs)
    span_y=max(ys)-min(ys)
    if span_x==0 and span_y==0:return None
    available_x=max(1,width_px*padding)
    available_y=max(1,height_px*padding)
    required=max(span_x*256/available_x,span_y*256/available_y,1e-12)
    zoom=math.floor(-math.log2(required))
    return max(min_zoom,min(max_zoom,zoom))

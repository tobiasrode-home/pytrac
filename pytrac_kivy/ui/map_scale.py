"""Maßstab für Symbole anhand der aktuellen MapView-Projektion."""
import math

def meters_to_pixels(map_view, latitude, longitude, meters):
    """Projizierte Pixelgröße einer Nord-Süd-Distanz am aktuellen Zoom."""
    if not all(math.isfinite(float(v)) for v in (latitude,longitude,meters)):
        return 0.0
    if meters<=0:return 0.0
    delta_lat=math.degrees(float(meters)/6378137.0)
    x0,y0=map_view.get_window_xy_from(float(latitude),float(longitude),map_view.zoom)
    x1,y1=map_view.get_window_xy_from(float(latitude)+delta_lat,float(longitude),map_view.zoom)
    return math.hypot(x1-x0,y1-y0)

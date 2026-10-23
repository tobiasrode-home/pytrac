"""Fahrtrichtung gegenüber der Spur aus dem gültigen IMU-Kurs ableiten."""
from math import atan2, cos, degrees, radians, sin


def is_reverse_to_track(heading_deg, coordinates, heading_valid=True):
    """False bei fehlendem Kurs: keine erfundene Umkehrung."""
    if not heading_valid or heading_deg is None or not coordinates or len(coordinates) < 2:
        return False
    a, b = coordinates[0], coordinates[-1]
    dx = (float(b[0])-float(a[0]))*cos(radians((float(a[1])+float(b[1]))/2))
    dy = float(b[1])-float(a[1])
    if abs(dx)+abs(dy) < 1e-12:
        return False
    track_heading = (degrees(atan2(dx,dy))+360) % 360
    delta = (float(heading_deg)-track_heading+180)%360-180
    return abs(delta)>90

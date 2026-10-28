"""Positionskorrektur: Antenne -> Traktormitte auf Bodenhöhe.

Koordinatensystem Fahrzeug: x nach vorn, y nach rechts, z nach oben.
Heading: 0° Norden, 90° Osten. Roll positiv: rechte Seite sinkt.
Pitch positiv: Fahrzeugnase steigt. Alle Abstände in Metern.
"""
from math import cos, sin, radians, degrees, asin, isfinite

EARTH_RADIUS_M = 6378137.0

def move_position(latitude, longitude, east_m, north_m):
    lat=float(latitude); lon=float(longitude)
    scale=EARTH_RADIUS_M*cos(radians(lat))
    if abs(scale)<1.0:
        raise ValueError("Positionskorrektur nahe den Polen nicht unterstützt")
    return (lat+degrees(north_m/EARTH_RADIUS_M),
            lon+degrees(east_m/scale))

def compensate_antenna(latitude, longitude, heading_deg, pitch_deg, roll_deg,
                       offset_forward_m=0.0, offset_right_m=0.0, height_m=0.0):
    """Gibt Traktormitte am Boden zurück; IMU-Winkel müssen kalibriert sein.

    Die Position des Antennenvektors relativ zur Traktormitte wird zunächst
    mit Roll (um x), Pitch (um y) und anschließend Heading (um z) gedreht.
    """
    values=(latitude,longitude,heading_deg,pitch_deg,roll_deg,
            offset_forward_m,offset_right_m,height_m)
    if not all(isfinite(float(v)) for v in values):
        raise ValueError("Nicht endliche GPS-/IMU-/Antennenwerte")
    x=float(offset_forward_m); y=float(offset_right_m); z=float(height_m)
    roll=radians(float(roll_deg))
    pitch=radians(float(pitch_deg))
    heading=radians(float(heading_deg))
    # Roll positiv: rechte Seite tiefer; y-Rechts-Achse dreht nach unten.
    y1=y*cos(roll)+z*sin(roll)
    z1=-y*sin(roll)+z*cos(roll)
    x2=x*cos(pitch)-z1*sin(pitch)
    y2=y1
    # x2 nach vorne, y2 nach rechts -> Ost/Nord
    east=x2*sin(heading)+y2*cos(heading)
    north=x2*cos(heading)-y2*sin(heading)
    return move_position(latitude,longitude,-east,-north)

def rear_implement_edge(latitude,longitude,heading_deg,tractor_length_m,
                        implement_length_m,mount_type='rear',work_offset_m=0.0):
    """Hinterkante des Anbaugeräts bei Vorwärtsfahrt; Länge ab Traktorheck.

    Bei front/towed sind Geometrieannahmen nicht gesichert.
    """
    if mount_type!='rear':
        raise ValueError("Nur Heckanbau unterstützt; Geometrie für andere Montage unbekannt")
    rear_distance=float(tractor_length_m)/2+float(implement_length_m)
    if rear_distance<=0:raise ValueError("Ungültige Fahrzeug-/Gerätelänge")
    h=radians(float(heading_deg))
    east=-rear_distance*sin(h)+float(work_offset_m)*cos(h)
    north=-rear_distance*cos(h)-float(work_offset_m)*sin(h)
    return move_position(latitude,longitude,east,north)

"""Abstand zum Geräte-Stopp in Metern und Zentimetern."""
from math import hypot
from pytrac_kivy.ui.guidance_navigation import xy

def stop_distance_text(distance_m):
    if distance_m is None:
        return "Entfernung unbekannt"
    distance_m = max(0.0, float(distance_m))
    if distance_m >= 1:
        return f"Noch {distance_m:.2f} m bis zum Stopppunkt"
    return f"Noch {round(distance_m * 100):d} cm bis zum Stopppunkt"

def signed_distance_to_stop(position, target, track_coordinates):
    """Vorzeichen entlang der Spur: positiv = noch vor dem Ziel, negativ = vorbei."""
    if not track_coordinates or len(track_coordinates) < 2:
        return None
    # Richtungsvektor am zum Ziel nächstliegenden Segment.
    best = None
    for a, b in zip(track_coordinates, track_coordinates[1:]):
        ax, ay = xy(a, target)
        bx, by = xy(b, target)
        dx, dy = bx-ax, by-ay
        length = hypot(dx, dy)
        if length < 1e-6: continue
        t = max(0, min(1, -(ax*dx+ay*dy)/(length*length)))
        distance = hypot(ax+t*dx, ay+t*dy)
        if best is None or distance < best[0]:
            best = (distance, dx/length, dy/length)
    if best is None: return None
    px, py = xy(position, target)
    return -(px*best[1]+py*best[2])

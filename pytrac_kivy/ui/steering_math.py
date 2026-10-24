"""Richtung und Stärke der manuellen Lenkempfehlung."""
from math import isfinite

def correction_from_offset(signed_offset_m, reverse=False, full_scale_m=.75):
    if not isfinite(float(signed_offset_m)) or full_scale_m <= 0:
        raise ValueError('Ungültige Spurabweichung')
    signed = -float(signed_offset_m) if reverse else float(signed_offset_m)
    return max(-1., min(1., signed/full_scale_m))

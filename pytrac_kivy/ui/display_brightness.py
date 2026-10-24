"""Helligkeit über Linux-backlight-sysfs, z.B. Raspberry Pi Touch Display 2."""
from pathlib import Path

BACKLIGHT_ROOT = Path("/sys/class/backlight")

def available_backlights(root=BACKLIGHT_ROOT):
    try:
        return [p for p in root.iterdir() if p.is_dir() and
                (p / "brightness").exists() and (p / "max_brightness").exists()]
    except OSError:
        return []

def choose_backlight(root=BACKLIGHT_ROOT):
    devices = available_backlights(root)
    if not devices:
        return None
    return next((p for p in devices if "rpi" in p.name.lower() or "touch" in p.name.lower()),devices[0])

def read_brightness(root=BACKLIGHT_ROOT):
    device=choose_backlight(root)
    if device is None:
        return None
    try:
        maximum=int((device/"max_brightness").read_text().strip())
        current=int((device/"brightness").read_text().strip())
        if maximum<=0:
            return None
        return round(100*current/maximum)
    except (OSError,ValueError):
        return None

def set_brightness(percent,root=BACKLIGHT_ROOT):
    device=choose_backlight(root)
    if device is None:
        raise RuntimeError("Keine regelbare Displaybeleuchtung gefunden.")
    try:
        maximum=int((device/"max_brightness").read_text().strip())
        if maximum<=0:raise ValueError("Ungültiger Maximalwert")
        # Nicht komplett abschalten: sonst ist der Touchscreen schwer bedienbar.
        value=max(1,round(max(10,min(100,float(percent)))*maximum/100))
        (device/"brightness").write_text(str(value))
    except PermissionError as exc:
        raise RuntimeError("Keine Schreibrechte für die Displayhelligkeit.") from exc
    except OSError as exc:
        raise RuntimeError("Displayhelligkeit konnte nicht gesetzt werden: "+str(exc)) from exc

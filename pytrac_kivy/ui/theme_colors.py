"""Zentrale, frei anpassbare RGBA-Farben (0.0 bis 1.0) für PyTrac-Menüs.

Nach Änderungen die Kivy-Oberfläche vollständig neu starten.
Die 2D-Navigation, Lenkhilfe und fachlichen Statusfarben bleiben separat.
"""
DARK = {
    "window": (0.06, 0.07, 0.09, 1),
    "text": (1, 1, 1, 1),
    "button": (0.16, 0.43, 0.28, 1),
    "button_text": (1, 1, 1, 1),
    "input": (0.14, 0.17, 0.20, 1),
    "input_text": (1, 1, 1, 1),
    "popup": (0.10, 0.12, 0.15, 1),
    "popup_title": (1, 1, 1, 1),
    "popup_separator": (0.30, 0.60, 0.40, 1),
}
LIGHT = {
    "window": (0.95, 0.96, 0.98, 1),
    "text": (0.08, 0.13, 0.19, 1),
    "button": (0.75, 0.83, 0.90, 1),
    "button_text": (0.08, 0.13, 0.19, 1),
    "input": (1, 1, 1, 1),
    "input_text": (0.08, 0.13, 0.19, 1),
    "popup": (0.96, 0.97, 0.99, 1),
    "popup_title": (0.08, 0.13, 0.19, 1),
    "popup_separator": (0.45, 0.58, 0.69, 1),
}

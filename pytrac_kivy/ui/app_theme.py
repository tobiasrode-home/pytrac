"""Central light/dark palette for PyTrac menus and their transient dialogs.

The dashboard's precision drawing and steering indicator manage their own theme.
Do not replace their canvas instructions here.
"""
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner

DARK_BG = (0.06, 0.07, 0.09, 1)
LIGHT_BG = (0.95, 0.96, 0.98, 1)
LIGHT_TEXT = (0.08, 0.13, 0.19, 1)
LIGHT_BUTTON = (0.75, 0.83, 0.90, 1)


def apply_theme(root, dark):
    """Apply colors to menu widgets, including widgets added after initial load.

    The original dark colors are captured once per widget and restored exactly.
    """
    Window.clearcolor = DARK_BG if dark else LIGHT_BG
    if root is None:
        return

    def walk(widget):
        module = widget.__class__.__module__
        name = widget.__class__.__name__
        # These widgets render their own meaningful graphics and status colors.
        if (name in ('Precision2D', 'Precision2DWidget', 'SteeringIndicator')
                or 'precision_2d' in module or 'steering_bar' in module):
            return
        if not hasattr(widget, '_pytrac_theme_original'):
            original = {}
            for attr in ('color', 'background_color', 'foreground_color',
                         'cursor_color', 'selection_color'):
                if hasattr(widget, attr):
                    try:
                        original[attr] = tuple(getattr(widget, attr))
                    except (TypeError, ValueError):
                        pass
            widget._pytrac_theme_original = original

        original = widget._pytrac_theme_original
        if dark:
            for attr, value in original.items():
                setattr(widget, attr, value)
        elif isinstance(widget, (Button, Spinner)):
            widget.background_color = LIGHT_BUTTON
            widget.color = LIGHT_TEXT
        elif isinstance(widget, TextInput):
            widget.background_color = (1, 1, 1, 1)
            widget.foreground_color = LIGHT_TEXT
            widget.cursor_color = LIGHT_TEXT
        elif isinstance(widget, Label):
            widget.color = LIGHT_TEXT
        for child in widget.children:
            walk(child)

    walk(root)

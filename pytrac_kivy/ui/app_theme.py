"""Kivy widget theme. Preserve the existing dark palette exactly.

Never modify the canvas or children of Precision2D; its colors encode guidance.
"""
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.slider import Slider
from kivy.uix.switch import Switch


def apply_theme(root, dark):
    Window.clearcolor = (0.06, 0.07, 0.09, 1) if dark else (0.95, 0.96, 0.98, 1)
    def walk(widget):
        if widget.__class__.__name__ in ('Precision2D', 'Precision2DWidget') or 'precision_2d' in widget.__class__.__module__:
            return
        if not hasattr(widget, '_pytrac_theme_original'):
            original={}
            for name in ('color','background_color','foreground_color','cursor_color','selection_color'):
                if hasattr(widget,name):
                    try: original[name]=tuple(getattr(widget,name))
                    except (TypeError,ValueError): pass
            widget._pytrac_theme_original=original
        orig=widget._pytrac_theme_original
        if dark:
            for name,value in orig.items():
                setattr(widget,name,value)
        else:
            if isinstance(widget, Button):
                widget.background_color=(0.75,0.83,0.90,1)
                widget.color=(0.08,0.13,0.19,1)
            elif isinstance(widget, TextInput):
                widget.background_color=(1,1,1,1)
                widget.foreground_color=(0.08,0.13,0.19,1)
                widget.cursor_color=(0.08,0.13,0.19,1)
            elif isinstance(widget, Label):
                widget.color=(0.08,0.13,0.19,1)
        for child in widget.children:
            walk(child)
    walk(root)

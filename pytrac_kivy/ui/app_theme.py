"""PyTrac Menü-Theme: Popups bereits VOR dem Öffnen einfärben."""
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle
from pytrac_kivy.ui.theme_colors import DARK, LIGHT

_dark = True
_original_open = None

def _skip(widget):
    cls = widget.__class__
    return (cls.__name__ in ('Precision2D', 'Precision2DWidget', 'SteeringIndicator')
            or 'precision_2d' in cls.__module__ or 'steering_bar' in cls.__module__)

def _paint_popup(popup, palette):
    # Kivy Popup/ModalView nutzt eine eigene Hintergrundgrafik.
    # Mit einem weißen Textur-Pixel wird background_color tatsächlich sichtbar.
    try:
        popup.background = 'atlas://data/images/defaulttheme/modalview-background'
        popup.background_color = palette['popup']
    except Exception:
        pass
    for attr, key in (('title_color','popup_title'),('separator_color','popup_separator')):
        if hasattr(popup,attr):
            setattr(popup,attr,palette[key])

def apply_theme(root, dark):
    global _dark
    _dark=bool(dark)
    palette=DARK if _dark else LIGHT
    Window.clearcolor=palette['window']
    if root is None: return
    def walk(widget):
        if _skip(widget): return
        if isinstance(widget, Popup): _paint_popup(widget,palette)
        if not hasattr(widget,'_pytrac_theme_original'):
            original={}
            for attr in ('color','background_color','foreground_color','cursor_color','selection_color'):
                if hasattr(widget,attr):
                    try: original[attr]=tuple(getattr(widget,attr))
                    except (TypeError,ValueError): pass
            widget._pytrac_theme_original=original
        orig=widget._pytrac_theme_original
        if _dark:
            # Bewahrt die existierenden individuellen Darkmode-Farben.
            for attr,value in orig.items(): setattr(widget,attr,value)
        elif isinstance(widget,(Button,Spinner)):
            widget.background_color=palette['button']
            widget.color=palette['button_text']
        elif isinstance(widget,TextInput):
            widget.background_color=palette['input']
            widget.foreground_color=palette['input_text']
            widget.cursor_color=palette['input_text']
        elif isinstance(widget,Label):
            widget.color=palette['text']
        for child in widget.children: walk(child)
    walk(root)

def install_popup_theme():
    """Einmalig installieren: Popup.open() färbt vor dem ersten Frame ein."""
    global _original_open
    if _original_open is not None: return
    _original_open=Popup.open
    def themed_open(self,*args,**kwargs):
        apply_theme(self,_dark)
        # Beim Öffnen ist der Popup-Inhalt vollständig vorhanden; keine Verzögerung.
        return _original_open(self,*args,**kwargs)
    Popup.open=themed_open

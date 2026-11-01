"""Central PyTrac UI theme, applied before widgets become visible.

2D drawing and steering-bar graphics deliberately manage their own colors.
"""
from pathlib import Path
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.modalview import ModalView
from pytrac_kivy.ui.theme_colors import DARK, LIGHT

_dark = True
_original_modal_open = None
_WHITE = str(Path(__file__).with_name('popup_white.png'))


def _skip(widget):
    cls = widget.__class__
    return (cls.__name__ in ('Precision2D', 'Precision2DWidget', 'SteeringIndicator')
            or 'precision_2d' in cls.__module__ or 'steering_bar' in cls.__module__)


def _style_modal(widget, palette):
    # The Kivy atlas background is intrinsically dark; tinting it white is not enough.
    if Path(_WHITE).is_file():
        widget.background = _WHITE
        widget.border = (0, 0, 0, 0)
    widget.background_color = palette['popup']
    if isinstance(widget, Popup):
        widget.title_color = palette['popup_title']
        widget.separator_color = palette['popup_separator']


def apply_theme(root, dark):
    global _dark
    _dark = bool(dark)
    palette = DARK if _dark else LIGHT
    Window.clearcolor = palette['window']
    if root is None:
        return
    def visit(widget):
        if _skip(widget):
            return
        if not hasattr(widget, '_pytrac_theme_original'):
            original = {}
            for attr in ('color', 'background_color', 'foreground_color', 'cursor_color'):
                if hasattr(widget, attr):
                    try:
                        original[attr] = tuple(getattr(widget, attr))
                    except (TypeError, ValueError):
                        pass
            widget._pytrac_theme_original = original
        if isinstance(widget, ModalView):
            _style_modal(widget, palette)
        if isinstance(widget, (Button, Spinner)):
            widget.background_normal = ''
            widget.background_down = ''
            selected = bool(getattr(widget, '_pytrac_brightness_selected', False))
            widget.background_color = palette['selected_button'] if selected else palette['button']
            widget.color = palette['selected_button_text'] if selected else palette['button_text']
        elif isinstance(widget, TextInput):
            widget.background_color = palette['input']
            widget.foreground_color = palette['input_text']
            widget.cursor_color = palette['input_text']
        elif isinstance(widget, Label):
            widget.color = palette['text']
        for child in list(widget.children):
            visit(child)
    visit(root)


def install_popup_theme():
    """Theme any Popup/ModalView synchronously, before the first visible frame."""
    global _original_modal_open
    if _original_modal_open is not None:
        return
    _original_modal_open = ModalView.open
    def themed_open(self, *args, **kwargs):
        apply_theme(self, _dark)
        return _original_modal_open(self, *args, **kwargs)
    ModalView.open = themed_open

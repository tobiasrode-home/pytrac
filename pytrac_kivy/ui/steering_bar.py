"""Visuelle Lenkhilfe für manuelle Geradeaus-Spurführung (keine Steuerbefehle)."""
from pytrac_kivy.ui.steering_math import correction_from_offset
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout




class SteeringIndicator(Widget):
    """Ein Balken, der vom Mittelpunkt in die benötigte Lenkrichtung ausschlägt."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.correction = None
        self.bind(pos=self._draw, size=self._draw)

    def set_correction(self, correction):
        self.correction = correction
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        x, y = self.pos
        w, h = self.size
        if w < 1 or h < 1:
            return
        cy = y + h / 2
        margin = dp(14)
        usable = max(1., w - 2 * margin)
        with self.canvas:
            Color(.12, .15, .15, 1)
            RoundedRectangle(pos=(x, y + dp(6)), size=(w, h - dp(12)), radius=[dp(9)])
            Color(.35, .38, .38, 1)
            Rectangle(pos=(x + margin, cy - dp(1)), size=(usable, dp(2)))
            Color(.9, .9, .9, 1)
            Rectangle(pos=(x + w/2 - dp(1), y + dp(8)), size=(dp(2), h - dp(16)))
            if self.correction is not None:
                amount = max(-1., min(1., float(self.correction)))
                width = abs(amount) * usable / 2
                Color((.2, .85, .35, 1) if abs(amount) < .08 else (.98, .68, .16, 1))
                Rectangle(pos=(x + w/2 + min(0., amount * usable / 2), cy - dp(7)),
                          size=(max(dp(2), width), dp(14)))


class SteeringBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=dp(1), **kwargs)
        self.label = Label(text='Lenkhilfe: kein GPS / keine Spur', size_hint_y=None,
                           height=dp(22), font_size='15sp', bold=True)
        self.indicator = SteeringIndicator()
        # Text nicht mehr als eigene Zeile anzeigen; Wert steht im 2D-HUD.
        self.add_widget(self.indicator)

    def update(self, signed_offset_m=None, reverse=False):
        if signed_offset_m is None:
            self.indicator.set_correction(None)
            self.label.text = 'Lenkhilfe: kein GPS / keine Spur'
            return
        try:
            correction = correction_from_offset(signed_offset_m, reverse)
        except (ValueError, TypeError, OverflowError):
            self.update(None)
            return
        self.indicator.set_correction(correction)
        distance = abs(float(signed_offset_m))
        if distance < .06:
            self.label.text = f'Ideallinie · {distance:.2f} m'
        else:
            self.label.text = f'{"LINKS" if correction < 0 else "RECHTS"} korrigieren · {distance:.2f} m'

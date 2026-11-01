"""Visuelle Lenkhilfe, ohne Eingriff in die Spurführung oder das Layout."""
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from pytrac_kivy.ui.steering_math import correction_from_offset


class SteeringIndicator(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dark_mode = True
        self.correction = None
        # Separate color instruction: never rely on the color left by another draw.
        with self.canvas:
            self._background_color = Color(0.12, 0.15, 0.15, 1)
            self._background = RoundedRectangle(radius=[dp(9)])
            self._track_color = Color(.35, .38, .38, 1)
            self._track = Rectangle()
            self._center_color = Color(.9, .9, .9, 1)
            self._center = Rectangle()
            self._deflection_color = Color(1, 1, 1, 1)
            self._deflection = Rectangle(size=(0, 0))
        self.bind(pos=self._draw, size=self._draw)
        self._draw()

    def set_dark_mode(self, dark):
        self.dark_mode = bool(dark)
        self._draw()

    def set_correction(self, correction):
        self.correction = correction
        self._draw()

    def _draw(self, *_):
        x, y = self.pos
        w, h = self.size
        if self.dark_mode:
            self._background_color.rgba = (.12, .15, .15, 1)
            self._track_color.rgba = (.35, .38, .38, 1)
            self._center_color.rgba = (.9, .9, .9, 1)
            self._deflection_color.rgba = (1, 1, 1, 1)
        else:
            self._background_color.rgba = (1, 1, 1, 1)
            self._track_color.rgba = (.72, .75, .78, 1)
            self._center_color.rgba = (0, 0, 0, 1)
            self._deflection_color.rgba = (0, 0, 0, 1)
        if w < 1 or h < 1:
            self._deflection.size = (0, 0)
            return
        cy = y + h / 2
        margin = dp(14)
        usable = max(1., w - 2 * margin)
        self._background.pos = (x, y + dp(6))
        self._background.size = (w, max(0, h - dp(12)))
        self._track.pos = (x + margin, cy - dp(1))
        self._track.size = (usable, dp(2))
        self._center.pos = (x + w/2 - dp(1), y + dp(8))
        self._center.size = (dp(2), max(0, h - dp(16)))
        if self.correction is None:
            self._deflection.size = (0, 0)
            return
        amount = max(-1., min(1., float(self.correction)))
        width = abs(amount) * usable / 2
        self._deflection.pos = (x + w/2 + min(0., amount * usable / 2), cy - dp(7))
        self._deflection.size = (max(dp(2), width), dp(14))


class SteeringBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=dp(1), **kwargs)
        self.label = Label(text='Lenkhilfe: kein GPS / keine Spur', size_hint_y=None,
                           height=dp(22), font_size='15sp', bold=True)
        self.indicator = SteeringIndicator()
        self.add_widget(self.indicator)

    def set_dark_mode(self, dark):
        self.indicator.set_dark_mode(dark)
        self.label.color = (1, 1, 1, 1) if dark else (0, 0, 0, 1)

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

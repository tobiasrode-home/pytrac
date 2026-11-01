"""Eigenstaendige Sensor-Einstellungsseite von PyTrac (Datenbank via Backend-API)."""
import math
import threading
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from pytrac_kivy.ui.fullscreen_keyboard import bind_fullscreen_keyboard


class SensorScreen(BoxLayout):
    def __init__(self, api_client=None, on_back=None, on_navigation_settings=None, **kwargs):
        super().__init__(orientation='vertical', padding=dp(14), spacing=dp(10), **kwargs)
        self.api_client = api_client
        self.on_back = on_back
        self.on_navigation_settings = on_navigation_settings
        self._request_serial = 0
        self._saving = False
        header = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        header.add_widget(Label(text='[b]Sensoren[/b]', markup=True, font_size='25sp'))
        header.add_widget(self._button('Zurück', lambda *_: self.go_back(), width=dp(180)))
        self.add_widget(header)
        self.add_widget(Label(text='BNO085 – Einbaulage', bold=True, font_size='20sp',
                              size_hint_y=None, height=dp(38)))
        self.add_widget(Label(text='Offsets werden dauerhaft über das Backend in tractor.db gespeichert.\n'
                              'Die Werte werden nach dem Speichern direkt an die Anzeige übergeben.',
                              size_hint_y=None, height=dp(60)))
        self.heading_offset_input = TextInput(text='0', multiline=False, input_filter=None,
                                              size_hint_y=None, height=dp(48))
        self.roll_offset_input = TextInput(text='0', multiline=False, input_filter=None,
                                           size_hint_y=None, height=dp(48))
        bind_fullscreen_keyboard(self.heading_offset_input, 'Ausrichtungs-Offset in Grad')
        bind_fullscreen_keyboard(self.roll_offset_input, 'Neigungs-Offset in Grad (Roll)')
        for title, field in [('Ausrichtung / Yaw (°)', self.heading_offset_input),
                             ('Neigung / Roll (°)', self.roll_offset_input)]:
            row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
            row.add_widget(Label(text=title, size_hint_x=.48))
            row.add_widget(field)
            self.add_widget(row)
        self.status_label = Label(text='', size_hint_y=None, height=dp(42))
        self.add_widget(self.status_label)
        self.add_widget(BoxLayout(size_hint_y=1))
        self.save_button = self._button('In Datenbank speichern', lambda *_: self.save(), height=dp(54))
        self.add_widget(self.save_button)
        self.add_widget(self._button('Gespeicherte Werte neu laden', lambda *_: self.load(), height=dp(48)))

    @staticmethod
    def _button(text, callback, height=dp(52), width=None):
        button = Button(text=text, size_hint_y=None, height=height, background_normal='',
                        background_down='', background_color=(.16, .43, .28, 1),
                        color=(1, 1, 1, 1), font_size='17sp')
        if width is not None:
            button.size_hint_x = None
            button.width = width
        button.bind(on_release=callback)
        return button

    def go_back(self):
        if self.on_back:
            self.on_back()

    def load(self):
        if self.api_client is None:
            self.status_label.text = 'API-Client nicht verfügbar'
            return
        self._request_serial += 1
        request_id = self._request_serial
        self.status_label.text = 'Sensorwerte werden geladen …'
        def worker():
            try:
                data = self.api_client.get('/api/navigation-settings')
                if hasattr(data, 'json'):
                    data = data.json()
                if not isinstance(data, dict):
                    raise ValueError('Ungültige Antwort des Backends')
                Clock.schedule_once(lambda _dt, d=data, n=request_id: self._loaded(d, n))
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(lambda _dt, m=message, n=request_id: self._error(m, n))
        threading.Thread(target=worker, daemon=True).start()

    def _loaded(self, data, request_id):
        if request_id != self._request_serial:
            return
        self.heading_offset_input.text = str(data.get('imu_heading_offset_deg', 0.0))
        self.roll_offset_input.text = str(data.get('imu_roll_offset_deg', 0.0))
        self.status_label.text = 'Werte aus Datenbank geladen'
        if self.on_navigation_settings:
            self.on_navigation_settings(dict(data))

    def _error(self, message, request_id):
        if request_id == self._request_serial:
            self.status_label.text = 'Fehler: ' + message

    def save(self):
        if self._saving:
            return
        try:
            heading = float(self.heading_offset_input.text.replace(',', '.'))
            roll = float(self.roll_offset_input.text.replace(',', '.'))
            if not math.isfinite(heading) or not -180 <= heading <= 180:
                raise ValueError('Yaw muss zwischen -180° und +180° liegen')
            if not math.isfinite(roll) or not -45 <= roll <= 45:
                raise ValueError('Roll muss zwischen -45° und +45° liegen')
        except ValueError as exc:
            self.status_label.text = str(exc)
            return
        if self.api_client is None:
            self.status_label.text = 'API-Client nicht verfügbar'
            return
        self._request_serial += 1
        request_id = self._request_serial
        self._saving = True
        self.save_button.disabled = True
        self.status_label.text = 'Speichere …'
        payload = {'imu_heading_offset_deg': heading, 'imu_roll_offset_deg': roll}
        def worker():
            try:
                data = self.api_client.put('/api/navigation-settings', payload)
                if hasattr(data, 'json'):
                    data = data.json()
                if not isinstance(data, dict):
                    raise ValueError('Ungültige Antwort des Backends')
                Clock.schedule_once(lambda _dt, d=data, n=request_id: self._saved(d, n))
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(lambda _dt, m=message, n=request_id: self._save_failed(m, n))
        threading.Thread(target=worker, daemon=True).start()

    def _saved(self, data, request_id):
        self._saving = False
        self.save_button.disabled = False
        self._loaded(data, request_id)
        if request_id == self._request_serial:
            self.status_label.text = 'Sensor-Offsets in Datenbank gespeichert'

    def _save_failed(self, message, request_id):
        self._saving = False
        self.save_button.disabled = False
        self._error('Speichern fehlgeschlagen: ' + message, request_id)

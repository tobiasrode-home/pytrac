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
        self._poll_event = None
        self._poll_busy = False
        self._latest_imu = None
        header = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        header.add_widget(Label(text='[b]Sensoren[/b]', markup=True, font_size='25sp'))
        header.add_widget(self._button('Zurück', lambda *_: self.go_back(), width=dp(180)))
        self.add_widget(header)
        self.add_widget(Label(text='ZED-F9P – aktuelle GPS-Werte', bold=True, font_size='20sp', size_hint_y=None, height=dp(35)))
        self.gps_live = Label(text='Warte auf GPS-Daten …', size_hint_y=None, height=dp(104), halign='left', valign='middle')
        self.gps_live.bind(size=lambda obj, _val: setattr(obj, 'text_size', obj.size))
        self.add_widget(self.gps_live)
        self.add_widget(Label(text='BNO085 – aktuelle IMU-Werte (unkorrigiert)', bold=True, font_size='20sp', size_hint_y=None, height=dp(35)))
        self.imu_live = Label(text='Warte auf IMU-Daten …', size_hint_y=None, height=dp(76), halign='left', valign='middle')
        self.imu_live.bind(size=lambda obj, _val: setattr(obj, 'text_size', obj.size))
        self.add_widget(self.imu_live)
        self.add_widget(self._button('Aktuelle IMU-Lage als Nullstellung speichern', lambda *_: self.save_current_zero(), height=dp(54)))
        self.add_widget(Label(text='BNO085 – Einbaulage', bold=True, font_size='20sp',
                              size_hint_y=None, height=dp(38)))
        self.add_widget(Label(text='Offsets werden dauerhaft über das Backend in tractor.db gespeichert.\n'
                              'Die Werte werden nach dem Speichern direkt an die Anzeige übergeben.',
                              size_hint_y=None, height=dp(60)))
        self.heading_offset_input = TextInput(text='0', multiline=False, input_filter=None,
                                              size_hint_y=None, height=dp(48))
        self.pitch_offset_input = TextInput(text='0', multiline=False, size_hint_y=None, height=dp(48))
        self.roll_offset_input = TextInput(text='0', multiline=False, input_filter=None,
                                           size_hint_y=None, height=dp(48))
        bind_fullscreen_keyboard(self.heading_offset_input, 'Ausrichtungs-Offset in Grad')
        bind_fullscreen_keyboard(self.pitch_offset_input, 'Pitch-Offset in Grad')
        bind_fullscreen_keyboard(self.roll_offset_input, 'Neigungs-Offset in Grad (Roll)')
        for title, field in [('Ausrichtung / Yaw (°)', self.heading_offset_input),
                             ('Neigung / Roll (°)', self.roll_offset_input),
                             ('Neigung / Pitch (°)', self.pitch_offset_input)]:
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
        self.pitch_offset_input.text = str(data.get('imu_pitch_offset_deg', 0.0))
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
            pitch = float(self.pitch_offset_input.text.replace(',', '.'))
            if not math.isfinite(heading) or not -180 <= heading <= 180:
                raise ValueError('Yaw muss zwischen -180° und +180° liegen')
            if not math.isfinite(pitch) or not -90 <= pitch <= 90:
                raise ValueError('Pitch muss zwischen -90° und +90° liegen')
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
        payload = {'imu_heading_offset_deg': heading, 'imu_roll_offset_deg': roll, 'imu_pitch_offset_deg': pitch}
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

    def start_live(self):
        self.stop_live()
        self._poll_event = Clock.schedule_interval(self._poll, 1.0)
        self._poll(0)

    def stop_live(self):
        if self._poll_event is not None:
            self._poll_event.cancel()
            self._poll_event = None

    def _poll(self, _dt):
        if self._poll_busy or self.api_client is None:
            return
        self._poll_busy = True
        def worker():
            try:
                data = self.api_client.get('/api/vehicle/state')
                if hasattr(data, 'json'):
                    data = data.json()
                if not isinstance(data, dict):
                    raise ValueError('Ungültiger Sensorstatus')
                Clock.schedule_once(lambda _dt, d=data: self._show_live(d))
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(lambda _dt, m=message: self._live_error(m))
            finally:
                Clock.schedule_once(lambda _dt: setattr(self, '_poll_busy', False))
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _fmt(value, digits=2):
        try:
            return f'{float(value):.{digits}f}' if value is not None else '—'
        except (TypeError, ValueError):
            return '—'

    def _show_live(self, data):
        quality = {4:'RTK FIXED', 5:'RTK FLOAT', 2:'DGPS', 1:'GNSS'}.get(data.get('gps_fix_quality'), 'Unbekannt')
        self.gps_live.text = (
            f"Status: {quality} | gültig: {'Ja' if data.get('gps_valid') else 'Nein'}\n"
            f"Breite: {self._fmt(data.get('latitude'), 8)}°    Länge: {self._fmt(data.get('longitude'), 8)}°\n"
            f"Höhe: {self._fmt(data.get('altitude_m'))} m    Tempo: {self._fmt(data.get('speed_mps'))} m/s")
        self.imu_live.text = (
            f"Gültig: {'Ja' if data.get('imu_valid') else 'Nein'}\n"
            f"Yaw: {self._fmt(data.get('heading_deg'))}°    "
            f"Pitch: {self._fmt(data.get('pitch_deg'))}°    "
            f"Roll: {self._fmt(data.get('roll_deg'))}°")
        self._latest_imu = (dict(data) if data.get('imu_valid') and all(
            isinstance(data.get(k), (int, float)) and math.isfinite(data[k])
            for k in ('heading_deg', 'pitch_deg', 'roll_deg')) else None)

    def _live_error(self, message):
        self.gps_live.text = 'Sensorstatus nicht verfügbar: ' + message
        self._latest_imu = None

    def save_current_zero(self):
        if self._latest_imu is None:
            self.status_label.text = 'Keine gültigen aktuellen IMU-Werte vorhanden'
            return
        data = self._latest_imu
        # Offset = -Rohwert. Das Backend liefert hier unkompensierte Sensorwinkel.
        heading = -float(data['heading_deg'])
        heading = (heading + 180) % 360 - 180
        pitch = -float(data['pitch_deg'])
        roll = -float(data['roll_deg'])
        if not (-45 <= roll <= 45):
            self.status_label.text = 'Roll-Neigung über 45°: Einbaulage prüfen'
            return
        self.heading_offset_input.text = str(round(heading, 4))
        self.pitch_offset_input.text = str(round(pitch, 4))
        self.roll_offset_input.text = str(round(roll, 4))
        self.save()

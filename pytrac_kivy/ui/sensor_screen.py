"""Sensor status and persisted IMU mounting reference (no dashboard transformations)."""
import math
import threading
from datetime import datetime, timezone
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label


class SensorScreen(BoxLayout):
    def __init__(self, api_client, on_back=None, **kwargs):
        super().__init__(orientation='vertical', padding=dp(12), spacing=dp(8), **kwargs)
        self.api_client = api_client
        self.on_back = on_back
        self._poll = None
        self._busy = False
        self._active = False
        self._last_state = None
        self._zero = None
        self._generation = 0
        header = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        back = Button(text='Zurück', size_hint_x=None, width=dp(150))
        back.bind(on_release=lambda *_: self.go_back())
        header.add_widget(back)
        header.add_widget(Label(text='[b]Sensoren[/b]', markup=True, font_size='25sp'))
        self.add_widget(header)
        self.add_widget(Label(text='ZED-F9P – GPS', bold=True, font_size='21sp',
                              size_hint_y=None, height=dp(35)))
        self.gps = Label(text='Warte auf GPS-Daten ...', halign='left', valign='top',
                         font_size='19sp')
        self.gps.bind(size=lambda inst, _value: setattr(inst, 'text_size', inst.size))
        self.add_widget(self.gps)
        self.add_widget(Label(text='BNO085 – IMU (Rohwerte)', bold=True, font_size='21sp',
                              size_hint_y=None, height=dp(35)))
        self.imu = Label(text='Warte auf IMU-Daten ...', halign='left', valign='top',
                         font_size='19sp')
        self.imu.bind(size=lambda inst, _value: setattr(inst, 'text_size', inst.size))
        self.add_widget(self.imu)
        self.zero_label = Label(text='Gespeicherte Nullstellung: wird geladen',
                                size_hint_y=None, height=dp(38), font_size='17sp')
        self.add_widget(self.zero_label)
        self.save_button = Button(text='Aktuelle IMU-Lage als Nullstellung speichern',
                                  size_hint_y=None, height=dp(55))
        self.save_button.bind(on_release=lambda *_: self.save_zero())
        self.add_widget(self.save_button)
        self.status = Label(text='Nullstellung verändert die 2D-Navigation nicht.',
                            size_hint_y=None, height=dp(35))
        self.add_widget(self.status)

    def go_back(self):
        self.stop()
        if self.on_back:
            self.on_back()

    def start(self):
        self.stop()
        self._active = True
        self._generation += 1
        self._last_state = None
        self.save_button.disabled = True
        self._load_zero(self._generation)
        self._poll = Clock.schedule_interval(self._refresh, 1.0)
        self._refresh(0)

    def stop(self):
        self._active = False
        self._generation += 1
        if self._poll is not None:
            self._poll.cancel()
            self._poll = None

    def _load_zero(self, generation):
        def work():
            try:
                data = self.api_client.get('/api/navigation-settings')
                Clock.schedule_once(lambda _dt: self._show_zero(data, generation))
            except Exception as exc:
                msg = str(exc)
                Clock.schedule_once(lambda _dt: self._show_error(msg, generation))
        threading.Thread(target=work, daemon=True).start()

    def _show_zero(self, data, generation):
        if not self._active or generation != self._generation:
            return
        self._zero = data
        self.zero_label.text = ('Gespeicherte Nullstellung: Yaw {:+.1f}°  Pitch {:+.1f}°  Roll {:+.1f}°'
                                .format(data.get('imu_zero_yaw_deg', 0),
                                        data.get('imu_zero_pitch_deg', 0),
                                        data.get('imu_zero_roll_deg', 0)))

    def _show_error(self, message, generation):
        if self._active and generation == self._generation:
            self.status.text = 'Backend: ' + message

    def _refresh(self, _dt):
        if not self._active or self._busy:
            return
        self._busy = True
        generation = self._generation
        def work():
            try:
                state = self.api_client.get('/api/vehicle/state')
                Clock.schedule_once(lambda _dt: self._show_state(state, generation))
            except Exception as exc:
                msg = str(exc)
                Clock.schedule_once(lambda _dt: self._show_error(msg, generation))
            finally:
                Clock.schedule_once(lambda _dt: setattr(self, '_busy', False))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _fmt(value, precision=2):
        return '—' if value is None else f'{value:.{precision}f}'

    def _show_state(self, data, generation):
        if not self._active or generation != self._generation:
            return
        self._last_state = data
        fix = {0:'KEIN FIX', 1:'GPS', 2:'DGPS', 4:'RTK FIXED', 5:'RTK FLOAT'}
        quality = data.get('gps_fix_quality')
        status = fix.get(quality, str(quality) if quality is not None else '—')
        gps_ok = bool(data.get('available') and data.get('gps_valid'))
        imu_ok = bool(data.get('available') and data.get('imu_valid'))
        self.gps.text = (f'Status: {status} ({"aktuell" if gps_ok else "nicht aktuell"})\n'
                         f'Breite: {self._fmt(data.get("latitude"), 7)}°    '
                         f'Länge: {self._fmt(data.get("longitude"), 7)}°\n'
                         f'Höhe: {self._fmt(data.get("altitude_m"))} m    '
                         f'Geschwindigkeit: {self._fmt(data.get("speed_mps"))} m/s')
        self.imu.text = (f'Status: {"aktuell" if imu_ok else "nicht aktuell"}\n'
                         f'Yaw: {self._fmt(data.get("heading_deg"))}°    '
                         f'Pitch: {self._fmt(data.get("pitch_deg"))}°    '
                         f'Roll: {self._fmt(data.get("roll_deg"))}°')
        self.save_button.disabled = not (imu_ok and all(
            isinstance(data.get(key), (int, float)) and math.isfinite(data[key])
            for key in ('heading_deg','pitch_deg','roll_deg')))

    def save_zero(self):
        data = self._last_state
        if not data or self.save_button.disabled or not data.get('available') or not data.get('imu_valid'):
            self.status.text = 'Keine aktuellen gültigen IMU-Daten.'
            return
        payload = {'yaw_deg': float(data['heading_deg']),
                   'pitch_deg': float(data['pitch_deg']),
                   'roll_deg': float(data['roll_deg'])}
        if not all(math.isfinite(v) for v in payload.values()):
            self.status.text = 'Ungültige IMU-Werte.'
            return
        self.save_button.disabled = True
        generation = self._generation
        def work():
            try:
                self.api_client.put('/api/navigation-settings/imu-zero', payload)
                Clock.schedule_once(lambda _dt: self._saved(generation))
            except Exception as exc:
                msg = str(exc)
                Clock.schedule_once(lambda _dt: self._show_error(msg, generation))
        threading.Thread(target=work, daemon=True).start()

    def _saved(self, generation):
        if not self._active or generation != self._generation:
            return
        self.status.text = 'Nullstellung in tractor.db gespeichert.'
        self._load_zero(generation)

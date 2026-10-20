"""Maschinenverwaltung für den PyTrac-Bordcomputer."""
import threading

import requests
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.gridlayout import GridLayout


class MachineManager(BoxLayout):
    def __init__(self, api_url, on_back=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kwargs)
        self.api_url = api_url.rstrip("/")
        self.on_back = on_back

        header = BoxLayout(size_hint_y=None, height=dp(55))
        header.add_widget(Label(text="[b]Maschinenverwaltung[/b]", markup=True))
        header.add_widget(Button(
            text="Zurück", size_hint_x=None, width=dp(150),
            on_release=lambda *_: self.on_back() if self.on_back else None,
        ))
        self.add_widget(header)

        scroll = ScrollView()
        content = GridLayout(cols=1, spacing=dp(6), size_hint_y=None)
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        self.add_widget(scroll)

        self.tractor_fields = {}
        self.implement_fields = {}

        content.add_widget(Label(
            text="Traktor", size_hint_y=None, height=dp(35)
        ))
        for key, label, default in [
            ("name", "Name", ""),
            ("length_m", "Länge (m)", "6"),
            ("width_m", "Breite (m)", "2.5"),
            ("wheelbase_m", "Radstand (m)", "2.8"),
            ("max_steering_angle_deg", "Max. Lenkwinkel (Grad)", "35"),
            ("gps_offset_length_m", "GPS-Versatz längs (m)", "0"),
            ("gps_offset_width_m", "GPS-Versatz seitlich (m)", "0"),
        ]:
            self.tractor_fields[key] = self._input(content, label, default)

        content.add_widget(Button(
            text="Traktor speichern", size_hint_y=None, height=dp(50),
            on_release=lambda *_: self._save("tractor"),
        ))
        content.add_widget(Label(
            text="Anbaugerät", size_hint_y=None, height=dp(35)
        ))
        for key, label, default in [
            ("name", "Name", ""),
            ("length_m", "Länge (m)", "2"),
            ("working_width_m", "Arbeitsbreite (m)", "3"),
            ("work_offset_m", "Arbeitsversatz (m)", "0"),
        ]:
            self.implement_fields[key] = self._input(content, label, default)

        self.mount = Spinner(
            text="Heck", values=("Heck", "Front", "Gezogen"),
            size_hint_y=None, height=dp(45),
        )
        content.add_widget(self.mount)
        content.add_widget(Button(
            text="Anbaugerät speichern", size_hint_y=None, height=dp(50),
            on_release=lambda *_: self._save("implement"),
        ))
        self.status = Label(text="", size_hint_y=None, height=dp(60))
        content.add_widget(self.status)

    def _input(self, parent, label, default):
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(Label(text=label, size_hint_x=0.48))
        field = TextInput(text=default, multiline=False, size_hint_x=0.52)
        row.add_widget(field)
        parent.add_widget(row)
        return field

    def _save(self, kind):
        fields = self.tractor_fields if kind == "tractor" else self.implement_fields
        try:
            payload = {}
            for key, field in fields.items():
                value = field.text.strip()
                if key == "name":
                    if not value:
                        raise ValueError("Bitte einen Namen eingeben.")
                    payload[key] = value
                else:
                    payload[key] = float(value.replace(",", ".") or 0)

            if kind == "implement":
                payload["mount_type"] = {
                    "Heck": "rear", "Front": "front", "Gezogen": "towed"
                }[self.mount.text]
                path = "/api/implements"
            else:
                path = "/api/tractors"

        except (ValueError, KeyError) as exc:
            self.status.text = f"Ungültige Eingabe: {exc}"
            return

        def run():
            try:
                response = requests.post(
                    self.api_url + path, json=payload, timeout=4
                )
                response.raise_for_status()
                message = "Eintrag erfolgreich gespeichert."
            except Exception as exc:
                message = f"Speichern fehlgeschlagen: {exc}"
            Clock.schedule_once(lambda dt: setattr(self.status, "text", message))

        threading.Thread(target=run, daemon=True).start()

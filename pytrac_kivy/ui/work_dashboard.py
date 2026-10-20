"""Arbeitsübersicht für das aktuelle FastAPI-Backend.

Die Oberfläche zeigt Maschinen-/Feldauswahl, Kartenansicht und Sensorstatus.
Arbeitsgangsteuerung wird erst angeboten, wenn entsprechende Backend-Endpunkte
implementiert sind; es werden keine nicht vorhandenen Endpunkte aufgerufen.
"""

import threading

import requests
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

try:
    from kivy_garden.mapview import MapView, MapMarker
    from pytrac_kivy.ui.map_layers import FieldOverlay, field_center
except ImportError:
    MapView = None
    MapMarker = None
    FieldOverlay = None
    field_center = None


GREEN = (0.16, 0.43, 0.28, 1)
DARK = (0.08, 0.105, 0.09, 1)


class WorkDashboard(BoxLayout):
    """Hauptübersicht mit Auswahlstatus, Karte und Live-Sensordaten."""

    def __init__(
        self,
        api_url,
        device_id="pico-tractor-01",
        selection=None,
        api_client=None,
        on_settings=None,
        on_status=None,
        refresh_interval=1.0,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(8),
            **kwargs,
        )
        self.api_url = api_url.rstrip("/")
        self.device_id = device_id
        self.selection = selection if selection is not None else {}
        self.api_client = api_client
        self.on_settings = on_settings
        self.on_status = on_status
        self.refresh_interval = max(0.5, float(refresh_interval))
        self.busy = False
        self._refresh_event = None
        self._latest_state = None
        self._marker = None

        header = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        header.add_widget(Label(
            text="[b]PyTrac · Arbeitsübersicht[/b]",
            markup=True,
            font_size="23sp",
            halign="left",
        ))
        header.add_widget(self._button("Einstellungen", self.open_settings))
        header.add_widget(self._button("Aktualisieren", self.refresh))
        self.add_widget(header)

        self.selection_label = Label(
            text="", size_hint_y=None, height=dp(40), halign="left"
        )
        self.add_widget(self.selection_label)

        body = BoxLayout(orientation="horizontal", spacing=dp(8))
        self.add_widget(body)

        if MapView is not None:
            self.map_view = MapView(
                lat=51.3, lon=9.5, zoom=14, size_hint_x=0.68
            )
            self.field_overlay = FieldOverlay(self.map_view)
            self.map_view.add_layer(self.field_overlay)
            body.add_widget(self.map_view)
        else:
            self.map_view = None
            self.field_overlay = None
            body.add_widget(Label(
                text="Kartenansicht nicht verfügbar.\n"
                     "Installiere kivy-garden.mapview.",
                size_hint_x=0.68,
            ))

        panel = BoxLayout(
            orientation="vertical", spacing=dp(8), padding=dp(10),
            size_hint_x=0.32,
        )
        body.add_widget(panel)
        panel.add_widget(Label(
            text="[b]Fahrzeugstatus[/b]", markup=True,
            size_hint_y=None, height=dp(42), font_size="18sp",
        ))
        self.connection_label = self._status_label("Backend: wird geprüft")
        self.gps_label = self._status_label("GPS: —")
        self.position_label = self._status_label("Position: —")
        self.heading_label = self._status_label("Richtung: —")
        self.speed_label = self._status_label("Geschwindigkeit: —")
        self.imu_label = self._status_label("IMU: —")
        for widget in (
            self.connection_label, self.gps_label, self.position_label,
            self.heading_label, self.speed_label, self.imu_label,
        ):
            panel.add_widget(widget)
        panel.add_widget(Widget())
        self.message_label = Label(
            text="Warte auf Sensordaten …", halign="left", valign="top"
        )
        panel.add_widget(self.message_label)

        self.update_selection()
        self.selection_changed()
        Clock.schedule_once(lambda _dt: self.refresh(), 0)
        self._refresh_event = Clock.schedule_interval(
            lambda _dt: self.refresh(), self.refresh_interval
        )

    def _button(self, text, callback):
        button = Button(
            text=text, size_hint_x=None, width=dp(170),
            background_normal="", background_down="",
            background_color=GREEN, color=(1, 1, 1, 1),
        )
        button.bind(on_release=lambda *_: callback())
        return button

    @staticmethod
    def _status_label(text):
        return Label(text=text, halign="left", valign="middle",
                     size_hint_y=None, height=dp(42))

    def open_settings(self):
        if self.on_settings:
            self.on_settings()

    def request(self, path):
        if self.api_client is not None:
            return self.api_client.get(path)
        response = requests.get(
            f"{self.api_url}/{path.lstrip('/')}", timeout=5
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def update_selection(self):
        def name(kind, title):
            item = self.selection.get(kind)
            return item.get("name", "nicht gewählt") if item else "nicht gewählt"
        tractor = name("tractor", "Traktor")
        implement = name("implement", "Anbaugerät")
        field = name("field", "Feld")
        self.selection_label.text = (
            f"Traktor: {tractor}    ·    Anbaugerät: {implement}    ·    Feld: {field}"
        )

    def selection_changed(self):
        self.update_selection()
        field = self.selection.get("field")
        if self.field_overlay:
            self.field_overlay.set_data(field=field, track_points=[])
        if field and self.map_view and field_center:
            center = field_center(field)
            if center:
                self.map_view.center_on(center[0], center[1])
                self.map_view.zoom = max(self.map_view.zoom, 15)

    def refresh(self):
        if self.busy:
            return
        self.busy = True

        def worker():
            try:
                data = self.request("/api/vehicle/state")
                Clock.schedule_once(lambda _dt, value=data: self._show_state(value))
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(lambda _dt, value=message: self._show_error(value))
            finally:
                self.busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _show_error(self, message):
        self.connection_label.text = "Backend: FEHLER"
        self.message_label.text = message
        if self.on_status:
            self.on_status(message)

    def _show_state(self, data):
        self._latest_state = data
        available = bool(data.get("available"))
        self.connection_label.text = (
            "Backend: verbunden · Sensoren aktuell"
            if available else "Backend: verbunden · keine aktuellen Sensordaten"
        )
        gps_valid = bool(data.get("gps_valid"))
        self.gps_label.text = "GPS: gültig" if gps_valid else "GPS: kein gültiger Fix"
        lat, lon = data.get("latitude"), data.get("longitude")
        if gps_valid and lat is not None and lon is not None:
            self.position_label.text = f"Position: {float(lat):.6f}, {float(lon):.6f}"
            if self.map_view:
                self.map_view.center_on(float(lat), float(lon))
                if MapMarker is not None:
                    if self._marker is not None:
                        try:
                            self.map_view.remove_widget(self._marker)
                        except Exception:
                            pass
                    self._marker = MapMarker(lat=float(lat), lon=float(lon))
                    self.map_view.add_widget(self._marker)
        else:
            self.position_label.text = "Position: —"
        heading = data.get("heading_deg")
        self.heading_label.text = (
            f"Richtung: {float(heading):.1f}°" if heading is not None
            else "Richtung: —"
        )
        speed = data.get("speed_mps")
        self.speed_label.text = (
            f"Geschwindigkeit: {float(speed) * 3.6:.1f} km/h"
            if speed is not None else "Geschwindigkeit: —"
        )
        self.imu_label.text = (
            "IMU: gültig" if data.get("imu_valid") else "IMU: nicht verfügbar"
        )
        reason = data.get("reason")
        self.message_label.text = str(reason or "Sensordaten werden laufend aktualisiert.")
        if self.on_status:
            self.on_status(self.message_label.text)

    def stop(self):
        if self._refresh_event is not None:
            self._refresh_event.cancel()
            self._refresh_event = None

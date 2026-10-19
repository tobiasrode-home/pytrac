"""PyTrac: Arbeitsübersicht, Karte und Arbeitsgangsteuerung."""

import threading

import requests

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from kivy_garden.mapview import MapView, MapMarker

from ui.map_layers import FieldOverlay, field_center


DARK = (0.08, 0.105, 0.09, 1)
PANEL = (0.13, 0.17, 0.145, 1)
GREEN = (0.16, 0.43, 0.28, 1)
RED = (0.52, 0.19, 0.17, 1)


class WorkDashboard(BoxLayout):
    def __init__(
        self,
        api_url,
        device_id,
        selection,
        on_settings=None,
        on_status=None,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(4),
            **kwargs,
        )

        self.api_url = api_url.rstrip("/")
        self.device_id = device_id
        self.selection = selection
        self.on_settings = on_settings
        self.on_status = on_status

        self.busy = False
        self.refreshing = False
        self.last_session_id = None
        self.last_position = None
        self.current_marker = None
        self.current_session = None
        self.current_sensor = {}
        self.current_latest = {}
        self._refresh_lock = threading.Lock()

        # Kopfzeile
        header = BoxLayout(
            size_hint_y=None,
            height=dp(52),
            spacing=dp(8),
        )

        settings_button = self.make_button(
            "Einstellungen",
            PANEL,
            self.open_settings,
        )
        settings_button.size_hint_x = None
        settings_button.width = dp(190)

        header.add_widget(settings_button)
        header.add_widget(Label(
            text="[b]Arbeitsübersicht[/b]",
            markup=True,
            font_size="24sp",
            halign="left",
        ))
        header.add_widget(Widget())
        self.add_widget(header)

        # Kartenansicht
        self.map_container = BoxLayout()
        self.map_view = MapView(
            lat=51.0,
            lon=10.0,
            zoom=15,
            double_tap_zoom=True,
        )

        self.field_overlay = FieldOverlay(self.map_view)
        self.map_view.add_layer(self.field_overlay)
        self.map_container.add_widget(self.map_view)
        self.add_widget(self.map_container)

        # Spurführungsanzeige
        self.guidance_panel = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(112),
            padding=dp(12),
            spacing=dp(4),
        )

        with self.guidance_panel.canvas.before:
            Color(*PANEL)
            self.guidance_bg = RoundedRectangle(
                pos=self.guidance_panel.pos,
                size=self.guidance_panel.size,
                radius=[dp(12)],
            )

        self.guidance_panel.bind(
            pos=self._update_guidance_bg,
            size=self._update_guidance_bg,
        )

        self.guidance_title = Label(
            text="SPURFÜHRUNG",
            font_size="13sp",
            bold=True,
            halign="left",
            size_hint_y=None,
            height=dp(22),
        )

        self.guidance_value = Label(
            text="Warte auf GPS und Arbeitsgang …",
            font_size="22sp",
            bold=True,
            halign="center",
            valign="middle",
        )
        self.guidance_value.bind(
            size=lambda widget, size: setattr(
                widget, "text_size", size
            )
        )

        self.guidance_panel.add_widget(self.guidance_title)
        self.guidance_panel.add_widget(self.guidance_value)
        self.add_widget(self.guidance_panel)

        # Arbeitsganginformationen
        self.detail_label = Label(
            text="Noch kein Arbeitsgang aktiv.",
            size_hint_y=None,
            height=dp(38),
            font_size="15sp",
            halign="left",
            valign="middle",
        )
        self.detail_label.bind(
            size=lambda widget, size: setattr(
                widget, "text_size", size
            )
        )
        self.add_widget(self.detail_label)

        # Bedienknöpfe unten
        controls = GridLayout(
            cols=4,
            spacing=dp(8),
            size_hint_y=None,
            height=dp(68),
        )

        self.start_button = self.make_button(
            "Start",
            GREEN,
            lambda *_: self.action("start"),
        )
        self.pause_button = self.make_button(
            "Pause",
            PANEL,
            lambda *_: self.action("pause"),
        )
        self.resume_button = self.make_button(
            "Fortsetzen",
            PANEL,
            lambda *_: self.action("resume"),
        )
        self.finish_button = self.make_button(
            "Beenden",
            RED,
            lambda *_: self.action("finish"),
        )

        for button in (
            self.start_button,
            self.pause_button,
            self.resume_button,
            self.finish_button,
        ):
            controls.add_widget(button)

        self.add_widget(controls)

        # Erster Abruf nach Aufbau der Oberfläche
        Clock.schedule_once(lambda _dt: self.refresh(), 0.5)

    # ---------------------------------------------------------
    # Oberfläche
    # ---------------------------------------------------------

    def make_button(self, text, color, callback):
        button = Button(
            text=text,
            background_normal="",
            background_down="",
            background_color=color,
            color=(1, 1, 1, 1),
            font_size="17sp",
            bold=True,
        )
        button.bind(on_release=callback)
        return button

    def _update_guidance_bg(self, *_):
        self.guidance_bg.pos = self.guidance_panel.pos
        self.guidance_bg.size = self.guidance_panel.size

    def open_settings(self, *_):
        if self.on_settings:
            self.on_settings()

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    def request(self, path, method="GET", payload=None):
        response = requests.request(
            method,
            self.api_url + path,
            json=payload,
            timeout=5,
        )
        response.raise_for_status()

        if not response.content:
            return {}

        return response.json()

    # ---------------------------------------------------------
    # Auswahl und Karte
    # ---------------------------------------------------------

    def selection_changed(self):
        field = self.selection.get("field")

        if field:
            self.center_on_field(field)

        self.update_map(field, [])

    def center_on_field(self, field):
        center = field_center(field) if field else None

        if center:
            self.map_view.center_on(*center)
            self.map_view.zoom = max(self.map_view.zoom, 15)

    def update_map(self, field, track_points):
        self.field_overlay.set_data(
            field=field,
            track_points=track_points,
        )

    def update_position(self, latest):
        try:
            lat = float(latest["latitude"])
            lon = float(latest["longitude"])
        except (KeyError, TypeError, ValueError):
            return

        first_position = self.last_position is None
        self.last_position = (lat, lon)

        if self.current_marker is None:
            self.current_marker = MapMarker(
                lat=lat,
                lon=lon,
            )
            self.map_view.add_marker(self.current_marker)
        else:
            self.current_marker.lat = lat
            self.current_marker.lon = lon

        if first_position:
            self.map_view.center_on(lat, lon)

    # ---------------------------------------------------------
    # Aktualisierung
    # ---------------------------------------------------------

    def refresh(self):
        if not self._refresh_lock.acquire(blocking=False):
            return

        def worker():
            try:
                session_data = self.request(
                    "/api/work-sessions/current"
                )

                sensor = self.request(
                    f"/api/sensors/{self.device_id}/status"
                )

                latest = self.request(
                    f"/api/sensors/{self.device_id}/latest"
                )

                session = session_data.get("session")
                points = []

                if session:
                    try:
                        track_data = self.request(
                            f"/api/work-sessions/{session['id']}/track"
                        )
                        points = track_data.get("points", [])
                    except requests.RequestException:
                        # Eine fehlende Track-Route soll nicht
                        # die komplette Übersicht blockieren.
                        points = []

                Clock.schedule_once(
                    lambda _dt: self.update_display(
                        session_data,
                        sensor,
                        latest,
                        points,
                    )
                )

            except Exception as exc:
                message = f"Backend nicht erreichbar: {exc}"
                Clock.schedule_once(
                    lambda _dt, msg=message: self.set_error(msg)
                )
            finally:
                self._refresh_lock.release()

        threading.Thread(target=worker, daemon=True).start()

    def set_error(self, message):
        self.detail_label.text = message

    def update_display(self, data, sensor, latest, points):
        session = data.get("session")
        guidance = data.get("guidance") or {}

        self.current_session = session
        self.current_sensor = sensor
        self.current_latest = latest

        if self.on_status:
            self.on_status(sensor, latest, session)

        if session:
            area_ha = float(
                data.get("coverage_area_m2") or 0
            ) / 10000

            field = session.get("field") or self.selection.get("field")
            field_name = (
                field.get("name", "Feld")
                if field
                else "Feld"
            )

            self.detail_label.text = (
                f"{field_name} · Arbeitsgang {session.get('id', '?')} · "
                f"{session.get('status', '?')} · "
                f"Bearbeitet: {area_ha:.3f} ha"
            )

            self.last_session_id = session.get("id")
            self.update_map(field, points)

        else:
            field = self.selection.get("field")
            self.last_session_id = None
            self.detail_label.text = (
                "Kein Arbeitsgang aktiv. Bitte Feld, Traktor und "
                "Anbaugerät auswählen und Start drücken."
            )
            self.update_map(field, [])

        # GPS-Marker nur mit gültiger Position aktualisieren.
        if (
            sensor.get("gps_valid")
            and latest.get("latitude") is not None
            and latest.get("longitude") is not None
        ):
            self.update_position(latest)

        self.update_guidance(guidance, session)

    # ---------------------------------------------------------
    # Spurführung
    # ---------------------------------------------------------

    def update_guidance(self, guidance, session):
        if not session:
            self.guidance_title.text = "SPURFÜHRUNG"
            self.guidance_value.text = (
                "Arbeitsgang starten, um die Spurführung zu aktivieren."
            )
            return

        if not guidance.get("gps_valid", False):
            self.guidance_title.text = "GPS NICHT GÜLTIG"
            self.guidance_value.text = guidance.get(
                "message",
                "Warte auf einen aktuellen GPS-Fix.",
            )
            return

        if not guidance.get("guidance_valid", False):
            self.guidance_title.text = "SPURFÜHRUNG"
            self.guidance_value.text = guidance.get(
                "message",
                "GPS gültig – Referenzspur noch nicht verfügbar.",
            )
            return

        error = guidance.get("cross_track_error_m")
        correction = guidance.get("direction_correction_deg")
        side = guidance.get("cross_track_side", "unknown")

        if error is None:
            self.guidance_value.text = guidance.get(
                "message",
                "Spurführung verfügbar",
            )
        else:
            direction = {
                "left": "links",
                "right": "rechts",
                "center": "mittig",
            }.get(side, side)

            self.guidance_value.text = (
                f"{abs(float(error)):.2f} m {direction}"
            )

            if correction is not None:
                self.guidance_value.text += (
                    f" · Korrektur: {float(correction):+.1f}°"
                )

        self.guidance_title.text = "SPURFÜHRUNG AKTIV"

    # ---------------------------------------------------------
    # Arbeitsgangaktionen
    # ---------------------------------------------------------

    def action(self, name):
        if self.busy:
            return

        self.busy = True

        def worker():
            try:
                if name == "start":
                    field = self.selection.get("field")
                    tractor = self.selection.get("tractor")
                    implement = self.selection.get("implement")

                    if not field or not tractor or not implement:
                        raise ValueError(
                            "Bitte zuerst Feld, Traktor und "
                            "Anbaugerät in den Einstellungen auswählen."
                        )

                    result = self.request(
                        "/api/work-sessions",
                        method="POST",
                        payload={
                            "field_id": int(field["id"]),
                            "tractor_id": int(tractor["id"]),
                            "implement_id": int(implement["id"]),
                        },
                    )

                else:
                    result = self.request(
                        f"/api/work-sessions/{name}",
                        method="POST",
                        payload={},
                    )

                message = result.get(
                    "message",
                    result.get("status", f"Aktion {name} ausgeführt."),
                )

                Clock.schedule_once(
                    lambda _dt, msg=message: self.set_error(msg)
                )

            except Exception as exc:
                message = f"Aktion fehlgeschlagen: {exc}"
                Clock.schedule_once(
                    lambda _dt, msg=message: self.set_error(msg)
                )
            finally:
                self.busy = False
                Clock.schedule_once(lambda _dt: self.refresh())

        threading.Thread(target=worker, daemon=True).start()

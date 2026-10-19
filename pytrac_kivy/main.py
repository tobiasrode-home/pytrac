"""PyTrac-Bordcomputer: Hauptfenster und Navigation."""

from datetime import datetime

from kivy.config import Config

# Displaykonfiguration vor den übrigen Kivy-Imports
Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")
Config.set("graphics", "resizable", "0")
Config.set("graphics", "rotation", "270")

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from config import API_BASE_URL, DEFAULT_DEVICE_ID
from ui.work_dashboard import WorkDashboard
from ui.settings_screen import SettingsScreen
from ui.master_data_screen import MasterDataScreen
from ui.wifi_manager import WifiManager

BACKGROUND = (0.055, 0.075, 0.065, 1)
PANEL = (0.12, 0.16, 0.135, 1)
GREEN = (0.18, 0.48, 0.31, 1)


class StatusBar(BoxLayout):
    """Bleibt auf allen Seiten sichtbar."""

    def __init__(self, selection, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(76),
            padding=[dp(14), dp(8)],
            spacing=dp(12),
            **kwargs,
        )

        self.selection = selection

        with self.canvas.before:
            Color(*PANEL)
            self.bg = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(12)],
            )

        self.bind(pos=self._update_bg, size=self._update_bg)

        self.gps_label = self._label(
            "GPS: wartet", (1, 0.75, 0.3, 1)
        )
        self.tractor_label = self._label("Traktor: –")
        self.implement_label = self._label("Gerät: –")
        self.time_label = self._label("--:--:--")
        self.speed_label = self._label("0,0 km/h")

        for widget in (
            self.gps_label,
            self.tractor_label,
            self.implement_label,
            self.time_label,
            self.speed_label,
        ):
            self.add_widget(widget)

        Clock.schedule_interval(self.update_clock, 1)
        self.update_clock(0)

    def _label(self, text, color=(0.93, 0.96, 0.93, 1)):
        return Label(
            text=text,
            color=color,
            font_size="16sp",
            bold=True,
            halign="center",
            valign="middle",
            size_hint_x=1,
        )

    def _update_bg(self, *_):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def update_clock(self, _dt):
        self.time_label.text = datetime.now().strftime("%H:%M:%S")

    def update_data(self, sensor, latest, session):
        gps_valid = bool(sensor.get("gps_valid", False))

        if gps_valid:
            satellites = sensor.get("satellites")
            sat_text = (
                f" · {satellites} Sat."
                if satellites is not None
                else ""
            )
            self.gps_label.text = "GPS FIX" + sat_text
            self.gps_label.color = (0.45, 1, 0.58, 1)
        else:
            self.gps_label.text = "GPS KEIN FIX"
            self.gps_label.color = (1, 0.42, 0.35, 1)

        current = session or {}

        tractor = (
            current.get("tractor")
            or self.selection.get("tractor")
        )
        implement = (
            current.get("implement")
            or self.selection.get("implement")
        )

        self.tractor_label.text = (
            "Traktor: " + tractor.get("name", "–")
            if tractor else "Traktor: –"
        )
        self.implement_label.text = (
            "Gerät: " + implement.get("name", "–")
            if implement else "Gerät: –"
        )

        speed = latest.get("speed_mps") if latest else None

        if speed is not None and gps_valid:
            self.speed_label.text = (
                f"{float(speed) * 3.6:.1f} km/h"
            )
        else:
            self.speed_label.text = "– km/h"


class PyTracRoot(BoxLayout):
    """Gemeinsamer Rahmen mit dauerhafter Statusleiste."""

    def __init__(self, api_url, device_id, **kwargs):
        super().__init__(
            orientation="vertical",
            padding=dp(10),
            spacing=dp(8),
            **kwargs,
        )

        self.api_url = api_url.rstrip("/")
        self.device_id = device_id

        self.selection = {
            "field": None,
            "tractor": None,
            "implement": None,
        }

        self.status_bar = StatusBar(self.selection)
        self.add_widget(self.status_bar)

        self.page_container = BoxLayout()
        self.add_widget(self.page_container)

        self.dashboard = WorkDashboard(
            api_url=self.api_url,
            device_id=self.device_id,
            selection=self.selection,
            on_settings=self.show_settings,
            on_status=self.update_status,
        )

        self.settings_screen = SettingsScreen(
            api_url=self.api_url,
            selection=self.selection,
            on_back=self.show_dashboard,
            on_selection_changed=self.selection_changed,
            on_master_data=self.show_master_data,
            on_wifi_manager=self.show_wifi_manager,
        )

        self.master_data_screen = MasterDataScreen(
            api_url=self.api_url,
            selection=self.selection,
            on_back=self.show_settings,
            on_selection_changed=self.selection_changed,
        )

        self.show_dashboard()

    def show_dashboard(self, *_):
        self.page_container.clear_widgets()
        self.page_container.add_widget(self.dashboard)
        self.dashboard.refresh()

    def show_settings(self, *_):
        self.page_container.clear_widgets()
        self.page_container.add_widget(self.settings_screen)
        self.settings_screen.load_choices()

    def show_master_data(self, *_):
        self.page_container.clear_widgets()
        self.page_container.add_widget(self.master_data_screen)
        self.master_data_screen.load_choices()

    def show_wifi_manager(self, *_):
        self.page_container.clear_widgets()
        self.wifi_manager = WifiManager(
            on_back=self.show_settings
        )

        self.page_container.add_widget(self.wifi_manager)

    def selection_changed(self):
        self.dashboard.selection_changed()
        self.status_bar.update_data({}, None, None)

        self.settings_screen.update_selection_buttons()

    def update_status(self, sensor, latest, session):
        self.status_bar.update_data(sensor, latest, session)


class PyTracApp(App):
    title = "PyTrac – Traktor-Bordcomputer"

    def build(self):
        Window.clearcolor = BACKGROUND

        print("PyTrac API:", API_BASE_URL, flush=True)

        return PyTracRoot(
            api_url=API_BASE_URL,
            device_id=DEFAULT_DEVICE_ID,
        )


if __name__ == "__main__":
    PyTracApp().run()

"""Startpunkt der PyTrac-Kivy-Anwendung."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Kivy-Konfiguration muss vor dem Import von App und anderen Kivy-Modulen erfolgen.

Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")
Config.set("graphics", "resizable", "0")
Config.set("graphics", "rotation", "270")

from kivy.app import App
from kivy.uix.screenmanager import Screen, ScreenManager, NoTransition

from pytrac_core.config import settings
from pytrac_kivy.dependencies import create_api_client
from pytrac_kivy.ui.master_data_screen import MasterDataScreen
from pytrac_kivy.ui.settings_screen import SettingsScreen
from pytrac_kivy.ui.wifi_manager import WifiManager
from pytrac_kivy.ui.work_dashboard import WorkDashboard


class PytracKivyApp(App):
    """Root-App und Navigation zwischen Übersicht und Einstellungen."""

    title = "PyTrac"

    def build(self):
        self.settings = settings()
        self.api_client = create_api_client()
        self.selection = {"tractor": None, "implement": None, "field": None}
        self.screen_manager = ScreenManager(transition=NoTransition())

        self.dashboard = WorkDashboard(
            api_url=self.settings.kivy_api_base_url,
            device_id="pico-tractor-01",
            selection=self.selection,
            api_client=self.api_client,
            on_settings=self.show_settings,
            refresh_interval=self.settings.kivy_refresh_interval,
        )
        self._add_screen("dashboard", self.dashboard)

        self.settings_screen = SettingsScreen(
            api_url=self.settings.kivy_api_base_url,
            selection=self.selection,
            api_client=self.api_client,
            on_back=self.show_dashboard,
            on_selection_changed=self.selection_changed,
            on_master_data=self.show_master_data,
            on_wifi_manager=self.show_wifi,
        )
        self._add_screen("settings", self.settings_screen)

        self.master_data_screen = MasterDataScreen(
            api_url=self.settings.kivy_api_base_url,
            selection=self.selection,
            api_client=self.api_client,
            on_back=self.show_settings,
            on_selection_changed=self.selection_changed,
        )
        self._add_screen("master_data", self.master_data_screen)

        self.wifi_screen = WifiManager(on_back=self.show_settings)
        self._add_screen("wifi", self.wifi_screen)

        self.screen_manager.current = "dashboard"
        return self.screen_manager

    def _add_screen(self, name, widget):
        screen = Screen(name=name)
        screen.add_widget(widget)
        self.screen_manager.add_widget(screen)

    def show_dashboard(self):
        self.screen_manager.current = "dashboard"
        self.dashboard.selection_changed()
        self.dashboard.refresh()

    def show_settings(self):
        self.screen_manager.current = "settings"
        self.settings_screen.load_choices()

    def show_master_data(self):
        self.screen_manager.current = "master_data"
        self.master_data_screen.load_choices()

    def show_wifi(self):
        self.screen_manager.current = "wifi"

    def selection_changed(self):
        self.dashboard.selection_changed()
        self.settings_screen.update_selection_buttons()

    def on_stop(self):
        dashboard = getattr(self, "dashboard", None)
        if dashboard is not None:
            dashboard.stop()
        client = getattr(self, "api_client", None)
        if client is not None:
            client.close()


if __name__ == "__main__":
    PytracKivyApp().run()

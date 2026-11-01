"""Startpunkt der PyTrac-Kivy-Anwendung."""
import sys
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(PROJECT_ROOT))
from kivy.config import Config
Config.set('graphics','width','1280')
Config.set('graphics','height','720')
Config.set('graphics','resizable','0')
Config.set('graphics','rotation','270')
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from pytrac_kivy.ui.app_theme import apply_theme
import threading
from kivy.uix.screenmanager import Screen,ScreenManager,NoTransition
from pytrac_core.config import settings
from pytrac_kivy.dependencies import create_api_client
from pytrac_kivy.ui.master_data_screen import MasterDataScreen
from pytrac_kivy.ui.settings_screen import SettingsScreen
from pytrac_kivy.ui.device_settings_screen import DeviceSettingsScreen
from pytrac_kivy.ui.wifi_manager import WifiManager
from pytrac_kivy.ui.work_dashboard import WorkDashboard
import logging

# HTTP-Abfragen an das lokale Backend nicht mehr als DEBUG ausgeben
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("requests.packages.urllib3").setLevel(logging.WARNING)

class PytracKivyApp(App):
    title='PyTrac'
    def build(self):
        self.settings=settings
        self._dark_mode=True
        self.api_client=create_api_client()
        self.selection={'tractor':None,'implement':None,'field':None}
        self.screen_manager=ScreenManager(transition=NoTransition())
        self.dashboard=WorkDashboard(api_url=settings.kivy_api_base_url,selection=self.selection,
            api_client=self.api_client,on_settings=self.show_settings,
            refresh_interval=settings.kivy_refresh_interval)
        self._add_screen('dashboard',self.dashboard)
        self.settings_screen=SettingsScreen(api_url=settings.kivy_api_base_url,
            selection=self.selection,api_client=self.api_client,on_back=self.show_dashboard,
            on_selection_changed=self.selection_changed,on_master_data=self.show_master_data,
            on_wifi_manager=self.show_wifi,on_work_order_loaded=self.work_order_loaded,
            on_work_order_reset=self.reset_work_order,
            on_navigation_settings=self.dashboard.set_navigation_settings,
            on_work_mode=self.dashboard.set_work_mode,
            on_device_settings=self.show_device_settings)
        self._add_screen('settings',self.settings_screen)
        self.device_settings_screen=DeviceSettingsScreen(
            api_client=self.api_client,on_back=self.show_settings,
            on_navigation_settings=self.dashboard.set_navigation_settings,
            on_work_mode=self.dashboard.set_work_mode,
            on_theme_changed=self.set_dark_mode)
        self._add_screen('device_settings',self.device_settings_screen)
        self.master_data_screen=MasterDataScreen(api_url=settings.kivy_api_base_url,
            selection=self.selection,api_client=self.api_client,on_back=self.show_settings,
            on_selection_changed=self.selection_changed)
        self._add_screen('master_data',self.master_data_screen)
        self.wifi_screen=WifiManager(on_back=self.show_settings)
        self._add_screen('wifi',self.wifi_screen)
        self.screen_manager.current='dashboard'
        Clock.schedule_once(lambda _dt:self._load_theme(),0)
        # Dynamisch erzeugte Menüs und Popups erhalten das aktuelle Theme.
        Clock.schedule_interval(self._refresh_menu_theme, 0.35)
        return self.screen_manager
    def _load_theme(self):
        def worker():
            try:
                result=self.api_client.get('/api/navigation-settings')
                if isinstance(result,dict):
                    dark=bool(result.get('dark_mode',True))
                    Clock.schedule_once(lambda _dt:self.set_dark_mode(dark))
            except Exception:
                logging.getLogger(__name__).exception('Darkmode konnte nicht geladen werden')
        threading.Thread(target=worker,daemon=True).start()

    def _refresh_menu_theme(self, _dt):
        # Dashboard-Zeichnung nicht periodisch anfassen; nur Menüs/Dialoge.
        if self.screen_manager.current != "dashboard":
            apply_theme(self.screen_manager, self._dark_mode)
            # Kivy-Popups werden direkt an Window angehängt.
            for child in Window.children:
                if child is not self.screen_manager:
                    apply_theme(child, self._dark_mode)

    def set_dark_mode(self,dark):
        self._dark_mode=bool(dark)
        apply_theme(self.screen_manager,self._dark_mode)
        self._refresh_menu_theme(0)
        self.dashboard.precision_view.set_dark_mode(self._dark_mode)
        self.dashboard.steering_bar.set_dark_mode(self._dark_mode)

    def _add_screen(self,name,widget):
        screen=Screen(name=name);screen.add_widget(widget);self.screen_manager.add_widget(screen)
    def work_order_loaded(self,planning,guidance,objects):
        self.dashboard.load_work_order(planning,guidance,objects)
        self.settings_screen.update_selection_buttons()
        self.screen_manager.current='dashboard'
    def reset_work_order(self):
        self.dashboard.reset_work_order()

    def show_dashboard(self):
        self.screen_manager.current='dashboard'
        self.set_dark_mode(self._dark_mode)
        self.dashboard.selection_changed()
        self.dashboard.refresh()
    def show_settings(self):
        Clock.schedule_once(lambda _dt:self.set_dark_mode(self._dark_mode),0)
        self.screen_manager.current='settings';self.settings_screen.load_choices();self.settings_screen.load_navigation_settings()
    def show_device_settings(self):
        Clock.schedule_once(lambda _dt:self.set_dark_mode(self._dark_mode),0)
        self.screen_manager.current="device_settings"
        self.device_settings_screen.load_settings()
    def show_master_data(self):
        self.screen_manager.current='master_data';self.master_data_screen.load_choices()
        self._refresh_menu_theme(0)
    def show_wifi(self):
        self.screen_manager.current='wifi'
        self._refresh_menu_theme(0)
    def selection_changed(self):
        self.dashboard.selection_changed();self.settings_screen.update_selection_buttons()
    def on_stop(self):
        self.dashboard.stop();self.api_client.close()
if __name__=='__main__':PytracKivyApp().run()

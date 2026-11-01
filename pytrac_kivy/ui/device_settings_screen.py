"""Separate persistent device settings; does not modify 2D layout."""
import logging
import threading
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from pytrac_kivy.ui.display_brightness import read_brightness, set_brightness
from pytrac_kivy.ui.fullscreen_keyboard import bind_fullscreen_keyboard

log=logging.getLogger(__name__)

class DeviceSettingsScreen(BoxLayout):
    def __init__(self,api_client,on_back=None,on_navigation_settings=None,
                 on_work_mode=None,on_theme_changed=None,**kwargs):
        super().__init__(orientation='vertical',padding=dp(12),spacing=dp(9),**kwargs)
        self.api_client=api_client
        self.on_back=on_back
        self.on_navigation_settings=on_navigation_settings
        self.on_work_mode=on_work_mode
        self.on_theme_changed=on_theme_changed
        self._request_id=0
        self._saving=False
        self._loaded=False
        self._saved_snapshot=None
        self._pending_back=False
        self._confirm_popup=None

        header=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(8))
        header.add_widget(self._button('← Zurück',lambda *_:self.go_back(),width=dp(145)))
        header.add_widget(Label(text='[b]Geräte Einstellungen[/b]',markup=True,font_size='24sp'))
        self.add_widget(header)

        scroll=ScrollView(do_scroll_x=False,bar_width=dp(8))
        content=BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(9),padding=(0,dp(6),0,dp(6)))
        content.bind(minimum_height=content.setter('height'))
        scroll.add_widget(content)
        self.add_widget(scroll)

        # Alle Einstellungen: links Parametername, rechts Bedienfeld.
        mode_row=self._setting_row(content,'Aufzeichnung')
        self.mode_value=1
        self.mode_button=self._button('Halbautomatisch  ▾',lambda *_:self._open_mode_popup(),height=52)
        mode_row.add_widget(self.mode_button)

        heading_row=self._setting_row(content,'Ausrichtung (°)')
        self.heading_input=TextInput(text='0',multiline=False,input_filter='float',
                                     size_hint_y=None,height=dp(48),font_size='19sp')
        bind_fullscreen_keyboard(self.heading_input,'Ausrichtungs-Offset in Grad')
        heading_row.add_widget(self.heading_input)

        roll_row=self._setting_row(content,'Neigung (°)')
        self.roll_input=TextInput(text='0',multiline=False,input_filter='float',
                                  size_hint_y=None,height=dp(48),font_size='19sp')
        bind_fullscreen_keyboard(self.roll_input,'Neigungs-Offset in Grad')
        roll_row.add_widget(self.roll_input)

        brightness_row=self._setting_row(content,'Helligkeit')
        self.brightness_value=100
        self.brightness_buttons={}
        buttons=BoxLayout(spacing=dp(10))
        for percent in (50,100):
            button=self._button(f'{percent} %',lambda _btn,v=percent:self._select_brightness(v),height=52)
            buttons.add_widget(button)
            self.brightness_buttons[percent]=button
        brightness_row.add_widget(buttons)

        theme_row=self._setting_row(content,'Darkmode')
        switch_holder=BoxLayout(size_hint_x=1,orientation='horizontal')
        self.dark_mode_switch=Switch(active=True,size_hint=(None,None),
                                     width=dp(120),height=dp(68))
        switch_holder.add_widget(self.dark_mode_switch)
        switch_holder.add_widget(Label())
        theme_row.add_widget(switch_holder)
        self.save_button=self._button('Einstellungen speichern',lambda *_:self.save(),height=dp(58))
        self.add_widget(self.save_button)
        self.status=Label(text='',size_hint_y=None,height=dp(35))
        self.add_widget(self.status)

    @staticmethod
    def _setting_row(content,name):
        row=BoxLayout(size_hint_y=None,height=dp(68),spacing=dp(14))
        row.add_widget(Label(text=name,size_hint_x=.40,halign='left',
                             valign='middle',font_size='19sp'))
        row.children[0].bind(size=lambda widget,_:setattr(widget,'text_size',widget.size))
        control=BoxLayout(size_hint_x=.60,orientation='vertical',padding=(0,dp(7),0,dp(7)))
        row.add_widget(control)
        content.add_widget(row)
        return control

    def _set_mode(self,value):
        self.mode_value=int(value)
        self.mode_button.text=('Manuell  ▾','Halbautomatisch  ▾','Automatisch  ▾')[self.mode_value]

    def _open_mode_popup(self):
        panel=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(10))
        popup=Popup(title='Aufzeichnung',content=panel,size_hint=(.72,None),
                    height=dp(310),auto_dismiss=True)
        for index,title in enumerate(('Manuell','Halbautomatisch','Automatisch')):
            button=self._button(title,lambda _btn,v=index:(self._set_mode(v),popup.dismiss()),height=60)
            panel.add_widget(button)
        popup.open()

    @staticmethod
    def _button(text,callback,height=54,width=None):
        b=Button(text=text,size_hint_y=None,height=dp(height),font_size='18sp',
                 background_normal='',background_color=(.16,.43,.28,1))
        if width is not None:
            b.size_hint_x=None
            b.width=width
        b.bind(on_release=callback)
        return b

    def _select_brightness(self,percent):
        self.brightness_value=percent
        for value,button in self.brightness_buttons.items():
            button.background_color=(.16,.43,.28,1) if value==percent else (.25,.28,.32,1)

    def _snapshot(self):
        # Strings beibehalten, damit auch unfertige Eingaben als Änderung zählen.
        return (self.mode_value, self.heading_input.text,
                self.roll_input.text, self.brightness_value,
                bool(self.dark_mode_switch.active))

    def _is_dirty(self):
        return self._loaded and self._saved_snapshot is not None and self._snapshot() != self._saved_snapshot

    def go_back(self):
        if self._saving:
            self.status.text='Bitte warten: Einstellungen werden gespeichert.'
            return
        if self._is_dirty():
            self._show_unsaved_popup()
            return
        if self.on_back:
            self.on_back()

    def _show_unsaved_popup(self):
        if self._confirm_popup:
            return
        content=BoxLayout(orientation='vertical',padding=dp(14),spacing=dp(12))
        content.add_widget(Label(text='Es gibt ungespeicherte Änderungen.\nWas möchtest du tun?',
                                 halign='center',valign='middle'))
        row=BoxLayout(size_hint_y=None,height=dp(62),spacing=dp(8))
        discard=self._button('Verwerfen',lambda *_:self._discard_and_back())
        save=self._button('Speichern',lambda *_:self._save_from_popup())
        stay=self._button('Schließen / bleiben',lambda *_:self._close_unsaved_popup())
        for btn in (discard,save,stay):row.add_widget(btn)
        content.add_widget(row)
        self._confirm_popup=Popup(title='Ungespeicherte Einstellungen',content=content,
                                  size_hint=(.86,None),height=dp(210),auto_dismiss=False)
        self._confirm_popup.open()

    def _close_unsaved_popup(self):
        popup=self._confirm_popup
        self._confirm_popup=None
        if popup:popup.dismiss()

    def _discard_and_back(self):
        self._close_unsaved_popup()
        if self.on_back:self.on_back()

    def _save_from_popup(self):
        # Speichern und auf dem Geräte-Einstellungsbildschirm bleiben.
        self._close_unsaved_popup()
        self.save()

    def load_settings(self):
        self._request_id+=1
        request_id=self._request_id
        self._loaded=False
        self.save_button.disabled=True
        self.status.text='Lade Geräteeinstellungen …'
        def worker():
            try:
                result=self.api_client.get('/api/navigation-settings')
                if not isinstance(result,dict):
                    raise ValueError('Ungültige Antwort des Backends')
                Clock.schedule_once(lambda _dt,d=result,n=request_id:self._loaded_settings(d,n))
            except Exception as exc:
                msg=str(exc)
                Clock.schedule_once(lambda _dt,m=msg,n=request_id:self._load_error(m,n))
        threading.Thread(target=worker,daemon=True).start()

    def _loaded_settings(self,data,request_id):
        if request_id!=self._request_id:
            return
        self.dark_mode_switch.active=bool(data.get('dark_mode',True))
        self._set_mode({'manual':0,'confirmed':1,'automatic':2}.get(data.get('work_mode'),1))
        self.heading_input.text=str(data.get('imu_heading_offset_deg',0))
        self.roll_input.text=str(data.get('imu_roll_offset_deg',0))
        self._select_brightness(min((50,100),key=lambda v:abs(v-int(data.get('display_brightness_percent',100)))))
        self._loaded=True
        self._saved_snapshot=self._snapshot()
        self.save_button.disabled=False
        self.status.text='Einstellungen aus der Datenbank geladen'

    def _load_error(self,message,request_id):
        if request_id!=self._request_id:
            return
        self.status.text='Laden fehlgeschlagen: '+message
        self.save_button.disabled=True

    def save(self):
        if not self._loaded or self._saving:
            return
        try:
            heading=float(self.heading_input.text.replace(',','.'))
            roll=float(self.roll_input.text.replace(',','.'))
            brightness=self.brightness_value
            if not 10<=brightness<=100:
                raise ValueError('Helligkeit muss zwischen 10 und 100 % liegen')
            import math
            if not math.isfinite(heading) or not -180<=heading<=180:
                raise ValueError('Ausrichtung muss zwischen -180° und +180° liegen')
            if not math.isfinite(roll) or not -45<=roll<=45:
                raise ValueError('Neigung muss zwischen -45° und +45° liegen')
        except ValueError as exc:
            self.status.text=str(exc)
            return
        data={
            'work_mode':('manual','confirmed','automatic')[self.mode_value],
            'imu_heading_offset_deg':heading,
            'imu_roll_offset_deg':roll,
            'display_brightness_percent':brightness,
            'dark_mode':bool(self.dark_mode_switch.active),
        }
        self._saving=True
        self.save_button.disabled=True
        self.status.text='Speichere …'
        def worker():
            try:
                result=self.api_client.patch('/api/navigation-settings/device-settings',data)
                if hasattr(result,'json'):
                    result=result.json()
                Clock.schedule_once(lambda _dt,d=result:self._saved(d))
            except Exception as exc:
                msg=str(exc)
                Clock.schedule_once(lambda _dt,m=msg:self._save_error(m))
        threading.Thread(target=worker,daemon=True).start()

    def _saved(self,data):
        self._saving=False
        self.save_button.disabled=False
        if not isinstance(data,dict):
            self.status.text='Ungültige Speicherantwort'
            return
        # Erst nach bestätigter Backend-Antwort gilt der Stand als gespeichert.
        self._saved_snapshot=self._snapshot()
        if self.on_theme_changed:
            self.on_theme_changed(bool(data.get('dark_mode',True)))
        if self.on_work_mode:
            self.on_work_mode(data['work_mode'])
        if self.on_navigation_settings:
            self.on_navigation_settings(data)
        try:
            set_brightness(data['display_brightness_percent'])
            self.status.text='In tractor.db gespeichert und Helligkeit angewendet'
        except (RuntimeError,ValueError) as exc:
            self.status.text='In tractor.db gespeichert; Display: '+str(exc)

    def _save_error(self,message):
        self._saving=False
        self.save_button.disabled=False
        self.status.text='Speichern fehlgeschlagen: '+message

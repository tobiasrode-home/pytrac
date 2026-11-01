"""Separate persistent device settings; does not modify 2D layout."""
import logging
import threading
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from pytrac_kivy.ui.display_brightness import read_brightness, set_brightness
from pytrac_kivy.ui.fullscreen_keyboard import bind_fullscreen_keyboard

log=logging.getLogger(__name__)

class DeviceSettingsScreen(BoxLayout):
    def __init__(self,api_client,on_back=None,on_navigation_settings=None,
                 on_work_mode=None,**kwargs):
        super().__init__(orientation='vertical',padding=dp(12),spacing=dp(9),**kwargs)
        self.api_client=api_client
        self.on_back=on_back
        self.on_navigation_settings=on_navigation_settings
        self.on_work_mode=on_work_mode
        self._request_id=0
        self._saving=False
        self._loaded=False

        header=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(8))
        header.add_widget(self._button('Zurück',lambda *_:self.go_back(),width=dp(145)))
        header.add_widget(Label(text='[b]Geräte Einstellungen[/b]',markup=True,font_size='24sp'))
        self.add_widget(header)

        self.add_widget(Label(text='Arbeitsmodus',bold=True,font_size='20sp',
                              size_hint_y=None,height=dp(35)))
        mode_row=BoxLayout(size_hint_y=None,height=dp(58),spacing=dp(12))
        mode_row.add_widget(Label(text='Manuell',size_hint_x=None,width=dp(110)))
        self.mode_slider=Slider(min=0,max=2,step=1,value=1)
        mode_row.add_widget(self.mode_slider)
        mode_row.add_widget(Label(text='Automatik',size_hint_x=None,width=dp(125)))
        self.add_widget(mode_row)
        self.mode_label=Label(text='Aktiv: Mit Bestätigung',size_hint_y=None,height=dp(30))
        self.mode_slider.bind(value=lambda _,v:setattr(
            self.mode_label,'text',('Aktiv: Manuell', 'Aktiv: Mit Bestätigung',
                                    'Aktiv: Automatik ohne Bestätigung')[int(round(v))]))
        self.add_widget(self.mode_label)
        self.add_widget(Label(text='Automatik: Aufzeichnung an Start/Endpunkt ohne Bestätigung; '
                              'Gerät weiterhin manuell bedienen.',
                              size_hint_y=None,height=dp(35)))

        self.add_widget(Label(text='GPS / IMU-Offsets',bold=True,font_size='20sp',
                              size_hint_y=None,height=dp(35)))
        offset_row=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(8))
        offset_row.add_widget(Label(text='Ausrichtung (°)',size_hint_x=.28))
        self.heading_input=TextInput(text='0',multiline=False,input_filter='float',size_hint_x=.18)
        bind_fullscreen_keyboard(self.heading_input,'Ausrichtungs-Offset in Grad')
        offset_row.add_widget(self.heading_input)
        offset_row.add_widget(Label(text='Neigung (°)',size_hint_x=.26))
        self.roll_input=TextInput(text='0',multiline=False,input_filter='float',size_hint_x=.18)
        bind_fullscreen_keyboard(self.roll_input,'Neigungs-Offset in Grad')
        offset_row.add_widget(self.roll_input)
        self.add_widget(offset_row)

        self.add_widget(Label(text='Displayhelligkeit',bold=True,font_size='20sp',
                              size_hint_y=None,height=dp(35)))
        brightness_row=BoxLayout(size_hint_y=None,height=dp(54),spacing=dp(8))
        self.brightness_value=75
        self.brightness_buttons={}
        for percent in (25,50,75,100):
            button=self._button(f'{percent} %',lambda _btn,v=percent:self._select_brightness(v))
            brightness_row.add_widget(button)
            self.brightness_buttons[percent]=button
        self.add_widget(brightness_row)
        self.add_widget(Label(text='Helligkeit wählen und Einstellungen speichern.',
                              size_hint_y=None,height=dp(28)))
        self.add_widget(BoxLayout())
        self.save_button=self._button('Einstellungen speichern',lambda *_:self.save(),height=dp(58))
        self.add_widget(self.save_button)
        self.status=Label(text='',size_hint_y=None,height=dp(35))
        self.add_widget(self.status)

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

    def go_back(self):
        if self.on_back:
            self.on_back()

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
        self.mode_slider.value={'manual':0,'confirmed':1,'automatic':2}.get(data.get('work_mode'),1)
        self.heading_input.text=str(data.get('imu_heading_offset_deg',0))
        self.roll_input.text=str(data.get('imu_roll_offset_deg',0))
        self._select_brightness(min((25,50,75,100),key=lambda v:abs(v-int(data.get('display_brightness_percent',75)))))
        self._loaded=True
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
            'work_mode':('manual','confirmed','automatic')[int(round(self.mode_slider.value))],
            'imu_heading_offset_deg':heading,
            'imu_roll_offset_deg':roll,
            'display_brightness_percent':brightness,
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

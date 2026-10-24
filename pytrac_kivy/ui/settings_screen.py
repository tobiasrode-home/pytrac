"""Stammdaten- und Arbeitsauftragsauswahl der PyTrac-Kivy-App."""
import threading
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from pytrac_kivy.ui.display_brightness import read_brightness, set_brightness
from pytrac_kivy.ui.fullscreen_keyboard import bind_fullscreen_keyboard
from pytrac_kivy.ui.work_order_dialog import open_work_order_dialog
from pytrac_kivy.ui.create_work_order import open_create_work_order

class SettingsScreen(BoxLayout):
    def __init__(self,api_url,selection,api_client=None,on_back=None,
                 on_selection_changed=None,on_master_data=None,on_wifi_manager=None,
                 on_work_order_loaded=None,on_work_order_reset=None,on_navigation_settings=None,**kwargs):
        super().__init__(orientation='vertical',padding=dp(9),spacing=dp(5),**kwargs)
        self.api_url=api_url.rstrip('/')
        self.api_client=api_client
        self.selection=selection
        self.on_back=on_back
        self.on_selection_changed=on_selection_changed
        self.on_master_data=on_master_data
        self.on_wifi_manager=on_wifi_manager
        self.on_work_order_loaded=on_work_order_loaded
        self.on_work_order_reset=on_work_order_reset
        self.on_navigation_settings=on_navigation_settings
        self.navigation_options={"gps_smoothing_enabled":False,"imu_heading_offset_deg":0.0}
        self.choices={'tractor':[],'implement':[],'field':[]}
        self.selection_buttons={}
        header=BoxLayout(size_hint_y=None,height=dp(50),spacing=dp(6))
        header.add_widget(Label(text='[b]Einstellungen[/b]',markup=True,font_size='25sp'))
        header.add_widget(self.make_button('Zur Übersicht',lambda *_:self.go_back(),width=dp(180)))
        header.add_widget(self.make_button('Stammdaten',lambda *_:self.open_master_data(),width=dp(180)))
        header.add_widget(self.make_button('Wifi',lambda *_:self.open_wifi_manager(),width=dp(180)))
        self.add_widget(header)
        self.add_widget(Label(text='Arbeitsauftrag auswählen',size_hint_y=None,height=dp(25),bold=True,font_size='18sp'))
        self.work_order_button=self.make_button('Gespeicherten Arbeitsauftrag laden',lambda *_:self.open_work_order(),height=dp(48))
        self.add_widget(self.work_order_button)
        # Deutlicher vertikaler Abstand zu den Aktionen darunter.
        self.add_widget(BoxLayout(size_hint_y=None,height=dp(22)))
        work_actions=BoxLayout(size_hint_y=None,height=dp(46),spacing=dp(8))
        work_actions.add_widget(self.make_button("Neuen Arbeitsauftrag erstellen",lambda *_:self.create_work_order()))
        work_actions.add_widget(self.make_button("Arbeitsauftrag zurücksetzen",lambda *_:self.reset_work_order()))
        self.add_widget(work_actions)
        self.add_widget(Label(text='Oder Traktor, Anbaugerät und Feld manuell auswählen:',size_hint_y=None,height=dp(26)))
        for kind,title in [('tractor','Traktor'),('implement','Anbaugerät'),('field','Feld')]:
            self.add_widget(Label(text=title,size_hint_y=None,height=dp(21),bold=True))
            button=self.make_button(self.selection_text(kind),lambda _btn,k=kind:self.open_picker(k),height=dp(43))
            self.selection_buttons[kind]=button
            self.add_widget(button)
        self.status_label=Label(text='Lade Auswahlmöglichkeiten …',size_hint_y=None,height=dp(32))
        self.add_widget(self.status_label)
        # Freier Raum wächst mit der Displayhöhe. Navigationseinstellungen
        # sitzen direkt über der Helligkeit am unteren Displayrand.
        self.add_widget(BoxLayout(size_hint_y=1))
        self._loading_nav_settings=True
        self.add_widget(Label(text="GPS und IMU",size_hint_y=None,height=dp(26),
                              bold=True,font_size="18sp"))
        nav_row=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(8))
        nav_row.add_widget(Label(text="GPS glätten",size_hint_x=.25))
        self.smoothing_switch=Switch(active=False,size_hint_x=.12)
        self.smoothing_switch.bind(active=self._smoothing_changed)
        nav_row.add_widget(self.smoothing_switch)
        nav_row.add_widget(Label(text="IMU-Offset (°)",size_hint_x=.27))
        self.heading_offset_input=TextInput(text="0",multiline=False,
                                            input_filter=None,size_hint_x=.16)
        bind_fullscreen_keyboard(self.heading_offset_input,"IMU-Offset in Grad (-180 bis +180)")
        nav_row.add_widget(self.heading_offset_input)
        self.add_widget(nav_row)
        self.add_widget(self.make_button("GPS-/IMU-Einstellungen speichern",
                                         lambda *_:self.save_navigation_settings(),
                                         height=dp(44)))
        self.add_widget(BoxLayout(size_hint_y=None,height=dp(12)))
        self._loading_nav_settings=False
        self.load_navigation_settings()
        brightness=read_brightness()
        brightness_row=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(8))
        brightness_row.add_widget(Label(text="Displayhelligkeit",size_hint_x=None,width=dp(160)))
        self.brightness_buttons={}
        for level in (25,50,75,100):
            button=self.make_button(f"{level} %",lambda _btn,level=level:self.set_display_brightness(level))
            button.disabled=brightness is None
            brightness_row.add_widget(button)
            self.brightness_buttons[level]=button
        self.add_widget(brightness_row)
        self.brightness_label=Label(text=(f"Aktuell: {brightness} %" if brightness is not None else
                                          "Displayhelligkeit nicht verfügbar"),
                                    size_hint_y=None,height=dp(24))
        self.add_widget(self.brightness_label)
        self.load_choices()

    def _smoothing_changed(self,_widget,active):
        if not self._loading_nav_settings:
            self.status_label.text=("GPS-Glättung eingeschaltet – Speichern drücken" if active
                                    else "GPS-Glättung ausgeschaltet – Speichern drücken")

    def load_navigation_settings(self):
        def worker():
            try:
                data=self.api_client.get("/api/navigation-settings")
                Clock.schedule_once(lambda _dt:self.apply_navigation_settings(data))
            except Exception as exc:
                Clock.schedule_once(lambda _dt,msg=str(exc):setattr(self.status_label,"text","Navigationseinstellungen: "+msg))
        threading.Thread(target=worker,daemon=True).start()

    def apply_navigation_settings(self,data):
        self._loading_nav_settings=True
        try:
            self.navigation_options=dict(data)
            self.smoothing_switch.active=bool(data.get("gps_smoothing_enabled",False))
            self.heading_offset_input.text=str(data.get("imu_heading_offset_deg",0.0))
            if self.on_navigation_settings:self.on_navigation_settings(self.navigation_options)
        finally:
            self._loading_nav_settings=False

    def save_navigation_settings(self):
        try:
            value=float(self.heading_offset_input.text.replace(",","."))
            if not -180<=value<=180:raise ValueError("Offset muss zwischen -180° und +180° liegen")
        except ValueError as exc:
            self.status_label.text="Ungültiger IMU-Offset: "+str(exc)
            return
        payload={"gps_smoothing_enabled":bool(self.smoothing_switch.active),
                 "imu_heading_offset_deg":value}
        def worker():
            try:
                data=self.api_client.put("/api/navigation-settings",payload)
                if hasattr(data,"json"):data=data.json()
                Clock.schedule_once(lambda _dt:self._saved_navigation_settings(data))
            except Exception as exc:
                Clock.schedule_once(lambda _dt,msg=str(exc):setattr(self.status_label,"text","Speichern fehlgeschlagen: "+msg))
        threading.Thread(target=worker,daemon=True).start()

    def _saved_navigation_settings(self,data):
        self.apply_navigation_settings(data)
        self.status_label.text="GPS-/IMU-Einstellungen in tractor.db gespeichert"

    def set_display_brightness(self,value):
        try:
            set_brightness(value)
            self.brightness_label.text=f"Aktuell: {value} %"
        except (RuntimeError,ValueError) as exc:
            self.brightness_label.text="Helligkeit konnte nicht geändert werden"
            self.status_label.text=str(exc)

    @staticmethod
    def make_button(text,callback,height=None,width=None):
        button=Button(text=text,size_hint_y=None,height=height or dp(54),background_normal='',
            background_down='',background_color=(.16,.43,.28,1),color=(1,1,1,1),font_size='17sp')
        if width is not None:button.size_hint_x=None;button.width=width
        button.bind(on_release=callback)
        return button
    def request(self,path):
        return self.api_client.get(path)
    def selection_text(self,kind):
        item=self.selection.get(kind)
        title={'tractor':'Traktor','implement':'Anbaugerät','field':'Feld'}[kind]
        return f"{title}: {item.get('name','Unbekannt')}" if item else f'{title}: noch nicht ausgewählt'
    def update_selection_buttons(self):
        for kind,button in self.selection_buttons.items():button.text=self.selection_text(kind)
    def load_choices(self):
        def worker():
            try:
                choices={kind:self.request('/api/'+path) for kind,path in
                         [('tractor','tractors'),('implement','implements'),('field','fields')]}
                Clock.schedule_once(lambda _dt:self.set_choices(choices))
            except Exception as exc:
                Clock.schedule_once(lambda _dt,msg=str(exc):setattr(self.status_label,'text','Laden fehlgeschlagen: '+msg))
        threading.Thread(target=worker,daemon=True).start()
    def set_choices(self,choices):
        self.choices=choices
        self.status_label.text=(f"{len(choices['tractor'])} Traktoren · "
            f"{len(choices['implement'])} Anbaugeräte · {len(choices['field'])} Felder")
        self.update_selection_buttons()
    def open_picker(self,kind):
        items=self.choices.get(kind,[])
        if not items:self.status_label.text='Keine Einträge vorhanden';return
        content=BoxLayout(orientation='vertical',spacing=dp(6),padding=dp(10))
        scroll=ScrollView()
        rows=BoxLayout(orientation='vertical',spacing=dp(6),size_hint_y=None)
        rows.bind(minimum_height=rows.setter('height'))
        popup=Popup(title=f'{kind} auswählen',content=content,size_hint=(.85,.85))
        if kind=="field":
            search=TextInput(hint_text="Feldname suchen – antippen für Vollbildtastatur",
                             multiline=False,size_hint_y=None,height=dp(55))
            content.add_widget(search)
            bind_fullscreen_keyboard(search,"Feldname suchen")
            def filter_fields(_instance,query):
                rows.clear_widgets()
                for item in items:
                    if query.casefold() in item.get("name","").casefold():
                        rows.add_widget(self.make_button(item.get("name",str(item.get("id"))),
                            lambda _btn,entry=item:self.choose(kind,entry,popup),height=dp(58)))
            search.bind(text=filter_fields)
        for item in items:
            rows.add_widget(self.make_button(item.get('name',str(item.get('id'))),
                lambda _btn,entry=item:self.choose(kind,entry,popup),height=dp(58)))
        scroll.add_widget(rows);content.add_widget(scroll)
        content.add_widget(self.make_button('Abbrechen',lambda *_:popup.dismiss(),height=dp(48)))
        popup.open()
    def choose(self,kind,item,popup):
        self.selection[kind]=item;self.update_selection_buttons()
        self.status_label.text=f"Ausgewählt: {item.get('name','Unbekannt')}"
        popup.dismiss()
        if self.on_selection_changed:self.on_selection_changed()
    def reset_work_order(self):
        for kind in ("tractor","implement","field"):self.selection[kind]=None
        self.work_order_button.text="Gespeicherten Arbeitsauftrag laden"
        self.update_selection_buttons()
        self.status_label.text="Arbeitsauftrag abgewählt; gespeicherte Fahrten bleiben erhalten"
        if self.on_work_order_reset:self.on_work_order_reset()

    def create_work_order(self):
        if not self.api_client:
            self.status_label.text="API-Client fehlt";return
        open_create_work_order(self.api_client,self.choices,self._work_order_loaded)

    def open_work_order(self):
        if not self.api_client:
            self.status_label.text='API-Client fehlt';return
        open_work_order_dialog(self.api_client,self._work_order_loaded)
    def _work_order_loaded(self,planning,guidance,objects):
        self.selection.update(objects)
        self.update_selection_buttons()
        self.work_order_button.text=f"Arbeitsauftrag: {planning.get('name','Ohne Namen')}"
        self.status_label.text='Arbeitsauftrag geladen'
        if self.on_work_order_loaded:self.on_work_order_loaded(planning,guidance,objects)
    def go_back(self):
        if self.on_back:self.on_back()
    def open_master_data(self):
        if self.on_master_data:self.on_master_data()
    def open_wifi_manager(self):
        if self.on_wifi_manager:self.on_wifi_manager()

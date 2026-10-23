"""PyTrac-Ackernavi: gespeicherte Arbeit laden und mit GPS manuell abfahren.

Keine Lenkbefehle, keine automatische Gerätebetätigung. Das Rangieren im
Vorgewende bleibt beim Fahrer. GPS muss gültig sein.
"""
import threading
from pathlib import Path
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import PushMatrix, PopMatrix, Rotate
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from pytrac_kivy.ui.guidance_navigation import GuidanceNavigator
from pytrac_kivy.ui.steering_bar import SteeringBar

try:
    from kivy_garden.mapview import MapView, MapMarker
    from pytrac_kivy.ui.map_layers import FieldOverlay, field_center
    from pytrac_kivy.ui.guidance_overlay import GuidanceOverlay
except ImportError:
    MapView=MapMarker=FieldOverlay=GuidanceOverlay=field_center=None

TRACTOR_ICON=Path(__file__).resolve().parents[1]/'assets'/'tractor.png'
GREEN=(.16,.43,.28,1)

if MapMarker is not None:
    class TractorMarker(MapMarker):
        def __init__(self,**kwargs):
            super().__init__(**kwargs)
            with self.canvas.before:
                PushMatrix()
                self._rotation=Rotate(angle=0,origin=self.center)
            with self.canvas.after:
                PopMatrix()
            self.bind(pos=self._update_origin,size=self._update_origin)
        def _update_origin(self,*_):
            self._rotation.origin=self.center
        def set_heading(self,heading):
            self._rotation.angle=-float(heading)
else:
    TractorMarker=None


class WorkDashboard(BoxLayout):
    def __init__(self,api_url,selection=None,api_client=None,on_settings=None,
                 on_status=None,refresh_interval=1.,**kwargs):
        super().__init__(orientation='vertical',spacing=dp(7),padding=dp(8),**kwargs)
        self.api_url=api_url.rstrip('/')
        self.api_client=api_client
        self.selection=selection if selection is not None else {}
        self.on_settings=on_settings
        self.on_status=on_status
        self.refresh_interval=max(.5,float(refresh_interval))
        self.busy=False
        self.navigator=None
        self._marker=None
        self._latest_state=None
        self.abstract_map=True
        self._refresh_event=None

        header=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(6))
        header.add_widget(Label(text='[b]PyTrac · Ackernavi[/b]',markup=True,font_size='23sp'))
        header.add_widget(self._button('Einstellungen',self.open_settings,145))
        header.add_widget(self._button('Aktualisieren',self.refresh,135))
        self.add_widget(header)
        steering_row=BoxLayout(size_hint_y=None,height=dp(74))
        steering_row.add_widget(Widget(size_hint_x=.25))
        self.steering_bar=SteeringBar(size_hint_x=.5)
        steering_row.add_widget(self.steering_bar)
        steering_row.add_widget(Widget(size_hint_x=.25))
        self.add_widget(steering_row)
        self.selection_label=self._label('',height=34)
        self.add_widget(self.selection_label)
        self.map_mode_button=self._button('Karte: Abstrakt',self.toggle_map_mode,155)
        header.add_widget(self.map_mode_button)

        body=BoxLayout(spacing=dp(8))
        self.add_widget(body)
        if MapView is not None:
            self.map_view=MapView(lat=51.3,lon=9.5,zoom=14,size_hint_x=.67)
            self.field_overlay=FieldOverlay(self.map_view)
            self.map_view.add_layer(self.field_overlay)
            self.field_overlay.set_abstract(True)
            self.guidance_overlay=GuidanceOverlay(self.map_view)
            self.map_view.add_layer(self.guidance_overlay)
            self.map_view.bind(zoom=lambda *_:self._scale_tractor())
            body.add_widget(self.map_view)
        else:
            self.map_view=self.field_overlay=self.guidance_overlay=None
            body.add_widget(Label(text='Karte nicht verfügbar: kivy-garden.mapview installieren',size_hint_x=.67))

        panel=BoxLayout(orientation='vertical',spacing=dp(5),padding=dp(6),size_hint_x=.33)
        body.add_widget(panel)
        self.order_label=self._label('Kein Arbeitsauftrag geladen',height=43)
        self.track_label=self._label('Spur: —',height=40)
        self.offset_label=self._label('Spurabweichung: —',height=40)
        self.remaining_label=self._label('Strecke: —',height=38)
        self.action_label=self._label('Geräteaktion: —',height=60)
        self.gps_label=self._label('GPS: —',height=34)
        self.speed_label=self._label('Geschwindigkeit: —',height=34)
        self.message_label=self._label('Bereit',height=65)
        for label in (self.order_label,self.track_label,self.offset_label,self.remaining_label,
                      self.action_label,self.gps_label,self.speed_label,self.message_label):
            panel.add_widget(label)
        phase=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(5))
        phase.add_widget(self._button('Hauptfeld',lambda:self.switch_phase('main')))
        phase.add_widget(self._button('Vorgewende',lambda:self.switch_phase('headland')))
        panel.add_widget(phase)
        controls=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(5))
        controls.add_widget(self._button('Vorige Spur',self.previous_track))
        controls.add_widget(self._button('Nächste Spur',self.next_track))
        panel.add_widget(controls)
        actions=BoxLayout(size_hint_y=None,height=dp(52),spacing=dp(5))
        actions.add_widget(self._button('Absenken bestätigen',lambda:self.confirm('lower')))
        actions.add_widget(self._button('Ausheben bestätigen',lambda:self.confirm('raise')))
        panel.add_widget(actions)
        panel.add_widget(Widget())
        self.update_selection()
        self._refresh_event=Clock.schedule_interval(lambda _dt:self.refresh(),self.refresh_interval)
        Clock.schedule_once(lambda _dt:self.refresh(),0)

    @staticmethod
    def _label(value,height=38):
        label=Label(text=value,size_hint_y=None,height=dp(height),halign='left',valign='middle')
        label.bind(size=lambda obj,_:setattr(obj,'text_size',(obj.width,None)))
        return label

    @staticmethod
    def _button(text,callback,width=None):
        kw={'size_hint_x':None,'width':dp(width)} if width else {}
        button=Button(text=text,background_normal='',background_color=GREEN,**kw)
        button.bind(on_release=lambda *_:callback())
        return button

    def open_settings(self):
        if self.on_settings:self.on_settings()

    def toggle_map_mode(self):
        self.abstract_map=not self.abstract_map
        self.map_mode_button.text='Karte: Abstrakt' if self.abstract_map else 'Karte: Normal'
        if self.field_overlay:
            self.field_overlay.set_abstract(self.abstract_map)

    def load_work_order(self,planning,guidance,objects):
        """Wird aus SettingsScreen nach erfolgreichem Laden aufgerufen."""
        self._loaded(planning,guidance,objects)

    def _loaded(self,planning,guidance,objects):
        self.steering_bar.update(None)
        self.navigator=GuidanceNavigator(guidance,planning)
        self.selection.update(objects)
        self.selection_changed()
        self.order_label.text=f"Arbeit: {planning.get('name','—')}"
        self.message_label.text='Hauptfeld geladen · Navigation bereit'
        self._update_track_display()

    def update_selection(self):
        def name(kind):
            return (self.selection.get(kind) or {}).get('name','nicht gewählt')
        self.selection_label.text=(f"Traktor: {name('tractor')}  ·  Gerät: {name('implement')}  ·  Feld: {name('field')}")

    def selection_changed(self):
        self.update_selection()
        field=self.selection.get('field')
        if self.field_overlay:
            self.field_overlay.set_data(field=field,track_points=[])
        if field and self.map_view and field_center:
            center=field_center(field)
            if center:
                self.map_view.center_on(*center)
                self.map_view.zoom=max(self.map_view.zoom,15)

    def _update_track_display(self):
        if not self.navigator:return
        self.steering_bar.update(None)
        nav=self.navigator
        track=nav.track
        if track is None:
            self.track_label.text='Keine Spuren in dieser Phase'
            return
        self.track_label.text=(f"{'Hauptfeld' if nav.state.phase=='main' else 'Vorgewende'}: "
                               f"Spur {nav.state.track_index+1}/{len(nav.tracks)}"
                               + (f" · Seite {track.get('side_id')}" if track.get('side_id') is not None else ''))
        if self.guidance_overlay:
            self.guidance_overlay.set_plan(nav.guidance,nav.state.phase,track['id'])

    def switch_phase(self,phase):
        if not self.navigator:return
        try:
            self.navigator.select(phase)
            self._update_track_display()
            self.message_label.text='Phase gewechselt · Gerät vor Beginn prüfen'
        except ValueError as exc:
            self.message_label.text=str(exc)

    def next_track(self):
        if not self.navigator:return
        try:
            if not self.navigator.next_track():
                self.message_label.text='Letzte Spur dieser Phase erreicht'
            else:
                self.message_label.text='Zur nächsten Spur rangieren · Gerät ausgehoben'
                self._update_track_display()
        except ValueError as exc:self.message_label.text=str(exc)

    def previous_track(self):
        if not self.navigator:return
        try:
            index=max(0,self.navigator.state.track_index-1)
            self.navigator.select(self.navigator.state.phase,index)
            self._update_track_display()
        except ValueError as exc:self.message_label.text=str(exc)

    def confirm(self,action):
        if not self.navigator:return
        data=self._latest_state or {}
        speed=data.get('speed_mps')
        stopped=(speed is not None and abs(float(speed))<=.15)
        try:
            self.navigator.confirm(action,stopped=stopped)
            self.message_label.text=('Absenken bestätigt · Gerät aktiv' if action=='lower'
                                     else 'Ausheben bestätigt · Spur abgeschlossen')
        except (ValueError,TypeError) as exc:
            self.message_label.text=str(exc)

    def refresh(self):
        if self.busy:return
        self.busy=True
        def worker():
            try:
                data=self.api_client.get('/api/vehicle/state')
                Clock.schedule_once(lambda _dt,value=data:self._show_state(value))
            except Exception as exc:
                Clock.schedule_once(lambda _dt,error=str(exc):self._show_error(error))
            finally:self.busy=False
        threading.Thread(target=worker,daemon=True).start()

    def _show_error(self,error):
        self.gps_label.text='Backend: nicht erreichbar'
        self.message_label.text=error
        self.steering_bar.update(None)
        if self.navigator:self.navigator.update(0,0,gps_valid=False)

    def _show_state(self,data):
        self._latest_state=data
        valid=bool(data.get('gps_valid') and data.get('available'))
        lat,lon=data.get('latitude'),data.get('longitude')
        valid=valid and lat is not None and lon is not None
        self.gps_label.text='GPS: gültig' if valid else 'GPS: kein aktueller Fix'
        speed=data.get('speed_mps')
        self.speed_label.text=(f'Geschwindigkeit: {float(speed)*3.6:.1f} km/h'
                               if speed is not None else 'Geschwindigkeit: —')
        if valid and self.map_view and TractorMarker:
            self.map_view.center_on(float(lat),float(lon))
            if self._marker is None:
                self._marker=TractorMarker(lat=float(lat),lon=float(lon),source=str(TRACTOR_ICON),size=(dp(48),dp(48)))
                self.map_view.add_widget(self._marker)
            self._marker.lat=float(lat)
            self._marker.lon=float(lon)
            self._scale_tractor()
            heading=data.get('heading_deg')
            if heading is not None and data.get('imu_valid'):
                self._marker.set_heading(heading)
        if self.navigator:
            fix=self.navigator.update(lon,lat,gps_valid=valid) if valid else self.navigator.update(0,0,gps_valid=False)
            if fix:
                signed=fix['signed_offset_m']
                self.steering_bar.update(signed, reverse=self._driving_reverse(data))
                self.offset_label.text=(f'Spurabweichung: {abs(signed):.2f} m '
                                        + ('links' if signed>0 else 'rechts' if signed<0 else 'mittig'))
                self.remaining_label.text=f"Bis Spurende: {fix['remaining_m']:.1f} m"
                action=fix['event_action']
                if action:
                    self.action_label.text=(('Absenken' if action=='lower' else 'Ausheben')
                                            + f" · Stopppunkt {fix['event_distance_m']:.1f} m")
                else:
                    self.action_label.text='Spur abgeschlossen · nächste Spur wählen'
            else:
                self.steering_bar.update(None)
                self.offset_label.text='Spurabweichung: GPS fehlt'
                self.remaining_label.text='Strecke: —'
                self.action_label.text='Keine Gerätebestätigung ohne GPS'
        elif not valid:
            self.steering_bar.update(None)
            self.message_label.text=str(data.get('reason') or 'Kein gültiger GPS-Fix')
        if self.on_status:self.on_status(self.message_label.text)

    def _driving_reverse(self, data):
        """Fahrtrichtung zur gewählten Spur, nicht Rückwärtsgang-Erkennung."""
        from pytrac_kivy.ui.steering_direction import is_reverse_to_track
        if not self.navigator or not self.navigator.track:
            return False
        return is_reverse_to_track(data.get('heading_deg'),
                                   self.navigator.track.get('coordinates'),
                                   heading_valid=bool(data.get('imu_valid')))

    def _scale_tractor(self):
        if not self._marker or not self.map_view:
            return
        from pytrac_kivy.ui.map_scale import meters_to_pixels
        # Traktor als ca. 4,5 m langes Symbol; aus Darstellungsgründen begrenzt.
        px=meters_to_pixels(self.map_view,self._marker.lat,self._marker.lon,4.5)
        length=max(dp(14),min(dp(190),px))
        self._marker.size=(length*.65,length)

    def stop(self):
        if self._refresh_event:
            self._refresh_event.cancel()
            self._refresh_event=None

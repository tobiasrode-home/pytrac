"""PyTrac-Ackernavi: gespeicherte Arbeit laden und mit GPS manuell abfahren.

Keine Lenkbefehle, keine automatische Gerätebetätigung. Das Rangieren im
Vorgewende bleibt beim Fahrer. GPS muss gültig sein.
"""
import threading
from pathlib import Path
from pytrac_kivy.ui.stop_distance import stop_distance_text, signed_distance_to_stop
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics import PushMatrix, PopMatrix, Rotate
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget

from pytrac_kivy.ui.guidance_navigation import GuidanceNavigator
from pytrac_kivy.ui.steering_bar import SteeringBar
from pytrac_kivy.ui.map_autozoom import fit_field_zoom
from pytrac_kivy.ui.gps_filter import AdaptiveGpsFilter, adjusted_heading

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
        self.refresh_interval=max(.2,float(refresh_interval))
        self.busy=False
        self.navigator=None
        self._marker=None
        self._latest_state=None
        self.gps_filter=AdaptiveGpsFilter()
        self.gps_smoothing_enabled=False
        self.imu_heading_offset_deg=0.0
        self._last_gps_sample=None
        self.abstract_map=True
        self._refresh_event=None

        # Die Lenkhilfe belegt die gesamte Displaybreite und steht ganz oben.
        self.steering_bar=SteeringBar(size_hint_y=None,height=dp(86))
        self.add_widget(self.steering_bar)
        # Kompakte, durchgehende Statuszeile unter der Lenkempfehlung.
        self.selection_label=self._label('',height=36)
        self.selection_label.font_size='13sp'
        self.selection_label.shorten=True
        self.selection_label.shorten_from='right'
        self.add_widget(self.selection_label)
        self._popup=None
        self._popup_key=None
        self._dismissed_event=None
        self.recording=False
        self.record_override=None  # None=Automatik, True=manuell AN, False=manuell AUS
        self.recorded_points=[]  # Kompatibilitätszähler für aktuelle Sitzung
        self._recorded_count=0
        self._last_record_signature=None
        self.progress_points=[]
        self._popup_distance_label=None
        self._popup_action=None
        self._popup_feedback_label=None

        body=BoxLayout(spacing=dp(8))
        self.add_widget(body)
        if MapView is not None:
            self.map_view=MapView(lat=51.3,lon=9.5,zoom=14)
            self.field_overlay=FieldOverlay(self.map_view)
            self.map_view.add_layer(self.field_overlay)
            self.field_overlay.set_abstract(True)
            self.guidance_overlay=GuidanceOverlay(self.map_view)
            self.map_view.add_layer(self.guidance_overlay)
            self.map_view.bind(zoom=lambda *_:self._scale_tractor())
            body.add_widget(self.map_view)
        else:
            self.map_view=self.field_overlay=self.guidance_overlay=None
            body.add_widget(Label(text='Karte nicht verfügbar: kivy-garden.mapview installieren'))

        # Interne Statuslabels bleiben für bestehende Abläufe und Fehlermeldungen
        # erhalten, werden aber NICHT als rechte Seitenleiste angezeigt.
        self.order_label=self._label('Kein Arbeitsauftrag geladen',height=43)
        self.track_label=self._label('Spur: —',height=40)
        self.offset_label=self._label('Spurabweichung: —',height=40)
        self.remaining_label=self._label('Strecke: —',height=38)
        self.action_label=self._label('Geräteaktion: —',height=60)
        self.gps_label=self._label('GPS: —',height=34)
        self.speed_label=self._label('Geschwindigkeit: —',height=34)
        self.message_label=self._label('Bereit',height=65)
        # Alle Bedienelemente in einer durchgehenden unteren Leiste.
        footer=BoxLayout(size_hint_y=None,height=dp(60),spacing=dp(6))
        self.add_widget(footer)
        for title,callback in (
            ('Einstellungen',self.open_settings),
            ('Karte',self.toggle_map_mode),
            ('Hauptfeld',lambda:self.switch_phase('main')),
            ('Vorgewende',lambda:self.switch_phase('headland')),
            ('Vorige Spur',self.previous_track),
            ('Nächste Spur',self.next_track),
        ):
            footer.add_widget(self._button(title,callback))
        self.record_button=self._button('GPS: pausiert',self.toggle_record_override)
        footer.add_widget(self.record_button)
        self._update_record_button()
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
        if self.field_overlay:
            self.field_overlay.set_abstract(self.abstract_map)

    def load_work_order(self,planning,guidance,objects):
        """Wird aus SettingsScreen nach erfolgreichem Laden aufgerufen."""
        self._loaded(planning,guidance,objects)

    def _loaded(self,planning,guidance,objects):
        self.steering_bar.update(None)
        self.recording=False
        self.record_override=None
        self.recorded_points=[]
        self._last_record_signature=None
        self.progress_points=[]
        self._recorded_count=0
        self._dismissed_event=None
        self._update_record_button()
        self.navigator=GuidanceNavigator(guidance,planning)
        self._reference_rebuilt=(guidance.get("reference_source")=="driven")
        self.selection.update(objects)
        self.selection_changed()
        self.order_label.text=f"Arbeit: {planning.get('name','—')}"
        self.update_selection()
        self.message_label.text='Hauptfeld geladen · Navigation bereit'
        self._update_track_display()
        self._load_progress(planning['id'])
        Clock.schedule_once(lambda _dt:self._fit_loaded_field(),0.25)

    def reset_work_order(self):
        """Nur aktive Auswahl zurücksetzen, keine gespeicherten Daten löschen."""
        self.recording=False
        self.record_override=None
        self.navigator=None
        self.progress_points=[]
        self._recorded_count=0
        self._last_record_signature=None
        self._update_record_button()
        self.order_label.text="Kein Arbeitsauftrag geladen"
        self.track_label.text="Spur: —"
        self.message_label.text="Arbeitsauftrag abgewählt"
        self.steering_bar.update(None)
        self.selection_changed()
        if self.guidance_overlay:
            self.guidance_overlay.set_plan({},'main','')
        self._draw_progress()

    def _load_progress(self,planning_id):
        """Nachladen aus tractor.db über die lokale API."""
        def worker():
            try:
                result=self.api_client.get(f"/api/work-plannings/{planning_id}/progress")
                Clock.schedule_once(lambda _dt:self._apply_progress(planning_id,result))
            except Exception as exc:
                Clock.schedule_once(lambda _dt,error=str(exc):setattr(self.message_label,'text','Fahrdaten laden fehlgeschlagen: '+error))
        threading.Thread(target=worker,daemon=True).start()

    def _apply_progress(self,planning_id,result):
        if not self.navigator or self.navigator.planning['id']!=planning_id:return
        self.progress_points=list(result.get('points',[]))
        self._recorded_count=len(self.progress_points)
        if self.progress_points:
            last=self.progress_points[-1]
            phase=last.get("phase","main")
            tracks=self.navigator.guidance.get("tracks" if phase=="main" else "headland_tracks",[])
            index=next((i for i,t in enumerate(tracks) if str(t.get("id"))==str(last.get("track_id"))),None)
            if index is not None:
                try:self.navigator.select(phase,index)
                except ValueError:pass
                self._update_track_display()
        self._draw_progress()
        self.message_label.text=f"{self._recorded_count} GPS-Punkte geladen · letzte Spur gewählt, Gerät erneut bestätigen"

    def _draw_progress(self):
        if self.field_overlay:
            self.field_overlay.set_data(field=self.selection.get('field'),track_points=self.progress_points,
                                        working_width_m=(self.selection.get('implement') or {}).get('working_width_m',0))

    def _fit_loaded_field(self):
        if not self.map_view:return
        field=self.selection.get('field')
        if not field:return
        zoom=fit_field_zoom(field,self.map_view.width,self.map_view.height)
        center=field_center(field) if field_center else None
        if center:self.map_view.center_on(*center)
        if zoom is not None:self.map_view.zoom=zoom

    def update_selection(self):
        def name(kind):
            return str((self.selection.get(kind) or {}).get('name') or '—')
        nav=self.navigator
        valid=bool((self._latest_state or {}).get('gps_valid') and
                   (self._latest_state or {}).get('available'))
        if nav and nav.track:
            track=f'{nav.state.track_index+1}/{len(nav.tracks)}'
        else:
            track='—/—'
        implement='Aktiv' if nav and nav.state.active else 'Bereit'
        planning=nav.planning if nav else {}
        work=str(planning.get('name') or '—')
        ident=str(planning.get('id') or '—')
        speed=(self._latest_state or {}).get('speed_mps')
        try:
            speed_text=f'{max(0.0,float(speed))*3.6:.1f} km/h' if valid and speed is not None else '— km/h'
        except (TypeError,ValueError):
            speed_text='— km/h'
        quality=(self._latest_state or {}).get('gps_fix_quality')
        gps_status=({4:'RTK Fix',5:'RTK Float',2:'DGPS'}.get(quality,'GPS') if valid else 'N/A')
        self.selection_label.text=(
            f"GPS: {gps_status}   |   Tempo: {speed_text}   |   Spur: {track}   |   "
            f"Arbeitsgerät: {implement}   |   Arbeit: {work} "
            f"({name('tractor')}, {name('implement')}, {name('field')}, ID {ident})")

    def selection_changed(self):
        self.update_selection()
        field=self.selection.get('field')
        if self.field_overlay:
            self.field_overlay.set_data(field=field,track_points=self.progress_points,
                                        working_width_m=(self.selection.get("implement") or {}).get("working_width_m",0))
        if field and self.map_view and field_center:
            center=field_center(field)
            if center:
                self.map_view.center_on(*center)
                Clock.schedule_once(lambda _dt:self._fit_loaded_field(),0.15)

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
        self.update_selection()

    def switch_phase(self,phase):
        if not self.navigator:return
        try:
            self.navigator.select(phase)
            self._dismissed_event=None
            self._update_track_display()
            self.message_label.text='Phase gewechselt · Gerät vor Beginn prüfen'
        except ValueError as exc:
            self.message_label.text=str(exc)

    def next_track(self):
        if not self.navigator:return
        nav=self.navigator
        if (nav.guidance.get('guidance_mode')=='boundary_reference'
                and nav.state.phase=='main' and nav.state.track_index==0
                and nav.state.confirmed_raise and not getattr(self,'_reference_rebuilt',False)):
            self._finish_reference_track()
            return
        try:
            if not self.navigator.next_track():
                self.message_label.text='Letzte Spur dieser Phase erreicht'
            else:
                self.message_label.text='Zur nächsten Spur rangieren · Gerät ausgehoben'
                self._dismissed_event=None
                self._dismissed_event=None
            self._update_track_display()
        except ValueError as exc:self.message_label.text=str(exc)

    def _finish_reference_track(self):
        """Abgeschlossene erste Fahrt als tatsächliche Referenz übernehmen."""
        nav=self.navigator
        planning_id=nav.planning['id']
        self.message_label.text='Referenzfahrt wird übernommen …'
        def worker():
            try:
                guidance=self.api_client.post(
                    f'/api/work-plannings/{planning_id}/guidance',
                    {'output_mode':'targets','use_recorded_reference':True})
                if guidance.get('reference_source')!='driven':
                    raise ValueError('Mindestens zwei GPS-Punkte auf Spur 1 erforderlich')
                Clock.schedule_once(lambda _dt:self._apply_driven_reference(planning_id,guidance))
            except Exception as exc:
                Clock.schedule_once(lambda _dt,msg=str(exc):setattr(self.message_label,'text',
                    'Referenzfahrt konnte nicht übernommen werden: '+msg))
        threading.Thread(target=worker,daemon=True).start()

    def _apply_driven_reference(self,planning_id,guidance):
        if not self.navigator or self.navigator.planning['id']!=planning_id:return
        nav=self.navigator
        nav.guidance=guidance
        self._reference_rebuilt=True
        if nav.next_track():
            self.message_label.text='Folgespuren aus tatsächlicher Referenzfahrt berechnet'
        else:
            self.message_label.text='Keine weitere Spur vorhanden'
        self._update_track_display()

    def previous_track(self):
        if not self.navigator:return
        try:
            index=max(0,self.navigator.state.track_index-1)
            self.navigator.select(self.navigator.state.phase,index)
            self._dismissed_event=None
            self._update_track_display()
        except ValueError as exc:self.message_label.text=str(exc)

    def _update_record_button(self):
        """Status und Bedienknopf für manuelle GPS-Übersteuerung."""
        if self.record_override is None:
            self.record_button.text=('GPS: läuft\
AUTO' if self.recording
                                     else 'GPS: pausiert\
AUTO')
        else:
            self.record_button.text=('GPS: läuft\
MANUELL' if self.recording
                                     else 'GPS: pausiert\
MANUELL')

    def toggle_record_override(self):
        """Manuelle Aufnahme unabhängig von der bestätigten Geräteposition.

        Tippen wechselt den aktuellen Aufnahmestatus. Die nächste
        Gerätebestätigung gibt die Kontrolle wieder an die Automatik zurück.
        """
        if not self.navigator:
            self.message_label.text='Zuerst einen Arbeitsauftrag laden'
            return
        self.record_override=not self.recording
        self.recording=self.record_override
        self._update_record_button()
        self.message_label.text=('GPS manuell gestartet – unabhängig vom Gerätestatus'
                                 if self.recording else
                                 'GPS manuell pausiert – unabhängig vom Gerätestatus')

    def _show_event_popup(self,action,manual=False):
        if not self.navigator or self._popup is not None:
            return
        fix=self.navigator.last_fix
        key=(self.navigator.state.phase,self.navigator.state.track_index,action)
        if not manual and (key==self._dismissed_event or not fix or
                           fix.get('event_distance_m') is None or
                           fix['event_distance_m']>5.0):
            return
        title='Anbaugerät absenken' if action=='lower' else 'Anbaugerät ausheben'
        layout=BoxLayout(orientation='vertical',padding=dp(18),spacing=dp(16))
        layout.add_widget(Label(text=title+'\
Anhalten, Gerät manuell bedienen und bestätigen.',
                                font_size='23sp',halign='center'))
        self._popup_distance_label=Label(text='GPS-Abstand wird berechnet …',
                                         font_size='29sp',bold=True,
                                         size_hint_y=None,height=dp(65))
        layout.add_widget(self._popup_distance_label)
        self._popup_action=action
        self._update_popup_distance()
        self._popup_feedback_label=Label(text='GPS kann schwanken. Gerät erst manuell bedienen.',
                                          font_size='17sp',halign='center',
                                          size_hint_y=None,height=dp(46))
        layout.add_widget(self._popup_feedback_label)
        big=Button(text=('ABSENKEN BESTÄTIGEN' if action=='lower' else 'AUSHEBEN BESTÄTIGEN'),
                   size_hint_y=None,height=dp(135),font_size='27sp',bold=True,
                   background_normal='',background_color=GREEN)
        layout.add_widget(big)
        cancel=Button(text='Später',size_hint_y=None,height=dp(52))
        layout.add_widget(cancel)
        popup=Popup(title='Geräte-Stopp',content=layout,size_hint=(.82,.78),
                    auto_dismiss=False)
        self._popup=popup
        def dismiss_later(*_):
            self._dismissed_event=key
            popup.dismiss()
            self._popup=None
            self._popup_distance_label=None
            self._popup_action=None
            self._popup_feedback_label=None
        def do_confirm(*_):
            self.confirm(action)
            if self.navigator and ((action=='lower' and self.navigator.state.confirmed_lower)
                                   or (action=='raise' and self.navigator.state.confirmed_raise)):
                self.record_override=None
                self.recording=(action=='lower')
                self._update_record_button()
                self._dismissed_event=None
                popup.dismiss()
                self._popup=None
                self._popup_distance_label=None
                self._popup_action=None
                self._popup_feedback_label=None
            else:
                # Fehler direkt im sichtbaren Popup ausgeben.
                if self._popup_feedback_label:
                    self._popup_feedback_label.text=self.message_label.text
        big.bind(on_release=do_confirm)
        cancel.bind(on_release=dismiss_later)
        popup.open()

    def _update_popup_distance(self):
        if self._popup_distance_label is None or not self.navigator:
            return
        fix=self.navigator.last_fix
        if not fix or fix.get('event_action')!=self._popup_action:
            self._popup_distance_label.text='GPS-Signal fehlt – bitte warten'
            return
        distance=fix.get('event_distance_m')
        text=stop_distance_text(distance)
        event=self.navigator.event(self._popup_action)
        target=(event.get('vehicle_stop_coordinate') or event.get('coordinate')) if event else None
        state=self._latest_state or {}
        if target and state.get('latitude') is not None and state.get('longitude') is not None:
            along=signed_distance_to_stop(
                [state['longitude'],state['latitude']],target,
                self.navigator.track.get('coordinates',[]))
            if along is not None and along < -0.15:
                text='Stopppunkt passiert · '+text.replace('Noch ','Abstand ')
        if distance is not None and distance <= 0.30:
            text='Stopppunkt erreicht · '+f'{distance*100:.0f} cm Abstand'
        self._popup_distance_label.text=text

    def confirm(self,action):
        if not self.navigator:return
        data=self._latest_state or {}
        speed=data.get('speed_mps')
        stopped=(speed is not None and abs(float(speed))<=.15)
        try:
            self.navigator.confirm(action,stopped=stopped,distance_tolerance_m=5.0)
            self.message_label.text=('Absenken bestätigt · Gerät aktiv' if action=='lower'
                                     else 'Ausheben bestätigt · Spur abgeschlossen')
        except (ValueError,TypeError) as exc:
            self.message_label.text=str(exc)
            self._update_popup_distance()
            if self._popup_feedback_label:
                self._popup_feedback_label.text=str(exc)

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
        self.update_selection()
        if self.navigator:self.navigator.update(0,0,gps_valid=False)

    def set_navigation_settings(self,data):
        enabled=bool(data.get("gps_smoothing_enabled",False))
        offset=float(data.get("imu_heading_offset_deg",0.))
        if enabled!=self.gps_smoothing_enabled:
            self.gps_filter.reset()
            self._last_gps_sample=None
        self.gps_smoothing_enabled=enabled
        self.imu_heading_offset_deg=offset

    def _show_state(self,data):
        # Rohdaten bleiben unverändert im Backend. Anzeige und Navigation
        # erhalten eine Kopie mit korrigierter IMU-Ausrichtung und optional
        # gefilterten Koordinaten.
        data=dict(data)
        valid=bool(data.get('gps_valid') and data.get('available'))
        lat,lon=data.get('latitude'),data.get('longitude')
        valid=valid and lat is not None and lon is not None
        if data.get('imu_valid') and data.get('heading_deg') is not None:
            data['heading_deg']=adjusted_heading(data['heading_deg'],self.imu_heading_offset_deg)
        if valid:
            raw_sample=(data.get('timestamp'),float(lat),float(lon))
            sample=raw_sample
            if sample==self._last_gps_sample:
                # Kein neuer Sensor-Fix: Position unverändert lassen.
                if self._latest_state:
                    lat=self._latest_state.get('latitude',lat)
                    lon=self._latest_state.get('longitude',lon)
            else:
                self._last_gps_sample=sample
                if self.gps_smoothing_enabled:
                    try:
                        lat,lon=self.gps_filter.update(lat,lon,data.get('timestamp'),
                            speed_mps=data.get('speed_mps'),accuracy_m=data.get('gps_accuracy_m'))
                    except (ValueError,TypeError,OverflowError):
                        self.gps_filter.reset()
            data['latitude'],data['longitude']=lat,lon
        else:
            self.gps_filter.reset()
            self._last_gps_sample=None
        self._latest_state=data
        self.gps_label.text=(('GPS: gültig · geglättet' if self.gps_smoothing_enabled else 'GPS: gültig · roh')
                             if valid else 'GPS: kein aktueller Fix')
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
        if valid and self.recording and self.navigator and (self.navigator.state.active or self.record_override is True):
            try:
                # Sensor-Zeitstempel verhindert wiederholtes Speichern desselben Fixes.
                signature=raw_sample
                if signature!=self._last_record_signature:
                    from hashlib import sha256
                    fix_key=sha256(repr(signature).encode("utf-8")).hexdigest()
                    payload={"fix_key":fix_key,"phase":self.navigator.state.phase,
                             "track_id":str(self.navigator.track['id']),
                             "latitude":float(lat),"longitude":float(lon),
                             "speed_mps":speed,"accuracy_m":data.get('gps_accuracy_m')}
                    point=self.api_client.post(
                        f"/api/work-plannings/{self.navigator.planning['id']}/progress",payload)
                    self._last_record_signature=signature
                    if not any(p.get('fix_key')==fix_key for p in self.progress_points):
                        self.progress_points.append(point)
                    self._recorded_count=len(self.progress_points)
                    self._draw_progress()
            except Exception as exc:
                self.recording=False
                self._update_record_button()
                self.message_label.text=f'GPS-Speicherfehler: {exc} · nach Fehlerbehebung GPS-Knopf drücken'
        if self.navigator:
            fix=self.navigator.update(lon,lat,gps_valid=valid) if valid else self.navigator.update(0,0,gps_valid=False)
            if fix:
                self._update_popup_distance()
                signed=fix['signed_offset_m']
                self.steering_bar.update(signed, reverse=self._driving_reverse(data))
                self.offset_label.text=(f'Spurabweichung: {abs(signed):.2f} m '
                                        + ('links' if signed>0 else 'rechts' if signed<0 else 'mittig'))
                self.remaining_label.text=f"Bis Spurende: {fix['remaining_m']:.1f} m"
                action=fix['event_action']
                if action and fix.get('event_distance_m') is not None and fix['event_distance_m']<=5.0:
                    self._show_event_popup(action)
                if action:
                    self.action_label.text=(('Absenken' if action=='lower' else 'Ausheben')
                                            + f" · Stopppunkt {fix['event_distance_m']:.1f} m")
                else:
                    self.action_label.text='Spur abgeschlossen · nächste Spur wählen'
            else:
                self._update_popup_distance()
                self.steering_bar.update(None)
                self.offset_label.text='Spurabweichung: GPS fehlt'
                self.remaining_label.text='Strecke: —'
                self.action_label.text='Keine Gerätebestätigung ohne GPS'
        elif not valid:
            self.steering_bar.update(None)
            self.message_label.text=str(data.get('reason') or 'Kein gültiger GPS-Fix')
        self.update_selection()
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

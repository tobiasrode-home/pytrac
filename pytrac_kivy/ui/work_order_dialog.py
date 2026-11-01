"""Auswahl eines gespeicherten Arbeitsauftrags aus der Backend-Datenbank."""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
import threading
from pathlib import Path
from pytrac_kivy.ui.app_theme import apply_theme
from pytrac_kivy.ui.theme_colors import DARK, LIGHT
from kivy.app import App


def _current_palette():
    app = App.get_running_app()
    return DARK if bool(getattr(app, "_dark_mode", True)) else LIGHT


def _prepare_popup(popup):
    """Set popup background and widget colors before the first visible frame."""
    palette = _current_palette()
    dark = palette is DARK
    # Kivy's default Popup background atlas is dark even with a light tint.
    # An opaque white pixel makes the configured RGBA tint exact.
    popup.background = str(Path(__file__).with_name("popup_white.png"))
    popup.border = (0, 0, 0, 0)
    popup.background_color = palette["popup"]
    apply_theme(popup, dark)
    popup.background_color = palette["popup"]



def _picker_button(text, height):
    """Same dimensions and default colors as SettingsScreen.make_button."""
    palette = _current_palette()
    return Button(
        text=text, size_hint_y=None, height=height,
        background_normal='', background_down='',
        background_color=palette["button"],
        color=palette["button_text"], font_size='17sp',
    )


def open_work_order_dialog(api_client, on_loaded, selection=None):
    selection=selection or {}
    filters={key: (selection.get(key) or {}).get("id") for key in ("tractor", "implement", "field")}
    content=BoxLayout(orientation='vertical',spacing=dp(6),padding=dp(10))
    status=Label(text='Gespeicherte Arbeiten werden geladen …',size_hint_y=None,height=dp(35))
    content.add_widget(status)
    scroll=ScrollView()
    items=BoxLayout(orientation='vertical',spacing=dp(6),size_hint_y=None)
    items.bind(minimum_height=items.setter('height'))
    scroll.add_widget(items)
    content.add_widget(scroll)
    popup=Popup(title='Arbeitsauftrag auswählen',content=content,size_hint=(.85,.85))
    close=_picker_button('Abbrechen', dp(48))
    close.bind(on_release=lambda *_:popup.dismiss())
    content.add_widget(close)

    def fail(error):
        status.text=str(error)

    def populate(plans):
        plans=[plan for plan in plans if all(value is None or str(plan.get(key+'_id'))==str(value) for key,value in filters.items())]
        status.text=f'{len(plans)} passende Arbeitsaufträge' if plans else 'Keine Arbeitsaufträge für diese Auswahl gefunden'
        items.clear_widgets()
        for plan in plans:
            label=plan.get('name') or f"Arbeitsauftrag #{plan.get('id')}"
            button=_picker_button(label, dp(58))
            def choose(_button, selected=plan):
                status.text=f"Lade {selected.get('name','Arbeitsauftrag')} …"
                def load_session(session_id):
                    def worker():
                        try:
                            load_selected(selected, session_id)
                        except Exception as exc:
                            Clock.schedule_once(lambda _dt, error=str(exc):fail(error))
                    threading.Thread(target=worker,daemon=True).start()

                def load_selected(selected, session_id):
                    try:
                        # 'targets': keine ungeprüften Wendekurven als navigierbare Route.
                        use_driven=False
                        if selected.get('guidance_mode')=='boundary_reference':
                            progress=api_client.get(f"/api/work-plannings/{selected['id']}/progress")
                            use_driven=any(p.get('phase')=='main' and str(p.get('track_id'))!='1'
                                           for p in progress.get('points',[]))
                        guidance=api_client.post(f"/api/work-plannings/{selected['id']}/guidance",
                            {'output_mode':'targets','use_recorded_reference':use_driven})
                        field=api_client.get(f"/api/fields/{selected['field_id']}")
                        tractor=api_client.get(f"/api/tractors/{selected['tractor_id']}")
                        implement=api_client.get(f"/api/implements/{selected['implement_id']}")
                        def done(_dt):
                            selected_with_session=dict(selected, _work_session_id=session_id)
                            on_loaded(selected_with_session,guidance,{'field':field,'tractor':tractor,'implement':implement})
                            popup.dismiss()
                        Clock.schedule_once(done)
                    except Exception as exc:
                        Clock.schedule_once(lambda _dt, error=str(exc):fail(error))

                def ask_session(sessions):
                    content2=BoxLayout(orientation='vertical',spacing=dp(8),padding=dp(8))
                    content2.add_widget(Label(text='Neuen Einsatz starten oder vorhandenen fortsetzen?',size_hint_y=None,height=dp(45)))
                    history=ScrollView()
                    rows=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None)
                    rows.bind(minimum_height=rows.setter('height'))
                    history.add_widget(rows);content2.add_widget(history)
                    session_popup=Popup(title='Einsatz / Workhistory auswählen',content=content2,size_hint=(.8,.8))
                    def pick(session_id):
                        session_popup.dismiss()
                        load_session(session_id)
                    def create_new(*_):
                        def worker():
                            try:
                                created=api_client.post(f"/api/work-plannings/{selected['id']}/sessions",{})
                                Clock.schedule_once(lambda _dt:pick(created['id']))
                            except Exception as exc:
                                Clock.schedule_once(lambda _dt,error=str(exc):fail(error))
                        threading.Thread(target=worker,daemon=True).start()
                    new_btn=_picker_button('Neuen Einsatz beginnen', dp(58))
                    new_btn.bind(on_release=create_new);content2.add_widget(new_btn)
                    for entry in sessions:
                        title=entry.get('name') or entry.get('started_at','')[:16].replace('T',' ')
                        b=_picker_button(f"Fortsetzen: {title} ({entry.get('point_count',0)} Punkte)", dp(58))
                        b.bind(on_release=lambda _btn,session_id=entry['id']:pick(session_id))
                        rows.add_widget(b)
                    cancel=_picker_button('Abbrechen', dp(48))
                    cancel.bind(on_release=lambda *_:session_popup.dismiss());content2.add_widget(cancel)
                    _prepare_popup(session_popup)
                    session_popup.open()
                def session_worker():
                    try:
                        sessions=api_client.get(f"/api/work-plannings/{selected['id']}/sessions")
                        Clock.schedule_once(lambda _dt:ask_session(sessions))
                    except Exception as exc:
                        Clock.schedule_once(lambda _dt,error=str(exc):fail(error))
                threading.Thread(target=session_worker,daemon=True).start()
            button.bind(on_release=choose)
            items.add_widget(button)
        _prepare_popup(popup)

    def worker():
        try:
            plans=api_client.get('/api/work-plannings')
            Clock.schedule_once(lambda _dt:populate(plans))
        except Exception as exc:
            Clock.schedule_once(lambda _dt,error=str(exc):fail(error))
    threading.Thread(target=worker,daemon=True).start()
    _prepare_popup(popup)
    popup.open()
    return popup

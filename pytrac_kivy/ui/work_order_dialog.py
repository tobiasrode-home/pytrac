"""Auswahl eines gespeicherten Arbeitsauftrags aus der Backend-Datenbank."""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
import threading


def open_work_order_dialog(api_client, on_loaded):
    content=BoxLayout(orientation='vertical',spacing=dp(8),padding=dp(8))
    status=Label(text='Gespeicherte Arbeiten werden geladen …',size_hint_y=None,height=dp(35))
    content.add_widget(status)
    scroll=ScrollView()
    items=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None)
    items.bind(minimum_height=items.setter('height'))
    scroll.add_widget(items)
    content.add_widget(scroll)
    popup=Popup(title='Arbeitsauftrag laden',content=content,size_hint=(.8,.85))
    close=Button(text='Schließen',size_hint_y=None,height=dp(44))
    close.bind(on_release=lambda *_:popup.dismiss())
    content.add_widget(close)

    def fail(error):
        status.text=str(error)

    def populate(plans):
        status.text=f'{len(plans)} gespeicherte Arbeitsaufträge'
        for plan in plans:
            label=f"{plan.get('name','Ohne Namen')}  ·  #{plan.get('id')}"
            button=Button(text=label,size_hint_y=None,height=dp(54))
            def choose(_button, selected=plan):
                status.text=f"Lade {selected.get('name','Arbeitsauftrag')} …"
                def worker():
                    try:
                        # 'targets': keine ungeprüften Wendekurven als navigierbare Route.
                        guidance=api_client.post(f"/api/work-plannings/{selected['id']}/guidance",{'output_mode':'targets'})
                        field=api_client.get(f"/api/fields/{selected['field_id']}")
                        tractor=api_client.get(f"/api/tractors/{selected['tractor_id']}")
                        implement=api_client.get(f"/api/implements/{selected['implement_id']}")
                        def done(_dt):
                            on_loaded(selected,guidance,{'field':field,'tractor':tractor,'implement':implement})
                            popup.dismiss()
                        Clock.schedule_once(done)
                    except Exception as exc:
                        Clock.schedule_once(lambda _dt, error=str(exc):fail(error))
                threading.Thread(target=worker,daemon=True).start()
            button.bind(on_release=choose)
            items.add_widget(button)

    def worker():
        try:
            plans=api_client.get('/api/work-plannings')
            Clock.schedule_once(lambda _dt:populate(plans))
        except Exception as exc:
            Clock.schedule_once(lambda _dt,error=str(exc):fail(error))
    threading.Thread(target=worker,daemon=True).start()
    popup.open()
    return popup

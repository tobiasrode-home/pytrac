"""Arbeitsplanung direkt am Pi, mit denselben Backend-APIs wie das Webfrontend."""
import threading
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from pytrac_kivy.ui.fullscreen_keyboard import bind_fullscreen_keyboard

def open_create_work_order(api,choices,on_created):
    content=BoxLayout(orientation="vertical",spacing=dp(7),padding=dp(10))
    scroll=ScrollView()
    form=BoxLayout(orientation="vertical",spacing=dp(6),size_hint_y=None)
    form.bind(minimum_height=form.setter("height"))
    scroll.add_widget(form);content.add_widget(scroll)
    popup=Popup(title="Neuen Arbeitsauftrag anlegen",content=content,size_hint=(.94,.94))
    def row(label,widget):
        box=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(6))
        box.add_widget(Label(text=label,size_hint_x=.43))
        box.add_widget(widget);form.add_widget(box)
    def entry(label,default="",numeric=False):
        widget=TextInput(text=str(default),multiline=False,input_filter="float" if numeric else None)
        bind_fullscreen_keyboard(widget,label)
        row(label,widget);return widget
    name=entry("Bezeichnung")
    def select(label,values):
        widget=Spinner(text=values[0] if values else "Keine Auswahl",values=values)
        row(label,widget);return widget
    lookup={}
    for kind,label in (("tractor","Traktor"),("implement","Anbaugerät"),("field","Feld")):
        records=choices.get(kind,[])
        names=[f"{x['name']} (#{x['id']})" for x in records]
        widget=select(label,names)
        lookup[kind]=(widget,dict(zip(names,records)))
    edges=select("Ausrichtungskante",["edge-0"])
    start_a=select("Startgrenze A",["edge-1"])
    start_b=select("Startgrenze B",["edge-2"])
    widths=entry("Vorgewende-Breiten","",numeric=True)
    speed=entry("Geschwindigkeit km/h","",numeric=True)
    turn=select("Wendemanöver",["u_turn","y_turn"])
    headland=select("Vorgewende",["all_around","headlands_only"])
    status=Label(text="Feld und Gerät auswählen",size_hint_y=None,height=dp(52))
    content.add_widget(status)
    def selected(kind):
        widget,records=lookup[kind]
        if widget.text not in records:raise ValueError(kind+" auswählen")
        return records[widget.text]
    def update_edges(*_):
        try:
            field=selected("field")
            boundary=field.get("boundary") or []
            if isinstance(boundary,dict):boundary=boundary.get("coordinates",[[]])[0]
            count=len(boundary)-1 if len(boundary)>1 and boundary[0]==boundary[-1] else len(boundary)
            values=[f"edge-{i}" for i in range(max(0,count))]
            if len(values)<3:raise ValueError("Feld benötigt mindestens drei Kanten")
            for widget,default in ((edges,0),(start_a,1),(start_b,2)):
                widget.values=values;widget.text=values[default]
        except Exception as exc:status.text=str(exc)
    lookup["field"][0].bind(text=update_edges)
    update_edges()
    def worker():
        try:
            tractor=selected("tractor");implement=selected("implement");field=selected("field")
            payload={"name":name.text.strip(),"tractor_id":tractor["id"],
                     "implement_id":implement["id"],"field_id":field["id"],
                     "turn_type":turn.text,"headland_mode":headland.text,
                     "bed_working":False,"alignment_boundary_id":edges.text,
                     "start_boundary_a_id":start_a.text,"start_boundary_b_id":start_b.text,
                     "headland_working_widths":int(float(widths.text)) if widths.text.strip() else None,
                     "speed":float(speed.text) if speed.text.strip() else None}
            if not payload["name"]:raise ValueError("Bezeichnung fehlt")
            if payload["start_boundary_a_id"]==payload["start_boundary_b_id"]:
                raise ValueError("Zwei verschiedene Startgrenzen wählen")
            if payload["headland_working_widths"] is None:
                defaults=api.post("/api/work-plannings/defaults",
                                  {"tractor_id":tractor["id"],"implement_id":implement["id"]})
                payload["headland_working_widths"]=defaults["default_headland_working_widths"]
            # Erst Vorschau prüfen, dann speichern und Spurführung berechnen.
            api.post("/api/work-plannings/preview",payload)
            plan=api.post("/api/work-plannings",payload)
            guidance=api.post(f"/api/work-plannings/{plan['id']}/guidance",{"output_mode":"targets"})
            Clock.schedule_once(lambda _dt:(popup.dismiss(),on_created(plan,guidance,
                                {"tractor":tractor,"implement":implement,"field":field})))
        except Exception as exc:
            Clock.schedule_once(lambda _dt,msg=str(exc):setattr(status,"text","Fehler: "+msg))
    footer=BoxLayout(size_hint_y=None,height=dp(55),spacing=dp(8))
    create=Button(text="Berechnen und speichern")
    create.bind(on_release=lambda *_:threading.Thread(target=worker,daemon=True).start())
    footer.add_widget(create)
    cancel=Button(text="Abbrechen");cancel.bind(on_release=lambda *_:popup.dismiss())
    footer.add_widget(cancel);content.add_widget(footer)
    popup.open()
    return popup

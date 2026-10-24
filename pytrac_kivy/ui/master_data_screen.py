"""PyTrac: Stammdaten verwalten, Touch-Tastatur mit stabilem Fokus (V17)."""
import math
import threading
import requests
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from pytrac_kivy.ui.keyboard import TouchKeyboard
from pytrac_kivy.ui.fullscreen_keyboard import open_fullscreen_keyboard

GPS_POLL_INTERVAL = 1.0
MIN_POINT_DISTANCE_M = 2.0

class MasterDataScreen(BoxLayout):
    def __init__(self, api_url, selection, api_client=None, on_back=None,
                 on_selection_changed=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(18), spacing=dp(12), **kwargs)
        self.api_url = api_url.rstrip("/")
        self.api_client = api_client
        self.selection = selection
        self.on_back = on_back
        self.on_selection_changed = on_selection_changed
        self.choices = {"tractor": [], "implement": [], "field": []}
        header = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(64), spacing=dp(12))
        header.add_widget(Label(text="[b]Stammdaten verwalten[/b]", markup=True,
                                font_size="24sp", halign="left"))
        header.add_widget(self.make_button("Zurück", self.go_back, width=dp(170)))
        self.add_widget(header)
        self.add_widget(Label(text="Wähle aus, welche Stammdaten du neu erfassen möchtest.",
                              size_hint_y=None, height=dp(60), halign="left", valign="middle"))
        self.add_widget(self.make_button("Traktor anlegen", lambda *_: self.open_form("tractor"), height=dp(76)))
        self.add_widget(self.make_button("Anbaugerät anlegen", lambda *_: self.open_form("implement"), height=dp(76)))
        self.add_widget(self.make_button("Feld per GPS erfassen", lambda *_: self.open_field_capture(), height=dp(76)))
        self.add_widget(Label(text="Felder werden durch Abfahren der Feldgrenze mit dem GPS des Pico erfasst.",
                              size_hint_y=None, height=dp(56), halign="left", valign="middle"))
        self.status_label = Label(text="Bereit zur Stammdatenerfassung.",
                                  size_hint_y=None, height=dp(48))
        self.add_widget(self.status_label)
        self.add_widget(Widget(size_hint_y=1))

    def make_button(self, text, callback, height=dp(54), width=None):
        button = Button(text=text, size_hint_y=None, height=height,
                        background_normal="", background_down="",
                        background_color=(0.16, 0.43, 0.28, 1),
                        color=(1, 1, 1, 1), font_size="17sp", bold=True)
        if width is not None:
            button.size_hint_x = None
            button.width = width
        button.bind(on_release=callback)
        return button

    def request(self, path, method="GET", payload=None):
        if self.api_client is not None:
            return self.api_client.request(path, method=method, payload=payload)
        response = requests.request(method, self.api_url + path, json=payload, timeout=8)
        response.raise_for_status()
        return response.json() if response.content else {}

    def attach_touch_keyboard(self, text_input, keyboard_container):
        """Bei Fokusverlust durch Tastendruck offen halten; FERTIG schließt."""
        state = {"keyboard": None}
        def finish_input(instance):
            keyboard_container.clear_widgets()
            keyboard_container.height = 0
            state["keyboard"] = None
            instance.focus = False

        def show_keyboard(instance, focused):
            if not focused:
                # Ein virtueller Button übernimmt Kivy-Fokus. Nicht schließen!
                return
            current = state["keyboard"]
            if current is not None and current.parent is keyboard_container:
                return
            keyboard_container.clear_widgets()
            keyboard_container.height = dp(210)
            numeric = getattr(instance, "input_filter", None) == "float"
            keyboard = TouchKeyboard(target=instance, numeric=numeric,
                                     on_done=lambda: finish_input(instance))
            state["keyboard"] = keyboard
            keyboard_container.add_widget(keyboard)

        text_input.bind(focus=show_keyboard)

    def load_choices(self, on_loaded=None):
        def worker():
            try:
                choices = {kind: self.request(endpoint) for kind, endpoint in
                           (("tractor", "/api/tractors"),
                            ("implement", "/api/implements"),
                            ("field", "/api/fields"))}
                Clock.schedule_once(lambda _dt: apply_choices(choices))
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(lambda _dt: setattr(
                    self.status_label, "text", "Laden fehlgeschlagen: " + message))
        def apply_choices(choices):
            self.choices = choices
            self.status_label.text = (
                f'{len(choices["tractor"])} Traktoren · '
                f'{len(choices["implement"])} Anbaugeräte · '
                f'{len(choices["field"])} Felder')
            if on_loaded:
                on_loaded(choices)
        threading.Thread(target=worker, daemon=True).start()

    def select_created(self, kind, created):
        selected = next((item for item in self.choices.get(kind, [])
                         if item.get("id") == created.get("id")), created)
        self.selection[kind] = selected
        if self.on_selection_changed:
            self.on_selection_changed()

    def _reload_and_select(self, kind, created):
        def loaded(_choices):
            self.select_created(kind, created)
            area = float(created.get("area_m2", 0.0)) / 10000.0
            suffix = f" · {area:.3f} ha" if kind == "field" else ""
            self.status_label.text = f'Gespeichert: {created.get("name", "Unbekannt")}{suffix}'
        self.load_choices(on_loaded=loaded)

    def open_form(self, kind):
        if kind == "tractor":
            title = "Neuen Traktor erfassen"
            fields = [
                ("name", "Name", "text", None),
                ("length_m", "Länge (m)", "number", "4.5"),
                ("width_m", "Breite (m)", "number", "2.5"),
                ("wheelbase_m", "Radstand (m)", "number", "2.8"),
                ("max_steering_angle_deg", "Max. Lenkwinkel (Grad)", "number", "35"),
                ("gps_offset_length_m", "GPS-Versatz längs (m)", "number", "0"),
                ("gps_offset_width_m", "GPS-Versatz seitlich (m)", "number", "0"),
            ]
            endpoint = "/api/tractors"
        elif kind == "implement":
            title = "Neues Anbaugerät erfassen"
            fields = [
                ("name", "Name", "text", None),
                ("length_m", "Länge (m)", "number", "2.0"),
                ("working_width_m", "Arbeitsbreite (m)", "number", "3.0"),
                ("mount_type", "Anbauart", "choice", "rear"),
                ("work_offset_m", "Arbeitsversatz (m)", "number", "0"),
            ]
            endpoint = "/api/implements"
        else:
            self.status_label.text = f"Unbekannter Erfassungstyp: {kind}"
            return

        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        form = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        keyboard_container = BoxLayout(orientation="vertical", size_hint_y=None, height=0)
        inputs = {}
        for key, label_text, input_type, default in fields:
            form.add_widget(Label(text=label_text, size_hint_y=None, height=dp(46),
                                  halign="left", valign="middle"))
            if input_type == "choice":
                widget = Spinner(
                    text={"front": "Vorne", "rear": "Hinten", "towed": "Gezogen"}.get(default, "Hinten"),
                    values=("Vorne", "Hinten", "Gezogen"),
                    size_hint_y=None, height=dp(46))
            else:
                widget = TextInput(
                    text=default or "", hint_text=label_text, multiline=False,
                    input_filter="float" if input_type == "number" else None,
                    size_hint_y=None, height=dp(46), write_tab=False)
            inputs[key] = widget
            form.add_widget(widget)
            if isinstance(widget, TextInput):
                self.attach_touch_keyboard(widget, keyboard_container)
        scroll.add_widget(form)
        content.add_widget(scroll)
        content.add_widget(keyboard_container)
        status = Label(text="", size_hint_y=None, height=dp(38), halign="left", valign="middle")
        content.add_widget(status)
        buttons = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(52))
        save_button = self.make_button("Speichern", lambda *_: save())
        buttons.add_widget(save_button)
        popup = Popup(title=title, content=content, size_hint=(0.95, 0.95), auto_dismiss=False)
        buttons.add_widget(self.make_button("Abbrechen", lambda *_: close_form()))
        content.add_widget(buttons)

        def hide_keyboard():
            keyboard_container.clear_widgets()
            keyboard_container.height = 0
            for widget in inputs.values():
                if isinstance(widget, TextInput):
                    widget.focus = False

        def close_form():
            hide_keyboard()
            popup.dismiss()

        def save():
            payload = {}
            try:
                for key, label_text, input_type, _default in fields:
                    widget = inputs[key]
                    if input_type == "choice":
                        payload[key] = {"Vorne": "front", "Hinten": "rear",
                                        "Gezogen": "towed"}[widget.text]
                    elif input_type == "number":
                        value = widget.text.strip().replace(",", ".")
                        if not value:
                            raise ValueError(f"Bitte '{label_text}' ausfüllen.")
                        number = float(value)
                        if not math.isfinite(number):
                            raise ValueError(f"'{label_text}' muss eine gültige Zahl sein.")
                        payload[key] = number
                    else:
                        payload[key] = widget.text.strip()
                if not payload.get("name"):
                    raise ValueError("Bitte einen Namen eingeben.")
            except (ValueError, KeyError) as exc:
                status.text = str(exc)
                return
            save_button.disabled = True
            status.text = "Speichere …"
            hide_keyboard()
            def worker():
                try:
                    created = self.request(endpoint, method="POST", payload=payload)
                    Clock.schedule_once(lambda _dt: saved(created))
                except Exception as exc:
                    message = str(exc)
                    Clock.schedule_once(lambda _dt: failed(message))
            def saved(created):
                popup.dismiss()
                self.status_label.text = "Gespeichert: " + str(created.get("name", payload["name"]))
                self._reload_and_select(kind, created)
            def failed(message):
                save_button.disabled = False
                status.text = "Speichern fehlgeschlagen: " + message
            threading.Thread(target=worker, daemon=True).start()
        popup.open()

    def open_field_capture(self):
        content = BoxLayout(orientation="vertical", spacing=dp(10), padding=dp(12))
        name_input = TextInput(hint_text="Feldname, z. B. Nordschlag", multiline=False,
                               size_hint_y=None, height=dp(52), write_tab=False)
        keyboard_container = BoxLayout(orientation="vertical", size_hint_y=None, height=0)
        # Feldname bekommt eine bildschirmfüllende Tastatur mit Eingabeanzeige oben.
        name_input.bind(on_touch_down=lambda instance,touch:
                        open_fullscreen_keyboard(instance,"Feldname eingeben")
                        if instance.collide_point(*touch.pos) else None)
        content.add_widget(name_input)
        content.add_widget(Widget(size_hint_y=None, height=dp(80)))
        content.add_widget(keyboard_container)
        content.add_widget(Label(
            text="Feldgrenze mit dem Traktor abfahren.\\n"
                 "Die Positionen kommen vom Pico über das Backend.",
            size_hint_y=None, height=dp(64)))
        status = Label(text="Bereit. GPS wird beim Start geprüft.", halign="center")
        content.add_widget(status)
        points = []
        state = {"recording": False, "busy": False}
        event = {"poll": None}
        buttons = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(60))
        start_button = self.make_button("Aufzeichnung starten", lambda *_: start_recording())
        stop_button = self.make_button("Stoppen und speichern", lambda *_: stop_recording())
        stop_button.disabled = True
        buttons.add_widget(start_button)
        buttons.add_widget(stop_button)
        content.add_widget(buttons)
        popup = Popup(title="Feld per GPS erfassen", content=content,
                      size_hint=(0.92, 0.82), auto_dismiss=False)
        content.add_widget(self.make_button("Abbrechen", lambda *_: cancel_capture()))

        def haversine_m(a, b):
            lon1, lat1 = a
            lon2, lat2 = b
            radius = 6371000.0
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            value = (math.sin(dphi / 2) ** 2 +
                     math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
            return 2 * radius * math.asin(math.sqrt(min(1.0, max(0.0, value))))

        def handle_gps(data):
            if not state["recording"]:
                return
            if not data.get("gps_valid", False):
                status.text = "GPS nicht zuverlässig: " + str(data.get("reason", "Kein gültiger Fix"))
                return
            try:
                lon, lat = float(data["longitude"]), float(data["latitude"])
            except (KeyError, TypeError, ValueError):
                status.text = "GPS-Antwort enthält keine gültigen Koordinaten."
                return
            if not (math.isfinite(lon) and math.isfinite(lat)
                    and -180 <= lon <= 180 and -90 <= lat <= 90):
                status.text = "Ungültige GPS-Koordinaten."
                return
            point = [lon, lat]
            if not points or haversine_m(points[-1], point) >= MIN_POINT_DISTANCE_M:
                points.append(point)
            status.text = f"Aufzeichnung läuft · {len(points)} Punkte · GPS gültig"

        def gps_error(message):
            if state["recording"]:
                status.text = "GPS/API-Fehler: " + message

        def poll_gps(_dt):
            if not state["recording"] or state["busy"]:
                return
            state["busy"] = True
            def worker():
                try:
                    data = self.request("/api/vehicle/state")
                    Clock.schedule_once(lambda _dt: handle_gps(data))
                except Exception as exc:
                    message = str(exc)
                    Clock.schedule_once(lambda _dt: gps_error(message))
                finally:
                    state["busy"] = False
            threading.Thread(target=worker, daemon=True).start()

        def start_recording():
            if not name_input.text.strip():
                status.text = "Bitte zuerst einen Feldnamen eingeben."
                return
            start_button.disabled = True
            status.text = "Prüfe GPS-Verbindung …"
            def worker():
                try:
                    data = self.request("/api/vehicle/state")
                    if not data.get("gps_valid", False):
                        raise ValueError("Kein gültiger GPS-Fix: " + str(data.get("reason", "unbekannt")))
                    Clock.schedule_once(lambda _dt: begin_recording(data))
                except Exception as exc:
                    message = str(exc)
                    Clock.schedule_once(lambda _dt: start_failed(message))
            threading.Thread(target=worker, daemon=True).start()

        def begin_recording(data):
            points.clear()
            state["recording"] = True
            handle_gps(data)
            stop_button.disabled = False
            status.text = f"Aufzeichnung läuft · {len(points)} Punkte"
            event["poll"] = Clock.schedule_interval(poll_gps, GPS_POLL_INTERVAL)

        def start_failed(message):
            start_button.disabled = False
            status.text = "Start nicht möglich: " + message

        def stop_recording():
            if not state["recording"]:
                return
            state["recording"] = False
            if event["poll"] is not None:
                event["poll"].cancel()
                event["poll"] = None
            stop_button.disabled = True
            if len(points) < 3:
                status.text = "Zu wenige GPS-Punkte. Mindestens drei Positionen sind erforderlich."
                start_button.disabled = False
                return
            ring = [point[:] for point in points]
            if ring[-1] != ring[0]:
                ring.append(ring[0][:])
            payload = {"name": name_input.text.strip(), "boundary": ring,
                       "reference_line": []}
            status.text = f"Speichere Feld mit {len(points)} GPS-Punkten …"
            def worker():
                try:
                    created = self.request("/api/fields", method="POST", payload=payload)
                    Clock.schedule_once(lambda _dt: field_saved(created))
                except Exception as exc:
                    message = str(exc)
                    Clock.schedule_once(lambda _dt: field_save_failed(message))
            threading.Thread(target=worker, daemon=True).start()

        def field_saved(created):
            popup.dismiss()
            self.status_label.text = "Feld gespeichert: " + str(created.get("name", name_input.text.strip()))
            self._reload_and_select("field", created)

        def field_save_failed(message):
            stop_button.disabled = True
            start_button.disabled = False
            status.text = "Speichern fehlgeschlagen: " + message

        def cancel_capture():
            state["recording"] = False
            if event["poll"] is not None:
                event["poll"].cancel()
                event["poll"] = None
            keyboard_container.clear_widgets()
            popup.dismiss()

        popup.open()

    def go_back(self, *_):
        if self.on_back:
            self.on_back()

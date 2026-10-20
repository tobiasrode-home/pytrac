"""PyTrac: Einstellungen und Erfassung von Traktoren, Anbaugeräten und Feldern."""

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


GPS_DEVICE_ID = "pico-tractor-01"
GPS_POLL_INTERVAL = 1.0
MIN_POINT_DISTANCE_M = 2.0


class SettingsScreen(BoxLayout):
    """Einstellungsseite mit Auswahl und Erfassung neuer Datensätze."""

    def __init__(
        self,
        api_url,
        selection,
        api_client=None,
        on_back=None,
        on_selection_changed=None,
        on_master_data=None,
        on_wifi_manager=None,
        **kwargs,
    ):
        super().__init__(
            orientation="vertical",
            padding=dp(18),
            spacing=dp(12),
            **kwargs,
        )

        self.api_url = api_url.rstrip("/")
        self.api_client = api_client
        self.selection = selection
        self.on_back = on_back
        self.on_selection_changed = on_selection_changed
        self.on_master_data = on_master_data
        self.on_wifi_manager = on_wifi_manager

        self.choices = {
            "tractor": [],
            "implement": [],
            "field": [],
        }
        self.selection_buttons = {}

        header = BoxLayout(
            size_hint_y=None,
            height=dp(58),
            spacing=dp(10),
        )
        header.add_widget(Label(
            text="[b]Einstellungen[/b]",
            markup=True,
            font_size="25sp",
            halign="left",
        ))
        header.add_widget(self.make_button(
            "Zur Übersicht",
            self.go_back,
            width=dp(180),
        ))

        header.add_widget(self.make_button(
            "Stammdaten",
            self.open_master_data,
            width=dp(180),
         ))
        
        header.add_widget(self.make_button(
            "Wifi",
            self.open_wifi_manager,
            width=dp(180),
            
        ))

        self.add_widget(header)

        self.add_widget(Label(
            text=(
                "Maschinenkonfiguration und Feld "
                "für den nächsten Arbeitsgang auswählen."
            ),
            size_hint_y=None,
            height=dp(52),
            halign="left",
        ))

        for kind, title in (
            ("tractor", "Traktor auswählen"),
            ("implement", "Anbaugerät auswählen"),
            ("field", "Feld auswählen"),
        ):
            self.add_widget(Label(
                text=title,
                size_hint_y=None,
                height=dp(32),
                halign="left",
                bold=True,
                font_size="17sp",
            ))

            button = self.make_button(
                self.selection_text(kind),
                lambda _btn, k=kind: self.open_picker(k),
                height=dp(68),
            )
            self.selection_buttons[kind] = button
            self.add_widget(button)


        self.status_label = Label(
            text="Lade Auswahlmöglichkeiten …",
            size_hint_y=None,
            height=dp(48),
        )
        self.add_widget(self.status_label)
        self.add_widget(WidgetSpacer())

        self.load_choices()

    # ---------------------------------------------------------------
    # UI und API
    # ---------------------------------------------------------------
    
    def attach_touch_keyboard(self, text_input, keyboard_container):
        """Bindet die vorhandene Bildschirmtastatur an ein TextInput."""

        def show_keyboard(instance, focused):
            keyboard_container.clear_widgets()

            if not focused:
                return

            numeric = (
                getattr(instance, "input_filter", None) == "float"
            )

            keyboard = TouchKeyboard(
                target=instance,
                numeric=numeric,
                on_done=lambda: finish_input(instance),
            )

            keyboard_container.add_widget(keyboard)

        def finish_input(instance):
            instance.focus = False
            keyboard_container.clear_widgets()

        text_input.bind(focus=show_keyboard)
        
    def make_button(
        self,
        text,
        callback,
        height=dp(54),
        width=None,
    ):
        button = Button(
            text=text,
            size_hint_y=None,
            height=height,
            background_normal="",
            background_down="",
            background_color=(0.16, 0.43, 0.28, 1),
            color=(1, 1, 1, 1),
            font_size="17sp",
            bold=True,
        )

        if width is not None:
            button.size_hint_x = None
            button.width = width

        button.bind(on_release=callback)
        return button

    def request(self, path, method="GET", payload=None):
        """Führt einen API-Aufruf aus und liefert JSON zurück."""
        if self.api_client is not None:
            return self.api_client.request(path, method=method, payload=payload)
        response = requests.request(
            method,
            self.api_url + path,
            json=payload,
            timeout=8,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def selection_text(self, kind):
        selected = self.selection.get(kind)

        title = {
            "tractor": "Traktor",
            "implement": "Anbaugerät",
            "field": "Feld",
        }[kind]

        if selected:
            return f'{title}: {selected.get("name", "Unbekannt")}'

        return f"{title}: noch nicht ausgewählt"

    def update_selection_buttons(self):
        for kind, button in self.selection_buttons.items():
            button.text = self.selection_text(kind)

    def load_choices(self):
        def worker():
            try:
                choices = {
                    "tractor": self.request("/api/tractors"),
                    "implement": self.request("/api/implements"),
                    "field": self.request("/api/fields"),
                }

                Clock.schedule_once(
                    lambda _dt: self.set_choices(choices)
                )

            except Exception as exc:
                message = str(exc)

                Clock.schedule_once(
                    lambda _dt, msg=message: setattr(
                        self.status_label,
                        "text",
                        "Laden fehlgeschlagen: " + msg,
                    )
                )

        threading.Thread(target=worker, daemon=True).start()

    def set_choices(self, choices):
        self.choices = choices

        self.status_label.text = (
            f'{len(choices["tractor"])} Traktoren · '
            f'{len(choices["implement"])} Anbaugeräte · '
            f'{len(choices["field"])} Felder'
        )

        self.update_selection_buttons()
         # ---------------------------------------------------------------
    # Vorhandene Einträge auswählen
    # ---------------------------------------------------------------

    def open_picker(self, kind):
        titles = {
            "tractor": "Traktor auswählen",
            "implement": "Anbaugerät auswählen",
            "field": "Feld auswählen",
        }

        items = self.choices.get(kind, [])

        if not items:
            self.status_label.text = (
                "Keine Einträge vorhanden. Bitte einen neuen "
                "Eintrag erfassen."
            )
            return

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(10),
        )

        scroll = ScrollView()

        rows = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
        )
        rows.bind(minimum_height=rows.setter("height"))

        popup = Popup(
            title=titles[kind],
            content=content,
            size_hint=(0.85, 0.85),
            auto_dismiss=True,
        )

        for item in items:
            button = self.make_button(
                item.get("name", f'ID {item.get("id")}'),
                lambda _btn, entry=item: self.choose(
                    kind, entry, popup
                ),
                height=dp(58),
            )
            rows.add_widget(button)

        scroll.add_widget(rows)
        content.add_widget(scroll)

        content.add_widget(self.make_button(
            "Abbrechen",
            lambda *_: popup.dismiss(),
            height=dp(48),
        ))

        popup.open()

    def choose(self, kind, item, popup):
        self.selection[kind] = item
        self.update_selection_buttons()

        self.status_label.text = (
            f'Ausgewählt: {item.get("name", "Unbekannt")}'
        )

        popup.dismiss()

        if self.on_selection_changed:
            self.on_selection_changed()

    # ---------------------------------------------------------------
    # Traktor und Anbaugerät erfassen
    # ---------------------------------------------------------------

    def open_form(self, kind):
        """Öffnet das Formular zum Anlegen eines Traktors oder Anbaugeräts."""

        if kind == "tractor":
            title = "Neuen Traktor erfassen"

            fields = [
                ("name", "Name", "text", None),
                ("length_m", "Länge (m)", "number", "4.5"),
                ("width_m", "Breite (m)", "number", "2.5"),
                ("wheelbase_m", "Radstand (m)", "number", "2.8"),
                (
                    "max_steering_angle_deg",
                    "Max. Lenkwinkel (Grad)",
                    "number",
                    "35",
                ),
                (
                    "gps_offset_length_m",
                    "GPS-Versatz längs (m)",
                    "number",
                    "0",
                ),
                (
                    "gps_offset_width_m",
                    "GPS-Versatz seitlich (m)",
                    "number",
                    "0",
                ),
            ]

        elif kind == "implement":
            title = "Neues Anbaugerät erfassen"

            fields = [
                ("name", "Name", "text", None),
                ("length_m", "Länge (m)", "number", "2.0"),
                (
                    "working_width_m",
                    "Arbeitsbreite (m)",
                    "number",
                    "3.0",
                ),
                (
                    "mount_type",
                    "Anbauart",
                    "choice",
                    "rear",
                ),
                (
                    "work_offset_m",
                    "Arbeitsversatz (m)",
                    "number",
                    "0",
                ),
            ]

        else:
            self.status_label.text = (
                f"Unbekannter Erfassungstyp: {kind}"
            )
            return

        # -----------------------------------------------------------
        # Dialog und Formular
        # -----------------------------------------------------------

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(12),
        )

        scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
        )

        form = GridLayout(
            cols=2,
            spacing=dp(8),
            size_hint_y=None,
        )

        form.bind(minimum_height=form.setter("height"))

        # Tastaturcontainer muss vor der Formularschleife existieren.
        keyboard_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=0,
        )

        inputs = {}

        for key, label_text, input_type, default in fields:
            form.add_widget(
                Label(
                    text=label_text,
                    size_hint_y=None,
                    height=dp(46),
                    halign="left",
                    valign="middle",
                )
            )

            if input_type == "choice":
                default_position = {
                    "front": "Vorne",
                    "rear": "Hinten",
                    "towed": "Gezogen",
                }.get(default, "Hinten")

                widget = Spinner(
                    text=default_position,
                    values=("Vorne", "Hinten", "Gezogen"),
                    size_hint_y=None,
                    height=dp(46),
                )

            else:
                widget = TextInput(
                    text=default or "",
                    hint_text=label_text,
                    multiline=False,
                    input_filter=(
                        "float" if input_type == "number" else None
                    ),
                    size_hint_y=None,
                    height=dp(46),
                    write_tab=False,
                )

            inputs[key] = widget
            form.add_widget(widget)

            # Bildschirmtastatur an jedes TextInput binden.
            if isinstance(widget, TextInput):
                self.attach_touch_keyboard(
                    widget,
                    keyboard_container,
                )

        scroll.add_widget(form)
        content.add_widget(scroll)
        content.add_widget(keyboard_container)

        # -----------------------------------------------------------
        # Status und Schaltflächen
        # -----------------------------------------------------------

        status = Label(
            text="",
            size_hint_y=None,
            height=dp(38),
            halign="left",
            valign="middle",
        )

        content.add_widget(status)

        buttons = GridLayout(
            cols=2,
            spacing=dp(8),
            size_hint_y=None,
            height=dp(52),
        )

        save_button = self.make_button(
            "Speichern",
            lambda *_: save(),
        )

        buttons.add_widget(save_button)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.95, 0.95),
            auto_dismiss=False,
        )

        buttons.add_widget(
            self.make_button(
                "Abbrechen",
                lambda *_: close_form(),
            )
        )

        content.add_widget(buttons)

        # -----------------------------------------------------------
        # Dialog schließen
        # -----------------------------------------------------------

        def close_form():
            for widget in inputs.values():
                if isinstance(widget, TextInput):
                    widget.focus = False

            keyboard_container.clear_widgets()
            keyboard_container.height = 0
            popup.dismiss()

        # -----------------------------------------------------------
        # Formular validieren und speichern
        # -----------------------------------------------------------

        def save():
            payload = {}

            try:
                for key, label_text, input_type, default in fields:
                    widget = inputs[key]

                    if input_type == "choice":
                        positions = {
                            "Vorne": "front",
                            "Hinten": "rear",
                            "Gezogen": "towed",
                        }

                        payload[key] = positions[widget.text]

                    elif input_type == "number":
                        value = widget.text.strip()

                        if not value:
                            raise ValueError(
                                f"Bitte '{label_text}' ausfüllen."
                            )

                        # Dezimalkomma und Dezimalpunkt akzeptieren.
                        value = value.replace(",", ".")
                        number = float(value)

                        if not math.isfinite(number):
                            raise ValueError(
                                f"'{label_text}' muss eine "
                                "gültige Zahl sein."
                            )

                        payload[key] = number

                    else:
                        payload[key] = widget.text.strip()

                if not payload.get("name"):
                    raise ValueError(
                        "Bitte einen Namen eingeben."
                    )

            except (ValueError, KeyError) as exc:
                status.text = str(exc)
                return

            save_button.disabled = True
            status.text = "Speichere …"

            # Tastatur schließen, bevor gespeichert wird.
            for widget in inputs.values():
                if isinstance(widget, TextInput):
                    widget.focus = False

            keyboard_container.clear_widgets()
            keyboard_container.height = 0

            # -------------------------------------------------------
            # Backend-Aufruf im Hintergrund
            # -------------------------------------------------------

            def worker():
                try:
                    endpoint = (
                        "/api/tractors"
                        if kind == "tractor"
                        else "/api/implements"
                    )

                    created = self.request(
                        endpoint,
                        method="POST",
                        payload=payload,
                    )

                    Clock.schedule_once(
                        lambda _dt: saved(created)
                    )

                except Exception as exc:
                    message = str(exc)

                    Clock.schedule_once(
                        lambda _dt, msg=message: failed(msg)
                    )

            def saved(created):
                popup.dismiss()

                self.status_label.text = (
                    "Gespeichert: "
                    + str(
                        created.get(
                            "name",
                            payload["name"],
                        )
                    )
                )

                self.load_choices()

                # Neuen Eintrag als aktuelle Auswahl übernehmen.
                if self.on_selection_changed:
                    Clock.schedule_once(
                        lambda _dt: self.select_created(
                            kind,
                            created,
                        ),
                        0.5,
                    )

            def failed(message):
                save_button.disabled = False

                status.text = (
                    "Speichern fehlgeschlagen: "
                    + message
                )

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        popup.open()
    def select_created(self, kind, created):
        """Wählt einen neu angelegten Eintrag nach dem Neuladen aus."""
        items = self.choices.get(kind, [])

        selected = next(
            (
                item for item in items
                if item.get("id") == created.get("id")
            ),
            created,
        )

        self.selection[kind] = selected
        self.update_selection_buttons()

        if self.on_selection_changed:
            self.on_selection_changed()
# ---------------------------------------------------------------
    # Feldgrenze per GPS erfassen
    # ---------------------------------------------------------------

    def open_field_capture(self):
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(12),
        )

        name_input = TextInput(
            hint_text="Feldname, z. B. Nordschlag",
            multiline=False,
            size_hint_y=None,
            height=dp(52),
            write_tab=False,
        )
        keyboard_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=0,
        )
        self.attach_touch_keyboard(
            name_input,
            keyboard_container,
        )
        content.add_widget(name_input) 
        content.add_widget(Widget(
            size_hint_y=None,
            height=dp(220),
        ))
        content.add_widget(keyboard_container)

        content.add_widget(Label(
            text=(
                "Feldgrenze mit dem Traktor abfahren.\n"
                "Die Positionen kommen vom Pico über das Backend."
            ),
            size_hint_y=None,
            height=dp(64),
        ))

        status = Label(
            text="Bereit. GPS wird beim Start geprüft.",
            halign="center",
        )
        content.add_widget(status)

        points = []
        state = {
            "recording": False,
            "busy": False,
        }
        event = {"poll": None}

        buttons = GridLayout(
            cols=2,
            spacing=dp(8),
            size_hint_y=None,
            height=dp(60),
        )

        start_button = self.make_button(
            "Aufzeichnung starten",
            lambda *_: start_recording(),
        )

        stop_button = self.make_button(
            "Stoppen und speichern",
            lambda *_: stop_recording(),
        )
        stop_button.disabled = True

        buttons.add_widget(start_button)
        buttons.add_widget(stop_button)
        content.add_widget(buttons)

        popup = Popup(
            title="Feld per GPS erfassen",
            content=content,
            size_hint=(0.92, 0.82),
            auto_dismiss=False,
        )

        content.add_widget(self.make_button(
            "Abbrechen",
            lambda *_: cancel_capture(),
        ))

        def haversine_m(a, b):
            """Entfernung zwischen zwei GPS-Punkten in Metern."""
            lon1, lat1 = a
            lon2, lat2 = b

            radius = 6371000.0
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)

            value = (
                math.sin(dphi / 2) ** 2
                + math.cos(phi1)
                * math.cos(phi2)
                * math.sin(dlambda / 2) ** 2
            )

            value = min(1.0, max(0.0, value))

            return 2 * radius * math.asin(math.sqrt(value))

        def poll_gps(_dt):
            if not state["recording"] or state["busy"]:
                return

            state["busy"] = True

            def worker():
                try:
                    data = self.request(
                        f"/api/sensors/{GPS_DEVICE_ID}/latest"
                    )

                    Clock.schedule_once(
                        lambda _dt: handle_gps(data)
                    )

                except Exception as exc:
                    message = str(exc)

                    Clock.schedule_once(
                        lambda _dt, msg=message: gps_error(msg)
                    )

                finally:
                    state["busy"] = False

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        def handle_gps(data):
            if not state["recording"]:
                return

            if not data.get("gps_valid", False):
                status.text = (
                    "GPS nicht zuverlässig: "
                    + str(data.get("reason", "Kein gültiger Fix"))
                )
                return

            try:
                lon = float(data["longitude"])
                lat = float(data["latitude"])
            except (KeyError, TypeError, ValueError):
                status.text = (
                    "GPS-Antwort enthält keine gültigen Koordinaten."
                )
                return

            if not (
                math.isfinite(lon)
                and math.isfinite(lat)
                and -180 <= lon <= 180
                and -90 <= lat <= 90
            ):
                status.text = "Ungültige GPS-Koordinaten."
                return

            point = [lon, lat]

            if not points:
                points.append(point)
            elif (
                haversine_m(points[-1], point)
                >= MIN_POINT_DISTANCE_M
            ):
                points.append(point)

            status.text = (
                f"Aufzeichnung läuft · {len(points)} Punkte · "
                "GPS gültig"
            )

        def gps_error(message):
            if state["recording"]:
                status.text = "GPS/API-Fehler: " + message

        def start_recording():
            if not name_input.text.strip():
                status.text = (
                    "Bitte zuerst einen Feldnamen eingeben."
                )
                return

            start_button.disabled = True
            status.text = "Prüfe GPS-Verbindung …"

            def worker():
                try:
                    data = self.request(
                        f"/api/sensors/{GPS_DEVICE_ID}/latest"
                    )

                    if not data.get("gps_valid", False):
                        raise ValueError(
                            "Kein gültiger GPS-Fix: "
                            + str(data.get("reason", "unbekannt"))
                        )

                    Clock.schedule_once(
                        lambda _dt: begin_recording(data)
                    )

                except Exception as exc:
                    message = str(exc)

                    Clock.schedule_once(
                        lambda _dt, msg=message: start_failed(msg)
                    )

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        def begin_recording(data):
            start_button.disabled = True
            points.clear()
            state["recording"] = True

            handle_gps(data)

            stop_button.disabled = False

            status.text = (
                f"Aufzeichnung läuft · {len(points)} Punkte"
            )

            event["poll"] = Clock.schedule_interval(
                poll_gps,
                GPS_POLL_INTERVAL,
            )

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
                status.text = (
                    "Zu wenige GPS-Punkte. Mindestens drei "
                    "Positionen sind erforderlich."
                )
                start_button.disabled = False
                return

            # GeoJSON-Polygone müssen einen geschlossenen Ring haben.
            ring = [point[:] for point in points]

            if ring[-1] != ring[0]:
                ring.append(ring[0][:])

            payload = {
                "name": name_input.text.strip(),
                # Das Backend erwartet eine Punktliste [longitude, latitude],
                # kein GeoJSON-Objekt.
                "boundary": ring,
                "reference_line": [],
            }

            status.text = (
                f"Speichere Feld mit {len(points)} GPS-Punkten …"
            )

            def worker():
                try:
                    created = self.request(
                        "/api/fields",
                        method="POST",
                        payload=payload,
                    )

                    Clock.schedule_once(
                        lambda _dt: field_saved(created)
                    )

                except Exception as exc:
                    message = str(exc)

                    Clock.schedule_once(
                        lambda _dt, msg=message: field_save_failed(msg)
                    )

            threading.Thread(
                target=worker,
                daemon=True,
            ).start()

        def field_saved(created):
            popup.dismiss()

            area_ha = float(created.get("area_m2", 0.0)) / 10000.0

            self.status_label.text = (
                f'Feld gespeichert: {created.get("name")} · '
                f"{area_ha:.3f} ha"
            )

            self.load_choices()

            if self.on_selection_changed:
                Clock.schedule_once(
                    lambda _dt: self.select_created(
                        "field", created
                    ),
                    0.5,
                )

        def field_save_failed(message):
            state["recording"] = False
            stop_button.disabled = True
            start_button.disabled = False

            status.text = (
                "Speichern fehlgeschlagen: " + message
            )

        def cancel_capture():
            state["recording"] = False

            if event["poll"] is not None:
                event["poll"].cancel()
                event["poll"] = None

            popup.dismiss()

        popup.open()

    def go_back(self, *_):
        if self.on_back:
            self.on_back()
            
    def open_master_data(self, *_):
        """Öffnet die separate Stammdatenseite."""
        if self.on_master_data:
            self.on_master_data()

    def open_wifi_manager(self, *_):
        """Öffnet die separate Stammdatenseite."""
        if self.on_wifi_manager:
            self.on_wifi_manager()


class WidgetSpacer(BoxLayout):
    """Flexibler Abstand am unteren Rand der Einstellungsseite."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=1, **kwargs)

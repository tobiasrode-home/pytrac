"""PyTrac: Einstellungen und Auswahl vorhandener Stammdaten."""

import threading

import requests
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

class SettingsScreen(BoxLayout):
    """Einstellungen und Auswahl vorhandener Traktoren, Geräte und Felder."""

    def __init__(
        self, api_url, selection, api_client=None, on_back=None,
        on_selection_changed=None, on_master_data=None,
        on_wifi_manager=None, **kwargs
    ):
        super().__init__(
            orientation="vertical", padding=dp(18), spacing=dp(12), **kwargs
        )
        self.api_url = api_url.rstrip("/")
        self.api_client = api_client
        self.selection = selection
        self.on_back = on_back
        self.on_selection_changed = on_selection_changed
        self.on_master_data = on_master_data
        self.on_wifi_manager = on_wifi_manager
        self.choices = {"tractor": [], "implement": [], "field": []}
        self.selection_buttons = {}

        header = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(10))
        header.add_widget(Label(
            text="[b]Einstellungen[/b]", markup=True, font_size="25sp",
            halign="left"
        ))
        header.add_widget(self.make_button(
            "Zur Übersicht", self.go_back, width=dp(180)
        ))
        header.add_widget(self.make_button(
            "Stammdaten", self.open_master_data, width=dp(180)
        ))
        header.add_widget(self.make_button(
            "Wifi", self.open_wifi_manager, width=dp(180)
        ))
        self.add_widget(header)
        self.add_widget(Label(
            text="Maschinenkonfiguration und Feld für den nächsten "
                 "Arbeitsgang auswählen.",
            size_hint_y=None, height=dp(52), halign="left"
        ))

        for kind, title in (
            ("tractor", "Traktor auswählen"),
            ("implement", "Anbaugerät auswählen"),
            ("field", "Feld auswählen"),
        ):
            self.add_widget(Label(
                text=title, size_hint_y=None, height=dp(32),
                halign="left", bold=True, font_size="17sp"
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
            size_hint_y=None, height=dp(48)
        )
        self.add_widget(self.status_label)
        self.add_widget(BoxLayout(size_hint_y=1))
        self.load_choices()

    def make_button(self, text, callback, height=dp(54), width=None):
        button = Button(
            text=text, size_hint_y=None, height=height,
            background_normal="", background_down="",
            background_color=(0.16, 0.43, 0.28, 1),
            color=(1, 1, 1, 1), font_size="17sp", bold=True,
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
            method, self.api_url + path, json=payload, timeout=8
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
        """Lädt die Auswahlmöglichkeiten im Hintergrund."""
        def worker():
            try:
                choices = {
                    "tractor": self.request("/api/tractors"),
                    "implement": self.request("/api/implements"),
                    "field": self.request("/api/fields"),
                }
                Clock.schedule_once(lambda _dt: self.set_choices(choices))
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(
                    lambda _dt, msg=message: setattr(
                        self.status_label, "text", "Laden fehlgeschlagen: " + msg
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

    def open_picker(self, kind):
        titles = {
            "tractor": "Traktor auswählen",
            "implement": "Anbaugerät auswählen",
            "field": "Feld auswählen",
        }
        items = self.choices.get(kind, [])
        if not items:
            self.status_label.text = (
                "Keine Einträge vorhanden. Bitte einen neuen Eintrag erfassen."
            )
            return

        content = BoxLayout(
            orientation="vertical", spacing=dp(6), padding=dp(10)
        )
        scroll = ScrollView()
        rows = BoxLayout(
            orientation="vertical", spacing=dp(6), size_hint_y=None
        )
        rows.bind(minimum_height=rows.setter("height"))
        popup = Popup(
            title=titles[kind], content=content,
            size_hint=(0.85, 0.85), auto_dismiss=True
        )
        for item in items:
            rows.add_widget(self.make_button(
                item.get("name", f'ID {item.get("id")}'),
                lambda _btn, entry=item: self.choose(kind, entry, popup),
                height=dp(58),
            ))
        scroll.add_widget(rows)
        content.add_widget(scroll)
        content.add_widget(self.make_button(
            "Abbrechen", lambda *_: popup.dismiss(), height=dp(48)
        ))
        popup.open()

    def choose(self, kind, item, popup):
        self.selection[kind] = item
        self.update_selection_buttons()
        self.status_label.text = f'Ausgewählt: {item.get("name", "Unbekannt")}'
        popup.dismiss()
        if self.on_selection_changed:
            self.on_selection_changed()

    def go_back(self, *_):
        if self.on_back:
            self.on_back()

    def open_master_data(self, *_):
        if self.on_master_data:
            self.on_master_data()

    def open_wifi_manager(self, *_):
        if self.on_wifi_manager:
            self.on_wifi_manager()

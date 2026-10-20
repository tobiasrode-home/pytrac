"""PyTrac: Separate Seite zur Erfassung neuer Stammdaten."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from pytrac_kivy.ui.settings_screen import SettingsScreen


class MasterDataScreen(SettingsScreen):
    """Seite zum Anlegen von Traktoren, Geräten und Feldern."""

    def __init__(
        self,
        api_url,
        selection,
        api_client=None,
        on_back=None,
        on_selection_changed=None,
        **kwargs,
    ):
        # Bestehende API-, Formular-, GPS- und Tastaturlogik übernehmen.
        super().__init__(
            api_url=api_url,
            selection=selection,
            api_client=api_client,
            on_back=on_back,
            on_selection_changed=on_selection_changed,
            **kwargs,
        )

        # Die Auswahloberfläche der Einstellungen entfernen.
        # Die Methoden und ihre internen Referenzen bleiben erhalten.
        self.clear_widgets()

        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(64),
            spacing=dp(12),
        )

        header.add_widget(
            Label(
                text="[b]Stammdaten verwalten[/b]",
                markup=True,
                font_size="24sp",
                halign="left",
            )
        )

        header.add_widget(
            self.make_button(
                "Zurück",
                self.go_back,
                width=dp(170),
            )
        )

        self.add_widget(header)

        self.add_widget(
            Label(
                text=(
                    "Wähle aus, welche Stammdaten "
                    "du neu erfassen möchtest."
                ),
                size_hint_y=None,
                height=dp(60),
                halign="left",
                valign="middle",
            )
        )

        self.add_widget(
            self.make_button(
                "Traktor anlegen",
                lambda *_: self.open_form("tractor"),
                height=dp(76),
            )
        )

        self.add_widget(
            self.make_button(
                "Anbaugerät anlegen",
                lambda *_: self.open_form("implement"),
                height=dp(76),
            )
        )

        self.add_widget(
            self.make_button(
                "Feld per GPS erfassen",
                lambda *_: self.open_field_capture(),
                height=dp(76),
            )
        )

        self.add_widget(
            Label(
                text=(
                    "Felder werden durch Abfahren der Feldgrenze "
                    "mit dem GPS des Pico erfasst."
                ),
                size_hint_y=None,
                height=dp(56),
                halign="left",
                valign="middle",
            )
        )

        # status_label wird von den übernommenen Methoden verwendet.
        # Es bleibt deshalb als Objekt erhalten, auch wenn es nicht
        # mehr Bestandteil der ursprünglichen Oberfläche ist.

    def go_back(self, *_):
        """Zurück zur Einstellungsseite."""
        if self.on_back:
            self.on_back()

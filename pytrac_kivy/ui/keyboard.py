# ------------------------------------------------------------
# ui/keyboard.py
# PyTrac - Universelle Touch-Bildschirmtastatur
# Deutsche QWERTZ-Tastatur, Sonderzeichen und NumPad
# ------------------------------------------------------------

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button


# ------------------------------------------------------------
# Farben
# ------------------------------------------------------------

KEY_COLOR = (0.18, 0.20, 0.22, 1)
SPECIAL_COLOR = (0.12, 0.35, 0.55, 1)
ACTIVE_COLOR = (0.10, 0.48, 0.65, 1)
ENTER_COLOR = (0.15, 0.55, 0.25, 1)
DELETE_COLOR = (0.65, 0.15, 0.15, 1)


class TouchKeyboard(BoxLayout):
    """
    Universelle Bildschirmtastatur für Kivy-TextInput.

    Kompatibel mit der bisherigen Verwendung:

        TouchKeyboard(
            target=text_input,
            numeric=False,
            on_done=callback,
        )

    Seiten:
        abc     Kleinbuchstaben
        ABC     Großbuchstaben
        123     Ziffern und Satzzeichen
        #+=     Sonderzeichen
        NumPad  Numerische Tastatur
    """

    def __init__(
        self,
        target,
        numeric=False,
        on_done=None,
        **kwargs,
    ):
        kwargs.pop("size_hint_y", None)
        kwargs.pop("height", None)

        super().__init__(
            orientation="vertical",
            spacing=dp(4),
            padding=dp(4),
            size_hint_y=None,
            height=dp(285),
            **kwargs,
        )

        self.target = target
        self.numeric = numeric
        self.on_done_callback = on_done

        self.page = "NumPad" if numeric else "abc"

        self._build()

    # --------------------------------------------------------
    # Tastatur aufbauen
    # --------------------------------------------------------

    def _build(self):
        self.clear_widgets()

        # Seitenwahl
        self.page_bar = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            spacing=dp(4),
        )
        self.add_widget(self.page_bar)

        pages = ["abc", "ABC", "123", "#+=", "NumPad"]

        for page in pages:
            button = Button(
                text=page,
                font_size=dp(15),
                background_normal="",
                background_down="",
                background_color=(
                    ACTIVE_COLOR
                    if page == self.page
                    else SPECIAL_COLOR
                ),
            )
            button.bind(
                on_release=lambda instance, p=page:
                self.change_page(p)
            )
            self.page_bar.add_widget(button)

        # Bereich für die eigentlichen Tasten
        self.keys_area = BoxLayout(
            orientation="vertical",
            spacing=dp(4),
        )
        self.add_widget(self.keys_area)

        if self.page in ("abc", "ABC"):
            self._build_letters()

        elif self.page == "123":
            self._build_numbers()

        elif self.page == "#+=":
            self._build_symbols()

        elif self.page == "NumPad":
            self._build_numpad()

        # Gemeinsame untere Tastenreihe
        self._build_bottom_row()

        if self.page == "NumPad":
            self.height = dp(285)
        else:
            self.height = dp(250)

    def change_page(self, page):
        self.page = page
        self._build()

    # --------------------------------------------------------
    # Hilfsfunktion: Tastenreihe
    # --------------------------------------------------------

    def _add_row(self, characters, height=40):
        row = BoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(height),
        )

        for char in characters:
            button = Button(
                text=char,
                font_size=dp(18),
                background_normal="",
                background_down="",
                background_color=KEY_COLOR,
            )

            button.bind(
                on_release=lambda instance, value=char:
                self.insert_text(value)
            )

            row.add_widget(button)

        self.keys_area.add_widget(row)

    # --------------------------------------------------------
    # Buchstabentastatur: deutsches QWERTZ
    # --------------------------------------------------------

    def _build_letters(self):
        if self.page == "ABC":
            rows = [
                list("QWERTZUIOP") + ["Ü"],
                list("ASDFGHJKL") + ["Ö", "Ä"],
                list("YXCVBNM"),
            ]
        else:
            rows = [
                list("qwertzuiop") + ["ü"],
                list("asdfghjkl") + ["ö", "ä"],
                list("yxcvbnm"),
            ]

        for index, row in enumerate(rows):
            self._add_row(
                row,
                height=38 if index < 2 else 40,
            )

        # Zusätzliche häufig benötigte Zeichen
        self._add_row(
            [",", ".", "-", "_", "@"],
            height=36,
        )

    # --------------------------------------------------------
    # Zahlen und Satzzeichen
    # --------------------------------------------------------

    def _build_numbers(self):
        rows = [
            list("1234567890"),
            list(".,;:!?"),
            list("+-*/=%"),
        ]

        for row in rows:
            self._add_row(row, height=40)

    # --------------------------------------------------------
    # Sonderzeichen
    # --------------------------------------------------------

    def _build_symbols(self):
        rows = [
            list("!@#$%^&*"),
            list("()[]{}"),
            list("-_=+"),
            ["\\", "/", ":", ";", "'", '"'],
            ["?", "<", ">", "~", "`", "|"],
        ]

        for row in rows:
            self._add_row(row, height=34)

    # --------------------------------------------------------
    # NumPad
    # --------------------------------------------------------

    def _build_numpad(self):
        rows = [
            ["7", "8", "9"],
            ["4", "5", "6"],
            ["1", "2", "3"],
            [".", "0", ","],
        ]

        for row in rows:
            self._add_row(row, height=40)

    # --------------------------------------------------------
    # Gemeinsame Funktionstasten
    # --------------------------------------------------------

    def _build_bottom_row(self):
        row = BoxLayout(
            orientation="horizontal",
            spacing=dp(4),
            size_hint_y=None,
            height=dp(38),
        )

        if self.page != "NumPad":
            space = Button(
                text="Leerzeichen",
                font_size=dp(13),
                background_normal="",
                background_color=SPECIAL_COLOR,
            )
            space.bind(
                on_release=lambda *_: self.insert_text(" ")
            )
            row.add_widget(space)

        backspace = Button(
            text="⌫",
            font_size=dp(20),
            background_normal="",
            background_color=DELETE_COLOR,
        )
        backspace.bind(
            on_release=self.delete_character
        )
        row.add_widget(backspace)

        clear = Button(
            text="Leeren",
            font_size=dp(14),
            background_normal="",
            background_color=SPECIAL_COLOR,
        )
        clear.bind(
            on_release=self.clear_text
        )
        row.add_widget(clear)

        done = Button(
            text="FERTIG",
            font_size=dp(15),
            background_normal="",
            background_color=ENTER_COLOR,
        )
        done.bind(
            on_release=self.done
        )
        row.add_widget(done)

        self.add_widget(row)

    # --------------------------------------------------------
    # Text einfügen
    # --------------------------------------------------------

    def insert_text(self, text):
        if self.target is None:
            return

        try:
            self.target.insert_text(text)
            self.target.focus = True
        except (AttributeError, TypeError, ValueError):
            pass

    # --------------------------------------------------------
    # Zeichen links vom Cursor löschen
    # --------------------------------------------------------

    def delete_character(self, instance=None):
        target = self.target

        if target is None:
            return

        try:
            text = target.text
            cursor = target.cursor_index()
            cursor = max(0, min(cursor, len(text)))

            if cursor == 0:
                return

            new_text = text[:cursor - 1] + text[cursor:]

            target.text = new_text
            target.cursor = target.get_cursor_from_index(
                cursor - 1
            )
            target.focus = True

        except (
            AttributeError,
            IndexError,
            TypeError,
            ValueError,
        ):
            pass

    # --------------------------------------------------------
    # Gesamten Inhalt löschen
    # --------------------------------------------------------

    def clear_text(self, instance=None):
        if self.target is None:
            return

        self.target.text = ""
        self.target.cursor = (0, 0)
        self.target.focus = True

    # --------------------------------------------------------
    # Fertig
    # --------------------------------------------------------

    def done(self, instance=None):
        if self.on_done_callback:
            self.on_done_callback()

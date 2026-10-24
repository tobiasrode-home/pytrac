"""PyTrac Touch-Tastatur – stabile Umschaltung QWERTZ/ABC/123/Symbole/NumPad.

Wichtig: Die Tastatur setzt den TextInput-Fokus beim Tippen NICHT erneut.
Andernfalls kann die focus-Bindung im MasterDataScreen die Tastatur während
eines Seitenwechsels löschen und neu erstellen.
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button

KEY = (0.18, 0.20, 0.22, 1)
SPECIAL = (0.12, 0.35, 0.55, 1)
ACTIVE = (0.10, 0.48, 0.65, 1)
DONE = (0.15, 0.55, 0.25, 1)
DELETE = (0.65, 0.15, 0.15, 1)

PAGES = ("abc", "ABC", "123", "#+=", "NumPad")
ROWS = {
    "abc": (tuple("qwertzuiopü"), tuple("asdfghjklöä"), tuple("yxcvbnm"), (",", ".", "-", "_", "@")),
    "ABC": (tuple("QWERTZUIOPÜ"), tuple("ASDFGHJKLÖÄ"), tuple("YXCVBNM"), (",", ".", "-", "_", "@")),
    "123": (tuple("1234567890"), tuple(".,;:!?"), tuple("+-*/=%")),
    "#+=": (tuple("!@#$%^&*"), tuple("()[]{}"), tuple("-_=+"), ("\\", "/", ":", ";", "'", '"'), ("?", "<", ">", "~", "`", "|")),
    "NumPad": (("7","8","9"),("4","5","6"),("1","2","3"),(".","0",",")),
}

class TouchKeyboard(BoxLayout):
    """Kompatibel mit TouchKeyboard(target=..., numeric=..., on_done=...)."""

    def __init__(self, target, numeric=False, on_done=None, **kwargs):
        kwargs.pop("height", None)
        kwargs.pop("size_hint_y", None)
        super().__init__(orientation="vertical", size_hint_y=None, height=dp(205),
                         spacing=dp(3), padding=dp(3), **kwargs)
        self.target = target
        self.numeric = numeric
        self.on_done_callback = on_done
        self.page = "NumPad" if numeric else "abc"
        self._build()

    def _button(self, label, callback, color=KEY, font_size=17):
        button = Button(text=label, font_size=dp(font_size),
                        background_normal="", background_down="",
                        background_color=color)
        button.bind(on_release=lambda _instance: callback())
        return button

    def _build(self):
        self.clear_widgets()
        selector = BoxLayout(orientation="horizontal", spacing=dp(3),
                             size_hint_y=None, height=dp(34))
        for page in PAGES:
            selector.add_widget(self._button(
                page, lambda p=page: self.change_page(p),
                ACTIVE if self.page == page else SPECIAL, 14))
        self.add_widget(selector)

        # Die Tastatur passt in den vorhandenen 210-dp-Container der Stammdatenmaske.
        area = BoxLayout(orientation="vertical", spacing=dp(3))
        for chars in ROWS[self.page]:
            row = BoxLayout(orientation="horizontal", spacing=dp(3))
            for char in chars:
                row.add_widget(self._button(char, lambda c=char: self.insert_text(c)))
            area.add_widget(row)
        self.add_widget(area)

        bottom = BoxLayout(orientation="horizontal", spacing=dp(3),
                           size_hint_y=None, height=dp(38))
        if self.page != "NumPad":
            bottom.add_widget(self._button("Leerzeichen", lambda: self.insert_text(" "), SPECIAL, 13))
        bottom.add_widget(self._button("⌫", self.delete_character, DELETE, 21))
        bottom.add_widget(self._button("Leeren", self.clear_text, SPECIAL, 13))
        bottom.add_widget(self._button("FERTIG", self.done, DONE, 15))
        self.add_widget(bottom)

    def change_page(self, page):
        if page not in PAGES:
            raise ValueError("Unbekannte Tastaturseite: " + str(page))
        if page == self.page:
            return
        self.page = page
        self._build()

    def insert_text(self, text):
        if self.target is None:
            return
        # Kein self.target.focus = True: verhindert Fokus-/Rebuild-Schleifen.
        self.target.insert_text(text)

    def delete_character(self):
        if self.target is None:
            return
        target = self.target
        start, end = target.selection_from, target.selection_to
        if target.selection_text and start is not None and end is not None:
            lo, hi = sorted((start, end))
            target.text = target.text[:lo] + target.text[hi:]
            target.cursor = target.get_cursor_from_index(lo)
            target.cancel_selection()
            return
        pos = target.cursor_index()
        if pos > 0:
            target.text = target.text[:pos-1] + target.text[pos:]
            target.cursor = target.get_cursor_from_index(pos-1)

    def clear_text(self):
        if self.target is not None:
            self.target.text = ""
            self.target.cursor = self.target.get_cursor_from_index(0)

    def done(self):
        if self.on_done_callback:
            self.on_done_callback()

"""Große Vollbild-Touch-Tastatur mit sichtbarer Eingabe am oberen Rand."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from pytrac_kivy.ui.keyboard import TouchKeyboard

def open_fullscreen_keyboard(target, title="Text eingeben", on_done=None):
    content=BoxLayout(orientation="vertical",padding=dp(10),spacing=dp(8))
    content.add_widget(Label(text=title,size_hint_y=None,height=dp(35),font_size="21sp"))
    # Spiegelung per Bindung: Text bleibt auch bei Fokusverlust durch Buttons sichtbar.
    display=TextInput(text=target.text,multiline=False,readonly=True,
                      font_size="28sp",size_hint_y=None,height=dp(70))
    target.bind(text=lambda _instance,value:setattr(display,"text",value))
    content.add_widget(display)
    keyboard=TouchKeyboard(target=target,on_done=None)
    keyboard.size_hint_y=1
    keyboard.height=dp(380)
    content.add_widget(keyboard)
    footer=BoxLayout(size_hint_y=None,height=dp(60),spacing=dp(8))
    popup=Popup(title="",content=content,size_hint=(1,1),auto_dismiss=False,
                separator_height=0)
    def close():
        popup.dismiss()
        if on_done:on_done(target.text)
    keyboard.on_done_callback=close
    cancel=Button(text="FERTIG / ÜBERNEHMEN",font_size="20sp")
    cancel.bind(on_release=lambda *_:close())
    footer.add_widget(cancel)
    content.add_widget(footer)
    popup.open()
    return popup

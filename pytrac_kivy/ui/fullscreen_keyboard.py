"""Einheitliche Vollbild-Touch-Tastatur für PyTrac-Textfelder."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from pytrac_kivy.ui.keyboard import TouchKeyboard

def open_fullscreen_keyboard(target, title="Text eingeben", on_done=None):
    """Bearbeitet den vorhandenen TextInput; Anzeige oben bleibt synchron."""
    content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
    content.add_widget(Label(text=title, size_hint_y=None, height=dp(35), font_size="21sp"))
    display = TextInput(text=target.text, multiline=False, readonly=True,
                        password=bool(getattr(target,"password",False)),
                        font_size="28sp", size_hint_y=None, height=dp(70))
    def update_display(_instance, value):
        display.text=value
    target.bind(text=update_display)
    content.add_widget(display)
    numeric=getattr(target,"input_filter",None)=="float"
    keyboard=TouchKeyboard(target=target,numeric=numeric)
    keyboard.height=dp(360)
    content.add_widget(keyboard)
    footer=BoxLayout(size_hint_y=None,height=dp(60),spacing=dp(8))
    popup=Popup(title="",content=content,size_hint=(1,1),auto_dismiss=False,
                separator_height=0)
    closed=[False]
    def close():
        if closed[0]:return
        closed[0]=True
        target.unbind(text=update_display)
        popup.dismiss()
        if on_done:on_done(target.text)
    keyboard.on_done_callback=close
    done=Button(text="FERTIG / ÜBERNEHMEN",font_size="20sp")
    done.bind(on_release=lambda *_:close())
    footer.add_widget(done)
    content.add_widget(footer)
    popup.open()
    return popup

def bind_fullscreen_keyboard(target,title=None):
    """Öffnet beim Antippen und verhindert doppelte Dialoge."""
    state={"popup":None}
    def on_touch(instance,touch):
        if getattr(instance,"disabled",False) or not instance.collide_point(*touch.pos):
            return False
        popup=state["popup"]
        if popup is not None and popup.parent is not None:
            return False
        popup=open_fullscreen_keyboard(instance,title or instance.hint_text or "Text eingeben")
        state["popup"]=popup
        popup.bind(on_dismiss=lambda *_:state.update(popup=None))
        return False
    target.bind(on_touch_down=on_touch)
    return target

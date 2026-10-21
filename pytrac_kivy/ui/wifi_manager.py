import os
import re
import subprocess
import tempfile
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

from pytrac_kivy.ui.keyboard import TouchKeyboard


INTERFACE = "wlan0"


# =========================================================
# NetworkManager-Hilfsfunktionen
# =========================================================

def run_command(args, timeout=30):
    """Führt einen Systembefehl ohne Shell aus."""
    env = os.environ.copy()
    env["LC_ALL"] = "C"

    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(message or "Befehl fehlgeschlagen")

    return result.stdout.strip()


def unescape_nmcli(value):
    """Entschärft Escape-Sequenzen aus der nmcli-Ausgabe."""
    return value.replace(r"\:", ":").replace(r"\\", "\\")


def get_status():
    state = run_command([
        "nmcli", "-g", "GENERAL.STATE",
        "device", "show", INTERFACE,
    ])

    connection = run_command([
        "nmcli", "-g", "GENERAL.CONNECTION",
        "device", "show", INTERFACE,
    ])

    addresses = run_command([
        "nmcli", "-g", "IP4.ADDRESS",
        "device", "show", INTERFACE,
    ]).splitlines()

    address = (
        addresses[0].split("/")[0]
        if addresses and addresses[0]
        else ""
    )

    return state, connection, address


def scan_wifi():
    output = run_command([
        "nmcli",
        "--terse",
        "--escape", "yes",
        "--fields", "IN-USE,SSID,SIGNAL,SECURITY",
        "device", "wifi", "list",
        "--rescan", "yes",
        "ifname", INTERFACE,
    ], timeout=45)

    networks = []

    for line in output.splitlines():
        fields = re.split(r"(?<!\\):", line, maxsplit=3)

        if len(fields) != 4:
            continue

        active, ssid, signal, security = [
            unescape_nmcli(value)
            for value in fields
        ]

        if not ssid:
            ssid = "(Verstecktes Netzwerk)"

        networks.append({
            "ssid": ssid,
            "signal": signal,
            "security": security or "Offen",
            "active": active == "*",
        })

    return sorted(
        networks,
        key=lambda item: (
            not item["active"],
            -int(item["signal"] or 0),
            item["ssid"].casefold(),
        ),
    )


def saved_connections():
    output = run_command([
        "nmcli",
        "--terse",
        "--escape", "yes",
        "--fields", "NAME,UUID,TYPE",
        "connection", "show",
    ])

    profiles = []

    for line in output.splitlines():
        fields = re.split(r"(?<!\\):", line, maxsplit=2)

        if len(fields) != 3:
            continue

        name, uuid, kind = [
            unescape_nmcli(value)
            for value in fields
        ]

        if kind == "802-11-wireless":
            profiles.append({
                "name": name,
                "uuid": uuid,
            })

    return profiles


def connect_wifi(ssid, password, security):
    """
    Verbindet mit einem WLAN über NetworkManager.

    Das Passwort wird über eine temporäre Datei übergeben,
    nicht als Kommandozeilenargument.
    """
    fd, path = tempfile.mkstemp(prefix="wifi-secret-")

    try:
        os.fchmod(fd, 0o600)

        with os.fdopen(fd, "w", encoding="utf-8") as secret_file:
            if security and security != "Offen":
                secret_file.write(
                    "802-11-wireless-security.psk:" + password + "\n"
                )

        return run_command([
            "nmcli",
            "device", "wifi", "connect", ssid,
            "ifname", INTERFACE,
            "passwd-file", path,
        ], timeout=60)

    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# =========================================================
# Kivy WLAN-Verwaltung
# =========================================================

class WifiManager(BoxLayout):

    def __init__(self, on_back=None, **kwargs):
        self.on_back = on_back

        super().__init__(
            orientation="vertical",
            spacing=dp(8),
            padding=dp(10),
            **kwargs,
        )

        self.status = Label(
            text="WLAN-Status wird geladen ...",
            size_hint_y=None,
            height=dp(68),
            halign="center",
            valign="middle",
        )
        self.status.bind(size=self._fit_label)
        self.add_widget(self.status)

        toolbar = BoxLayout(
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )

        back_button = Button(text="Zurück")
        back_button.bind(on_release=self.go_back)
        toolbar.add_widget(back_button)
        
        refresh_button = Button(text="WLANs suchen")
        refresh_button.bind(
            on_release=lambda *_: self.refresh_networks()
        )
        toolbar.add_widget(refresh_button)

        profiles_button = Button(text="Gespeicherte WLANs")
        profiles_button.bind(
            on_release=lambda *_: self.show_profiles()
        )
        toolbar.add_widget(profiles_button)

        self.add_widget(toolbar)

        self.network_list = GridLayout(
            cols=1,
            spacing=dp(6),
            size_hint_y=None,
        )
        self.network_list.bind(
            minimum_height=self.network_list.setter("height")
        )

        scroll = ScrollView()
        scroll.add_widget(self.network_list)
        self.add_widget(scroll)

        self.refresh_status()
        self.refresh_networks()

    @staticmethod
    def _fit_label(widget, size):
        widget.text_size = size

    def go_back(self, instance=None):
        if self.on_back is not None:
            self.on_back()

    def run_async(self, task, callback):
        """Führt Netzwerkoperationen in einem Hintergrund-Thread aus."""

        def worker():
            try:
                result = task()
                error = None
            except Exception as exc:
                result = None
                error = str(exc)

            Clock.schedule_once(
                lambda dt: callback(result, error),
                0,
            )

        threading.Thread(target=worker, daemon=True).start()

    # -----------------------------------------------------
    # Status
    # -----------------------------------------------------

    def refresh_status(self):
        def update(result, error):
            if error:
                self.status.text = (
                    "WLAN-Status nicht verfügbar\n" + error
                )
                return

            state, connection, address = result

            self.status.text = (
                f"Status: {state}\n"
                f"Netzwerk: {connection or 'Keines'}\n"
                f"IP-Adresse: {address or 'Keine'}"
            )

        self.run_async(get_status, update)

    # -----------------------------------------------------
    # WLAN-Liste
    # -----------------------------------------------------

    def refresh_networks(self):
        self.network_list.clear_widgets()

        self.network_list.add_widget(Label(
            text="Suche nach WLANs ...",
            size_hint_y=None,
            height=dp(45),
        ))

        def update(networks, error):
            self.network_list.clear_widgets()

            if error:
                self.network_list.add_widget(Label(
                    text=f"Fehler bei der WLAN-Suche:\n{error}",
                    size_hint_y=None,
                    height=dp(80),
                ))
                return

            if not networks:
                self.network_list.add_widget(Label(
                    text="Keine WLANs gefunden.",
                    size_hint_y=None,
                    height=dp(45),
                ))

            for network in networks:
                active = (
                    "  ✓ VERBUNDEN"
                    if network["active"]
                    else ""
                )

                button = Button(
                    text=(
                        f"{network['ssid']}{active}\n"
                        f"Signal: {network['signal']} %"
                        f"   Sicherheit: {network['security']}"
                    ),
                    size_hint_y=None,
                    height=dp(68),
                    halign="left",
                    valign="middle",
                )
                button.bind(size=self._fit_label)
                button.bind(
                    on_release=lambda instance, item=network:
                    self.ask_password(item)
                )
                self.network_list.add_widget(button)

            self.refresh_status()

        self.run_async(scan_wifi, update)

    # -----------------------------------------------------
    # Verbindung mit Passwortdialog
    # -----------------------------------------------------

    def ask_password(self, network):
        ssid = network["ssid"]
        security = network["security"]

        if ssid == "(Verstecktes Netzwerk)":
            self.show_message(
                "Versteckte WLANs werden nicht unterstützt."
            )
            return

        if network["active"]:
            self.show_message(
                f"Du bist bereits mit {ssid} verbunden."
            )
            return

        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        content.add_widget(Label(
            text=f"Mit WLAN '{ssid}' verbinden",
            size_hint_y=None,
            height=dp(35),
        ))

        password_input = TextInput(
            hint_text="WLAN-Passwort",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=dp(18),
            write_tab=False,
        )

        if security == "Offen":
            password_input.hint_text = "Kein Passwort erforderlich"
            password_input.disabled = True

        content.add_widget(password_input)

        # Die WLAN-Ansicht muss dieselbe Touch-Tastatur wie die
        # übrigen Kivy-Formulare verwenden. Ein TextInput allein
        # öffnet auf Kiosk-/Touch-Systemen nicht immer eine Tastatur.
        keyboard_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=0,
        )
        content.add_widget(keyboard_container)

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )

        popup = Popup(
            title="WLAN verbinden",
            content=content,
            size_hint=(0.96, None),
            height=dp(190),
            auto_dismiss=False,
        )

        def finish_password_entry():
            password_input.focus = False

        def password_focus_changed(instance, focused):
            keyboard_container.clear_widgets()
            if focused and security != "Offen":
                keyboard_container.height = dp(250)
                popup.height = dp(470)
                keyboard_container.add_widget(TouchKeyboard(
                    target=password_input,
                    numeric=False,
                    on_done=finish_password_entry,
                ))
            else:
                keyboard_container.height = 0
                popup.height = dp(190)

        password_input.bind(focus=password_focus_changed)

        cancel = Button(text="Abbrechen")
        cancel.bind(on_release=popup.dismiss)
        buttons.add_widget(cancel)

        connect = Button(text="Verbinden")
        buttons.add_widget(connect)
        content.add_widget(buttons)

        def do_connect(*_):
            password = password_input.text

            if security != "Offen" and not password:
                self.show_message(
                    "Bitte gib das WLAN-Passwort ein."
                )
                return

            popup.dismiss()

            def task():
                return connect_wifi(ssid, password, security)

            def finished(result, error):
                self.show_message(
                    f"Verbindung fehlgeschlagen:\n{error}"
                    if error
                    else f"Verbindung zu {ssid} hergestellt."
                )
                self.refresh_status()
                self.refresh_networks()

            self.run_async(task, finished)

        connect.bind(on_release=do_connect)
        popup.open()
        if security != "Offen":
            # Fokus erst nach dem Öffnen setzen, damit die Bildschirmtastatur
            # korrekt in den Popup-Layoutbereich eingebaut wird.
            Clock.schedule_once(
                lambda _dt: setattr(password_input, "focus", True),
                0.15,
            )

    # -----------------------------------------------------
    # Gespeicherte Profile
    # -----------------------------------------------------

    def show_profiles(self):
        def update(profiles, error):
            if error:
                self.show_message(error)
                return

            content = BoxLayout(
                orientation="vertical",
                spacing=dp(7),
                padding=dp(8),
            )

            profile_list = GridLayout(
                cols=1,
                spacing=dp(6),
                size_hint_y=None,
            )
            profile_list.bind(
                minimum_height=profile_list.setter("height")
            )

            if not profiles:
                profile_list.add_widget(Label(
                    text="Keine gespeicherten WLANs.",
                    size_hint_y=None,
                    height=dp(45),
                ))

            for profile in profiles:
                row = BoxLayout(
                    size_hint_y=None,
                    height=dp(55),
                    spacing=dp(5),
                )

                row.add_widget(Label(text=profile["name"]))

                activate = Button(text="Verbinden")
                activate.bind(
                    on_release=lambda instance, uuid=profile["uuid"]:
                    self.activate_profile(uuid)
                )
                row.add_widget(activate)

                delete = Button(text="Löschen")
                delete.bind(
                    on_release=lambda instance, uuid=profile["uuid"]:
                    self.delete_profile(uuid)
                )
                row.add_widget(delete)

                profile_list.add_widget(row)

            scroll = ScrollView()
            scroll.add_widget(profile_list)
            content.add_widget(scroll)

            close = Button(
                text="Schließen",
                size_hint_y=None,
                height=dp(45),
            )
            content.add_widget(close)

            popup = Popup(
                title="Gespeicherte WLANs",
                content=content,
                size_hint=(0.98, 0.85),
            )
            close.bind(on_release=popup.dismiss)
            popup.open()

        self.run_async(saved_connections, update)

    def activate_profile(self, uuid):
        def task():
            return run_command([
                "nmcli", "connection", "up",
                "uuid", uuid,
                "ifname", INTERFACE,
            ], timeout=60)

        def finished(result, error):
            self.show_message(
                f"Verbindung fehlgeschlagen:\n{error}"
                if error
                else "Verbindung aktiviert."
            )
            self.refresh_status()
            self.refresh_networks()

        self.run_async(task, finished)

    def delete_profile(self, uuid):
        def task():
            return run_command([
                "nmcli", "connection", "delete",
                "uuid", uuid,
            ])

        def finished(result, error):
            self.show_message(
                f"Löschen fehlgeschlagen:\n{error}"
                if error
                else "WLAN-Profil gelöscht."
            )
            self.refresh_status()
            self.refresh_networks()

        self.run_async(task, finished)

    # -----------------------------------------------------
    # Meldungsdialog
    # -----------------------------------------------------

    def show_message(self, message):
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(10),
        )

        label = Label(
            text=message,
            halign="center",
            valign="middle",
        )
        label.bind(size=self._fit_label)
        content.add_widget(label)

        close = Button(
            text="OK",
            size_hint_y=None,
            height=dp(45),
        )
        content.add_widget(close)

        popup = Popup(
            title="WLAN-Verwaltung",
            content=content,
            size_hint=(0.9, None),
            height=dp(210),
        )
        close.bind(on_release=popup.dismiss)
        popup.open()


# =========================================================
# Eigenständige Test-App
# =========================================================

class WifiManagerApp(App):
    def build(self):
        return WifiManager()


if __name__ == "__main__":
    WifiManagerApp().run()

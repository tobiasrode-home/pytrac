"""PyTrac-Bordcomputer: Hauptfenster und Navigation."""
# Displaykonfiguration vor den übrigen Kivy-Imports
Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "720")
Config.set("graphics", "resizable", "0")
Config.set("graphics", "rotation", "270")


from kivy.app import App

from pytrac_kivy.dependencies import create_api_client


class PytracKivyApp(App):
    def build(self):
        self.api_client = create_api_client()

        # Hier deine vorhandene Root-Ansicht erzeugen.
        # Den Client an Dashboard und weitere Services übergeben.
        return self.build_existing_root()

    def on_stop(self):
        client = getattr(self, "api_client", None)

        if client is not None:
            client.close()

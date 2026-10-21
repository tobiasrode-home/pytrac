"""Zentrale Erstellung der Abhängigkeiten für die Kivy-App."""

from pytrac_core.config import settings
from pytrac_kivy.api.client import ApiClient


def create_api_client() -> ApiClient:
    """Erstellt den HTTP-Client anhand der zentralen Konfiguration."""
    return ApiClient(
        base_url=settings.kivy_api_base_url,
        timeout=settings.kivy_api_timeout,
    )

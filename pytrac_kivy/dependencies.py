"""Gemeinsame Abhängigkeiten für die Kivy-Anwendung."""

from pytrac_core.config import settings
from pytrac_kivy.api.client import ApiClient


def create_api_client() -> ApiClient:
    settings = settings
    return ApiClient(
        base_url=settings.kivy_api_base_url,
        timeout=settings.kivy_api_timeout,
    )

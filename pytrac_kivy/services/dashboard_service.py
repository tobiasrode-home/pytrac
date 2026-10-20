
from typing import Any

from pytrac_kivy.api.client import ApiClient


class DashboardService:
    def __init__(self, api: ApiClient) -> None:
        self.api = api

    def load_fields(self) -> list[dict[str, Any]]:
        result = self.api.get("/api/fields")

        if not isinstance(result, list):
            raise ValueError(
                "Ungültiges Antwortformat für Felder: "
                "Eine Liste wurde erwartet."
            )

        return result

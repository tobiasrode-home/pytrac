"""Gemeinsamer HTTP-Client für die PyTrac-Kivy-App."""

from typing import Any

import requests


class ApiError(RuntimeError):
    """Fehler bei der Kommunikation mit dem PyTrac-Backend."""


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 8.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(
        self,
        path: str,
        method: str = "GET",
        payload: Any = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()

            if not response.content:
                return {}

            return response.json()

        except requests.RequestException as exc:
            raise ApiError(
                f"Backend-Anfrage fehlgeschlagen ({path}): {exc}"
            ) from exc

        except ValueError as exc:
            raise ApiError(
                f"Backend lieferte ungültiges JSON ({path})"
            ) from exc

    def get(self, path: str) -> Any:
        return self.request(path)

    def post(self, path: str, payload: Any = None) -> Any:
        return self.request(path, method="POST", payload=payload)

    def close(self) -> None:
        self.session.close()

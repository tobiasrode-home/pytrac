
from typing import Any

import requests

from pytrac_kivy.api.errors import (
    ApiConnectionError,
    ApiResponseError,
)


class ApiClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: Any = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiConnectionError(
                f"Backend nicht erreichbar: {path}"
            ) from exc

        if not response.ok:
            detail = response.text[:500]
            raise ApiResponseError(
                f"HTTP {response.status_code} bei {path}: {detail}"
            )

        if not response.content:
            return None

        try:
            return response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise ApiResponseError(
                f"Ungültige JSON-Antwort von {path}"
            ) from exc

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: Any = None) -> Any:
        return self.request("POST", path, payload=payload)

    def put(self, path: str, payload: Any = None) -> Any:
        return self.request("PUT", path, payload=payload)

    def patch(self, path: str, payload: Any = None) -> Any:
        return self.request("PATCH", path, payload=payload)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def close(self) -> None:
        self.session.close()

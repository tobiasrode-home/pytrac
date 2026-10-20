"""Gemeinsamer HTTP-Client für die PyTrac-Kivy-App."""

from typing import Any

import requests


class ApiError(RuntimeError):
    """Fehler bei der Kommunikation mit dem PyTrac-Backend."""


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def request(self, path: str, method: str = "GET", payload: Any = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.request(
                method=method.upper(), url=url, json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError:
                if response.headers.get("content-type", "").startswith("text/"):
                    return response.text
                raise
        except requests.Timeout as exc:
            raise ApiError(f"Zeitüberschreitung bei Backend-Anfrage ({path}).") from exc
        except requests.ConnectionError as exc:
            raise ApiError(
                f"Backend unter {self.base_url} nicht erreichbar ({path})."
            ) from exc
        except requests.HTTPError as exc:
            response = exc.response
            detail = ""
            if response is not None:
                try:
                    body = response.json()
                    detail = body.get("detail", body) if isinstance(body, dict) else body
                except ValueError:
                    detail = response.text
                detail = f": {detail}" if detail else ""
                status = response.status_code
            else:
                status = "unbekannt"
            raise ApiError(f"Backend-Fehler {status} bei {path}{detail}") from exc
        except requests.RequestException as exc:
            raise ApiError(f"Backend-Anfrage fehlgeschlagen ({path}): {exc}") from exc
        except ValueError as exc:
            raise ApiError(f"Backend lieferte ungültiges JSON ({path}).") from exc

    def get(self, path: str) -> Any:
        return self.request(path, "GET")

    def post(self, path: str, payload: Any = None) -> Any:
        return self.request(path, "POST", payload)

    def put(self, path: str, payload: Any = None) -> Any:
        return self.request(path, "PUT", payload)

    def patch(self, path: str, payload: Any = None) -> Any:
        return self.request(path, "PATCH", payload)

    def delete(self, path: str) -> Any:
        return self.request(path, "DELETE")

    def close(self) -> None:
        self.session.close()

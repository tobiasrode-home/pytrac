
class ApiError(RuntimeError):
    """Basisklasse für Fehler bei Backend-Anfragen."""


class ApiConnectionError(ApiError):
    """Das Backend konnte nicht erreicht werden."""


class ApiResponseError(ApiError):
    """Das Backend lieferte einen Fehlerstatus oder ungültige Daten."""

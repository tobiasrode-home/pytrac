
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PyTrac Backend"
    environment: str = "development"

    # Datenbank
    database_url: str = "sqlite:///data/pytrac.db"

    # Backend
    host: str = "127.0.0.1"
    port: int = 8000

    # GPS-Empfänger
    gps_port: str = ""
    gps_baudrate: int = 9600

    # BNO085 IMU
    imu_port: str = ""
    imu_baudrate: int = 115200

    # Gemeinsame Ausgaberate der Sensoren
    sensor_output_rate_hz: float = 5.0



    kivy_api_base_url: str = "http://127.0.0.1:8000"
    kivy_api_timeout: float = 5.0
    kivy_refresh_interval: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def get_settings() -> Settings:
    """Gibt die einmalig geladene Anwendungskonfiguration zurück."""
    return settings

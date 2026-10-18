
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pytrac_core.config import settings


def _prepare_sqlite_database(database_url: str) -> None:
    """Erstellt das Datenbankverzeichnis, falls SQLite verwendet wird."""
    if not database_url.startswith("sqlite:///"):
        return

    database_path = database_url.removeprefix("sqlite:///")

    if database_path == ":memory:":
        return

    path = Path(database_path)

    if not path.is_absolute():
        path = Path.cwd() / path

    path.parent.mkdir(parents=True, exist_ok=True)


# Datenbankverbindung vorbereiten
_prepare_sqlite_database(settings.database_url)

# SQLAlchemy-Engine erstellen
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

# Session-Fabrik für Datenbankoperationen
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Stellt eine Datenbank-Session für FastAPI bereit."""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

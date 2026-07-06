from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.app.config import get_settings

engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False},  # required for SQLite + FastAPI
)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    """WAL mode + busy timeout so concurrent scheduler jobs (hourly candle
    refresh vs 5-minute trade lifecycle) retry briefly instead of raising
    'database is locked' — which could desync local trade state from
    stop-loss changes already applied on OANDA's side."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Import models so they register with Base.metadata
    import backend.app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

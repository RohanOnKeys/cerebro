from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cerebro.config import settings


def psycopg3_url(url: str) -> str:
    """Force the psycopg3 driver for bare postgresql:// URLs."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(
    psycopg3_url(settings.database_url),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    return SessionLocal()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cerebro.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Session:
    return SessionLocal()

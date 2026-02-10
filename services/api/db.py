from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        yield db
    finally:
        db.close()

"""
Database setup. SQLite is fine here because we have one writer (the agent
process) and low concurrency for a hackathon demo — no need for Postgres.

check_same_thread=False is required because FastAPI can serve a request on
a different thread than the one that created the connection.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./fleetagent.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a session, always closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

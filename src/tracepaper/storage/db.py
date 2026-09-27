"""Database setup using SQLAlchemy and SQLite."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

Base = declarative_base()


def get_engine(db_path: str):
    """
    Create SQLAlchemy engine for SQLite.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        SQLAlchemy Engine instance.
    """
    # Use StaticPool to allow access from multiple threads in tests
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


def get_session_factory(engine):
    """
    Create a session factory.

    Args:
        engine: SQLAlchemy Engine instance.

    Returns:
        Session factory (sessionmaker).
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine):
    """
    Initialize database tables.

    Args:
        engine: SQLAlchemy Engine instance.
    """
    Base.metadata.create_all(engine)

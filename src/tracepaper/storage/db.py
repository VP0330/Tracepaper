"""Database setup using SQLAlchemy and SQLite."""

from sqlalchemy import create_engine, text
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
    if db_path.startswith(("postgresql://", "postgresql+")):
        return create_engine(db_path, pool_pre_ping=True)

    sqlite_url = db_path if db_path.startswith("sqlite:") else (
        "sqlite:///:memory:" if db_path == ":memory:" else f"sqlite:///{db_path}"
    )
    options: dict[str, object] = {"connect_args": {"check_same_thread": False}}
    if sqlite_url.endswith(":memory:"):
        options["poolclass"] = StaticPool
    return create_engine(sqlite_url, **options)


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
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
                "chunk_id UNINDEXED, doc_id UNINDEXED, extracted_text)"
            ))
    elif engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_chunks_search_vector "
                "ON chunks USING GIN (to_tsvector('english', extracted_text))"
            ))

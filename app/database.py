import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

logger = logging.getLogger("subdox.database")

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,   # test each connection before use; auto-reconnect if the DB (e.g. Neon) closed it while idle
    pool_recycle=280,     # proactively recycle connections before they go stale
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_auto_migrations():
    """
    SQLAlchemy's create_all() only creates missing tables — it never alters
    an existing table. So whenever a model gains a new nullable column, the
    live database needs it added by hand. This does that automatically on
    startup: for every table that already exists, add any column present in
    the model but missing from the database. Safe because it only ever adds
    nullable columns, never removes or changes existing ones.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all() will create this one fresh; nothing to migrate
            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                try:
                    col_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}'))
                    logger.info("Auto-migration: added %s.%s", table.name, column.name)
                except Exception as e:
                    logger.error("Auto-migration failed for %s.%s: %s", table.name, column.name, e)

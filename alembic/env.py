import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import all models so Alembic autogenerate can detect schema changes.
import app.db.base  # noqa: F401
from app.core.config import settings
from app.models.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Tables that belong to our application models (populated from metadata).
# Alembic will ONLY track these; PostGIS system tables (tiger, topology,
# spatial_ref_sys, etc.) are silently ignored.
_APP_TABLES = set(target_metadata.tables.keys())


def include_object(_object, name, type_, _reflected, _compare_to):
    """
    Filter callback for Alembic autogenerate.

    Returns True  → Alembic tracks this object (create/drop/alter it).
    Returns False → Alembic ignores this object entirely.

    Strategy:
      • Tables that are reflected from the DB but NOT in our metadata
        (e.g. PostGIS tiger/topology/spatial_ref_sys tables) are excluded.
      • Tables that are in our metadata are always included.
      • Indexes, constraints, and columns follow their parent table.
    """
    if type_ == "table":
        return name in _APP_TABLES
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection needed)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations through an async engine (required for asyncpg)."""
    connectable = create_async_engine(settings.DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

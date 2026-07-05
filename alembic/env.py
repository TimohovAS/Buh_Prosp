from logging.config import fileConfig

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from backend.config import get_settings
from backend.database import Base
import backend.models  # noqa: F401 - register models in Base.metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _sync_database_url(database_url: str) -> str:
    """Return a sync SQLAlchemy URL for Alembic migrations."""
    url = make_url(database_url)
    if url.drivername == "sqlite+aiosqlite":
        return str(url.set(drivername="sqlite"))
    if url.drivername == "postgresql+asyncpg":
        return str(url.set(drivername="postgresql"))
    return str(url)


def _database_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    return _sync_database_url(x_args.get("database_url") or get_settings().database_url)


config.set_main_option("sqlalchemy.url", _database_url())


def _is_sqlite_context(context_or_connection) -> bool:
    dialect = getattr(context_or_connection, "dialect", None)
    return getattr(dialect, "name", None) == "sqlite"


def _is_sqlite_url() -> bool:
    return make_url(config.get_main_option("sqlalchemy.url")).get_backend_name() == "sqlite"


def include_object(obj, name, type_, reflected, compare_to):
    """Filter SQLite reflection noise out of Alembic autogenerate/check."""
    if _is_sqlite_url():
        if type_ == "column" and name == "id" and getattr(obj, "primary_key", False):
            return False
        if type_ in {"foreign_key_constraint", "unique_constraint"}:
            return False
    return True


def compare_type(context, inspected_column, metadata_column, inspected_type, metadata_type):
    """SQLite does not enforce VARCHAR lengths, so length-only diffs are noise."""
    if _is_sqlite_context(context) and isinstance(inspected_type, sa.String) and isinstance(metadata_type, sa.String):
        return False
    return None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=compare_type,
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=compare_type,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

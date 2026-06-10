"""
Alembic environment configuration.
"""
from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import the base and config
from app.db.base import Base
from app.core.config import settings
from app.db.migration_url import get_migration_database_url

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use direct Postgres for migrations (pooler endpoints cannot run DDL).
_migration_url = get_migration_database_url(
    settings.DATABASE_URL,
    settings.DATABASE_MIGRATION_URL,
)
config.set_main_option("sqlalchemy.url", _migration_url)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        # AUTOCOMMIT avoids pg_catalog lock contention when migrations run DDL.
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")
        connection.execute(sa.text("SET statement_timeout = '600s'"))
        connection.execute(sa.text("SET lock_timeout = '120s'"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,
        )

        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()


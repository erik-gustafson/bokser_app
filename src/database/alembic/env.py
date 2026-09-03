from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.config import settings
from src.database import models  # noqa: F401
from src.database.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DEFAULT_SCHEMA = None
MANAGED_SCHEMAS = frozenset(
    table.schema if table.schema != "public" else DEFAULT_SCHEMA
    for table in target_metadata.tables.values()
)


def get_target_schemas() -> frozenset[str | None]:
    """Return all model schemas, or a comma-separated subset from -x schemas=."""
    requested = context.get_x_argument(as_dictionary=True).get("schemas")
    if not requested:
        return MANAGED_SCHEMAS

    schemas = frozenset(
        DEFAULT_SCHEMA if name.strip() == "public" else name.strip()
        for name in requested.split(",")
        if name.strip()
    )
    unknown = schemas - MANAGED_SCHEMAS
    if unknown:
        names = ", ".join("public" if name is None else name for name in unknown)
        raise ValueError(f"Unknown Alembic target schema(s): {names}")
    return schemas


TARGET_SCHEMAS = get_target_schemas()


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    """Avoid reflecting schemas that are outside this application's metadata."""
    if type_ == "schema":
        return name in TARGET_SCHEMAS
    return True


def include_object(object_, name, type_, reflected, compare_to) -> bool:
    """Limit metadata and reflected objects when -x schemas= is supplied."""
    if type_ == "table":
        schema = object_.schema
    else:
        table = getattr(object_, "table", None)
        schema = getattr(table, "schema", None)

    if schema == "public":
        schema = DEFAULT_SCHEMA
    return schema in TARGET_SCHEMAS


def get_database_url() -> str:
    database_url = settings.database_url

    if not database_url:
        raise RuntimeError("settings.database_url is empty.")

    return database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            include_name=include_name,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

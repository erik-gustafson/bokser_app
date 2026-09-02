from sqlalchemy import inspect


def update_model(target, source, *, exclude: set[str] | None = None):
    exclude = exclude or set()

    mapper = inspect(type(target))

    for column in mapper.column_attrs:
        key = column.key

        if key in exclude:
            continue

        setattr(target, key, getattr(source, key))

from typing import TypeVar, Any
from sqlalchemy import inspect
from collections.abc import Callable, Hashable, Iterable, MutableSequence

T = TypeVar("T")


def update_model(
    target: Any,
    source: Any,
    *,
    exclude: set[str] | None = None,
    exclude_none: bool = True,
) -> None:
    exclude = exclude or set()

    mapper = inspect(type(target))

    for attr in mapper.column_attrs:
        key = attr.key
        column = attr.columns[0]

        # Never modify database identity
        if column.primary_key:
            continue

        # Never modify relationship foreign keys
        if column.foreign_keys:
            continue

        # Caller-defined immutable/business-key fields
        if key in exclude:
            continue

        value = getattr(source, key)

        # Missing source value leaves existing DB value unchanged
        if exclude_none and value is None:
            continue

        setattr(target, key, value)


def merge_model_collection(
    existing: MutableSequence[T],
    incoming: Iterable[T],
    *,
    key: Callable[[T], Hashable],
    exclude: set[str] | None = None,
) -> None:

    existing_by_key = {key(obj): obj for obj in existing}

    for incoming_obj in incoming:
        obj_key = key(incoming_obj)

        current = existing_by_key.get(obj_key)

        if current is None:
            existing.append(incoming_obj)
            existing_by_key[obj_key] = incoming_obj
            continue

        update_model(
            current,
            incoming_obj,
            exclude=exclude or set(),
        )

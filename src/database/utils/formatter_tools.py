from datetime import datetime
from typing import Any


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def as_str(value: Any) -> str:
    return "" if value is None else str(value)


def as_float(value: Any) -> float:
    return 0.0 if value is None else float(value)


def as_int(value: Any) -> int:
    return 0 if value is None else int(value)


def require_positive_int(data: dict[str, Any], field_name: str) -> int:
    value = data.get(field_name)

    if value is None or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc

    if parsed <= 0 or (isinstance(value, float) and not value.is_integer()):
        raise ValueError(f"{field_name} must be a positive integer")

    return parsed


def require_datetime(data: dict[str, Any], field_name: str) -> datetime:
    value = data.get(field_name)

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")

    try:
        parsed = parse_dt(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a timezone-aware timestamp") from exc

    if parsed is None or parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")

    return parsed

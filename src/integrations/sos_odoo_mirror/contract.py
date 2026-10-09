"""First mirror contract: complete, non-hierarchical partner snapshots only."""
from datetime import datetime, timezone
import hashlib
import json

FIELDS = ("name", "email", "phone", "website")
ENTITIES = ("customer", "vendor")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("invalid_observed_at")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_observed_at") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone_required")
    return result.astimezone(timezone.utc)


def digest(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "entity", "source_id", "observed_at", "values"}:
        raise ValueError("invalid_envelope")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("unsupported_schema")
    if payload["entity"] not in ENTITIES:
        raise ValueError("unsupported_entity")
    identifier = payload["source_id"]
    if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isdecimal() or int(identifier) <= 0 or len(identifier) > 32 or str(int(identifier)) != identifier:
        raise ValueError("invalid_source_id")
    observed = timestamp(payload["observed_at"])
    values = payload["values"]
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError("invalid_partner_fields")
    if any(not isinstance(v, str) or len(v) > 2048 or any(ord(c) < 32 for c in v) for v in values.values()):
        raise ValueError("invalid_partner_value")
    if not values["name"].strip():
        raise ValueError("name_required")
    return observed, digest(values)


def normalize(entity, record, observed_at):
    if not isinstance(record, dict):
        raise ValueError("invalid_source_record")
    if record.get("archived") not in (None, False):
        raise ValueError("archived_partner_pending")
    if record.get("parent") or record.get("parentId") or record.get("parent_id"):
        raise ValueError("partner_hierarchy_pending")
    identifier = record.get("id")
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("invalid_source_id")
    # Allowlist only. Passwords, payment tokens, raw JSON and notes never cross.
    phone, mobile = record.get("phone"), record.get("mobile")
    if any(v is not None and not isinstance(v, str) for v in (phone, mobile)):
        raise ValueError("invalid_partner_value")
    if phone and mobile and phone != mobile:
        raise ValueError("multiple_phone_numbers_pending")
    values = {field: ("" if record.get(field) is None else record[field]) for field in FIELDS}
    values["phone"] = phone or mobile or ""
    payload = {"schema_version": 1, "entity": entity, "source_id": str(identifier),
               "observed_at": observed_at, "values": values}
    validate(payload)
    return payload


def replay_action(previous_time, previous_hash, observed, incoming_hash, target_matches):
    if not target_matches:
        raise ValueError("local_edit_conflict")
    if observed < previous_time:
        return "stale"
    if incoming_hash == previous_hash:
        return "duplicate"
    if observed == previous_time:
        raise ValueError("observation_conflict")
    return "update"

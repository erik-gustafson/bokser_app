"""Versioned contact snapshot contract; parent dependencies use SOS identities."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json

FIELDS = ("name", "email", "phone", "website")
CURRENT_FIELDS = FIELDS + ("mobile",)
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
    if not isinstance(payload, dict):
        raise ValueError("invalid_envelope")
    version = payload.get("schema_version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("unsupported_schema")
    expected = {"schema_version", "entity", "source_id", "observed_at", "values"}
    if version == 2:
        expected.add("parent_source_id")
    if set(payload) != expected:
        raise ValueError("invalid_envelope")
    if payload["entity"] not in ENTITIES:
        raise ValueError("unsupported_entity")
    identifier = payload["source_id"]
    if not valid_identifier(identifier):
        raise ValueError("invalid_source_id")
    observed = timestamp(payload["observed_at"])
    values = payload["values"]
    if not isinstance(values, dict) or set(values) != set(FIELDS if version == 1 else CURRENT_FIELDS):
        raise ValueError("invalid_partner_fields")
    if any(not isinstance(v, str) or len(v) > 2048 or any(ord(c) < 32 for c in v) for v in values.values()):
        raise ValueError("invalid_partner_value")
    if not values["name"].strip():
        raise ValueError("name_required")
    if version == 2:
        parent = payload["parent_source_id"]
        if parent is not None and (not valid_identifier(parent) or parent == identifier or payload["entity"] != "customer"):
            raise ValueError("invalid_parent_reference")
        return observed, digest({"values": values, "parent_source_id": parent})
    return observed, digest(values)


def valid_identifier(value):
    return (isinstance(value, str) and 0 < len(value) <= 32 and value.isascii()
            and value.isdecimal() and int(value) > 0 and str(int(value)) == value)


def normalize(entity, record, observed_at):
    if not isinstance(record, dict):
        raise ValueError("invalid_source_record")
    if record.get("archived") not in (None, False):
        raise ValueError("archived_partner_pending")
    identifier = record.get("id")
    if type(identifier) is not int or identifier <= 0:
        raise ValueError("invalid_source_id")
    # Allowlist only. Passwords, payment tokens, raw JSON and notes never cross.
    phone, mobile = record.get("phone"), record.get("mobile")
    if any(v is not None and not isinstance(v, str) for v in (phone, mobile)):
        raise ValueError("invalid_partner_value")
    values = {field: ("" if record.get(field) is None else record[field]) for field in CURRENT_FIELDS}
    values["phone"] = phone or mobile or ""
    parent = record.get("parent")
    if parent is not None:
        if not isinstance(parent, dict) or type(parent.get("id")) is not int:
            raise ValueError("invalid_parent_reference")
        parent = parent["id"]
    if record.get("parentId") is not None or record.get("parent_id") is not None:
        raise ValueError("unsupported_parent_alias")
    payload = {"schema_version": 2, "entity": entity, "source_id": str(identifier),
               "observed_at": observed_at, "values": values,
               "parent_source_id": str(parent) if parent is not None else None}
    validate(payload)
    return payload


def order_batch(batch):
    """Validate the entire dependency graph before creating any native records."""
    indexed = {p["source_id"]: p for p in batch}
    if len(indexed) != len(batch):
        raise ValueError("duplicate_source_id_in_batch")
    children = {key: [] for key in indexed}
    roots = deque()
    for payload in batch:
        validate(payload)
        parent = payload.get("parent_source_id")
        if parent is None:
            roots.append(payload["source_id"])
        elif parent not in indexed:
            raise ValueError("missing_parent_in_batch")
        else:
            children[parent].append(payload["source_id"])
    ordered = []
    while roots:
        identifier = roots.popleft()
        ordered.append(indexed[identifier])
        roots.extend(children[identifier])
    if len(ordered) != len(batch):
        raise ValueError("parent_cycle")
    return ordered


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

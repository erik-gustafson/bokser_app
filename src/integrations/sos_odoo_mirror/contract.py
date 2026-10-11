"""Versioned contact snapshot contract; parent dependencies use SOS identities."""
from collections import deque
from datetime import datetime, timezone
import hashlib
import json

FIELDS = ("name", "email", "phone", "website")
CURRENT_FIELDS = FIELDS + ("mobile",)
ENTITIES = ("customer", "vendor")
ADDRESS_FIELDS = ("line1", "line2", "line3", "line4", "line5", "city", "stateProvince", "postalCode", "country")
CONTACT_FIELDS = ("title", "firstName", "middleName", "lastName", "suffix")
MASTER_FIELDS = ("company_name", "alt_phone", "fax", "account_number", "contact", "primary", "shipping", "terms_id", "currency_id")
ALTERNATE_FIELDS = ("company", "contact", "phone", "email", "addressName", "addressType")


def alternate_addresses(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError("invalid_alternate_addresses")
    result, seen = [], set()
    for raw in value:
        values = text_object(raw, ALTERNATE_FIELDS)
        if not values["addressName"].strip() or not values["addressType"].strip():
            raise ValueError("alternate_address_key_required")
        # Names are source-owned keys, never native partner lookup keys. A
        # rename creates a new owned role and archives the old role on replay.
        key = digest([values["addressType"], values["addressName"]])
        if key in seen:
            raise ValueError("duplicate_alternate_address_key")
        seen.add(key)
        values.update(key=key, address=text_object(raw.get("address"), ADDRESS_FIELDS))
        result.append(values)
    return sorted(result, key=lambda r: r["key"])


def text_object(value, keys):
    if value is None:
        return {key: "" for key in keys}
    if not isinstance(value, dict) or not set(keys) <= set(value):
        raise ValueError("incomplete_master_fields")
    result = {key: value[key] or "" for key in keys}
    if any(value[key] is not None and not isinstance(value[key], str) for key in keys):
        raise ValueError("invalid_master_value")
    return result


def reference_id(value):
    if value is None:
        return None
    if not isinstance(value, dict) or type(value.get("id")) is not int or value["id"] <= 0:
        raise ValueError("invalid_master_reference")
    return str(value["id"])


def payload_digest(payload, version=None):
    version = payload["schema_version"] if version is None else version
    values = {key: payload["values"][key] for key in (FIELDS if version == 1 else CURRENT_FIELDS)}
    if version == 1:
        return digest(values)
    data = {"values": values, "parent_source_id": payload["parent_source_id"]}
    if version >= 3:
        data["master"] = payload["master"] if version >= 4 else {key: payload["master"][key] for key in MASTER_FIELDS}
    if version >= 4:
        data["archived"] = payload["archived"]
    # Revision and observation are watermarks, not business values.
    return digest(data)


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
    if type(version) is not int or version not in (1, 2, 3, 4):
        raise ValueError("unsupported_schema")
    expected = {"schema_version", "entity", "source_id", "observed_at", "values"}
    if version >= 2:
        expected.add("parent_source_id")
    if version >= 3:
        expected.update(("master", "sync_token"))
    if version >= 4:
        expected.add("archived")
        if type(payload.get("archived")) is not bool:
            raise ValueError("invalid_archived_flag")
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
    if version >= 3:
        token = payload["sync_token"]
        if not isinstance(token, str) or not token.isascii() or not token.isdecimal() or len(token) > 64 or str(int(token)) != token:
            raise ValueError("invalid_sync_token")
        master = payload["master"]
        extra = {"alternates", "custom_fields"} if version >= 4 else set()
        if not isinstance(master, dict) or set(master) != set(MASTER_FIELDS) | extra:
            raise ValueError("invalid_master_fields")
        for key in ("terms_id", "currency_id"):
            if master[key] is not None and not valid_identifier(master[key]):
                raise ValueError("invalid_master_reference")
        for key, keys in (("contact", CONTACT_FIELDS), ("primary", ADDRESS_FIELDS), ("shipping", ADDRESS_FIELDS)):
            if not isinstance(master[key], dict) or set(master[key]) != set(keys):
                raise ValueError("invalid_master_fields")
        strings = [master[key] for key in ("company_name", "alt_phone", "fax", "account_number")]
        strings += [v for key in ("contact", "primary", "shipping") for v in master[key].values()]
        if version >= 4:
            alternates = master["alternates"]
            if not isinstance(alternates, list):
                raise ValueError("invalid_alternate_addresses")
            if any(not isinstance(a, dict) or set(a) != set(ALTERNATE_FIELDS) | {"key", "address"} for a in alternates):
                raise ValueError("invalid_alternate_addresses")
            if alternate_addresses(alternates) != alternates:
                raise ValueError("invalid_alternate_address_identity")
            for alternate in alternates:
                strings += [alternate[k] for k in ALTERNATE_FIELDS] + list(alternate["address"].values())
            custom = master["custom_fields"]
            if not isinstance(custom, dict) or len(custom) > 1000 or any(not valid_identifier(k) for k in custom):
                raise ValueError("invalid_custom_fields")
            if any(v is not None and not isinstance(v, (str, bool, int, float)) for v in custom.values()):
                raise ValueError("invalid_custom_field_value")
            strings += [v for v in custom.values() if isinstance(v, str)]
        if any(not isinstance(v, str) or len(v) > 2048 or any(ord(c) < 32 and c not in "\t\r\n" for c in v) for v in strings):
            raise ValueError("invalid_master_value")
        if payload["entity"] == "vendor" and any(master["shipping"].values()):
            raise ValueError("vendor_shipping_unsupported")
    if version >= 2:
        parent = payload["parent_source_id"]
        if parent is not None and (not valid_identifier(parent) or parent == identifier or payload["entity"] != "customer"):
            raise ValueError("invalid_parent_reference")
    return observed, payload_digest(payload)


def valid_identifier(value):
    return (isinstance(value, str) and 0 < len(value) <= 32 and value.isascii()
            and value.isdecimal() and int(value) > 0 and str(int(value)) == value)


def normalize(entity, record, observed_at):
    if not isinstance(record, dict):
        raise ValueError("invalid_source_record")
    if record.get("summaryOnly") not in (None, False):
        raise ValueError("summary_master_record_forbidden")
    lifecycle = record.get("mirrorMasterVersion") == 4
    if record.get("archived") not in (None, False) and not lifecycle:
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
    if "syncToken" in record:
        required = {"contact", "terms", "currency", "companyName", "altPhone", "fax"}
        required.update(("billing", "shipping") if entity == "customer" else ("address", "accountNumber"))
        if not required <= set(record):
            raise ValueError("incomplete_master_capture_recapture_required")
        token = record["syncToken"]
        if type(token) is not int or token < 0:
            raise ValueError("invalid_sync_token")
        # Alternate addresses have no documented immutable identity. Do not drop
        # them or adopt native contacts by a mutable label.
        if record.get("altAddresses") and not lifecycle:
            raise ValueError("alternate_address_identity_review_required")
        for key in ("companyName", "altPhone", "fax", "accountNumber"):
            if record.get(key) is not None and not isinstance(record[key], str):
                raise ValueError("invalid_master_value")
        payload.update(schema_version=3, sync_token=str(token), master={
            "company_name": record["companyName"] or "", "alt_phone": record["altPhone"] or "",
            "fax": record["fax"] or "", "account_number": record.get("accountNumber") or "",
            "contact": text_object(record["contact"], CONTACT_FIELDS),
            "primary": text_object(record["billing" if entity == "customer" else "address"], ADDRESS_FIELDS),
            "shipping": text_object(record.get("shipping"), ADDRESS_FIELDS),
            "terms_id": reference_id(record["terms"]), "currency_id": reference_id(record["currency"])})
        if lifecycle:
            if type(record.get("archived")) is not bool or not isinstance(record.get("approvedCustomFields"), dict):
                raise ValueError("incomplete_lifecycle_capture")
            payload.update(schema_version=4, archived=record["archived"])
            payload["master"].update(alternates=alternate_addresses(record.get("altAddresses")),
                custom_fields=record["approvedCustomFields"])
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


def revision_action(previous_token, incoming_token, previous_hash, incoming_hash, target_matches):
    if not target_matches:
        raise ValueError("local_edit_conflict")
    if int(incoming_token) < int(previous_token):
        return "stale"
    if incoming_token == previous_token and incoming_hash != previous_hash:
        raise ValueError("source_revision_conflict")
    return "duplicate" if incoming_hash == previous_hash else "update"

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from datetime import datetime


class ReconciliationRequired(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ReconciliationRequired("Missing " + name)
    return value.strip()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ReconciliationRequired("Invalid quantity")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        raise ReconciliationRequired("Invalid quantity") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ReconciliationRequired("Quantities must be finite and positive")
    return parsed


@dataclass(frozen=True)
class PackRule:
    sku: str
    odoo_uom_id: int
    pack_type: str
    odoo_units_per_pack: Decimal

    def __post_init__(self):
        if self.pack_type not in {"Piece", "Unit", "Case", "Pack", "Master Case"}:
            raise ReconciliationRequired("Unsupported KSP pack type")
        if type(self.odoo_uom_id) is not int or self.odoo_uom_id <= 0:
            raise ReconciliationRequired("Invalid Odoo UoM mapping")
        text(self.sku, "SKU")
        number(self.odoo_units_per_pack)


def allocation_binding(payload, allocation, rules):
    if payload.get("schema_version") != 3 or payload.get("fulfillment_mode") != "reserved_only":
        raise ReconciliationRequired("KSP requires a version 3 reserved-only allocation")
    if allocation.get("wms_code") != "ksp":
        raise ReconciliationRequired("Only the KSP adapter route is accepted")
    if type(allocation.get("warehouse_id")) is not int or allocation["warehouse_id"] <= 0:
        raise ReconciliationRequired("Invalid physical warehouse allocation")
    if type(payload.get("picking_id")) is not int or payload["picking_id"] <= 0:
        raise ReconciliationRequired("Invalid anchor picking ID")
    if allocation not in payload.get("allocations", []):
        raise ReconciliationRequired("Allocation is not part of the frozen Odoo payload")
    code = text(allocation.get("submission_key"), "allocation submission key")
    rule_map = {(r.sku, r.odoo_uom_id): r for r in rules}
    if len(rule_map) != len(rules):
        raise ReconciliationRequired("Duplicate pack mappings")
    by_sku = {}
    for line in allocation.get("lines", []):
        sku = text(line.get("sku"), "component SKU")
        identity = tuple(line.get(key) for key in (
            "sale_line_id", "source_location_id", "product_id", "uom_id"
        ))
        if any(type(i) is not int or i <= 0 for i in identity):
            raise ReconciliationRequired("Invalid released line identity")
        rule = rule_map.get((sku, identity[3]))
        if not rule:
            raise ReconciliationRequired("Explicit SKU/UoM-to-KSP pack mapping required")
        if sku in by_sku and by_sku[sku]["identity"] != list(identity):
            raise ReconciliationRequired("KSP tracking cannot distinguish repeated SKU sales lines or source locations")
        mapped = by_sku.setdefault(sku, {
            "identity": list(identity), "pack_type": rule.pack_type,
            "units_per_pack": str(number(rule.odoo_units_per_pack)), "quantity": "0",
        })
        mapped["quantity"] = str(Decimal(mapped["quantity"]) + number(line.get("quantity")))
    if not by_sku:
        raise ReconciliationRequired("Empty KSP allocation")
    for mapped in by_sku.values():
        packs = Decimal(mapped["quantity"]) / Decimal(mapped["units_per_pack"])
        if packs != packs.to_integral_value():
            raise ReconciliationRequired("Reserved quantity is not a whole KSP pack")
    return {"code": code, "anchor_id": payload["picking_id"],
            "warehouse_id": allocation["warehouse_id"], "lines": by_sku}


def build_order(payload, allocation, rules, shipping_options=None):
    binding = allocation_binding(payload, allocation, rules)
    ship = payload.get("ship_to", {})
    if not isinstance(ship, dict):
        raise ReconciliationRequired("Invalid shipment address")
    # Prefer separately supplied names. Native Odoo otherwise provides one
    # name: first token -> firstName, remaining tokens -> lastName. Preserve
    # all name tokens; single-token contacts require explicit name fields.
    if "first_name" in ship or "last_name" in ship:
        first, last = ship.get("first_name"), ship.get("last_name")
    else:
        parts = text(ship.get("name"), "recipient name").split(maxsplit=1)
        first, last = parts[0], parts[1] if len(parts) == 2 else None
    country = text(ship.get("country"), "country").upper()
    if len(country) != 2 or not country.isascii() or not country.isalpha():
        raise ReconciliationRequired("Country must be a two-letter code")
    # KSP confirmed state and both recipient names are required for this
    # account even though the Gateway guide marks them optional at schema level.
    state = text(ship.get("state"), "shipment state")
    body = {
        "code": binding["code"],
        "customer": {"firstName": first, "lastName": last},
        "shipmentAddress": {
            "country": country,
            "state": state,
            "addressLine1": text(ship.get("street"), "street"),
            "city": text(ship.get("city"), "city"),
            "postalCode": text(ship.get("postal_code"), "postal code"),
        },
        "useSameAddress": True,
        "shipmentOrderLineList": [
            {"sku": sku, "packType": item["pack_type"],
             "packQuantity": int(Decimal(item["quantity"]) / Decimal(item["units_per_pack"]))}
            for sku, item in sorted(binding["lines"].items())
        ],
    }
    for source, target in (("street2", "addressLine2"), ("phone", "phoneNumber")):
        if ship.get(source):
            body["shipmentAddress"][target] = text(ship[source], source)
    if ship.get("email"):
        body["customer"]["email"] = text(ship["email"], "email")
    if payload.get("customer_reference"):
        body["clientReferenceCode"] = text(payload["customer_reference"], "customer reference")
        body["channelOrderNumber"] = body["clientReferenceCode"]
    if shipping_options:
        # No guessed service IDs or component prices from kit sales prices.
        allowed = {"carrierId", "carrierSetupIdentifier", "shippingOptionIdentifier",
                   "shippingOptionDetails", "packingInstructions", "retailerDetails", "customer"}
        if shipping_options.keys() - allowed:
            raise ReconciliationRequired("Unknown shipping option override")
        if any(v in (None, "") for v in shipping_options.values()):
            raise ReconciliationRequired("Omit empty shipping option overrides")
        options = dict(shipping_options)
        if "customer" in options:
            customer = options.pop("customer")
            if not isinstance(customer, dict) or customer.keys() - {"firstName", "lastName", "email"}:
                raise ReconciliationRequired("Invalid customer override")
            body["customer"].update(customer)
        body.update(options)
    # Validate the final request, including overrides, before journal staging,
    # delivery claims or network calls. Never fill absent fields with placeholders.
    for key in ("firstName", "lastName"):
        body["customer"][key] = text(body["customer"].get(key), "customer " + key)
    if "email" in body["customer"]:
        body["customer"]["email"] = text(body["customer"]["email"], "customer email")
    return body, binding


def package_reports(response, binding, accepted_order_id):
    """Tracking is a package snapshot, never an order-level delta."""
    if not isinstance(response, dict) or response.get("orderId") != accepted_order_id:
        raise ReconciliationRequired("Tracking response order ID differs from accepted order")
    packages = response.get("shipments")
    if not isinstance(packages, list):
        raise ReconciliationRequired("Missing package shipment list")
    if response.get("status") not in ("sent", "fulfilled"):
        raise ReconciliationRequired("Tracking status does not prove an accepted shipment; closed is ambiguous")
    reports = []
    seen = set()
    cumulative = defaultdict(Decimal)
    for package in packages:
        if not isinstance(package, dict):
            raise ReconciliationRequired("Invalid package record")
        tracking = text(package.get("trackingNumber"), "package tracking number")
        # Dedicated immutable package IDs are not documented. Tracking is the
        # provisional identity; never include quantity or polling time in it.
        if tracking in seen:
            raise ReconciliationRequired("Repeated tracking identity needs a KSP package identifier")
        seen.add(tracking)
        date = text(package.get("shipmentDate"), "package shipment date")
        try:
            parsed_date = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if parsed_date.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise ReconciliationRequired("Package shipment date requires an ISO timestamp with timezone") from None
        items = package.get("items")
        if not isinstance(items, list) or not items:
            raise ReconciliationRequired("Package needs explicit shipped component quantities")
        quantities = defaultdict(Decimal)
        for item in items:
            if not isinstance(item, dict):
                raise ReconciliationRequired("Invalid package item")
            if item.get("lotBatchNumber") or item.get("expiryDate"):
                raise ReconciliationRequired("Lot/expiry data needs an explicit tracking contract")
            sku = text(item.get("sku"), "shipped SKU")
            mapped = binding["lines"].get(sku)
            if not mapped or item.get("packType") != mapped["pack_type"]:
                raise ReconciliationRequired("Shipped SKU/pack type differs from the released allocation")
            shipped_packs = number(item.get("quantity"))
            if shipped_packs != shipped_packs.to_integral_value():
                raise ReconciliationRequired("KSP shipped pack quantity must be whole")
            quantities[sku] += shipped_packs * Decimal(mapped["units_per_pack"])
        lines = []
        for sku, quantity in sorted(quantities.items()):
            mapped = binding["lines"][sku]
            cumulative[sku] += quantity
            if cumulative[sku] > Decimal(mapped["quantity"]):
                raise ReconciliationRequired("Package totals exceed the released allocation")
            identifiers = ("sale_line_id", "source_location_id", "product_id", "uom_id")
            native_quantity = float(quantity)
            if not math.isfinite(native_quantity) or native_quantity <= 0:
                raise ReconciliationRequired("Shipped quantity is outside the native numeric range")
            lines.append(dict(zip(identifiers, mapped["identity"]), quantity=native_quantity))
        reports.append({
            "event_id": "ksp-package-" + digest([accepted_order_id, tracking]),
            "warehouse_id": binding["warehouse_id"], "submission_key": binding["code"],
            "wms_order_ref": accepted_order_id,
            "carrier": text(package.get("carrier"), "package carrier"),
            "tracking_numbers": [tracking], "lines": lines,
        })
    return sorted(reports, key=lambda r: r["event_id"])

"""Pure rules. All quantities are normalized units of ONE mapped product.

Adapters must resolve seller-SKU/UOM/kit mapping and correlate commitments with
WMS snapshots before invoking these rules. Booleans/evidence are supplied by the
trusted Odoo service, never accepted directly from a public request.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


def _quantity(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("Quantity must be a nonnegative integer")


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Stock timestamps must have a timezone")


@dataclass(frozen=True)
class StockSnapshot:
    warehouse: str
    available: int
    observed_at: datetime


@dataclass(frozen=True)
class Commitment:
    # Shared key for the SAME demand across channels, Odoo and WMS.
    key: str
    warehouse: str | None
    outstanding: int
    reflected_in_available: int = 0


@dataclass(frozen=True)
class InventoryDecision:
    quantity: int
    excluded_warehouses: tuple[str, ...]


def publishable_inventory(snapshots: Iterable[StockSnapshot], commitments: Iterable[Commitment],
                          *, now: datetime, max_age: timedelta | None,
                          buffer: int = 0, cap: int | None = None) -> InventoryDecision:
    _aware(now)
    _quantity(buffer)
    if cap is not None:
        _quantity(cap)
    if max_age is None or max_age <= timedelta(0):
        raise ValueError("Maximum stock age must be configured before publishing")
    stocks: dict[str, StockSnapshot] = {}
    excluded: set[str] = set()
    for stock in snapshots:
        _quantity(stock.available)
        _aware(stock.observed_at)
        if not stock.warehouse or stock.warehouse in stocks:
            raise ValueError("Require exactly one snapshot per warehouse and product")
        stocks[stock.warehouse] = stock
        if stock.observed_at > now or now - stock.observed_at > max_age:
            excluded.add(stock.warehouse)
    deductions: dict[str | None, int] = {}
    unique: dict[str, Commitment] = {}
    for commitment in commitments:
        _quantity(commitment.outstanding)
        _quantity(commitment.reflected_in_available)
        if not commitment.key or commitment.reflected_in_available > commitment.outstanding:
            raise ValueError("Invalid commitment correlation")
        if commitment.warehouse is not None and commitment.warehouse not in stocks:
            raise ValueError("Missing snapshot for allocated commitment warehouse")
        if commitment.key in unique:
            if commitment != unique[commitment.key]:
                raise ValueError("Conflicting duplicate commitment; resolve before publication")
            continue
        unique[commitment.key] = commitment
        deductions[commitment.warehouse] = deductions.get(commitment.warehouse, 0) + commitment.outstanding - commitment.reflected_in_available
    # Excluded warehouses contribute zero. Their allocations cannot consume healthy
    # stock unless Odoo reallocates them. Unallocated demand consumes the pool.
    pool = sum(max(0, stock.available - deductions.get(key, 0))
               for key, stock in stocks.items() if key not in excluded)
    quantity = max(0, pool - deductions.get(None, 0) - buffer)
    return InventoryDecision(min(quantity, cap) if cap is not None else quantity, tuple(sorted(excluded)))


def dispatch_allowed(*, fulfilled_by: str, status: str, mapping_valid: bool,
                     address_valid: bool, allocation_ready: bool,
                     cancellation_requested: bool, reservation_override: bool) -> bool:
    return (fulfilled_by == "MERCHANT" and status in {"UNSHIPPED", "PARTIALLY_SHIPPED"}
            and mapping_valid and address_valid and allocation_ready
            and not cancellation_requested and not reservation_override)


def reservation_release_allowed(*, accepted_by_wms: bool, stop_verified: bool,
                                shipped_quantity: int) -> bool:
    _quantity(shipped_quantity)
    return shipped_quantity == 0 and (not accepted_by_wms or stop_verified)

from __future__ import annotations

import logging

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import (
    Any,
    List,
    Tuple,
    Dict,
    Set,
    Optional,
    TypeVar,
    Protocol,
    Type,
    Sequence,
    Generic,
    Callable,
)
from dataclasses import dataclass, field

from sqlalchemy.sql.elements import ColumnElement, SQLColumnExpression

from src.database.models import (
    AcendaOrderHeaders,
    AcendaOrderItems,
    SosSalesOrderHeader,
    SosSalesOrderLine,
    SosItem,
)

from src.core.config import settings

logger = logging.getLogger(__name__)


IM_D2C_INCLUDED_CART_IDS = (
    "bh_im",
    "walmart",
    # "bbb",
    # "wayfair",
    # "kohls",
    # "macys",
    # "shopify",
    # "target",
)
IM_D2C_CREATE_DATE_FILTER = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
# IM_D2C_INCLUDED_CART_IDS = ("kohls",)
# IM_D2C_CREATE_DATE_FILTER = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
IM_D2C_EXCLUDED_CART_IDS = "bh_b2b"
IM_D2C_TERMINAL_STATUSES = ("shipped_or_confirmed", "canceled", "error")


WORKABLE_SYNC_STATUSES = {"queued", "error"}
GENERIC_SHIPMENT_SYNC_SOURCES = ("ksp", "productiv")
SUTTON_SALES_REPORT_SOURCE = "sutton_sales_report"
SOS_STAGES_TO_SEND = ("Ready to Send", "Resubmit", "Backorder", "Partial Backorder")


@dataclass
class OrderSnapshot:
    header: SosSalesOrderHeader
    lines: list[SosSalesOrderLine]


@dataclass
class LineAllocation:
    line: SosSalesOrderLine
    posted_qty: Decimal = field(default_factory=lambda: Decimal("0"))
    shipment_package_item_ids: list[int] = field(default_factory=list)

    def add(self, shipment_package_item_id: int, qty: Decimal) -> None:
        self.posted_qty += qty
        if shipment_package_item_id not in self.shipment_package_item_ids:
            self.shipment_package_item_ids.append(shipment_package_item_id)


@dataclass(frozen=True)
class AllocationResult:
    allocations: list[LineAllocation]
    unresolved_count: int
    unresolved_qty: Decimal
    messages: tuple[str, ...]

    @property
    def is_partial(self) -> bool:
        return self.unresolved_count > 0 or self.unresolved_qty > 0

    @property
    def error_message(self) -> str | None:
        if not self.messages:
            return None
        return "; ".join(self.messages)


@dataclass(frozen=True)
class PreparedSync:
    sync_id: int
    payload: dict[str, Any]
    allocations: list[LineAllocation]
    is_partial: bool
    partial_reason: str | None


@dataclass(frozen=True)
class PrepareResult:
    prepared: PreparedSync | None
    status: str | None
    error: str | None = None


def _rithum_normalize_line_key(s: str) -> str:
    return str(s).strip()


def _rithum_normalize_header_key(s: str) -> str:
    return str(s).strip()


def _guest_normalize_line_key(s: str) -> str:
    s = str(s).strip()
    parts = s.split("|")
    if len(parts) == 4:
        return f"{parts[0]}|{parts[1]}|{parts[3]}"
    return s


def _guest_normalize_header_key(s: str) -> str:
    return str(s).strip().split("|", 1)[0]


def _im_d2c_normalize_line_key(s: str) -> str:
    normalized = str(s).strip()
    if "|" in normalized:
        return normalized.split("|", 1)[1]
    return normalized


def _im_d2c_normalize_header_key(s: str) -> str:
    return str(s).strip()


def _default_stage_selector(
    subtotal: float, source: str | None
) -> Tuple[int, Optional[str]]:
    if subtotal and subtotal > 5000:
        return settings.SOS_ESCALATED_ORDER_STAGE_ID, (
            getattr(settings, "SOS_ESCALATED_ORDER_STAGE_NAME", None) or None
        )
    return (
        settings.SOS_DEFAULT_ORDER_STAGE_ID,
        settings.SOS_DEFAULT_ORDER_STAGE_NAME,
    )


def _marketplace_stage_selector(source: str | None) -> dict[str, str | int]:
    if source in settings.acenda_send_to_wms:
        return settings.sos_ready_to_send_order_stage_dict

    return settings.sos_marketplace_order_stage_dict


ModelT = TypeVar("ModelT", SosSalesOrderHeader, SosItem)
PODetailModelT = TypeVar("PODetailModelT")
POHeaderModelT = TypeVar("POHeaderModelT")

HeaderKey = str | int
HeaderKeyOpt = HeaderKey | None
ColType = type[str] | type[int]


@dataclass(frozen=True)
class POSyncSpec(Generic[POHeaderModelT, PODetailModelT]):
    source: str
    po_header_model: Type[POHeaderModelT]
    po_detail_model: Type[PODetailModelT]

    header_key_col: Callable[[Type[POHeaderModelT]], SQLColumnExpression[Any]]
    header_key_from_header: Callable[[POHeaderModelT], HeaderKeyOpt]
    header_key_from_detail: Callable[[PODetailModelT], HeaderKeyOpt]
    header_key_type: ColType
    detail_sort_key: Callable[[PODetailModelT], int]
    build_source_header_key: Callable[[POHeaderModelT], str]
    header_lookup_key_from_sync: Callable[[str], HeaderKeyOpt]
    normalize_line_key_from_sync: Callable[[str], str]
    normalize_header_key_from_sync: Callable[[str], str]
    detail_filters: Callable[[Type[PODetailModelT]], Sequence[ColumnElement[bool]]]
    order_number_prefix: str
    archived_default: bool
    stage_selector: Callable[[float, str | None], dict[str, int | str]]
    order_class_dict: dict[str, int | str]
    location_dict: dict[str, int | str]


GUEST_SPEC = POSyncSpec(
    source="guest",
    po_header_model=GuestSupplyPOHeader,
    po_detail_model=GuestSupplyPODetail,
    header_key_col=lambda H: H.po_number,
    header_key_from_header=lambda h: h.po_number,
    header_key_from_detail=lambda d: d.po_number,
    header_key_type=str,
    detail_sort_key=lambda d: d.line_num,
    build_source_header_key=lambda h: (
        f"{h.po_number}|{h.source_file}" if h.source_file else h.po_number
    ),
    header_lookup_key_from_sync=lambda s: s.split("|", 1)[0] if s else None,
    normalize_line_key_from_sync=_guest_normalize_line_key,
    normalize_header_key_from_sync=_guest_normalize_header_key,
    detail_filters=lambda _model: (),
    order_number_prefix=settings.SOS_DEFAULT_ORDER_PREFIX,
    archived_default=settings.SOS_DEFAULT_ARCHIVED,
    stage_selector=_default_stage_selector,
    order_class_id=settings.SOS_DEFAULT_CLASS_ID,
    order_class_name=settings.SOS_DEFAULT_CLASS_NAME,
    location_id=settings.SOS_DEFAULT_LOCATION_ID,
    location_name=settings.SOS_DEFAULT_LOCATION_NAME,
)

RITHUM_SPEC = POSyncSpec(
    source="rithum",
    po_header_model=RithumPOHeader,
    po_detail_model=RithumPODetail,
    header_key_col=lambda H: H.hub_order_id,
    header_key_from_header=lambda h: h.hub_order_id,
    header_key_from_detail=lambda d: d.hub_order_id,
    header_key_type=int,
    detail_sort_key=lambda d: int(
        d.order_line_item_number or d.merchant_line_item_number or d.hub_line_id
    ),
    build_source_header_key=lambda h: str(h.hub_order_id),
    header_lookup_key_from_sync=lambda s: int(s) if s else None,
    normalize_line_key_from_sync=_rithum_normalize_line_key,
    normalize_header_key_from_sync=_rithum_normalize_header_key,
    detail_filters=lambda _model: (),
    order_number_prefix=settings.SOS_DEFAULT_ORDER_PREFIX,
    archived_default=settings.SOS_DEFAULT_ARCHIVED,
    stage_selector=_default_stage_selector,
    order_class_id=settings.SOS_DEFAULT_CLASS_ID,
    order_class_name=settings.SOS_DEFAULT_CLASS_NAME,
    location_id=settings.SOS_DEFAULT_LOCATION_ID,
    location_name=settings.SOS_DEFAULT_LOCATION_NAME,
)

ACENDA_D2C_SPEC = POSyncSpec(
    source="acenda",
    po_header_model=AcendaOrderHeaders,
    po_detail_model=AcendaOrderItems,
    header_key_col=lambda h: h.id,
    header_key_from_header=lambda h: h.id,
    header_key_from_detail=lambda d: d.order_id,
    header_key_type=int,
    detail_sort_key=lambda d: int(d.id or 0),
    build_source_header_key=lambda h: str(h.id),
    header_lookup_key_from_sync=lambda s: int(s) if s else None,
    normalize_line_key_from_sync=_im_d2c_normalize_line_key,
    normalize_header_key_from_sync=_im_d2c_normalize_header_key,
    detail_filters=lambda d: (
        d.order.has(
            and_(
                # IMOrder.cart_id.notin_(IM_D2C_EXCLUDED_CART_IDS),
                IMOrder.cart_id.in_(IM_D2C_INCLUDED_CART_IDS),
                IMOrder.status.is_not(None),
                # IMOrder.cust_e_mail.is_(None),
                # IMOrder.status.notin_(IM_D2C_TERMINAL_STATUSES),
                IMOrder.created_date_time > IM_D2C_CREATE_DATE_FILTER,
            )
        ),
    ),
    order_number_prefix=settings.sos_default_mkt_prefix,
    archived_default=False,
    stage_selector=_marketplace_stage_selector,
    order_class_dict=settings.sos_dtc_class_dict,
    location_dict=settings.sos_ksp_location_dict,
)


__all__ = ["POSyncSpec", "ACENDA_D2C_SPEC"]

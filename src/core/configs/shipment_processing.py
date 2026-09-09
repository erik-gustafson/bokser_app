from __future__ import annotations

from typing import Literal
from dataclasses import dataclass

from .base import AppBaseSettings


class ShipmentProcessingSettings(AppBaseSettings):

    KSP_SMALL_PARCEL_CODES: dict[str, tuple[str, str]] = {
        "ups": ("UPS", "Standard"),
        "ups 2nd day air": ("UPS", "Expedited"),
        "ups 3 day select": ("UPS", "Expedited"),
        "ups next day air saver": ("UPS", "Expedited"),
        "ups next day air": ("UPS", "Expedited"),
        "ups worldwide expedited": ("UPS", "Expedited"),
        "ups standard": ("UPS", "Standard"),
        "ups2da": ("UPS", "Expedited"),
        "upswwx": ("UPS", "Expedited"),
        "fedex": ("FedEx", "Standard"),
        "fedex 2day": ("FedEx", "Expedited"),
        "fedex express saver": ("FedEx", "Expedited"),
        "fedex ground": ("FedEx", "Standard"),
        "fedex home delivery": ("FedEx", "Standard"),
        "fedex standard overnight": ("FedEx", "Expedited"),
        "fxg": ("FedEx", "Standard"),
        "fxhdl": ("FedEx", "Standard"),
        "fxso": ("FedEx", "Expedited"),
        "ehubusps": ("USPS", "Standard"),
        "ehubuspsfci": ("USPS", "Standard"),
        "ehubuspspm": ("USPS", "Expedited"),
        "ehubuspspmi": ("USPS", "Expedited"),
        "usps": ("USPS", "Standard"),
        "usps first class (ehub)": ("USPS", "Standard"),
        "usps ground advantage (tls)": ("USPS", "Standard"),
        "usps parcel select (ehub)": ("USPS", "Standard"),
        "usps parcel select (tls)": ("USPS", "Standard"),
        "usps priority mail (tls)": ("USPS", "Expedited"),
    }

    SMALL_PARCEL_CARRIERS: list[str] = ["UPS", "FEDEX", "USPS", "DHL", "SMALL PARCEL"]

"""Amazon upstream primitives; Odoo persistence and scheduling are not wired yet."""
from .client import AmazonClient, AmazonAPIError, AmazonWriteUncertain

__all__ = ["AmazonClient", "AmazonAPIError", "AmazonWriteUncertain"]

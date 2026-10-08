from pathlib import Path
from pydantic import SecretStr, Field
from .base import AppBaseSettings


class KSPGatewaySettings(AppBaseSettings):
    # No credentials are needed while the job is disabled.
    ksp_gateway_job_enabled: bool = False
    ksp_gateway_api_key: SecretStr | None = None
    ksp_gateway_journal_path: Path | None = None
    ksp_gateway_pack_rules_path: Path | None = None
    ksp_gateway_interval_minutes: int = Field(default=5, ge=1)
    ksp_gateway_requests_per_minute: int = Field(default=60, ge=1, le=60)
    ksp_gateway_enable_submissions: bool = False
    ksp_gateway_enable_shipments: bool = False
    ksp_gateway_confirm_tracking_identity: bool = False
    # Explicit synthetic delivery allowlist until generic dispatch is installed.
    ksp_gateway_picking_ids: list[int] = Field(default_factory=list)
    ksp_gateway_odoo_url: str | None = None
    ksp_gateway_odoo_database: str | None = None
    ksp_gateway_odoo_api_key: SecretStr | None = None


__all__ = ['KSPGatewaySettings']

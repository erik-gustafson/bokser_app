from pathlib import Path
from pydantic import Field, SecretStr
from .base import AppBaseSettings


class SosMirrorSettings(AppBaseSettings):
    sos_mirror_job_enabled: bool = False
    sos_mirror_source_owner_confirmed: bool = False
    sos_mirror_use_existing_lake: bool = True
    sos_mirror_account_code: str | None = None
    sos_mirror_company_id: int | None = Field(default=None, ge=1)
    sos_mirror_odoo_url: str | None = None
    sos_mirror_odoo_database: str | None = None
    sos_mirror_odoo_api_key: SecretStr | None = None
    sos_mirror_odoo_ca_bundle: Path | None = None
    sos_mirror_journal_root: Path | None = None
    sos_mirror_custom_field_ids: list[int] = Field(default_factory=list)
    sos_mirror_interval_minutes: int = Field(default=5, ge=1)
    sos_mirror_reconciliation_hours: int = Field(default=24, ge=1)
    sos_mirror_delivery_limit: int = Field(default=1000, ge=1, le=10000)


__all__=['SosMirrorSettings']

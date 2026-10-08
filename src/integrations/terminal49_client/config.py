from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Terminal49Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='TERMINAL49_', extra='ignore')
    enabled: bool = False
    database_url: SecretStr
    account_code: str = Field(min_length=1, max_length=64)
    api_key: SecretStr = SecretStr('')
    webhook_secret: SecretStr = SecretStr('')
    pull_token: SecretStr = SecretStr('')
    odoo_company_id: int = Field(gt=0)
    lake_root: Path = Path('/data_lake')
    max_body_bytes: int = Field(default=2_000_000, ge=1024, le=20_000_000)
    request_interval_seconds: float = Field(default=1.0, ge=0.1)
    reconcile_minutes: int = Field(default=60, ge=5)
    max_attempts: int = Field(default=8, ge=1, le=30)

    def require_enabled(self, *, worker=False):
        if not self.enabled:
            raise ValueError('Terminal49 is disabled')
        if not self.database_url.get_secret_value().startswith(('postgresql://', 'postgres://')):
            raise ValueError('Use a PostgreSQL connection URL without SQLAlchemy driver suffix')
        if worker and not self.api_key.get_secret_value():
            raise ValueError('Terminal49 API key is required for worker')
        if not worker and (not self.webhook_secret.get_secret_value() or len(self.pull_token.get_secret_value()) < 32):
            raise ValueError('Configure webhook secret and a pull token of at least 32 characters')

"""Opt-in inbound mirror. Source credentials are shared read-only with the loader."""
import logging
import ssl
import httpx
from src.integrations.sos_odoo_mirror.capture import API_BASE, source_scope
from src.integrations.sos_odoo_mirror.capture_cli import ExistingDatabaseTokenAuth
from src.integrations.sos_odoo_mirror.client import OdooMirrorClient
from src.integrations.sos_odoo_mirror.delivery import DeliveryJournal
from src.integrations.sos_odoo_mirror.sync import synchronize

logger=logging.getLogger(__name__)


class SosMirrorJob:
    def __init__(self, settings):
        if not settings.sos_mirror_source_owner_confirmed:raise ValueError('mirror_source_owner_confirmation_required')
        source_scope(settings.sos_mirror_account_code)
        if not settings.sos_mirror_company_id or not settings.sos_mirror_odoo_api_key or not settings.sos_mirror_journal_root:
            raise ValueError('mirror_target_configuration_required')
        if not settings.sos_mirror_odoo_database or not settings.sos_mirror_odoo_url:
            raise ValueError('mirror_target_configuration_required')
        if any(type(i) is not int or i<=0 for i in settings.sos_mirror_custom_field_ids) or len(set(settings.sos_mirror_custom_field_ids))!=len(settings.sos_mirror_custom_field_ids):
            raise ValueError('invalid_custom_field_approval')
        if not set(settings.sos_mirror_custom_field_ids)<={1,7}:
            raise ValueError('custom_field_not_owner_approved')
        self.settings=settings
        self.journal=DeliveryJournal(settings.sos_mirror_journal_root,{
            'url':settings.sos_mirror_odoo_url,'database':settings.sos_mirror_odoo_database,
            'account_code':settings.sos_mirror_account_code,'company_id':settings.sos_mirror_company_id})
        self.ssl_context=ssl.create_default_context(cafile=str(settings.sos_mirror_odoo_ca_bundle) if settings.sos_mirror_odoo_ca_bundle else None)

    async def run(self, *, reconcile=False):
        from src.integrations.sos_client import SOSClient
        s=self.settings
        async with SOSClient(base_url=API_BASE) as source, httpx.AsyncClient(verify=self.ssl_context) as http:
            source.auth=ExistingDatabaseTokenAuth()
            target=OdooMirrorClient(base_url=s.sos_mirror_odoo_url,database=s.sos_mirror_odoo_database,
                api_key=s.sos_mirror_odoo_api_key.get_secret_value(),client=http)
            return await synchronize(self.journal,source,target,account_code=s.sos_mirror_account_code,
                company_id=s.sos_mirror_company_id,approved_fields=s.sos_mirror_custom_field_ids,
                reconcile=reconcile,reconciliation_hours=s.sos_mirror_reconciliation_hours,
                delivery_limit=s.sos_mirror_delivery_limit,
                lake_root=s.lake_root if s.sos_mirror_use_existing_lake else None)

    async def tick(self):
        try:
            result=await self.run()
            logger.info('SOS mirror result counts: %s',result)
        except Exception:
            # Raw transport/source exceptions may contain headers or customer
            # data. Details stay out of worker logs; cursors remain replay-safe.
            logger.error('SOS mirror tick failed; verify configuration, source completeness and journal status')


def build_sos_mirror_job(settings):
    return SosMirrorJob(settings)

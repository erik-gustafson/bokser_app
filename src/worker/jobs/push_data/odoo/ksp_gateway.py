"""Optional KSP-only job; does not claim mixed-warehouse deliveries."""
import asyncio
from decimal import Decimal
import json
import logging
from pathlib import Path
from uuid import uuid4

from src.integrations.ksp_gateway import GatewayStore, KSPGatewayClient, PackRule, KSPGatewayWorker
from src.integrations.ksp_gateway.client import OdooFulfillmentClient
from src.integrations.ksp_gateway.mapping import build_order, ReconciliationRequired

logger = logging.getLogger('worker.ksp_gateway')


class KSPDeliveryClient(OdooFulfillmentClient):
    def read_delivery(self, picking_id):
        rows = self._call('read', {'ids': [picking_id], 'fields': [
            'id', 'bokser_dispatch_state', 'bokser_payload', 'bokser_claim_token']})
        if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('id') != picking_id:
            raise ReconciliationRequired('Could not verify the requested delivery')
        return rows[0]

    def claim(self, picking_id, claim_token):
        return self._call('bokser_claim_delivery', {'ids': [picking_id], 'claim_token': claim_token})


def submit_delivery(worker, odoo, picking_id):
    """Only an explicitly allowlisted, released delivery entirely routed to KSP."""
    row = odoo.read_delivery(picking_id)
    if row['bokser_dispatch_state'] not in ('queued', 'submitting', 'exception'):
        return {'state': 'skipped'}
    payload = row.get('bokser_payload')
    if not isinstance(payload, dict) or payload.get('picking_id') != picking_id:
        raise ReconciliationRequired('Missing matching frozen release payload')
    allocations = payload.get('allocations', [])
    # Other adapters currently have no Odoo dispatcher. Never seize their claim.
    if len(allocations) != 1 or allocations[0].get('wms_code') != 'ksp':
        return {'state': 'skipped_mixed_or_non_ksp'}
    allocation = allocations[0]
    body, mapping = build_order(payload, allocation, worker.rules)
    if not worker.enable_submissions:
        return {'state': 'preview'}
    try:
        staged = worker.store.get(mapping['code'])
        token = staged['claim_token']
    except KeyError:
        if row['bokser_dispatch_state'] != 'queued':
            raise ReconciliationRequired('Existing Odoo claim has no matching gateway journal; reconcile first')
        token = uuid4().hex
    # Preserve claim token durably BEFORE claiming Odoo. Interrupted claims can
    # resume by comparing the persisted token and exact payload on a fresh read.
    worker.store.stage(body, mapping, token)
    if row['bokser_dispatch_state'] == 'queued':
        claimed = odoo.claim(picking_id, token)
        if claimed and claimed != payload:
            raise ReconciliationRequired('Odoo claim returned a different frozen allocation')
        if not claimed:
            row = odoo.read_delivery(picking_id)
            if row.get('bokser_claim_token') != token or row.get('bokser_payload') != payload:
                raise ReconciliationRequired('Delivery claim belongs to another worker')
    elif row.get('bokser_claim_token') != token:
        raise ReconciliationRequired('Delivery claim differs from the persisted gateway claim')
    return worker.submit_allocation(payload, allocation, token)


class KSPGatewayJob:
    def __init__(self, worker, odoo, picking_ids):
        if any(type(i) is not int or i <= 0 for i in picking_ids):
            raise ValueError('KSP sandbox picking allowlist must contain positive IDs')
        self.worker, self.odoo, self.picking_ids = worker, odoo, list(dict.fromkeys(picking_ids))

    def run_once(self):
        summary = {'deliveries_checked': 0, 'orders_polled': 0, 'errors': 0}
        for picking_id in self.picking_ids:
            try:
                submit_delivery(self.worker, self.odoo, picking_id)
                summary['deliveries_checked'] += 1
            except Exception:
                summary['errors'] += 1
                # Never log buyer payloads, authentication values or response bodies.
                logger.error('KSP delivery %s requires reconciliation', picking_id)
        for code in self.worker.store.poll_codes():
            try:
                self.worker.poll_shipments(code)
                summary['orders_polled'] += 1
            except Exception:
                summary['errors'] += 1
                logger.error('A KSP gateway order requires reconciliation; inspect the private journal')
        return summary

    async def tick(self):
        # HTTPS and SQLite are synchronous; keep them off the shared asyncio loop.
        summary = await asyncio.to_thread(self.run_once)
        logger.info('KSP gateway cycle: checked=%s polled=%s errors=%s',
                    summary['deliveries_checked'], summary['orders_polled'], summary['errors'])


def build_ksp_gateway_job(settings):
    required = (settings.ksp_gateway_api_key, settings.ksp_gateway_journal_path,
                settings.ksp_gateway_pack_rules_path, settings.ksp_gateway_odoo_url,
                settings.ksp_gateway_odoo_database, settings.ksp_gateway_odoo_api_key)
    if not all(required):
        raise ValueError('Enabled KSP gateway job requires its own KSP/Odoo credentials, persistent journal and pack mappings')
    rows = json.loads(Path(settings.ksp_gateway_pack_rules_path).read_text())
    rules = [PackRule(row['sku'], row['odoo_uom_id'], row['pack_type'], Decimal(str(row['odoo_units_per_pack']))) for row in rows]
    store = GatewayStore(settings.ksp_gateway_journal_path,
                         requests_per_minute=settings.ksp_gateway_requests_per_minute)
    gateway = KSPGatewayClient(settings.ksp_gateway_api_key.get_secret_value(), store)
    odoo = KSPDeliveryClient(settings.ksp_gateway_odoo_url, settings.ksp_gateway_odoo_database,
                            settings.ksp_gateway_odoo_api_key.get_secret_value())
    worker = KSPGatewayWorker(gateway, odoo, store, rules,
              enable_submissions=settings.ksp_gateway_enable_submissions,
              enable_shipments=settings.ksp_gateway_enable_shipments,
              confirm_tracking_identity=settings.ksp_gateway_confirm_tracking_identity)
    return KSPGatewayJob(worker, odoo, settings.ksp_gateway_picking_ids)

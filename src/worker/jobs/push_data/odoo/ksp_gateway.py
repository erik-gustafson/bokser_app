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


def positive_ids(values, label):
    if not isinstance(values, (list, tuple)) or any(type(i) is not int or i <= 0 for i in values):
        raise ValueError(label + ' must contain positive integer IDs')
    return tuple(dict.fromkeys(values))


class DiscoveryScope:
    def __init__(self, company_ids, warehouse_ids):
        self.company_ids = positive_ids(company_ids, 'Company scope')
        self.warehouse_ids = positive_ids(warehouse_ids, 'Warehouse scope')
        if not self.company_ids or not self.warehouse_ids:
            raise ValueError('Discovery requires explicit company and KSP warehouse scopes')

    def validate(self, row, picking_id):
        company = row.get('company_id')
        if not isinstance(company, (list, tuple)) or not company or type(company[0]) is not int or company[0] not in self.company_ids:
            raise ReconciliationRequired('Delivery company differs from discovery scope')
        if row.get('state') in ('done', 'cancel'):
            return 'skipped_inactive'
        payload = row.get('bokser_payload')
        if not isinstance(payload, dict) or payload.get('picking_id') != picking_id:
            raise ReconciliationRequired('Missing matching frozen release payload')
        allocations = payload.get('allocations')
        if not isinstance(allocations, list) or len(allocations) != 1 or not isinstance(allocations[0], dict) or allocations[0].get('wms_code') != 'ksp':
            return 'skipped_mixed_or_non_ksp'
        warehouse = allocations[0].get('warehouse_id')
        if type(warehouse) is not int or warehouse not in self.warehouse_ids:
            return 'skipped_warehouse_scope'
        return None


class KSPDeliveryClient(OdooFulfillmentClient):
    def __init__(self, *args, company_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.company_ids = positive_ids(company_ids, 'Company scope')

    def _call(self, method, arguments):
        if self.company_ids:
            arguments = dict(arguments, context={'allowed_company_ids': list(self.company_ids)})
        return super()._call(method, arguments)

    def discover_deliveries(self, scope, after_id=0, limit=50):
        if type(after_id) is not int or after_id < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Invalid discovery page')
        domain = [
            ['id', '>', after_id], ['company_id', 'in', list(scope.company_ids)],
            ['picking_type_id.code', '=', 'outgoing'], ['location_dest_id.usage', '=', 'customer'],
            ['state', 'not in', ['done', 'cancel']], ['sale_id.state', '=', 'sale'],
            ['sale_id.bokser_managed', '=', True], ['sale_id.bokser_released_at', '!=', False],
            ['bokser_dispatch_state', 'in', ['queued', 'submitting', 'exception']],
        ]
        rows = self._call('search_read', {'domain': domain, 'fields': ['id'], 'order': 'id asc',
                                        'limit': limit, 'context': {'allowed_company_ids': list(scope.company_ids)}})
        if not isinstance(rows, list) or len(rows) > limit:
            raise ReconciliationRequired('Invalid discovery response')
        ids = []
        for row in rows:
            value = row.get('id') if isinstance(row, dict) else None
            if type(value) is not int or value <= (ids[-1] if ids else after_id):
                raise ReconciliationRequired('Discovery IDs must be increasing and unique')
            ids.append(value)
        return ids

    def read_delivery(self, picking_id):
        rows = self._call('read', {'ids': [picking_id], 'fields': [
            'id', 'state', 'company_id', 'bokser_dispatch_state', 'bokser_payload', 'bokser_claim_token']})
        if not isinstance(rows, list) or len(rows) != 1 or rows[0].get('id') != picking_id:
            raise ReconciliationRequired('Could not verify the requested delivery')
        return rows[0]

    def claim(self, picking_id, claim_token):
        return self._call('bokser_claim_delivery', {'ids': [picking_id], 'claim_token': claim_token})


def submit_delivery(worker, odoo, picking_id, *, scope=None):
    """Only a scoped or explicitly allowlisted, released delivery entirely routed to KSP."""
    row = odoo.read_delivery(picking_id)
    if scope is not None:
        skipped = scope.validate(row, picking_id)
        if skipped: return {'state': skipped}
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
    if scope is not None:
        try:
            existing = worker.store.get(mapping['code'])
        except KeyError:
            existing = None
        if existing and (existing['body'] != body or existing['mapping'] != mapping):
            raise ReconciliationRequired('Frozen content differs from the existing gateway journal')
        if row['bokser_dispatch_state'] != 'queued':
            if not existing or existing['claim_token'] != row.get('bokser_claim_token'):
                raise ReconciliationRequired('Existing delivery claim is not owned by this journal')
        elif row.get('bokser_claim_token'):
            raise ReconciliationRequired('Queued delivery has an unexpected claim')
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
    def __init__(self, worker, odoo, picking_ids, *, discovery_scope=None, batch_size=50, discovery_preview_only=True):
        if any(type(i) is not int or i <= 0 for i in picking_ids):
            raise ValueError('KSP sandbox picking allowlist must contain positive IDs')
        if discovery_scope is not None and picking_ids:
            raise ValueError('Choose discovery or explicit picking mode, not both')
        if type(batch_size) is not int or not 1 <= batch_size <= 200:
            raise ValueError('Discovery batch size must be 1 to 200')
        if discovery_scope is not None and discovery_preview_only and worker.enable_submissions:
            raise ValueError('Discovery preview cannot enable submissions')
        self.discovery_preview_only = discovery_preview_only
        self.scope, self.batch_size, self.after_id = discovery_scope, batch_size, 0
        self.worker, self.odoo, self.picking_ids = worker, odoo, list(dict.fromkeys(picking_ids))

    def run_once(self):
        summary = {'deliveries_checked': 0, 'orders_polled': 0, 'errors': 0}
        candidates = self.picking_ids
        if self.scope is not None:
            try:
                candidates = self.odoo.discover_deliveries(self.scope, self.after_id, self.batch_size)
                if not candidates and self.after_id:
                    self.after_id = 0
                    candidates = self.odoo.discover_deliveries(self.scope, 0, self.batch_size)
                if candidates: self.after_id = candidates[-1]
            except Exception:
                candidates = []
                summary['errors'] += 1
                logger.error('KSP discovery failed; no new delivery claimed')
        for picking_id in candidates:
            try:
                submit_delivery(self.worker, self.odoo, picking_id, scope=self.scope)
                summary['deliveries_checked'] += 1
            except Exception:
                summary['errors'] += 1
                # Never log buyer payloads, authentication values or response bodies.
                logger.error('KSP delivery %s requires reconciliation', picking_id)
        # Automatic preview performs Odoo reads only, including no KSP polling.
        if self.scope is not None and self.discovery_preview_only:
            return summary
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
    scope = DiscoveryScope(settings.ksp_gateway_company_ids, settings.ksp_gateway_warehouse_ids) if settings.ksp_gateway_discovery_enabled else None
    if scope is not None and settings.ksp_gateway_picking_ids:
        raise ValueError('Choose discovery or explicit picking mode, not both')
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
                            settings.ksp_gateway_odoo_api_key.get_secret_value(),
                            company_ids=scope.company_ids if scope else ())
    worker = KSPGatewayWorker(gateway, odoo, store, rules,
              enable_submissions=settings.ksp_gateway_enable_submissions,
              enable_shipments=settings.ksp_gateway_enable_shipments,
              confirm_tracking_identity=settings.ksp_gateway_confirm_tracking_identity)
    return KSPGatewayJob(worker, odoo, settings.ksp_gateway_picking_ids, discovery_scope=scope,
                         batch_size=settings.ksp_gateway_discovery_batch_size,
                         discovery_preview_only=settings.ksp_gateway_discovery_preview_only)

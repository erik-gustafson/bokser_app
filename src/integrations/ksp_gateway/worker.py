from .client import GatewayError
from .mapping import build_order, package_reports, ReconciliationRequired, text


class KSPGatewayWorker:
    """Dispatcher hook for an already claimed physical KSP allocation.

    The shared dispatcher retains ownership of delivery claims and the other
    warehouse routes. This worker never claims an entire mixed-warehouse job.
    """
    def __init__(self, gateway, odoo, store, rules, *, enable_submissions=False,
                 enable_shipments=False, confirm_tracking_identity=False):
        self.gateway, self.odoo, self.store, self.rules = gateway, odoo, store, rules
        self.enable_submissions = enable_submissions
        self.enable_shipments = enable_shipments
        # The guide lacks immutable shipment IDs. Keep stock writes disabled
        # until KSP confirms unique, stable package tracking and immutable items.
        self.confirm_tracking_identity = confirm_tracking_identity

    def submit_allocation(self, payload, allocation, claim_token, shipping_options=None):
        body, mapping = build_order(payload, allocation, self.rules, shipping_options)
        if not self.enable_submissions:
            return {"state": "preview", "order": body, "mapping": mapping}
        claim_token = text(claim_token, "existing Odoo claim token")
        binding = self.store.stage(body, mapping, claim_token)
        if binding["state"] == "ready" and self.store.start_post(mapping["code"]):
            try:
                response = self.gateway.submit_order(body)
                self._accept_response(mapping["code"], response)
            except GatewayError as exc:
                # A definitive 429 did not pass the rate limiter. All other
                # failures need reconciliation; never blindly re-POST a timeout.
                state = "ready" if exc.status == 429 else "uncertain"
                self.store.state(mapping["code"], state, note=str(exc))
                raise
        return self.reconcile(mapping["code"])

    def _accept_response(self, code, response):
        if not isinstance(response, dict) or response.get("code") != code:
            self.store.state(code, "uncertain", note="Unexpected submission response")
            raise ReconciliationRequired("Submission response does not match the frozen order code")
        order_id = text(response.get("orderId"), "gateway order ID")
        if response.get("status") in ("sent", "fulfilled"):
            self.store.state(code, "accepted", order_id=order_id, logiwa_id=response.get("logiwaOrderId"))
        elif response.get("status") == "received":
            self.store.state(code, "pending", order_id=order_id)
        else:
            self.store.state(code, "uncertain", order_id=order_id, note="Unverified gateway status")
            raise ReconciliationRequired("Gateway status does not prove warehouse acceptance")

    def reconcile(self, code):
        binding = self.store.get(code)
        if binding["state"] in ("posting", "uncertain"):
            # Exact list filtering is documented. The response envelope and
            # returned IDs must be confirmed before recovering unknown POSTs.
            found = self.gateway.find_order(code)
            if not found:
                return {"state": "uncertain", "code": code}
            # Do not accept an existing duplicate merely by code. Its full
            # address and line comparison needs an actual order-detail fixture.
            return {"state": "reconciliation_required", "code": code}
        if binding["state"] == "pending":
            # Actual sandbox order-detail returns flattened Logiwa fields, not
            # the gateway create response. Tracking exposes gateway identity
            # and acceptance status even before packages exist.
            response = self.gateway.tracking(binding["order_id"])
            if not isinstance(response, dict) or response.get("orderId") != binding["order_id"]:
                raise ReconciliationRequired("Pending status response does not match the saved gateway order")
            self._accept_response(code, {"code": code, "orderId": binding["order_id"],
                                         "status": response.get("status")})
            binding = self.store.get(code)
        if binding["state"] == "accepted":
            self.odoo.acknowledge(binding["mapping"]["anchor_id"], binding["claim_token"],
                                  binding["order_id"], binding["mapping"]["warehouse_id"])
            self.store.state(code, "acknowledged")
        return {"state": self.store.get(code)["state"], "code": code}

    def poll_shipments(self, code):
        binding = self.store.get(code)
        if binding["state"] != "acknowledged":
            return self.reconcile(code)
        raw = self.gateway.tracking(binding["order_id"])
        reports = package_reports(raw, binding["mapping"], binding["order_id"])
        if not self.enable_shipments or not self.confirm_tracking_identity:
            return {"state": "preview", "reports": reports}
        self.store.stage_packages(code, reports)
        count = 0
        for report in self.store.pending_packages(code):
            result = self.odoo.apply_shipment(binding["mapping"]["anchor_id"], report)
            # If Odoo committed but this write is interrupted, the exact same
            # event is retried; Odoo's ledger returns replay without stock writes.
            self.store.applied(report["event_id"], result)
            count += 1
        return {"state": "applied", "events": count, "code": code}

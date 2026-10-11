"""Synthetic HTTPS regression against an explicitly disposable mirror database.
Requires SOS_MIRROR_ODOO_URL/DATABASE/API_KEY/ACCOUNT/COMPANY in the environment.
Optional SOS_MIRROR_TLS_CA points to the local test certificate. Never logs keys.
The owner must provision/enable the test account; this script creates synthetic
partners and leaves them in that disposable database for inspection.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import ssl
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from src.integrations.sos_odoo_mirror.client import OdooMirrorClient
from src.integrations.sos_odoo_mirror.contract import ADDRESS_FIELDS, CONTACT_FIELDS, normalize


async def verify():
    database = os.environ["SOS_MIRROR_ODOO_DATABASE"]
    if not database.startswith("bokser_sos_mirror_local"):
        raise ValueError("disposable_database_required")
    company = int(os.environ["SOS_MIRROR_ODOO_COMPANY"])
    account = os.environ["SOS_MIRROR_ODOO_ACCOUNT"]
    context = ssl.create_default_context(cafile=os.environ.get("SOS_MIRROR_TLS_CA"))
    start = datetime.now(timezone.utc) - timedelta(days=1)
    source_id = secrets.randbelow(900000000) + 100000000
    checks = []
    async with httpx.AsyncClient(verify=context, trust_env=False) as http:
        client = OdooMirrorClient(base_url=os.environ["SOS_MIRROR_ODOO_URL"], database=database,
            api_key=os.environ["SOS_MIRROR_ODOO_API_KEY"], client=http)
        def payload(name="Synthetic runtime contact", offset=0, identifier=source_id, entity="customer"):
            return normalize(entity, {"id": identifier, "name": name},
                (start + timedelta(seconds=offset)).isoformat())
        async def send(p):
            return await client.import_partner(account_code=account, company_id=company, payload=p)
        async def blocked(p, code, company_id=company):
            response = await http.post(client.url, headers=client.headers,
                json={"account_code": account, "company_id": company_id, "payload": p})
            assert response.status_code >= 400 and code in response.text, "expected_gate_failed"
        first = await send(payload())
        assert first["status"] == "created"
        checks.append("create")
        duplicate = await send(payload())
        assert duplicate["status"] == "duplicate" and duplicate["partner_id"] == first["partner_id"]
        checks.append("duplicate")
        updated = await send(payload("Synthetic updated", 2))
        assert updated["status"] == "updated" and updated["partner_id"] == first["partner_id"]
        checks.append("update")
        assert (await send(payload("Synthetic older", 1)))["status"] == "stale"
        checks.append("stale")
        await blocked(payload("Synthetic conflict", 2), "observation_conflict")
        checks.append("same_time_conflict")
        edit = await http.post(client.url.split("/json/2/")[0] + "/json/2/res.partner/write",
            headers=client.headers, json={"ids": [first["partner_id"]], "vals": {"phone": "synthetic local edit"}})
        assert edit.status_code == 200
        await blocked(payload("Synthetic updated", 2), "local_edit_conflict")
        checks.append("local_edit_conflict")
        await blocked(payload(identifier=source_id+1), "SOS company not allowed", company_id=-1)
        checks.append("company_gate")
        assert (await send(payload(identifier=source_id+2, entity="vendor")))["status"] == "created"
        checks.append("vendor")
        concurrent = await asyncio.gather(send(payload(identifier=source_id+3)), send(payload(identifier=source_id+3)))
        assert sorted(v["status"] for v in concurrent) == ["created", "duplicate"]
        assert concurrent[0]["partner_id"] == concurrent[1]["partner_id"]
        checks.append("concurrent_replay")
        parent_payload = normalize("customer", {"id": source_id+4, "name": "Synthetic parent",
            "phone": "555-0100", "mobile": "555-0101"}, start.isoformat())
        root = await send(parent_payload)
        child_payload = normalize("customer", {"id": source_id+5, "name": "Synthetic child",
            "parent": {"id": source_id+4}}, start.isoformat())
        child = await send(child_payload)
        rows = await http.post(client.url.split("/json/2/")[0] + "/json/2/res.partner/read",
            headers=client.headers, json={"ids": [root["partner_id"], child["partner_id"]],
                "fields": ["parent_id", "phone", "bokser_sos_mobile"]})
        assert rows.status_code == 200
        by_id = {row["id"]: row for row in rows.json()}
        assert (by_id[root["partner_id"]]["phone"], by_id[root["partner_id"]]["bokser_sos_mobile"]) == ("555-0100", "555-0101")
        assert by_id[child["partner_id"]]["parent_id"][0] == root["partner_id"]
        checks.extend(["dual_phone", "parent_child"])
        assert (await send(child_payload))["status"] == "duplicate"
        checks.append("child_replay")
        missing = normalize("customer", {"id": source_id+6, "name": "Synthetic orphan",
            "parent": {"id": source_id+7}}, start.isoformat())
        await blocked(missing, "parent_binding_missing")
        checks.append("missing_parent")
        # The disposable owner provisions reviewed reference fixtures: SOS
        # currency 42, terms 11, country US and state US|NY. No source names are
        # used to adopt native partners or accounting reference records.
        def master(token=10, name="Synthetic master", identifier=source_id+20):
            address = dict.fromkeys(ADDRESS_FIELDS, "")
            address.update(line1="Synthetic Street", line2="Suite 2", line3="Line 3",
                line4="Line 4", line5="Line 5", city="Synthetic City", country="US", stateProvince="NY", postalCode="10001")
            contact = dict.fromkeys(CONTACT_FIELDS, "")
            contact.update(firstName="Synthetic", lastName="Person")
            return normalize("customer", dict(id=identifier, name=name, syncToken=token,
                companyName="Synthetic Company", altPhone="555-0102", fax="555-0103",
                billing=address, shipping=dict(address, line1="Synthetic Delivery"), contact=contact,
                currency={"id": 42}, terms={"id": 11}), start.isoformat())
        p = master()
        first = await send(p)
        assert first["status"] == "created"
        assert (await send(p))["status"] == "duplicate"
        checks.append("master_create_replay")
        read_url = client.url.split("/json/2/")[0] + "/json/2/res.partner/read"
        rows = await http.post(read_url, headers=client.headers, json={"ids": [first["partner_id"]],
            "fields": ["street", "street2", "bokser_sos_line3", "bokser_sos_line4", "bokser_sos_line5",
                "property_payment_term_id", "bokser_sos_currency_id", "child_ids"]})
        assert rows.status_code == 200
        row = rows.json()[0]
        assert [row[k] for k in ("street", "street2", "bokser_sos_line3", "bokser_sos_line4", "bokser_sos_line5")] == ["Synthetic Street", "Suite 2", "Line 3", "Line 4", "Line 5"]
        assert row["property_payment_term_id"] and row["bokser_sos_currency_id"] and len(row["child_ids"]) == 2
        checks.append("master_native_fields")
        older = master(9, "Synthetic older source")
        older["observed_at"] = (start + timedelta(days=2)).isoformat()
        assert (await send(older))["status"] == "stale"
        checks.append("source_revision_stale")
        await blocked(master(10, "Synthetic same revision conflict"), "source_revision_conflict")
        checks.append("source_revision_conflict")
        newer = master(11, "Synthetic newer source")
        newer["observed_at"] = (start - timedelta(days=1)).isoformat()
        assert (await send(newer))["status"] == "updated"
        assert (await send(master(12, "Synthetic newer source")))["status"] == "duplicate"
        assert (await send(master(11, "Synthetic stale after duplicate")))["status"] == "stale"
        checks.append("source_revision_advance")
        child_rows = await http.post(read_url, headers=client.headers, json={"ids": row["child_ids"], "fields": ["type", "name", "street"]})
        assert child_rows.status_code == 200
        delivery = next(v for v in child_rows.json() if v["type"] == "delivery")
        edit = await http.post(client.url.split("/json/2/")[0] + "/json/2/res.partner/write",
            headers=client.headers, json={"ids": [delivery["id"]], "vals": {"street": "Synthetic local edit"}})
        assert edit.status_code == 200
        await blocked(master(13, "Synthetic newer source"), "local_edit_conflict")
        checks.append("master_child_edit_conflict")
        unresolved = master(identifier=source_id+21)
        unresolved["master"]["currency_id"] = "999999999"
        await blocked(unresolved, "master_reference_mapping_required:currency")
        checks.append("master_reference_gate")
    print(json.dumps({"passed": checks}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disposable", action="store_true", required=True)
    parser.parse_args()
    try:
        asyncio.run(verify())
    except Exception:
        parser.exit(1, "mirror_runtime_check_failed; inspect disposable service logs\n")

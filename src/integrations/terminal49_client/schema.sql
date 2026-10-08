-- Additive, independently versioned schema. Does not alter Alembic's graph.
CREATE SCHEMA IF NOT EXISTS terminal49;
CREATE TABLE IF NOT EXISTS terminal49.schema_version (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), version integer NOT NULL
);
INSERT INTO terminal49.schema_version VALUES(true, 1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS terminal49.notifications (
    account text NOT NULL, notification_id uuid NOT NULL, event text NOT NULL,
    payload jsonb NOT NULL, sha256 text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'PENDING', attempts integer NOT NULL DEFAULT 0,
    retry_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz, last_error text,
    PRIMARY KEY(account, notification_id)
);
CREATE INDEX IF NOT EXISTS t49_pending ON terminal49.notifications(account, status, retry_at);
CREATE TABLE IF NOT EXISTS terminal49.deliveries (
    delivery_id text PRIMARY KEY, account text NOT NULL, notification_id uuid,
    signature_valid boolean NOT NULL, accepted boolean NOT NULL, duplicate boolean NOT NULL DEFAULT false,
    reason text, file_path text NOT NULL UNIQUE, sha256 text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS terminal49.mappings (
    account text NOT NULL, company_id integer NOT NULL CHECK(company_id > 0),
    container_id uuid NOT NULL, odoo_container_id integer NOT NULL CHECK(odoo_container_id > 0),
    expected_number text NOT NULL, active boolean NOT NULL DEFAULT true,
    next_refresh_at timestamptz NOT NULL DEFAULT now(), last_error text,
    PRIMARY KEY(account, company_id, container_id),
    UNIQUE(account, company_id, odoo_container_id)
);
CREATE TABLE IF NOT EXISTS terminal49.snapshots (
    account text NOT NULL, container_id uuid NOT NULL,
    shipment_id uuid, number text NOT NULL, observed_at timestamptz NOT NULL,
    payload jsonb NOT NULL, PRIMARY KEY(account, container_id)
);
CREATE TABLE IF NOT EXISTS terminal49.events (
    account text NOT NULL, resource_type text NOT NULL, event_id text NOT NULL,
    container_id uuid NOT NULL, payload jsonb NOT NULL, observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(account, resource_type, event_id, container_id)
);
-- Counter row lock serializes feed publication until transaction commit.
-- A bare sequence could expose N+1 while N is still uncommitted.
CREATE TABLE IF NOT EXISTS terminal49.feed_counter (
    account text PRIMARY KEY, version bigint NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS terminal49.feed (
    account text NOT NULL, version bigint NOT NULL, company_id integer NOT NULL,
    container_id uuid NOT NULL, odoo_container_id integer NOT NULL,
    payload jsonb NOT NULL, published_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(account, version)
);
CREATE INDEX IF NOT EXISTS t49_feed_company ON terminal49.feed(account, company_id, version);

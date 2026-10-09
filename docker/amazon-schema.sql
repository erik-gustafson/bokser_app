-- Run with amazon_admin in amazon_orders; runtime amazon_app cannot create tables.
BEGIN;
CREATE TABLE IF NOT EXISTS amazon.connector_cursor (
    account_code text PRIMARY KEY, watermark timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS amazon.connector_inbox (
    account_code text NOT NULL, order_id text NOT NULL, updated_at timestamptz NOT NULL,
    payload jsonb NOT NULL, delivered boolean NOT NULL DEFAULT false,
    PRIMARY KEY(account_code, order_id)
);
GRANT SELECT,INSERT,UPDATE,DELETE ON amazon.connector_cursor,amazon.connector_inbox TO amazon_app;
COMMIT;

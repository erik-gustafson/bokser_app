from psycopg.types.json import Jsonb
from datetime import datetime


class AmazonInbox:
    """Connection targets only the dedicated Amazon database, never the raw lake."""
    def __init__(self, connection, account_code):
        self.db, self.account = connection, account_code

    def lock(self):
        # Session lock covers fetch/store/delivery; all instances use this fence.
        row = self.db.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", ('amazon:' + self.account,)).fetchone()
        self.db.commit()
        if not row[0]:
            raise RuntimeError('Another Amazon worker owns this account')

    def cursor(self, initial):
        row = self.db.execute('SELECT watermark FROM amazon.connector_cursor WHERE account_code=%s', (self.account,)).fetchone()
        self.db.commit()
        return row[0] if row else initial

    def store_page(self, orders):
        with self.db.transaction():
            for order in orders:
                prior = self.db.execute('SELECT updated_at,payload FROM amazon.connector_inbox WHERE account_code=%s AND order_id=%s', (self.account, order['order_id'])).fetchone()
                if prior and prior[0] == datetime.fromisoformat(order['updated_at']) and prior[1] != order:
                    raise ValueError('Conflicting order version; cursor not advanced')
                self.db.execute("""INSERT INTO amazon.connector_inbox(account_code, order_id, updated_at, payload)
                    VALUES (%s,%s,%s,%s) ON CONFLICT(account_code,order_id) DO UPDATE
                    SET updated_at=EXCLUDED.updated_at,payload=EXCLUDED.payload,delivered=false
                    WHERE EXCLUDED.updated_at > connector_inbox.updated_at""",
                    (self.account, order['order_id'], order['updated_at'], Jsonb(order)))

    def retry_order(self, order_id):
        with self.db.transaction():
            self.db.execute('UPDATE amazon.connector_inbox SET delivered=false WHERE account_code=%s AND order_id=%s', (self.account, order_id))

    def advance(self, upper):
        with self.db.transaction():
            self.db.execute("""INSERT INTO amazon.connector_cursor(account_code,watermark) VALUES (%s,%s)
                ON CONFLICT(account_code) DO UPDATE SET watermark=GREATEST(connector_cursor.watermark,EXCLUDED.watermark)""", (self.account, upper))

    def pending(self):
        rows = self.db.execute('SELECT order_id,updated_at,payload FROM amazon.connector_inbox WHERE account_code=%s AND NOT delivered ORDER BY updated_at,order_id LIMIT 100', (self.account,)).fetchall()
        self.db.commit()
        return rows

    def acknowledge(self, order_id, updated_at):
        with self.db.transaction():
            self.db.execute('UPDATE amazon.connector_inbox SET delivered=true WHERE account_code=%s AND order_id=%s AND updated_at=%s', (self.account, order_id, updated_at))

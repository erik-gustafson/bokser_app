## Marketplace Order Load

1) Load New Order json and create SOS order

LEFT JOIN last 90 days of Acenda Orders to SOS on acenda.id = sos.customer_po

    SELECT acenda.order_headers.id
    FROM acenda.order_headers
    LEFT JOIN sos.sales_order_headers on acenda.order_headers.id::text = sos.sales_order_headers.customer_po
    WHERE acenda.order_headers.created_at >= CURRENT_DATE - 90

Map to SOS Fields
Create

- Not Logging failures outside of error table.  Rely on Acenda Header to Sos Header table Left Join (In Acenda Table, Not in SOS) to catch missing records.  


# Backfill

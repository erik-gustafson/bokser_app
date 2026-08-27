from __future__ import annotations

import unittest

from sqlalchemy.orm import configure_mappers

from src.database import models  # noqa: F401
from src.database.base import Base


class ModelMetadataTests(unittest.TestCase):
    def test_all_tables_have_resolvable_primary_and_foreign_keys(self) -> None:
        configure_mappers()

        for table in Base.metadata.sorted_tables:
            self.assertTrue(
                list(table.primary_key.columns),
                f"{table.fullname} does not define a primary key",
            )
            for foreign_key in table.foreign_keys:
                self.assertIsNotNone(foreign_key.column)

    def test_ingest_mappings_reference_model_columns(self) -> None:
        for mapper in Base.registry.mappers:
            ingest = getattr(mapper.class_, "Ingest", None)
            if ingest is None:
                continue

            columns = set(mapper.local_table.columns.keys())
            self.assertTrue(set(ingest.key_fields).issubset(columns))
            self.assertTrue(
                {field.target for field in ingest.field_map}.issubset(columns)
            )
            for key in ingest.key_fields:
                self.assertFalse(
                    mapper.local_table.c[key].nullable,
                    f"{mapper.local_table.fullname}.{key} is an ingest key but nullable",
                )

    def test_guest_supply_detail_uses_order_data_schema(self) -> None:
        detail = Base.metadata.tables["order_data.guest_supply_po_details"]
        foreign_key = next(iter(detail.c.po_number.foreign_keys))

        self.assertEqual(detail.schema, "order_data")
        self.assertEqual(
            foreign_key.target_fullname,
            "order_data.guest_supply_po_headers.po_number",
        )


if __name__ == "__main__":
    unittest.main()

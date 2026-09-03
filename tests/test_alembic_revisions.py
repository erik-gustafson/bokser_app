from __future__ import annotations

import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


class AlembicRevisionTests(unittest.TestCase):
    def test_revision_history_is_single_linear_chain(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        config = Config(repository_root / "alembic.ini")
        script = ScriptDirectory.from_config(config)

        self.assertEqual(len(script.get_heads()), 1)

        revisions = list(script.walk_revisions())
        self.assertTrue(revisions)
        self.assertFalse(
            [revision.revision for revision in revisions if revision.is_branch_point]
        )
        self.assertFalse(
            [revision.revision for revision in revisions if revision.is_merge_point]
        )


if __name__ == "__main__":
    unittest.main()

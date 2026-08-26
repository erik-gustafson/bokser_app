from __future__ import annotations

import logging
import sys
import unittest

from src.core.utils.logger import LOG_FORMAT, setup_logging


class ConsoleLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root_logger = logging.getLogger()
        self.original_level = self.root_logger.level
        self.original_handlers = self.root_logger.handlers[:]
        self.root_logger.handlers.clear()

    def tearDown(self) -> None:
        for handler in self.root_logger.handlers[:]:
            self.root_logger.removeHandler(handler)
            handler.close()
        self.root_logger.handlers[:] = self.original_handlers
        self.root_logger.setLevel(self.original_level)

    def test_setup_installs_one_stdout_handler(self) -> None:
        configured_logger = setup_logging("DEBUG")

        self.assertIs(configured_logger, self.root_logger)
        self.assertEqual(configured_logger.level, logging.DEBUG)
        self.assertEqual(len(configured_logger.handlers), 1)
        handler = configured_logger.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)
        self.assertIs(handler.stream, sys.stdout)
        self.assertEqual(handler.formatter._fmt, LOG_FORMAT)

    def test_repeated_setup_does_not_duplicate_handlers(self) -> None:
        first_handler = setup_logging("INFO").handlers[0]
        configured_logger = setup_logging("WARNING")

        self.assertEqual(configured_logger.level, logging.WARNING)
        self.assertEqual(len(configured_logger.handlers), 1)
        self.assertIsNot(configured_logger.handlers[0], first_handler)

    def test_invalid_log_level_falls_back_to_info(self) -> None:
        configured_logger = setup_logging("not-a-level")

        self.assertEqual(configured_logger.level, logging.INFO)


if __name__ == "__main__":
    unittest.main()

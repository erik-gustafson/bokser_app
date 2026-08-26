import logging
import sys

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _resolve_log_level(log_level: str) -> int:
    level = getattr(logging, str(log_level).upper(), logging.INFO)
    return level if isinstance(level, int) else logging.INFO


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure application logging for container stdout collection."""
    root_logger = logging.getLogger()
    root_logger.setLevel(_resolve_log_level(log_level))

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root_logger.addHandler(console_handler)

    return root_logger

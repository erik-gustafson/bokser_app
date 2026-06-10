# app/core/logging.py
import os
import logging
from logging.handlers import TimedRotatingFileHandler

DEFAULT_LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
FALLBACK_LOG_DIR = os.path.join(os.getcwd(), "logs")


def _build_file_handler(filepath: str) -> TimedRotatingFileHandler:
    handler = TimedRotatingFileHandler(
        filepath,
        when="midnight",
        backupCount=14,
        encoding="utf-8"
    )
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    return handler

def get_file_handler(filename: str):
    log_directories = [DEFAULT_LOG_DIR, FALLBACK_LOG_DIR]
    last_error: OSError | None = None

    for log_directory in log_directories:
        try:
            os.makedirs(log_directory, exist_ok=True)
            filepath = os.path.join(log_directory, filename)
            return _build_file_handler(filepath)
        except OSError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("No writable log directory available")

def setup_logging(log_file: str):
    """
    log_file -> "api.log" OR "worker.log" OR "migrate.log"
    """
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Remove any default handlers so logs don't double-print
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Add rotating file handler
    logger.addHandler(get_file_handler(log_file))

    # Add console handler for docker logs
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(console)

    return logger

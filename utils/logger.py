"""
utils/logger.py — Centralized logging setup.

Creates a single logger instance used across the entire application.
Using Python's built-in `logging` module (not print statements) gives us:
  - Timestamps on every message
  - Log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - Output to both console AND a rotating log file simultaneously
  - Easy filtering: set level to WARNING in production to reduce noise
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "supportflow.log")
LOG_FORMAT = "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# The single logger instance shared across the whole app.
# Other modules do: from utils.logger import logger
logger = logging.getLogger("supportflow")


def setup_logger(debug: bool = False) -> logging.Logger:
    """
    Configure the logger with console and file handlers.

    Called once during app initialisation.  Subsequent calls to
    `logging.getLogger("supportflow")` anywhere in the codebase return
    the same already-configured logger.

    Args:
        debug: If True, set level to DEBUG. Otherwise INFO.

    Returns:
        The configured logger instance.
    """
    # Avoid adding duplicate handlers if setup_logger is called more than once
    if logger.handlers:
        return logger

    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # ------------------------------------------------------------------
    # Console handler — prints to terminal
    # ------------------------------------------------------------------
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ------------------------------------------------------------------
    # File handler — writes to logs/supportflow.log
    # RotatingFileHandler caps the file at 5 MB, keeps 3 backups.
    # This means logs never consume unlimited disk space.
    # ------------------------------------------------------------------
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.info("Logger initialised. Log file: %s", LOG_FILE)
    return logger

"""
HighFold-C2C Logging Configuration

Provides console + file logging setup.
"""

import logging
import os
from pathlib import Path


def get_log_file_path() -> Path:
    """Get the log file path, creating the directory if needed."""
    log_dir = Path(os.getenv("LOG_DIR", "/tmp/highfold_c2c/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "highfold_c2c.log"


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
) -> None:
    """Configure application-wide logging.

    Parameters
    ----------
    level : str
        Root log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    log_file : Path, optional
        If provided, also write logs to this file.
    """
    handlers: list[logging.Handler] = []

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handlers.append(console)

    # File handler (optional)
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )

"""Logging configuration for inSTREAM."""
import logging


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the instream namespace prefix."""
    return logging.getLogger(f"instream.{name}")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for inSTREAM."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

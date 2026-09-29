import logging


def setup_logging() -> None:
    """Configure logging once when the application starts."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger named after the module using it."""
    return logging.getLogger(name)
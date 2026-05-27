"""Setup logging coerente per API e worker."""
import logging
import sys

from .config import settings


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s :: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    # Riduci verbosità di librerie chiacchierone
    for noisy in ("httpx", "httpcore", "urllib3", "apscheduler.scheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

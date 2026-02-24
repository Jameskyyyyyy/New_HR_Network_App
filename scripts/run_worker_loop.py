#!/usr/bin/env python3
"""Standalone send worker — runs every 30 seconds, processes due send jobs."""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.database import Base, engine, SessionLocal
from backend.app.models import entities  # noqa
from backend.app.services.queue_worker import process_due_send_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    Base.metadata.create_all(bind=engine)
    logger.info("Send worker started — polling every 30 seconds")

    while True:
        try:
            with SessionLocal() as db:
                result = process_due_send_jobs(db, limit=50)
            if result.get("sent", 0) > 0 or result.get("failed", 0) > 0:
                logger.info("Worker result: %s", result)
        except Exception:
            logger.exception("Worker error")
        time.sleep(30)


if __name__ == "__main__":
    main()

"""Background sweep that enforces the anonymous-visitor retention window.

Runs inside the FastAPI process (see main.py's lifespan) rather than as a
Temporal workflow: it's plain periodic maintenance with no external calls to
checkpoint or retry, so a simple asyncio loop is enough.
"""

import asyncio
import logging

from config import settings
from db.session import AsyncSessionFactory
from services import session_service

logger = logging.getLogger(__name__)


async def run_forever() -> None:
    while True:
        try:
            async with AsyncSessionFactory() as db:
                deleted = await session_service.purge_expired_visitor_sessions(db)
                if deleted:
                    logger.info(
                        "retention sweep: purged %d expired visitor session(s)",
                        deleted,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retention sweep failed; will retry next interval")

        await asyncio.sleep(settings.share_retention_sweep_interval_seconds)

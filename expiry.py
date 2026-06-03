"""
expiry.py
=========
Background job: silently mark stale gear needs and offers as expired.

Registered in bot.py as a repeating job (every hour).  Any entry whose
status is still the flow's default active status and whose `created`
timestamp is older than EXPIRY_DAYS will be flipped to "expired".

No message is posted — this runs completely silently.
"""

import logging

from telegram.ext import ContextTypes

from topics import FLOWS

EXPIRY_DAYS = 7

logger = logging.getLogger(__name__)


async def expire_old_entries(context: ContextTypes.DEFAULT_TYPE):
    storage = context.bot_data["storage"]
    total = 0
    for cfg in FLOWS.values():
        count = storage.expire_entries(
            cfg["store_key"],
            cfg["status_default"],
            days=EXPIRY_DAYS,
        )
        total += count
    if total:
        logger.info("Auto-expiry: marked %d stale entr%s as expired.", total, "y" if total == 1 else "ies")

"""
bot.py
======
Entry point. Wires up every flow defined in topics.py plus all feature modules.

Run locally:
    export BOT_TOKEN="..."   (or put it in a .env file)
    python bot.py

Deploy (webhook):
    Set WEBHOOK_URL and optionally PORT in the environment.
"""

import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from storage import Storage
from topics import FLOWS
from conversation import build_flow_handler
from lookups import build_list_handler, build_close_handler, build_clear_handler
from quotes import build_quote_handler
from sopranos import build_sopranos_handlers
from social import build_social_handlers
from transport import build_transport_handlers
from pitch import build_pitch_handlers
from expiry import expire_old_entries
from topic_guard import build_settopic_handler, build_removetopic_handler

# Optional: load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# ── Global commands ──────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "Agent"
    await update.message.reply_text(
        f"🔷 *Ay, {name}. Welcome to this thing of ours.*\n\n"
        "You need somethin', you got somethin'? You come to me. "
        "If there's a problem, hit /help and I'll lay it all out for ya. Don't involve anybody else.",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🔷 *Here's how it works around here. Capisce?*\n\n"

        "*Gear:*\n"
        "`/need` `/have` — post a request or offer\n"
        "`/needs` `/offers` `[location]` — see what's on the table\n"
        "`/filled <id>` `/cancel <id>` — close one out\n"
        "`/clearneeds` `/clearoffers` — wipe the slate\n\n"

        "_Quick like:_ `/need L8 XMPs near Caldwell` — done, no back-and-forth\n\n"

        "*Transport:*\n"
        "`/run <need_id> <offer_id>` — volunteer to move gear between agents\n"
        "`/runs` — your active runs\n"
        "`/delivered <run_id>` — mark it done\n\n"

        "*The Family:*\n"
        "`/rank` — check your rank\n"
        "`/promote` — make someone a Soldier (reply to their message)\n"
        "`/family` — see the full roster\n\n"

        "*Rats:*\n"
        "`/rat @username` `/unrat @username` `/rats`\n\n"

        "*Got an idea?:*\n"
        "`/pitch <idea>` — float a new bot feature (or just `/pitch` and I'll ask)\n"
        "`/ideas` — see what's on the table\n"
        "`/unpitch <id>` — pull one off the books\n\n"

        "*A little entertainment:*\n"
        "`/tony` `/paulie` `/christopher` `/silvio` `/junior` `/bobby` `/carmela` `[@username]`\n"
        "`/smurf [agent]` — say something about a blue mook\n\n"

        "*Topic management (Capos only):*\n"
        "`/settopic cmd1 cmd2` — lock commands to this topic\n"
        "`/settopic list` — see current assignments\n"
        "`/settopic clear cmd` — block a command everywhere\n"
        "`/removetopic cmd` — revert to built-in default"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ── Main ──────────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Set the BOT_TOKEN environment variable (or put it in .env).")

    app = Application.builder().token(token).build()
    # DB_PATH lets prod point at a persistent volume (e.g. /data/ingress_bot.db);
    # defaults to a local file for development.
    app.bot_data["storage"] = Storage(os.environ.get("DB_PATH", "ingress_bot.db"))

    # Global commands (no topic restriction)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_cmd))

    # Gear flows: /need, /have, /needs, /offers, /filled, /cancel, /clearneeds, /clearoffers
    for flow_key in FLOWS:
        app.add_handler(build_flow_handler(flow_key))
        app.add_handler(build_list_handler(flow_key))
        app.add_handler(build_close_handler(flow_key))
        app.add_handler(build_clear_handler(flow_key))

    # /smurf [agent] — roast a blue agent
    app.add_handler(build_quote_handler())

    # Sopranos character quote drops: /tony, /paulie, /christopher, /silvio, /junior, /bobby, /carmela
    for handler in build_sopranos_handlers():
        app.add_handler(handler)

    # Social: /rat, /unrat, /rats, /rank, /promote, /family
    for handler in build_social_handlers():
        app.add_handler(handler)

    # Gear transport chain: /run, /runs, /delivered
    for handler in build_transport_handlers():
        app.add_handler(handler)

    # Feature pitch box: /pitch, /ideas, /unpitch (global, no topic restriction)
    for handler in build_pitch_handlers():
        app.add_handler(handler)

    # Topic management: /settopic, /removetopic (always active, Capo/Underboss only for writes)
    app.add_handler(build_settopic_handler())
    app.add_handler(build_removetopic_handler())

    # Background job: silently expire stale entries every hour.
    # Requires python-telegram-bot[job-queue] (APScheduler). Skipped if unavailable.
    if app.job_queue:
        app.job_queue.run_repeating(expire_old_entries, interval=3600, first=60)
    else:
        logger.warning(
            "Job queue unavailable — auto-expiry disabled. "
            "Install python-telegram-bot[job-queue] to enable it."
        )

    # Run via webhook if WEBHOOK_URL is set, otherwise fall back to polling.
    webhook_url = os.environ.get("WEBHOOK_URL")
    if webhook_url:
        port = int(os.environ.get("PORT", 8443))
        logger.info("Bot started. Webhook on port %d...", port)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        logger.info("Bot started. Polling...")
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
